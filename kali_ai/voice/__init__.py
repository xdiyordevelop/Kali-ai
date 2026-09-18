"""
Voice subsystem for Kali AI: audio capture, VAD, wake-word detection, and STT/TTS coordination.
"""

from kali_ai.voice.audio import AudioDeviceInfo, AudioInputInterface, PipeWireAudioInput, MockAudioInput
from kali_ai.voice.vad import EnergyVAD, VADConfig
from kali_ai.voice.wake_word import WakeWordDetector, MockWakeWordDetector, EnergyPatternWakeWordDetector
from kali_ai.voice.stt import SpeechToText, MockSTT
from kali_ai.voice.tts import TextToSpeech, MockTTS
from kali_ai.voice.pipeline import VoicePipeline, VoicePipelineState

__all__ = [
    "AudioDeviceInfo",
    "AudioInputInterface",
    "PipeWireAudioInput",
    "MockAudioInput",
    "EnergyVAD",
    "VADConfig",
    "WakeWordDetector",
    "MockWakeWordDetector",
    "EnergyPatternWakeWordDetector",
    "SpeechToText",
    "MockSTT",
    "TextToSpeech",
    "MockTTS",
    "VoicePipeline",
    "VoicePipelineState",
]
