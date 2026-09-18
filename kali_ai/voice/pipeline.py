"""
Voice pipeline coordinator: integrates AudioInput, VAD, WakeWordDetector, CommandCapture, STT, and EventBus.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from kali_ai.core.events import Event
from kali_ai.core.exceptions import KaliAIError
from kali_ai.core.state import ApplicationState
from kali_ai.voice.audio import AudioInputInterface, PipeWireAudioInput
from kali_ai.voice.stt import SpeechToText, MockSTT
from kali_ai.voice.tts import TextToSpeech, MockTTS
from kali_ai.voice.vad import EnergyVAD, VADConfig
from kali_ai.voice.wake_word import EnergyPatternWakeWordDetector, WakeWordDetector

if TYPE_CHECKING:
    from kali_ai.core.application import KaliApplication
    from kali_ai.core.event_bus import EventBus

logger = logging.getLogger(__name__)


class VoicePipelineState(str, Enum):
    """Subsystem lifecycle states of the Voice Pipeline."""
    DISABLED = "DISABLED"
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    WAKE_DETECTED = "WAKE_DETECTED"
    CAPTURING_COMMAND = "CAPTURING_COMMAND"
    PROCESSING_STT = "PROCESSING_STT"
    ERROR = "ERROR"
    STOPPING = "STOPPING"

    def __str__(self) -> str:
        return self.value


class VoicePipeline:
    """
    Asynchronous voice coordinator running a local-first, privacy-respecting audio processing loop.
    Strictly prevents pre-wake microphone frames from ever reaching STT.
    """

    def __init__(
        self,
        audio_input: AudioInputInterface | None = None,
        vad: EnergyVAD | None = None,
        wake_word_detector: WakeWordDetector | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        event_bus: EventBus | None = None,
        app: KaliApplication | None = None,
        wake_word: str = "Sandy",
        silence_timeout_seconds: float = 1.2,
        max_command_duration_seconds: float = 8.0,
    ) -> None:
        self.audio_input = audio_input or PipeWireAudioInput()
        self.vad = vad or EnergyVAD()
        self.wake_word_detector = wake_word_detector or EnergyPatternWakeWordDetector(wake_word=wake_word, vad=self.vad)
        self.stt = stt or MockSTT()
        self.tts = tts or MockTTS()
        self.event_bus = event_bus
        self.app = app
        self.wake_word = wake_word
        self.silence_timeout_seconds = silence_timeout_seconds
        self.max_command_duration_seconds = max_command_duration_seconds

        self._state = VoicePipelineState.IDLE
        self._lock = threading.RLock()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def state(self) -> VoicePipelineState:
        with self._lock:
            return self._state

    def _set_state(self, new_state: VoicePipelineState, reason: str = "") -> None:
        with self._lock:
            old_state = self._state
            self._state = new_state
            logger.debug("VoicePipeline state: %s -> %s (%s)", old_state, new_state, reason)

    async def start(self) -> None:
        """Start the background listening loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._set_state(VoicePipelineState.LISTENING, reason="Pipeline started")

        try:
            self.audio_input.start()
            self.wake_word_detector.start()
        except Exception as exc:
            self._set_state(VoicePipelineState.ERROR, reason=f"Audio start error: {exc}")
            self._emit_event("voice.error", {"error": str(exc), "stage": "audio_start"})
            logger.error("Failed to start voice hardware: %s", exc)
            return

        self._emit_event("voice.started", {"wake_word": self.wake_word})
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("VoicePipeline listening loop started for wake-word '%s'", self.wake_word)

    async def stop(self) -> None:
        """Stop audio capture and background loop."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._set_state(VoicePipelineState.STOPPING, reason="Pipeline stopping")

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        try:
            self.wake_word_detector.stop()
            self.audio_input.stop()
        except Exception as exc:
            logger.warning("Error stopping audio input: %s", exc)

        self._set_state(VoicePipelineState.IDLE, reason="Pipeline stopped")
        self._emit_event("voice.stopped", {})
        logger.info("VoicePipeline stopped.")

    async def _listen_loop(self) -> None:
        """
        Primary continuous loop:
        1. Read 20ms audio frames locally.
        2. Feed to VAD & WakeWordDetector (STRICTLY LOCAL, zero STT buffering).
        3. Upon wake detection -> capture command utterance -> STT -> emit event -> resume LISTENING.
        """
        loop = asyncio.get_running_loop()

        while self._running:
            try:
                # 1. Read 20ms PCM frame (640 bytes) in executor to avoid blocking asyncio
                frame = await loop.run_in_executor(None, self.audio_input.read_frame, 640)
                if not frame:
                    await asyncio.sleep(0.01)
                    continue

                # 2. Local Wake-word Evaluation
                is_wake = self.wake_word_detector.feed_audio(frame)
                if is_wake:
                    await self._handle_wake_detection()

                # Yield control briefly to event loop
                await asyncio.sleep(0.001)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Unexpected error in voice listening loop: %s", exc)
                self._emit_event("voice.error", {"error": str(exc), "stage": "listen_loop"})
                await asyncio.sleep(0.5)

    async def _handle_wake_detection(self) -> None:
        """
        Handle transition when wake word is positively detected:
        1. Emits WAKE_WORD_DETECTED.
        2. Transitions application state IDLE -> ACTIVE.
        3. Captures subsequent user command with silence endpointing.
        4. Transcribes via STT and emits text command event.
        5. Returns application to IDLE.
        """
        detected, confidence = self.wake_word_detector.detect()
        logger.info("Wake word verified! Transitioning to ACTIVE mode (confidence: %.2f)", confidence)
        self._set_state(VoicePipelineState.WAKE_DETECTED, reason="Wake word verified")

        self._emit_event(
            "voice.wake_word_detected",
            {
                "wake_word": self.wake_word,
                "confidence": confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Transition main application state machine to ACTIVE if app reference is provided
        if self.app and self.app.current_state == ApplicationState.IDLE:
            try:
                self.app.state_machine.transition_to(
                    ApplicationState.ACTIVE, reason=f"Wake word '{self.wake_word}' detected"
                )
            except Exception as exc:
                logger.warning("Could not transition app state: %s", exc)

        # Acknowledge with optional short chime / TTS
        self.tts.speak("Yes?")

        # 3. Capture Command Utterance
        command_audio = await self._capture_command_audio()

        # 4. Process Speech-to-Text
        if command_audio:
            await self._process_command_stt(command_audio)
        else:
            logger.info("No speech command captured (timeout). Returning to LISTENING.")

        # 5. Return to LISTENING / IDLE
        self.wake_word_detector.reset()
        if self.app and self.app.current_state == ApplicationState.ACTIVE:
            try:
                self.app.state_machine.transition_to(
                    ApplicationState.IDLE, reason="Voice command interaction completed"
                )
            except Exception as exc:
                logger.warning("Could not return app state to IDLE: %s", exc)

        self._set_state(VoicePipelineState.LISTENING, reason="Resuming idle listening")

    async def _capture_command_audio(self) -> bytes:
        """
        Record audio strictly for the duration of the command utterance.
        Endpoints dynamically using VAD silence timeout.
        """
        self._set_state(VoicePipelineState.CAPTURING_COMMAND, reason="Recording command audio")
        self._emit_event("voice.command_capture_started", {})

        audio_buffer: list[bytes] = []
        silence_start: float | None = None
        speech_started = False
        start_time = time.time()
        loop = asyncio.get_running_loop()

        while self._running:
            # Check maximum duration timeout
            if time.time() - start_time > self.max_command_duration_seconds:
                logger.debug("Command capture reached max duration (%.1fs)", self.max_command_duration_seconds)
                break

            frame = await loop.run_in_executor(None, self.audio_input.read_frame, 640)
            if not frame:
                await asyncio.sleep(0.01)
                continue

            audio_buffer.append(frame)
            is_speech = self.vad.is_speech(frame)

            if is_speech:
                speech_started = True
                silence_start = None
            elif speech_started:
                # Speech occurred, now tracking silence endpoint
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= self.silence_timeout_seconds:
                    logger.debug("Endpoint detected: %.2fs silence after command", self.silence_timeout_seconds)
                    break
            else:
                # Waiting for initial speech to begin
                if time.time() - start_time > 3.0:
                    logger.debug("No initial command speech detected within 3.0s")
                    break

            await asyncio.sleep(0.001)

        total_bytes = sum(len(b) for b in audio_buffer)
        self._emit_event(
            "voice.command_capture_completed",
            {"captured_bytes": total_bytes, "speech_detected": speech_started},
        )
        return b"".join(audio_buffer) if speech_started else b""

    async def _process_command_stt(self, audio_pcm: bytes) -> None:
        """
        Execute Speech-to-Text transcription on captured command audio.
        """
        self._set_state(VoicePipelineState.PROCESSING_STT, reason="Transcribing command")
        self._emit_event("voice.stt_started", {"provider": self.stt.provider_name})

        loop = asyncio.get_running_loop()
        try:
            transcription = await loop.run_in_executor(None, self.stt.transcribe, audio_pcm)
            clean_text = transcription.strip()
            logger.info("Voice command transcribed: '%s'", clean_text)

            self._emit_event(
                "voice.stt_completed",
                {
                    "text": clean_text,
                    "provider": self.stt.provider_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "voice",
                },
            )
        except Exception as exc:
            logger.error("STT transcription failed: %s", exc)
            self._emit_event("voice.error", {"error": str(exc), "stage": "stt_transcribe"})

    def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish event safely to the EventBus."""
        if self.event_bus:
            self.event_bus.publish_nowait(
                Event(
                    event_type=event_type,
                    payload=payload,
                    source="voice_pipeline",
                )
            )
