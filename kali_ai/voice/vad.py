"""
Lightweight energy-based Voice Activity Detection (VAD) for Kali AI.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


@dataclass
class VADConfig:
    """Configuration parameters for energy-based VAD."""
    enabled: bool = True
    sensitivity: int = 3  # 1 (least sensitive) to 5 (most sensitive)
    speech_start_threshold: float = 400.0
    silence_timeout_seconds: float = 1.2
    frame_duration_ms: float = 20.0  # standard 20ms frames


class EnergyVAD:
    """
    Lightweight, fast RMS energy Voice Activity Detector.
    Calculates signal power over 16-bit PCM frames to accurately distinguish
    human speech from background silence.
    """

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config or VADConfig()
        self._noise_floor: float = 100.0

    @property
    def effective_threshold(self) -> float:
        """
        Calculate effective speech energy threshold based on sensitivity (1..5).
        Sensitivity 1: requires louder speech (multiplier 1.6).
        Sensitivity 5: detects quieter speech (multiplier 0.5).
        """
        multiplier_map = {
            1: 1.6,
            2: 1.3,
            3: 1.0,
            4: 0.7,
            5: 0.5,
        }
        mult = multiplier_map.get(self.config.sensitivity, 1.0)
        return max(50.0, self.config.speech_start_threshold * mult)

    def calculate_rms(self, frame: bytes) -> float:
        """
        Compute Root Mean Square (RMS) amplitude of 16-bit mono PCM bytes.
        """
        if not frame or len(frame) < 2:
            return 0.0

        # Number of 16-bit samples
        num_samples = len(frame) // 2
        try:
            samples = struct.unpack(f"<{num_samples}h", frame[: num_samples * 2])
        except struct.error:
            return 0.0

        if not samples:
            return 0.0

        # Sum of squares
        sum_sq = sum(float(s) * float(s) for s in samples)
        return math.sqrt(sum_sq / num_samples)

    def is_speech(self, frame: bytes) -> bool:
        """
        Determine whether an audio frame contains active human speech.
        If VAD is disabled, treats all non-empty audio as speech.
        """
        if not self.config.enabled:
            return len(frame) > 0

        rms = self.calculate_rms(frame)

        # Adaptively track gentle background noise floor
        if rms < self._noise_floor:
            self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms
        elif rms < self.effective_threshold:
            self._noise_floor = 0.99 * self._noise_floor + 0.01 * rms

        return rms >= self.effective_threshold
