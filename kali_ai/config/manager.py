"""
Configuration manager: loads, validates, updates, and persists application settings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kali_ai.config.schema import (
    AppConfig,
    CapabilityRole,
    ModelSlotConfig,
    SystemConfig,
    VoiceConfig,
    AutomationConfig,
)
from kali_ai.core.events import Event, EventType
from kali_ai.core.exceptions import ConfigurationError
from kali_ai.security.policy import SecurityPolicyConfig
from kali_ai.storage.repositories import ConfigRepository, SecurityPolicyRepository

if TYPE_CHECKING:
    from kali_ai.core.event_bus import EventBus

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Manages typed application configuration backed by SQLite repositories.
    Ensures safe persistence, validation, and change notification via EventBus.
    """

    def __init__(
        self,
        config_repo: ConfigRepository,
        policy_repo: SecurityPolicyRepository,
        event_bus: EventBus | None = None,
    ) -> None:
        self.config_repo = config_repo
        self.policy_repo = policy_repo
        self.event_bus = event_bus
        self._cached_config: AppConfig | None = None

    @property
    def config(self) -> AppConfig:
        """Return the current cached AppConfig (loads from DB if not yet loaded)."""
        if self._cached_config is None:
            self._cached_config = self.load()
        return self._cached_config

    def load(self) -> AppConfig:
        """
        Load configuration from SQLite, applying defaults for any missing items.
        Validates configuration before caching.
        """
        logger.debug("Loading application configuration from database")
        system_data = self._load_system_section()
        security_data = self._load_security_section()
        models_data = self._load_models_section()
        voice_data = self._load_voice_section()
        auto_data = self._load_automation_section()

        merged_data = {
            "system": system_data,
            "security": security_data,
            "models": models_data,
            "voice": voice_data,
            "automation": auto_data,
        }

        app_config = AppConfig.from_dict(merged_data)
        try:
            app_config.validate()
        except Exception as exc:
            raise ConfigurationError(f"Loaded configuration failed validation: {exc}") from exc

        self._cached_config = app_config
        return app_config

    def save(self) -> None:
        """Persist the current cached configuration to SQLite."""
        if self._cached_config is None:
            return

        self._cached_config.validate()
        now_iso = datetime.now(timezone.utc).isoformat()
        self._cached_config.system.updated_at = now_iso

        # 1. Save system settings
        self.config_repo.set("assistant.name", self._cached_config.system.assistant_name)
        self.config_repo.set("system.detected_hostname", self._cached_config.system.detected_hostname)
        self.config_repo.set("assistant.customized", self._cached_config.system.customized)
        self.config_repo.set("system.language", self._cached_config.system.language)
        self.config_repo.set("system.timezone", self._cached_config.system.timezone)
        self.config_repo.set("system.log_level", self._cached_config.system.log_level)
        self.config_repo.set("system.created_at", self._cached_config.system.created_at)
        self.config_repo.set("system.updated_at", self._cached_config.system.updated_at)

        # 2. Save models configuration
        for role, slot in self._cached_config.models.items():
            self.config_repo.set(f"models.{role}", slot.to_dict())

        # 3. Save voice configuration
        self.config_repo.set("voice", self._cached_config.voice.to_dict())

        # 4. Save automation configuration
        self.config_repo.set("automation", self._cached_config.automation.to_dict())

        # 5. Save security policy
        self.policy_repo.set_policy("security_policy", self._cached_config.security.to_dict())

        logger.debug("Configuration persisted successfully")

    def set_assistant_name(self, name: str, customized: bool = True) -> None:
        """Update assistant name, save, and emit events."""
        clean_name = name.strip()
        if len(clean_name) < 2:
            raise ConfigurationError("Assistant name must be at least 2 characters")

        old_name = self.config.system.assistant_name
        self.config.system.assistant_name = clean_name
        self.config.system.customized = customized
        self.save()

        if self.event_bus:
            self.event_bus.publish_nowait(
                Event(
                    event_type=EventType.ASSISTANT_NAME_CHANGED.value,
                    payload={"old_name": old_name, "new_name": clean_name, "customized": customized},
                    source="config_manager",
                )
            )

    def update_system(self, **kwargs: Any) -> None:
        """Update specific system configuration keys."""
        for k, v in kwargs.items():
            if hasattr(self.config.system, k):
                setattr(self.config.system, k, v)
            else:
                raise ConfigurationError(f"Unknown system config key: {k}")
        self.save()
        self._notify_config_changed("system")

    def update_security(self, **kwargs: Any) -> None:
        """Update security policy settings."""
        for k, v in kwargs.items():
            if hasattr(self.config.security, k):
                setattr(self.config.security, k, v)
            else:
                raise ConfigurationError(f"Unknown security config key: {k}")
        self.save()
        self._notify_config_changed("security")

    def reset_to_defaults(self, keep_hostname: bool = True) -> AppConfig:
        """Reset configuration to factory defaults while optionally preserving hostname."""
        current_hostname = self.config.system.detected_hostname if keep_hostname else "sandbox"
        default_config = AppConfig()
        default_config.system.detected_hostname = current_hostname

        self._cached_config = default_config
        self.save()
        self._notify_config_changed("all")
        logger.info("Configuration reset to defaults")
        return self._cached_config

    def _notify_config_changed(self, section: str) -> None:
        """Emit CONFIG_CHANGED event through the EventBus if connected."""
        if self.event_bus:
            self.event_bus.publish_nowait(
                Event(
                    event_type=EventType.CONFIG_CHANGED.value,
                    payload={"section": section, "timestamp": datetime.now(timezone.utc).isoformat()},
                    source="config_manager",
                )
            )

    def _load_system_section(self) -> dict[str, Any]:
        return {
            "assistant_name": self.config_repo.get("assistant.name", "Sandy"),
            "detected_hostname": self.config_repo.get("system.detected_hostname", "sandbox"),
            "customized": self.config_repo.get("assistant.customized", False),
            "language": self.config_repo.get("system.language", "en"),
            "timezone": self.config_repo.get("system.timezone", "UTC"),
            "log_level": self.config_repo.get("system.log_level", "INFO"),
            "created_at": self.config_repo.get("system.created_at"),
            "updated_at": self.config_repo.get("system.updated_at"),
        }

    def _load_security_section(self) -> dict[str, Any]:
        policy_data = self.policy_repo.get_policy("security_policy")
        if isinstance(policy_data, dict):
            return policy_data
        return SecurityPolicyConfig().to_dict()

    def _load_models_section(self) -> dict[str, Any]:
        models_data: dict[str, Any] = {}
        for role in CapabilityRole:
            raw = self.config_repo.get(f"models.{role.value}")
            if isinstance(raw, dict):
                models_data[role.value] = raw
            else:
                models_data[role.value] = ModelSlotConfig().to_dict()
        return models_data

    def _load_voice_section(self) -> dict[str, Any]:
        voice_data = self.config_repo.get("voice")
        if isinstance(voice_data, dict):
            return voice_data
        return VoiceConfig().to_dict()

    def _load_automation_section(self) -> dict[str, Any]:
        auto_data = self.config_repo.get("automation")
        if isinstance(auto_data, dict):
            return auto_data
        return AutomationConfig().to_dict()
