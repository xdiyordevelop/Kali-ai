"""
Security policy models and permission tiers for Kali AI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from kali_ai.core.exceptions import SecurityPolicyError


class PermissionTier(str, Enum):
    """
    Tiered permission classification for Kali AI actions.
    """
    # Safe observation: screenshots, reading files, searching internet, listing directories
    TIER_0_READ_ONLY = "TIER_0_READ_ONLY"

    # Standard interaction: opening standard desktop apps, mouse clicks, typing in focused windows
    TIER_1_STANDARD = "TIER_1_STANDARD"

    # Moderate sensitivity: modifying user files, running non-destructive scripts
    TIER_2_SENSITIVE = "TIER_2_SENSITIVE"

    # High risk / Destructive: sudo commands, file deletions, installing packages, network changes
    TIER_3_HIGH_RISK = "TIER_3_HIGH_RISK"

    def __str__(self) -> str:
        return self.value


# Standard default allowed commands (read-only and routine dev inspection)
DEFAULT_ALLOWED_COMMANDS = [
    "cat",
    "date",
    "df",
    "echo",
    "find",
    "free",
    "git status",
    "git log",
    "git diff",
    "grep",
    "head",
    "hostname",
    "ls",
    "ps",
    "pwd",
    "tail",
    "uname",
    "uptime",
    "wc",
    "which",
    "whoami",
]

# Strict blacklist of blocked high-risk destructive shell commands
DEFAULT_DENIED_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "chmod -R 777 /",
    "> /dev/sda",
    "> /dev/nvme",
]


@dataclass
class SecurityPolicyConfig:
    """
    Configuration model for security policy boundaries.
    """
    default_tier: PermissionTier = PermissionTier.TIER_1_STANDARD
    require_confirmation_for_tier2: bool = False
    require_confirmation_for_tier3: bool = True
    allow_sudo: bool = False
    allowed_commands: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_COMMANDS))
    denied_commands: list[str] = field(default_factory=lambda: list(DEFAULT_DENIED_COMMANDS))
    emergency_stop_enabled: bool = True
    emergency_stop_keycombo: str = "Ctrl+Alt+Escape"

    def validate(self) -> None:
        """Validate security policy integrity."""
        if not isinstance(self.default_tier, PermissionTier):
            if isinstance(self.default_tier, str):
                try:
                    self.default_tier = PermissionTier(self.default_tier)
                except ValueError as e:
                    raise SecurityPolicyError(f"Invalid default permission tier: {self.default_tier}") from e
            else:
                raise SecurityPolicyError("default_tier must be an instance of PermissionTier")

        if not self.emergency_stop_enabled:
            raise SecurityPolicyError("Emergency stop must remain enabled for system safety.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to dictionary."""
        data = asdict(self)
        data["default_tier"] = self.default_tier.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityPolicyConfig:
        """Construct SecurityPolicyConfig from dictionary."""
        tier_str = data.get("default_tier", PermissionTier.TIER_1_STANDARD.value)
        tier = PermissionTier(tier_str) if isinstance(tier_str, str) else tier_str

        return cls(
            default_tier=tier,
            require_confirmation_for_tier2=bool(data.get("require_confirmation_for_tier2", False)),
            require_confirmation_for_tier3=bool(data.get("require_confirmation_for_tier3", True)),
            allow_sudo=bool(data.get("allow_sudo", False)),
            allowed_commands=list(data.get("allowed_commands", DEFAULT_ALLOWED_COMMANDS)),
            denied_commands=list(data.get("denied_commands", DEFAULT_DENIED_COMMANDS)),
            emergency_stop_enabled=bool(data.get("emergency_stop_enabled", True)),
            emergency_stop_keycombo=str(data.get("emergency_stop_keycombo", "Ctrl+Alt+Escape")),
        )
