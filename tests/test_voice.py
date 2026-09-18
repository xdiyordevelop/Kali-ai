"""
Comprehensive unit and integration tests for the Voice subsystem (Phase 2).
Covers audio capture, VAD, wake-word detection, pipeline states, and strict privacy isolation.
"""

import asyncio
import unittest
from kali_ai.core.application import KaliApplication
from kali_ai.core.event_bus import EventBus
from kali_ai.core.events import Event
from kali_ai.core.state import ApplicationState
from kali_ai.voice.audio import AudioDeviceInfo, MockAudioInput
from kali_ai.voice.pipeline import VoicePipeline, VoicePipelineState
from kali_ai.voice.stt import MockSTT
from kali_ai.voice.tts import MockTTS
from kali_ai.voice.vad import EnergyVAD, VADConfig
from kali_ai.voice.wake_word import EnergyPatternWakeWordDetector, MockWakeWordDetector


class TestVoiceSubsystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.audio_input = MockAudioInput()
        self.vad = EnergyVAD(VADConfig(sensitivity=3, speech_start_threshold=300.0))
        self.wake_detector = MockWakeWordDetector(wake_word="Sandy", confidence_threshold=0.75)
        self.stt = MockSTT(default_text="open the terminal")
        self.tts = MockTTS()
        self.event_bus = EventBus()

        self.pipeline = VoicePipeline(
            audio_input=self.audio_input,
            vad=self.vad,
            wake_word_detector=self.wake_detector,
            stt=self.stt,
            tts=self.tts,
            event_bus=self.event_bus,
            wake_word="Sandy",
            silence_timeout_seconds=0.1,  # Fast timeout for tests
            max_command_duration_seconds=2.0,
        )

    async def asyncTearDown(self) -> None:
        if self.pipeline.state != VoicePipelineState.IDLE:
            await self.pipeline.stop()

    # 1. Audio Tests
    def test_audio_mock_device_info(self) -> None:
        info = self.audio_input.get_device_info()
        self.assertIsInstance(info, AudioDeviceInfo)
        self.assertEqual(info.id, "mock_device")

    def test_audio_read_and_stop(self) -> None:
        self.audio_input.start()
        self.assertTrue(self.audio_input.is_active)

        # Enqueue silence and speech
        self.audio_input.enqueue_silence_frames(count=2)
        frame = self.audio_input.read_frame(640)
        self.assertEqual(len(frame), 640)

        self.audio_input.stop()
        self.assertFalse(self.audio_input.is_active)

    # 2. VAD Tests
    def test_vad_silence_vs_speech(self) -> None:
        silent_frame = b"\x00" * 640
        self.assertFalse(self.vad.is_speech(silent_frame))
        self.assertEqual(self.vad.calculate_rms(silent_frame), 0.0)

        # Speech frame with high amplitude
        import struct
        loud_samples = struct.pack("<h", 8000) * 320
        self.assertTrue(self.vad.is_speech(loud_samples))
        self.assertGreater(self.vad.calculate_rms(loud_samples), 500.0)

    def test_vad_sensitivity_thresholds(self) -> None:
        vad_least_sensitive = EnergyVAD(VADConfig(sensitivity=1, speech_start_threshold=400.0))
        vad_most_sensitive = EnergyVAD(VADConfig(sensitivity=5, speech_start_threshold=400.0))

        # Sensitivity 1 requires higher energy than sensitivity 5
        self.assertGreater(
            vad_least_sensitive.effective_threshold,
            vad_most_sensitive.effective_threshold,
        )

    # 3. Wake Word Tests
    def test_mock_wake_word_detection(self) -> None:
        detector = MockWakeWordDetector(wake_word="Sandy")
        detector.start()

        # Before trigger
        is_detected, conf = detector.detect()
        self.assertFalse(is_detected)
        self.assertEqual(conf, 0.0)

        # Trigger
        detector.trigger(confidence=0.92)
        is_detected, conf = detector.detect()
        self.assertTrue(is_detected)
        self.assertEqual(conf, 0.92)

        # Reset
        detector.reset()
        is_detected, conf = detector.detect()
        self.assertFalse(is_detected)

    def test_energy_pattern_wake_word_detector(self) -> None:
        detector = EnergyPatternWakeWordDetector(wake_word="Sandy", vad=self.vad)
        detector.start()

        # Feed silence -> no detection
        silent_frame = b"\x00" * 640
        for _ in range(20):
            self.assertFalse(detector.feed_audio(silent_frame))

        detector.stop()

    # 4. Pipeline Execution & State Transitions
    async def test_pipeline_full_cycle(self) -> None:
        events_received: list[Event] = []

        async def record_event(e: Event) -> None:
            events_received.append(e)

        self.event_bus.subscribe_all(record_event)

        # Start pipeline
        await self.pipeline.start()
        self.assertEqual(self.pipeline.state, VoicePipelineState.LISTENING)

        # Enqueue speech frames to be captured as the command
        self.audio_input.enqueue_speech_frames(count=10, amplitude=6000)
        self.audio_input.enqueue_silence_frames(count=15)

        # Trigger wake word
        self.wake_detector.trigger(confidence=0.95)

        # Allow pipeline loop to process wake and command capture
        await asyncio.sleep(0.2)

        await self.pipeline.stop()

        # Verify STT was called with command
        self.assertEqual(self.stt.call_count, 1)

        # Verify event emissions
        event_types = [e.event_type for e in events_received]
        self.assertIn("voice.started", event_types)
        self.assertIn("voice.wake_word_detected", event_types)
        self.assertIn("voice.command_capture_started", event_types)
        self.assertIn("voice.command_capture_completed", event_types)
        self.assertIn("voice.stt_completed", event_types)

        # Verify command payload text
        stt_event = next(e for e in events_received if e.event_type == "voice.stt_completed")
        self.assertEqual(stt_event.payload["text"], "open the terminal")
        self.assertEqual(stt_event.payload["source"], "voice")

    async def test_pipeline_no_wake_word_remains_listening(self) -> None:
        """When no wake word is triggered, pipeline must remain in LISTENING and NEVER call STT."""
        await self.pipeline.start()

        # Enqueue random background audio frames
        self.audio_input.enqueue_speech_frames(count=10)
        self.audio_input.enqueue_silence_frames(count=10)

        # Do NOT trigger wake word
        await asyncio.sleep(0.1)

        self.assertEqual(self.pipeline.state, VoicePipelineState.LISTENING)
        self.assertEqual(self.stt.call_count, 0)  # STT must NOT be called

        await self.pipeline.stop()

    async def test_pipeline_stt_failure_recovers_safely(self) -> None:
        """If STT encounters an error, pipeline must emit voice.error and safely return to LISTENING."""
        self.stt.set_should_fail(True)

        events_received: list[Event] = []

        async def record_event(e: Event) -> None:
            events_received.append(e)

        self.event_bus.subscribe_all(record_event)

        await self.pipeline.start()

        # Enqueue speech and trigger wake word
        self.audio_input.enqueue_speech_frames(count=5)
        self.audio_input.enqueue_silence_frames(count=10)
        self.wake_detector.trigger()

        await asyncio.sleep(0.15)
        await self.pipeline.stop()

        event_types = [e.event_type for e in events_received]
        self.assertIn("voice.error", event_types)
        self.assertEqual(self.stt.call_count, 1)

    # 5. STRICT PRIVACY TESTS
    async def test_strict_privacy_pre_wake_audio_isolation(self) -> None:
        """
        MANDATORY PRIVACY TEST:
        Microphone frames processed BEFORE wake-word detection must NEVER be sent to STT.
        """
        await self.pipeline.start()

        # Feed 100 frames of speech while wake word is NOT triggered
        self.audio_input.enqueue_speech_frames(count=100)
        await asyncio.sleep(0.08)

        # Verify STT was NEVER called
        self.assertEqual(self.stt.call_count, 0)
        self.assertEqual(len(self.stt.transcribed_bytes), 0)

        # Now trigger wake word and feed command
        self.audio_input.enqueue_speech_frames(count=6)
        self.audio_input.enqueue_silence_frames(count=10)
        self.wake_detector.trigger()

        # Wait for command capture & STT to complete
        for _ in range(25):
            if self.stt.call_count > 0:
                break
            await asyncio.sleep(0.05)

        await self.pipeline.stop()

        # Now STT should have been called exactly ONCE, strictly for the command utterance
        self.assertEqual(self.stt.call_count, 1)
        self.assertEqual(len(self.stt.transcribed_bytes), 1)


if __name__ == "__main__":
    unittest.main()
