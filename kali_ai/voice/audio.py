"""
Audio capture abstraction and PipeWire driver for Kali AI.
"""

from __future__ import annotations

import abc
import logging
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

from kali_ai.core.exceptions import KaliAIError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDeviceInfo:
    """Information about an audio recording device."""
    id: str
    name: str
    description: str
    is_default: bool = True
    channels: int = 1
    sample_rate: int = 16000


class AudioInputInterface(abc.ABC):
    """Abstract interface for audio capture devices."""

    @abc.abstractmethod
    def start(self) -> None:
        """Start capturing audio stream."""
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop capturing audio stream."""
        pass

    @abc.abstractmethod
    def read_frame(self, num_bytes: int = 640) -> bytes:
        """
        Read a chunk of raw 16-bit mono PCM bytes.
        Returns empty bytes if stream has stopped or no data is available.
        """
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Release audio resources."""
        pass

    @abc.abstractmethod
    def get_device_info(self) -> AudioDeviceInfo:
        """Retrieve active microphone metadata."""
        pass

    @property
    @abc.abstractmethod
    def is_active(self) -> bool:
        """Check if audio input stream is currently capturing."""
        pass


class PipeWireAudioInput(AudioInputInterface):
    """
    PipeWire audio capture driver using native pw-record.
    Streams 16kHz 16-bit mono PCM without requiring external C libraries.
    """

    def __init__(self, target_device: str | None = None, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.target_device = target_device
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.RLock()
        self._is_active = False
        self._device_info: AudioDeviceInfo | None = None

    @classmethod
    def detect_default_device(cls) -> AudioDeviceInfo:
        """
        Dynamically inspect PipeWire via wpctl to discover default audio recording source.
        Never relies on hardcoded device IDs.
        """
        if not shutil.which("wpctl"):
            return AudioDeviceInfo(
                id="@DEFAULT_AUDIO_SOURCE@",
                name="default",
                description="Default System Microphone (Unchecked)",
            )

        try:
            out = subprocess.check_output(
                ["wpctl", "inspect", "@DEFAULT_AUDIO_SOURCE@"],
                stderr=subprocess.DEVNULL,
                timeout=3.0,
            ).decode("utf-8", errors="replace")

            # Parse device ID from output: "id 57, type PipeWire:Interface:Node"
            node_id_match = re.search(r"id\s+(\d+)", out)
            node_id = node_id_match.group(1) if node_id_match else "@DEFAULT_AUDIO_SOURCE@"

            # Parse description: node.description = "Built-in Audio Analog Stereo"
            desc_match = re.search(r'node\.description\s*=\s*"([^"]+)"', out)
            desc = desc_match.group(1) if desc_match else "Built-in Microphone"

            # Parse name: node.name = "alsa_input.pci-..."
            name_match = re.search(r'node\.name\s*=\s*"([^"]+)"', out)
            name = name_match.group(1) if name_match else "alsa_input"

            return AudioDeviceInfo(
                id=node_id,
                name=name,
                description=desc,
                is_default=True,
            )
        except Exception as exc:
            logger.warning("Could not inspect @DEFAULT_AUDIO_SOURCE@ via wpctl: %s. Using default target.", exc)
            return AudioDeviceInfo(
                id="@DEFAULT_AUDIO_SOURCE@",
                name="default",
                description="Default PipeWire Microphone",
                is_default=True,
            )

    def get_device_info(self) -> AudioDeviceInfo:
        with self._lock:
            if self._device_info is None:
                if self.target_device:
                    self._device_info = AudioDeviceInfo(
                        id=self.target_device,
                        name=f"target_{self.target_device}",
                        description=f"PipeWire Source {self.target_device}",
                    )
                else:
                    self._device_info = self.detect_default_device()
            return self._device_info

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._is_active and self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        with self._lock:
            if self.is_active:
                return

            if not shutil.which("pw-record"):
                raise KaliAIError(
                    "PipeWire recording tool 'pw-record' was not found on PATH. "
                    "Ensure pipewire is installed and running."
                )

            dev = self.get_device_info()
            target = dev.id

            cmd = [
                "pw-record",
                "--target",
                target,
                "--format",
                "s16",
                "--rate",
                str(self.sample_rate),
                "--channels",
                "1",
                "-",  # output PCM stream to stdout
            ]

            logger.info("Starting PipeWire audio capture: %s (target: %s)", " ".join(cmd), target)
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,  # Unbuffered binary streaming
                )
                self._is_active = True
            except Exception as exc:
                self._is_active = False
                self._proc = None
                raise KaliAIError(f"Failed to launch pw-record: {exc}") from exc

    def read_frame(self, num_bytes: int = 640) -> bytes:
        """
        Read up to num_bytes of 16-bit mono PCM.
        At 16kHz s16 mono: 640 bytes = 320 samples = 20ms of audio.
        """
        with self._lock:
            if not self.is_active or self._proc is None or self._proc.stdout is None:
                return b""

            try:
                data = self._proc.stdout.read(num_bytes)
                if not data:
                    # EOF or stream stopped
                    self._is_active = False
                    return b""
                return data
            except Exception as exc:
                logger.error("Error reading audio frame from pw-record: %s", exc)
                self._is_active = False
                return b""

    def stop(self) -> None:
        with self._lock:
            if not self._is_active and self._proc is None:
                return

            self._is_active = False
            if self._proc:
                try:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                        self._proc.wait(timeout=0.5)
                except Exception as exc:
                    logger.debug("Error stopping pw-record process: %s", exc)
                finally:
                    self._proc = None
            logger.info("PipeWire audio capture stopped.")

    def close(self) -> None:
        self.stop()


class MockAudioInput(AudioInputInterface):
    """
    Mock audio capture device for deterministic unit testing.
    Generates synthetic silence or custom test audio frames.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self._is_active = False
        self._queue: list[bytes] = []
        self._lock = threading.RLock()
        self.device_info = AudioDeviceInfo(
            id="mock_device",
            name="mock_mic",
            description="Virtual Test Microphone",
        )

    def enqueue_frames(self, frames: list[bytes]) -> None:
        """Add predefined audio frames to the stream."""
        with self._lock:
            self._queue.extend(frames)

    def enqueue_speech_frames(self, count: int = 50, amplitude: int = 8000) -> None:
        """Generate synthetic non-silent PCM frames simulating human speech energy."""
        import struct
        # 320 samples of a synthetic wave
        sample_bytes = struct.pack("<h", amplitude) * 320
        with self._lock:
            self._queue.extend([sample_bytes] * count)

    def enqueue_silence_frames(self, count: int = 50) -> None:
        """Generate synthetic silent PCM frames (amplitude 0)."""
        silent_frame = b"\x00" * 640
        with self._lock:
            self._queue.extend([silent_frame] * count)

    @property
    def is_active(self) -> bool:
        return self._is_active

    def start(self) -> None:
        self._is_active = True

    def stop(self) -> None:
        self._is_active = False

    def close(self) -> None:
        self.stop()
        with self._lock:
            self._queue.clear()

    def get_device_info(self) -> AudioDeviceInfo:
        return self.device_info

    def read_frame(self, num_bytes: int = 640) -> bytes:
        with self._lock:
            if not self._is_active:
                return b""
            if self._queue:
                return self._queue.pop(0)
            # Default to silence if queue exhausted
            return b"\x00" * num_bytes
