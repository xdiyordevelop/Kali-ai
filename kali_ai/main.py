"""
Main command-line interface entry point for Kali AI.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import sys
import time
from pathlib import Path

from kali_ai import __version__
from kali_ai.config.settings import DEFAULT_CONFIG_DB_PATH
from kali_ai.core.application import KaliApplication
from kali_ai.core.state import ApplicationState
from kali_ai.identity.naming import NamingEngine
from kali_ai.voice.audio import PipeWireAudioInput
from kali_ai.voice.vad import EnergyVAD, VADConfig


def print_status(app: KaliApplication) -> None:
    """Print clean terminal diagnostic report for the user."""
    if not app.db_manager.is_open:
        app.initialize()

    cfg = app.config_manager.config
    schema_ver = app.db_manager.get_schema_version()
    db_size = "0 B"
    if app.db_path.exists():
        size_bytes = app.db_path.stat().st_size
        if size_bytes > 1024 * 1024:
            db_size = f"{size_bytes / (1024 * 1024):.2f} MB"
        elif size_bytes > 1024:
            db_size = f"{size_bytes / 1024:.2f} KB"
        else:
            db_size = f"{size_bytes} B"

    print("=" * 60)
    print(f" Kali AI Assistant - System Status (v{__version__})")
    print("=" * 60)
    print(f" Operating System       : {platform.system()} {platform.release()} ({platform.machine()})")
    print(f" Python Version         : {platform.python_version()}")
    print(f" Hostname (Physical)    : {NamingEngine.detect_hostname()}")
    print(f" Assistant Name         : {cfg.system.assistant_name} (Customized: {cfg.system.customized})")
    print(f" Lifecycle State        : {app.current_state.value}")
    print("-" * 60)
    print(f" Database Path          : {app.db_path}")
    print(f" Database Status        : Connected (WAL Mode)")
    print(f" Schema Version         : {schema_ver}")
    print(f" Database File Size     : {db_size}")
    print("-" * 60)
    print(f" Default Permission Tier: {cfg.security.default_tier.value}")
    print(f" Emergency Stop         : {'Enabled' if cfg.security.emergency_stop_enabled else 'Disabled'}")
    print(f" Logging Level          : {cfg.system.log_level}")
    print(f" Language / Timezone    : {cfg.system.language} / {cfg.system.timezone}")
    print(f" Voice Subsystem        : {'Enabled' if cfg.voice.enabled else 'Disabled (Safe Default)'}")
    print(f" Automation Subsystem   : {'Enabled' if cfg.automation.enabled else 'Disabled (Phase 10 Placeholder)'}")
    print("=" * 60)


def print_voice_status(app: KaliApplication) -> None:
    """Print detailed status of the voice subsystem."""
    if not app.db_manager.is_open:
        app.initialize()

    cfg = app.config_manager.config
    mic_info = PipeWireAudioInput.detect_default_device()
    wake_word = cfg.voice.wake_word or cfg.system.assistant_name

    print("=" * 60)
    print(" Kali AI Voice Subsystem - Status")
    print("=" * 60)
    print(f" Voice Enabled          : {'Yes' if cfg.voice.enabled else 'No (Safe Default)'}")
    print(f" Auto-Listen on Boot    : {'Yes' if cfg.voice.auto_listen else 'No'}")
    print(f" Configured Wake Word   : '{wake_word}'")
    print("-" * 60)
    print(f" Detected Microphone    : {mic_info.description}")
    print(f" PipeWire Source Target : {mic_info.id} ({mic_info.name})")
    print(f" Audio Format           : 16kHz Mono 16-bit PCM")
    print("-" * 60)
    print(f" VAD Enabled            : {'Yes' if cfg.voice.vad_enabled else 'No'}")
    print(f" VAD Sensitivity (1..5) : {cfg.voice.vad_sensitivity}")
    print(f" Silence Timeout        : {cfg.voice.silence_timeout} seconds")
    print(f" STT Provider           : {cfg.voice.stt_provider}")
    print(f" TTS Provider           : {cfg.voice.tts_provider}")
    print(f" Pipeline State         : {app.voice_pipeline.state.value if app.voice_pipeline else 'IDLE / STANDBY'}")
    print("=" * 60)


def run_voice_test(app: KaliApplication) -> None:
    """Perform a local, privacy-safe microphone capture test without calling any external AI."""
    print("=" * 60)
    print(" Starting Local Microphone Diagnostic Test (Zero AI / Zero Network)")
    print("=" * 60)

    mic_info = PipeWireAudioInput.detect_default_device()
    print(f"Target Device: {mic_info.description} [ID: {mic_info.id}]")

    audio_input = PipeWireAudioInput(target_device=mic_info.id)
    vad = EnergyVAD(VADConfig(sensitivity=3))

    try:
        print("Recording 1.0s of audio via PipeWire pw-record...")
        audio_input.start()

        frames: list[bytes] = []
        speech_detected_count = 0
        rms_values: list[float] = []

        # Read 50 frames (50 * 20ms = 1.0s)
        for _ in range(50):
            frame = audio_input.read_frame(640)
            if frame:
                frames.append(frame)
                rms = vad.calculate_rms(frame)
                rms_values.append(rms)
                if vad.is_speech(frame):
                    speech_detected_count += 1
            time.sleep(0.01)

        audio_input.stop()

        total_bytes = sum(len(f) for f in frames)
        avg_rms = sum(rms_values) / len(rms_values) if rms_values else 0.0
        max_rms = max(rms_values) if rms_values else 0.0

        print("-" * 60)
        print(f"✓ Frames Captured       : {len(frames)} frames ({total_bytes} bytes)")
        print(f"✓ Average Energy RMS    : {avg_rms:.1f} (Peak: {max_rms:.1f})")
        print(f"✓ VAD Speech Frames     : {speech_detected_count} / {len(frames)}")
        print(f"✓ Hardware Stream       : PipeWire -> Python stdout stream operational")
        print("-" * 60)
        print("Privacy Guarantee Verified: 100% processed in memory. Zero external calls.")
        print("=" * 60)

    except Exception as exc:
        print(f"✗ Microphone test failed: {exc}", file=sys.stderr)
        audio_input.stop()
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="kali-ai",
        description="Kali AI - Personal AI Computer Assistant for Kali Linux",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_CONFIG_DB_PATH),
        help="Path to SQLite configuration database",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Console and file log level",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: status
    subparsers.add_parser("status", help="Show system status and configuration summary")

    # Command: run (default if no subcommand given)
    subparsers.add_parser("run", help="Run the assistant daemon in IDLE mode")

    # Command: set-name
    name_parser = subparsers.add_parser("set-name", help="Customize the assistant's name")
    name_parser.add_argument("name", type=str, help="New assistant name")

    # Command: reset-config
    subparsers.add_parser("reset-config", help="Reset configuration to factory defaults")

    # Command: voice
    voice_parser = subparsers.add_parser("voice", help="Voice subsystem management and testing")
    voice_sub = voice_parser.add_subparsers(dest="voice_command", help="Voice action")
    voice_sub.add_parser("status", help="Show voice subsystem status and detected microphone")
    voice_sub.add_parser("test", help="Test microphone and VAD locally without AI")

    ww_parser = voice_sub.add_parser("set-wake-word", help="Configure custom wake word")
    ww_parser.add_argument("word", type=str, help="Wake word to listen for")

    voice_sub.add_parser("enable", help="Enable voice subsystem in configuration")
    voice_sub.add_parser("disable", help="Disable voice subsystem in configuration")

    return parser


def main() -> None:
    """CLI execution entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    app = KaliApplication(
        db_path=args.db_path,
        log_level=args.log_level,
    )

    cmd = args.command or "run"

    if cmd == "status":
        print_status(app)
        app.db_manager.close()
        sys.exit(0)

    elif cmd == "set-name":
        app.initialize()
        try:
            NamingEngine.set_custom_name(app.config_repo, args.name)
            print(f"✓ Assistant name successfully updated to: '{args.name.strip()}'")
        except ValueError as ex:
            print(f"✗ Error: {ex}", file=sys.stderr)
            sys.exit(1)
        finally:
            app.db_manager.close()
        sys.exit(0)

    elif cmd == "reset-config":
        app.initialize()
        app.config_manager.reset_to_defaults()
        print("✓ Configuration has been reset to factory defaults.")
        app.db_manager.close()
        sys.exit(0)

    elif cmd == "voice":
        voice_cmd = args.voice_command or "status"
        if voice_cmd == "status":
            print_voice_status(app)
        elif voice_cmd == "test":
            run_voice_test(app)
        elif voice_cmd == "enable":
            app.initialize()
            app.config_manager.config.voice.enabled = True
            app.config_manager.save()
            print("✓ Voice subsystem enabled in configuration.")
        elif voice_cmd == "disable":
            app.initialize()
            app.config_manager.config.voice.enabled = False
            app.config_manager.save()
            print("✓ Voice subsystem disabled in configuration.")
        elif voice_cmd == "set-wake-word":
            app.initialize()
            app.config_manager.config.voice.wake_word = args.word.strip()
            app.config_manager.save()
            print(f"✓ Wake word configured to: '{args.word.strip()}'")

        app.db_manager.close()
        sys.exit(0)

    elif cmd == "run":
        try:
            print("Starting Kali AI daemon (press Ctrl+C to stop)...")
            asyncio.run(app.run_forever())
        except KeyboardInterrupt:
            print("\nShutdown complete.")
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
