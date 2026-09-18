"""
Wake-word detection abstraction and lightweight local detector for Kali AI.
"""

from __future__ import annotations

import abc
import logging
import time
from typing import Tuple

from kali_ai.voice.vad import EnergyVAD

logger = logging.getLogger(__name__)


class WakeWordDetector(abc.ABC):
    """
    Abstract interface for wake-word spotters.
    """

    def __init__(self, wake_word: str = "Sandy", confidence_threshold: float = 0.75) -> None:
        self.wake_word = wake_word.strip()
        self.confidence_threshold = confidence_threshold
        self._is_active = False

    @abc.abstractmethod
    def start(self) -> None:
        """Initialize and start detector."""
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop detector."""
        pass

    @abc.abstractmethod
    def feed_audio(self, frame: bytes) -> bool:
        """
        Feed a raw 16-bit PCM frame (typically 20ms).
        Returns True immediately if wake word was detected on this frame.
        """
        pass

    @abc.abstractmethod
    def detect(self) -> Tuple[bool, float]:
        """
        Check current detection status.
        Returns (is_detected, confidence_score).
        """
        pass

    @abc.abstractmethod
    def reset(self) -> None:
        """Reset internal accumulator state."""
        pass


class MockWakeWordDetector(WakeWordDetector):
    """
    Mock wake-word detector for deterministic unit tests.
    """

    def __init__(self, wake_word: str = "Sandy", confidence_threshold: float = 0.75) -> None:
        super().__init__(wake_word, confidence_threshold)
        self._triggered = False
        self._confidence = 0.0

    def start(self) -> None:
        self._is_active = True

    def stop(self) -> None:
        self._is_active = False

    def trigger(self, confidence: float = 0.95) -> None:
        """Programmatically trigger positive wake-word detection."""
        self._triggered = True
        self._confidence = confidence

    def feed_audio(self, frame: bytes) -> bool:
        # If triggered flag was manually set, return detection
        return self._triggered

    def detect(self) -> Tuple[bool, float]:
        if self._triggered:
            return True, self._confidence
        return False, 0.0

    def reset(self) -> None:
        self._triggered = False
        self._confidence = 0.0


class EnergyPatternWakeWordDetector(WakeWordDetector):
    """
    Lightweight, completely offline acoustic envelope wake-word detector.
    Analyzes temporal syllabic speech bursts and cadence corresponding
    to the configured wake word without requiring heavy neural networks.
    """

    def __init__(
        self,
        wake_word: str = "Sandy",
        confidence_threshold: float = 0.70,
        vad: EnergyVAD | None = None,
    ) -> None:
        super().__init__(wake_word, confidence_threshold)
        self.vad = vad or EnergyVAD()
        self._syllable_estimate = max(1, len(self.wake_word.split()) + max(1, len(self.wake_word) // 3))
        self._burst_count = 0
        self._burst_frames = 0
        self._silence_frames = 0
        self._last_detected = False
        self._last_confidence = 0.0
        self._in_speech = False

    def start(self) -> None:
        self._is_active = True
        self.reset()
        logger.debug(
            "EnergyPatternWakeWordDetector started for wake-word '%s' (est. syllables: %d)",
            self.wake_word,
            self._syllable_estimate,
        )

    def stop(self) -> None:
        self._is_active = False
        self.reset()

    def reset(self) -> None:
        self._burst_count = 0
        self._burst_frames = 0
        self._silence_frames = 0
        self._last_detected = False
        self._last_confidence = 0.0
        self._in_speech = False

    def feed_audio(self, frame: bytes) -> bool:
        if not self._is_active:
            return False

        is_voice = self.vad.is_speech(frame)

        if is_voice:
            self._burst_frames += 1
            self._silence_frames = 0
            if not self._in_speech and self._burst_frames >= 2:
                self._in_speech = True
                self._burst_count += 1
        else:
            self._silence_frames += 1
            if self._in_speech and self._silence_frames >= 4:
                # End of a speech syllable burst
                self._in_speech = False

        # If silence persists after some bursts, evaluate pattern
        if self._silence_frames >= 12 and self._burst_count > 0:
            total_duration_ms = (self._burst_frames + self._silence_frames) * self.vad.config.frame_duration_ms
            
            # Typical spoken wake word duration: 250ms to 1300ms
            if 250.0 <= total_duration_ms <= 1400.0:
                syllable_diff = abs(self._burst_count - self._syllable_estimate)
                if syllable_diff == 0:
                    confidence = 0.88
                elif syllable_diff == 1:
                    confidence = 0.76
                else:
                    confidence = 0.40

                if confidence >= self.confidence_threshold:
                    self._last_detected = True
                    self._last_confidence = confidence
                    logger.info(
                        "Wake word '%s' detected (confidence: %.2f, duration: %.0fms)",
                        self.wake_word,
                        confidence,
                        total_duration_ms,
                    )
                    self.reset()
                    return True

            # Reset pattern tracking on silence timeout
            self.reset()

        return False

    def detect(self) -> Tuple[bool, float]:
        return self._last_detected, self._last_confidence
