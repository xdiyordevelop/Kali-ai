"""
Text-To-Speech (TTS) abstraction and providers for Kali AI.
"""

from __future__ import annotations

import abc
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


class TextToSpeech(abc.ABC):
    """
    Abstract interface for Text-To-Speech providers.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the TTS provider."""
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if TTS provider is operational."""
        pass

    @abc.abstractmethod
    def speak(self, text: str) -> bool:
        """
        Synthesize and speak text. Returns True on success, False on error.
        """
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Interrupt active audio playback."""
        pass


class MockTTS(TextToSpeech):
    """
    Mock TTS provider recording spoken messages for testing.
    """

    def __init__(self) -> None:
        self.spoken_messages: list[str] = []
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def speak(self, text: str) -> bool:
        self.call_count += 1
        self.spoken_messages.append(text)
        logger.debug("[MockTTS] Spoke: '%s'", text)
        return True

    def stop(self) -> None:
        pass


class SystemTTS(TextToSpeech):
    """
    Lightweight fallback TTS using system speech utilities (espeak-ng, spd-say) if present.
    """

    def __init__(self) -> None:
        self._tool: str | None = None
        for cmd in ("espeak-ng", "espeak", "spd-say"):
            if shutil.which(cmd):
                self._tool = cmd
                break

    @property
    def provider_name(self) -> str:
        return f"system_{self._tool or 'none'}"

    def is_available(self) -> bool:
        return self._tool is not None

    def speak(self, text: str) -> bool:
        if not self.is_available() or not self._tool:
            logger.info("[SystemTTS-Simulated]: %s", text)
            return True

        try:
            subprocess.run([self._tool, text], check=True, timeout=5.0)
            return True
        except Exception as exc:
            logger.warning("System TTS failed: %s", exc)
            return False

    def stop(self) -> None:
        pass
