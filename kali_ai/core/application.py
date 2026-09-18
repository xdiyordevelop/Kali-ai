"""
Application bootstrap, lifecycle coordinator, and graceful shutdown orchestrator.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from kali_ai.config.manager import ConfigManager
from kali_ai.config.settings import DEFAULT_CONFIG_DB_PATH, DEFAULT_LOG_DIR
from kali_ai.core.event_bus import EventBus
from kali_ai.core.events import Event, EventType
from kali_ai.core.exceptions import KaliAIError
from kali_ai.core.state import ApplicationState, StateMachine
from kali_ai.identity.naming import NamingEngine
from kali_ai.observability.logging import setup_logging, get_logger
from kali_ai.storage.database import DatabaseManager
from kali_ai.storage.repositories import ConfigRepository, SecurityPolicyRepository

logger = get_logger(__name__)


class KaliApplication:
    """
    Main application coordinator managing database, event bus, configuration,
    state machine, and graceful lifecycle bootstrap.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        log_dir: Path | str | None = None,
        log_level: str = "INFO",
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_CONFIG_DB_PATH)
        self.log_dir = Path(log_dir or DEFAULT_LOG_DIR)
        self.log_level = log_level

        # Subsystems initialized during bootstrap
        self.state_machine = StateMachine(initial_state=ApplicationState.STARTING)
        self.event_bus = EventBus()
        self.db_manager = DatabaseManager(self.db_path)
        self.config_repo = ConfigRepository(self.db_manager)
        self.policy_repo = SecurityPolicyRepository(self.db_manager)
        self.config_manager = ConfigManager(
            config_repo=self.config_repo,
            policy_repo=self.policy_repo,
            event_bus=self.event_bus,
        )

        self._start_time: float | None = None
        self._stop_event = asyncio.Event()
        self._is_initialized = False
        self.voice_pipeline: Any | None = None

        # Hook state transitions to EventBus emission
        self.state_machine.add_transition_callback(self._on_state_transition)

    @property
    def current_state(self) -> ApplicationState:
        return self.state_machine.current_state

    @property
    def uptime_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def _on_state_transition(
        self, from_state: ApplicationState, to_state: ApplicationState, reason: str
    ) -> None:
        """Callback invoked whenever state changes."""
        self.event_bus.publish_nowait(
            Event(
                event_type=EventType.STATE_CHANGED.value,
                payload={
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "reason": reason,
                },
                source="state_machine",
            )
        )

    def initialize(self) -> None:
        """
        Synchronously initialize database connection, apply migrations,
        load configuration, and resolve the assistant name.
        Safe to call multiple times (idempotent).
        """
        if self._is_initialized:
            return

        setup_logging(log_level=self.log_level, log_dir=self.log_dir)
        logger.info("Initializing Kali AI application foundation...")

        # 1. Open database and ensure migrations are applied
        self.db_manager.open()

        # 2. Load configuration from DB
        self.config_manager.load()

        # 3. Detect hostname and resolve/initialize assistant name
        current_hostname = NamingEngine.detect_hostname()
        assistant_name, is_new = NamingEngine.resolve_assistant_name(
            self.config_repo, current_hostname=current_hostname
        )
        # Update cached config
        self.config_manager.config.system.assistant_name = assistant_name
        self.config_manager.config.system.detected_hostname = current_hostname

        logger.info(
            "Identity ready: Assistant Name='%s' (Hostname='%s', is_new=%s)",
            assistant_name,
            current_hostname,
            is_new,
        )

        self._is_initialized = True

    async def start(self) -> None:
        """
        Start the application runtime and transition to IDLE state.
        Sets up signal handlers for graceful shutdown.
        """
        if not self._is_initialized:
            self.initialize()

        self._start_time = time.time()
        self._setup_signals()

        # Transition from STARTING to IDLE
        self.state_machine.transition_to(
            ApplicationState.IDLE, reason="Application bootstrap completed"
        )

        await self.event_bus.publish(
            Event(
                event_type=EventType.APPLICATION_STARTED.value,
                payload={
                    "assistant_name": self.config_manager.config.system.assistant_name,
                    "hostname": self.config_manager.config.system.detected_hostname,
                    "state": self.current_state.value,
                },
                source="application",
            )
        )

        logger.info("Kali AI successfully started and is now in IDLE mode.")

        # Check if voice auto-listening is enabled in configuration
        vcfg = self.config_manager.config.voice
        if vcfg.enabled and vcfg.auto_listen:
            logger.info("Voice auto-listen enabled. Initializing VoicePipeline...")
            self.init_voice_pipeline()
            if self.voice_pipeline:
                await self.voice_pipeline.start()

    def init_voice_pipeline(
        self,
        audio_input: Any | None = None,
        wake_word_detector: Any | None = None,
        stt: Any | None = None,
        tts: Any | None = None,
    ) -> Any:
        """Initialize or return the voice pipeline with current configuration."""
        if self.voice_pipeline is None:
            from kali_ai.voice.pipeline import VoicePipeline
            from kali_ai.voice.vad import EnergyVAD, VADConfig

            vcfg = self.config_manager.config.voice
            wake_word = vcfg.wake_word or self.config_manager.config.system.assistant_name

            vad_cfg = VADConfig(
                enabled=vcfg.vad_enabled,
                sensitivity=vcfg.vad_sensitivity,
                silence_timeout_seconds=vcfg.silence_timeout,
            )
            vad = EnergyVAD(vad_cfg)

            self.voice_pipeline = VoicePipeline(
                audio_input=audio_input,
                vad=vad,
                wake_word_detector=wake_word_detector,
                stt=stt,
                tts=tts,
                event_bus=self.event_bus,
                app=self,
                wake_word=wake_word,
                silence_timeout_seconds=vcfg.silence_timeout,
            )
        return self.voice_pipeline

    async def stop(self, reason: str = "Clean shutdown requested") -> None:
        """
        Initiate graceful shutdown sequence:
        IDLE -> STOPPING -> STOPPED
        Flushes and closes event bus, database, and background resources.
        """
        if self.current_state in (ApplicationState.STOPPING, ApplicationState.STOPPED):
            logger.debug("Application already stopping/stopped.")
            return

        logger.info("Stopping Kali AI: %s", reason)

        # Transition to STOPPING
        try:
            self.state_machine.transition_to(ApplicationState.STOPPING, reason=reason)
        except Exception:
            # Force transition if in error or unexpected state
            pass

        await self.event_bus.publish(
            Event(
                event_type=EventType.APPLICATION_STOPPING.value,
                payload={"reason": reason},
                source="application",
            )
        )

        # Signal stop to any waiting loops
        self._stop_event.set()

        # Stop voice pipeline if active
        if self.voice_pipeline:
            try:
                await self.voice_pipeline.stop()
            except Exception as exc:
                logger.warning("Error stopping voice pipeline during shutdown: %s", exc)

        # Close database connection cleanly
        try:
            self.db_manager.close()
        except Exception as exc:
            logger.warning("Error closing database during shutdown: %s", exc)

        # Transition to STOPPED
        try:
            self.state_machine.transition_to(ApplicationState.STOPPED, reason="Shutdown complete")
        except Exception:
            pass

        await self.event_bus.publish(
            Event(
                event_type=EventType.APPLICATION_STOPPED.value,
                payload={"reason": "Shutdown complete"},
                source="application",
            )
        )

        logger.info("Kali AI stopped cleanly.")

    async def run_forever(self) -> None:
        """
        Keep running in the IDLE state until stop() is invoked or a termination signal is received.
        """
        await self.start()
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            logger.info("Main loop cancelled, shutting down...")
        finally:
            if self.current_state != ApplicationState.STOPPED:
                await self.stop(reason="Run loop terminated")

    def _setup_signals(self) -> None:
        """Register POSIX signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._handle_signal(s)))
        except (NotImplementedError, RuntimeError):
            # Fallback for non-standard execution contexts or threads
            def sync_handler(signum: int, frame: Any) -> None:
                asyncio.create_task(self.stop(reason=f"Received signal {signum}"))

            signal.signal(signal.SIGINT, sync_handler)
            signal.signal(signal.SIGTERM, sync_handler)

    async def _handle_signal(self, sig: signal.Signals) -> None:
        logger.info("Received POSIX signal: %s. Initiating graceful shutdown...", sig.name)
        await self.stop(reason=f"Received signal {sig.name}")
