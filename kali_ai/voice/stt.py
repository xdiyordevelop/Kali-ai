"""
Speech-To-Text (STT) abstraction and providers for Kali AI.
"""

from __future__ import annotations

import abc
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SpeechToText(abc.ABC):
    """
    Abstract interface for Speech-to-Text providers.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the STT provider."""
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if STT provider is available and configured."""
        pass

    @abc.abstractmethod
    def transcribe(self, audio_pcm: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe raw 16-bit mono PCM audio to text.
        Raises RuntimeError or returns empty string on failure.
        """
        pass


class MockSTT(SpeechToText):
    """
    Mock STT provider for unit testing and privacy verification.
    Records transcriptions and call counts to verify privacy boundaries.
    """

    def __init__(self, default_text: str = "open the browser") -> None:
        self.default_text = default_text
        self.call_count = 0
        self.transcribed_bytes: list[int] = []
        self._queue: list[str] = []
        self._should_fail = False

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def set_next_result(self, text: str) -> None:
        """Enqueue a specific transcription result."""
        self._queue.append(text)

    def set_should_fail(self, fail: bool) -> None:
        """Force transcribe() to simulate failure."""
        self._should_fail = fail

    def transcribe(self, audio_pcm: bytes, sample_rate: int = 16000) -> str:
        self.call_count += 1
        self.transcribed_bytes.append(len(audio_pcm))

        if self._should_fail:
            raise RuntimeError("Simulated STT transcription error")

        if self._queue:
            return self._queue.pop(0)

        return self.default_text
