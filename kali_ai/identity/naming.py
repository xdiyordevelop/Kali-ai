"""
Assistant naming engine: derives human-readable names deterministically from hostname.
"""

from __future__ import annotations

import logging
import re
import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kali_ai.storage.repositories import ConfigRepository

logger = logging.getLogger(__name__)

# Known domain suffixes to strip
DOMAIN_SUFFIXES = (
    ".local",
    ".lan",
    ".localdomain",
    ".home",
    ".internal",
    ".corp",
    ".domain",
)

# Friendly nicknames for common generic hostnames
KNOWN_NICKNAMES: dict[str, str] = {
    "sandbox": "Sandy",
    "kali": "Kallie",
    "kalibox": "Kallie",
    "kali-linux": "Kallie",
    "localhost": "Nova",
    "desktop": "Aura",
    "workstation": "Dexter",
    "laptop": "Lappi",
    "server": "Atlas",
    "raspberrypi": "Berry",
}


class NamingEngine:
    """
    Deterministic naming engine that generates a default assistant name from
    the machine hostname while strictly protecting user customizations.
    """

    @staticmethod
    def detect_hostname() -> str:
        """Detect the local machine hostname via socket."""
        try:
            return socket.gethostname()
        except Exception as exc:
            logger.warning("Could not resolve socket hostname: %s. Falling back to 'kali'", exc)
            return "kali"

    @staticmethod
    def sanitize_hostname(raw_hostname: str) -> str:
        """
        Sanitize hostname by stripping domain suffixes and punctuation.
        Returns a clean, lowercase token string.
        """
        if not raw_hostname:
            return "kali"

        cleaned = raw_hostname.strip().lower()

        # Strip standard local domain extensions
        for suffix in DOMAIN_SUFFIXES:
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)]

        # Replace non-alphanumeric characters with spaces
        cleaned = re.sub(r"[^a-z0-9]", " ", cleaned).strip()
        # Compress multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned or "kali"

    @classmethod
    def generate_default_name(cls, hostname: str) -> str:
        """
        Derive a friendly, deterministic default name from a hostname.
        Never calls external services or AI models.
        """
        sanitized = cls.sanitize_hostname(hostname)

        # Check exact match in dictionary first
        joined_key = sanitized.replace(" ", "")
        if joined_key in KNOWN_NICKNAMES:
            return KNOWN_NICKNAMES[joined_key]

        words = sanitized.split()
        if not words:
            return "Nova"

        first_word = words[0]

        # Check first word in dictionary
        if first_word in KNOWN_NICKNAMES:
            return KNOWN_NICKNAMES[first_word]

        # Clean alphabetic prefix
        alpha_chars = "".join(ch for ch in first_word if ch.isalpha())
        if not alpha_chars:
            return "Nova"

        # Apply natural phonetic nickname transformation
        if len(alpha_chars) <= 3:
            return alpha_chars.capitalize()

        # If word ends with 'box', strip it: e.g. 'sand' from 'sandbox'
        if alpha_chars.endswith("box") and len(alpha_chars) > 4:
            stem = alpha_chars[:-3]
            return stem.capitalize() + "y"

        # If length 4..7, capitalize directly
        if len(alpha_chars) <= 6:
            return alpha_chars.capitalize()

        # If longer word, take the first 4-5 letters and append 'y' or 'ie' if fitting
        stem = alpha_chars[:5]
        if stem.endswith(("s", "x", "z", "ch", "sh")):
            return stem.capitalize() + "ie"
        elif not stem.endswith(("a", "e", "i", "o", "u", "y")):
            return stem.capitalize() + "y"
        return stem.capitalize()

    @classmethod
    def resolve_assistant_name(
        cls, config_repo: ConfigRepository, current_hostname: str | None = None
    ) -> tuple[str, bool]:
        """
        Retrieve or initialize the assistant name.
        Returns tuple of (assistant_name, is_newly_created).

        Rule: If user previously customized the assistant name, it is NEVER overwritten,
        even if the hostname changes.
        """
        if current_hostname is None:
            current_hostname = cls.detect_hostname()

        existing_name = config_repo.get("assistant.name")
        is_customized = bool(config_repo.get("assistant.customized", False))
        stored_hostname = config_repo.get("system.detected_hostname")

        # 1. Existing customized name -> Keep forever
        if existing_name and is_customized:
            logger.debug("Preserving user-customized assistant name: '%s'", existing_name)
            return existing_name, False

        # 2. Existing default name, but hostname has NOT changed -> Keep
        if existing_name and stored_hostname == current_hostname:
            return existing_name, False

        # 3. First-time startup or hostname changed on non-customized setup -> Generate
        new_default = cls.generate_default_name(current_hostname)
        config_repo.set("assistant.name", new_default)
        config_repo.set("assistant.customized", False)
        config_repo.set("system.detected_hostname", current_hostname)

        logger.info(
            "Derived default assistant name '%s' from hostname '%s'",
            new_default,
            current_hostname,
        )
        return new_default, True

    @classmethod
    def set_custom_name(cls, config_repo: ConfigRepository, custom_name: str) -> str:
        """
        Validate and persist a user-selected assistant name.
        Marks assistant.customized = True.
        """
        cleaned = custom_name.strip()
        if not cleaned:
            raise ValueError("Assistant name cannot be empty")
        if len(cleaned) < 2 or len(cleaned) > 32:
            raise ValueError(f"Assistant name length must be between 2 and 32 characters (got {len(cleaned)})")
        if not re.match(r"^[a-zA-Z0-9\s_-]+$", cleaned):
            raise ValueError("Assistant name can only contain letters, numbers, spaces, underscores, and hyphens")

        config_repo.set("assistant.name", cleaned)
        config_repo.set("assistant.customized", True)
        logger.info("Assistant name updated by user to: '%s'", cleaned)
        return cleaned
