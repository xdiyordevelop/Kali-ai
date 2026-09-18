"""
Unit and integration tests for KaliApplication lifecycle and log redaction.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path

from kali_ai.core.application import KaliApplication
from kali_ai.core.events import EventType
from kali_ai.core.state import ApplicationState
from kali_ai.observability.logging import redact_sensitive_text


class TestApplicationLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_app.db"
        self.log_dir = Path(self.temp_dir.name) / "logs"
        self.app = KaliApplication(
            db_path=self.db_path,
            log_dir=self.log_dir,
            log_level="DEBUG",
        )

    async def asyncTearDown(self) -> None:
        if self.app.current_state != ApplicationState.STOPPED:
            await self.app.stop()
        self.temp_dir.cleanup()

    async def test_full_bootstrap_and_shutdown(self) -> None:
        events_emitted = []

        async def capture_event(event):
            events_emitted.append(event.event_type)

        self.app.event_bus.subscribe_all(capture_event)

        # 1. Initialize
        self.app.initialize()
        self.assertTrue(self.app.db_manager.is_open)
        self.assertEqual(self.app.current_state, ApplicationState.STARTING)

        # 2. Start
        await self.app.start()
        self.assertEqual(self.app.current_state, ApplicationState.IDLE)
        self.assertGreater(self.app.uptime_seconds, 0.0)

        # Verify events emitted
        self.assertIn(EventType.STATE_CHANGED.value, events_emitted)
        self.assertIn(EventType.APPLICATION_STARTED.value, events_emitted)

        # 3. Graceful shutdown
        await self.app.stop()
        self.assertEqual(self.app.current_state, ApplicationState.STOPPED)
        self.assertFalse(self.app.db_manager.is_open)
        self.assertIn(EventType.APPLICATION_STOPPED.value, events_emitted)

    def test_log_redaction(self) -> None:
        raw_msg = "User configured sk-1234567890abcdef1234567890 and password='super_secret_password' with Bearer abcdef1234567890123456"
        redacted = redact_sensitive_text(raw_msg)

        self.assertNotIn("sk-1234567890abcdef1234567890", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)
        self.assertNotIn("super_secret_password", redacted)
        self.assertNotIn("abcdef1234567890123456", redacted)
        self.assertIn("[REDACTED_TOKEN]", redacted)


if __name__ == "__main__":
    unittest.main()
