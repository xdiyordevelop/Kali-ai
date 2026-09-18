"""
Typed configuration schemas and capability placeholders for Kali AI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from kali_ai.core.exceptions import ConfigurationError
from kali_ai.security.policy import SecurityPolicyConfig


class CapabilityRole(str, Enum):
    """Abstract AI model capability roles."""
    REASONING = "REASONING"
    VISION = "VISION"
    CODING = "CODING"
    FAST = "FAST"
    STT = "STT"
    TTS = "TTS"

    def __str__(self) -> str:
        return self.value


@dataclass
class ModelSlotConfig:
    """Configuration slot for an AI capability role."""
    provider: str = "placeholder"
    model_name: str = "placeholder"
    api_key_env: str = ""
    fallback_provider: str = ""
    fallback_model: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelSlotConfig:
        return cls(
            provider=str(data.get("provider", "placeholder")),
            model_name=str(data.get("model_name", "placeholder")),
            api_key_env=str(data.get("api_key_env", "")),
            fallback_provider=str(data.get("fallback_provider", "")),
            fallback_model=str(data.get("fallback_model", "")),
            temperature=float(data.get("temperature", 0.2)),
            max_tokens=int(data.get("max_tokens", 4096)),
        )


@dataclass
class VoiceConfig:
    """Voice subsystem configuration."""
    enabled: bool = False
    wake_word: str = ""  # If empty, defaults to assistant_name
    auto_listen: bool = False
    vad_enabled: bool = True
    vad_sensitivity: int = 3
    silence_timeout: float = 1.2
    stt_provider: str = "mock"
    tts_provider: str = "mock"
    sample_rate: int = 16000
    feedback_audio_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceConfig:
        return cls(
            enabled=bool(data.get("enabled", False)),
            wake_word=str(data.get("wake_word", "")),
            auto_listen=bool(data.get("auto_listen", False)),
            vad_enabled=bool(data.get("vad_enabled", True)),
            vad_sensitivity=int(data.get("vad_sensitivity", 3)),
            silence_timeout=float(data.get("silence_timeout", 1.2)),
            stt_provider=str(data.get("stt_provider", "mock")),
            tts_provider=str(data.get("tts_provider", "mock")),
            sample_rate=int(data.get("sample_rate", 16000)),
            feedback_audio_enabled=bool(data.get("feedback_audio_enabled", True)),
        )


@dataclass
class AutomationConfig:
    """Automation and background scheduling placeholders."""
    enabled: bool = False
    scheduler_poll_seconds: int = 60
    max_concurrent_background_tasks: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationConfig:
        return cls(
            enabled=bool(data.get("enabled", False)),
            scheduler_poll_seconds=int(data.get("scheduler_poll_seconds", 60)),
            max_concurrent_background_tasks=int(data.get("max_concurrent_background_tasks", 2)),
        )


@dataclass
class SystemConfig:
    """Core system settings."""
    assistant_name: str = "Sandy"
    detected_hostname: str = "sandbox"
    customized: bool = False
    language: str = "en"
    timezone: str = "UTC"
    log_level: str = "INFO"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self) -> None:
        if not self.assistant_name or len(self.assistant_name.strip()) < 2:
            raise ConfigurationError(f"Invalid assistant name: '{self.assistant_name}' (minimum 2 characters)")
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ConfigurationError(f"Invalid log level: '{self.log_level}'")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemConfig:
        now_iso = datetime.now(timezone.utc).isoformat()
        return cls(
            assistant_name=str(data.get("assistant_name", "Sandy")),
            detected_hostname=str(data.get("detected_hostname", "sandbox")),
            customized=bool(data.get("customized", False)),
            language=str(data.get("language", "en")),
            timezone=str(data.get("timezone", "UTC")),
            log_level=str(data.get("log_level", "INFO")),
            created_at=str(data.get("created_at", now_iso)),
            updated_at=str(data.get("updated_at", now_iso)),
        )


@dataclass
class AppConfig:
    """Root application configuration aggregating all modular settings."""
    system: SystemConfig = field(default_factory=SystemConfig)
    security: SecurityPolicyConfig = field(default_factory=SecurityPolicyConfig)
    models: dict[str, ModelSlotConfig] = field(
        default_factory=lambda: {
            CapabilityRole.REASONING.value: ModelSlotConfig(),
            CapabilityRole.VISION.value: ModelSlotConfig(),
            CapabilityRole.CODING.value: ModelSlotConfig(),
            CapabilityRole.FAST.value: ModelSlotConfig(),
            CapabilityRole.STT.value: ModelSlotConfig(),
            CapabilityRole.TTS.value: ModelSlotConfig(),
        }
    )
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)

    def validate(self) -> None:
        """Validate all sub-configurations."""
        self.system.validate()
        self.security.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system.to_dict(),
            "security": self.security.to_dict(),
            "models": {k: v.to_dict() for k, v in self.models.items()},
            "voice": self.voice.to_dict(),
            "automation": self.automation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        system = SystemConfig.from_dict(data.get("system", {}))
        security = SecurityPolicyConfig.from_dict(data.get("security", {}))
        voice = VoiceConfig.from_dict(data.get("voice", {}))
        automation = AutomationConfig.from_dict(data.get("automation", {}))

        models: dict[str, ModelSlotConfig] = {}
        raw_models = data.get("models", {})
        for role in CapabilityRole:
            raw_slot = raw_models.get(role.value, {})
            models[role.value] = ModelSlotConfig.from_dict(raw_slot)

        return cls(
            system=system,
            security=security,
            models=models,
            voice=voice,
            automation=automation,
        )
