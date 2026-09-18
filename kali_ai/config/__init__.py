"""
Configuration package for Kali AI: typed schemas, defaults, and configuration manager.
"""

from kali_ai.config.schema import (
    AppConfig,
    SystemConfig,
    ModelSlotConfig,
    VoiceConfig,
    AutomationConfig,
    CapabilityRole,
)
from kali_ai.config.manager import ConfigManager

__all__ = [
    "AppConfig",
    "SystemConfig",
    "ModelSlotConfig",
    "VoiceConfig",
    "AutomationConfig",
    "CapabilityRole",
    "ConfigManager",
]
