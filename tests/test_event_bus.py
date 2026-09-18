"""
Unit tests for the asynchronous EventBus.
"""

import asyncio
import unittest
from kali_ai.core.event_bus import EventBus
from kali_ai.core.events import Event, EventType


class TestEventBus(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.bus = EventBus(history_limit=50)

    async def test_publish_and_subscribe(self) -> None:
        received_events = []

        async def handler(event: Event) -> None:
            received_events.append(event)

        token = self.bus.subscribe(EventType.STATE_CHANGED.value, handler)

        test_event = Event(
            event_type=EventType.STATE_CHANGED.value,
            payload={"from": "IDLE", "to": "ACTIVE"},
            source="test",
        )
        await self.bus.publish(test_event)

        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].id, test_event.id)
        self.assertEqual(received_events[0].payload["to"], "ACTIVE")

        # Unsubscribe and verify no more events received
        self.assertTrue(self.bus.unsubscribe(token))
        await self.bus.publish(test_event)
        self.assertEqual(len(received_events), 1)

    async def test_wildcard_subscriber(self) -> None:
        all_events = []

        async def wildcard_handler(event: Event) -> None:
            all_events.append(event)

        self.bus.subscribe_all(wildcard_handler)

        await self.bus.publish(Event(event_type="event.a", payload={"val": 1}))
        await self.bus.publish(Event(event_type="event.b", payload={"val": 2}))

        self.assertEqual(len(all_events), 2)
        self.assertEqual(all_events[0].event_type, "event.a")
        self.assertEqual(all_events[1].event_type, "event.b")

    async def test_failed_handler_isolation(self) -> None:
        """One handler throwing an unhandled exception must not crash other handlers or the publisher."""
        normal_received = []

        async def failing_handler(event: Event) -> None:
            raise RuntimeError("Unexpected handler crash!")

        async def healthy_handler(event: Event) -> None:
            normal_received.append(event)

        self.bus.subscribe("test.crash", failing_handler)
        self.bus.subscribe("test.crash", healthy_handler)

        # Should not raise exception
        await self.bus.publish(Event(event_type="test.crash", payload={"ok": True}))

        self.assertEqual(len(normal_received), 1)
        self.assertEqual(normal_received[0].payload["ok"], True)

    async def test_event_history(self) -> None:
        for i in range(10):
            await self.bus.publish(Event(event_type="history.test", payload={"i": i}))

        history = self.bus.get_history(limit=5)
        self.assertEqual(len(history), 5)
        self.assertEqual(history[-1].payload["i"], 9)


if __name__ == "__main__":
    unittest.main()
