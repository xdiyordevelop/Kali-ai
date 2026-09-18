"""
Asynchronous internal event bus for Kali AI.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from kali_ai.core.events import Event

logger = logging.getLogger(__name__)

# Handler can be either async (coroutine) or sync function accepting an Event
EventHandler = Callable[[Event], Awaitable[None] | None]


@dataclass(frozen=True)
class SubscriptionToken:
    """Unique token representing a registered event subscription."""
    id: str
    event_type: str  # specific event_type or "*" for all events


class EventBus:
    """
    High-performance, isolated asynchronous event bus.
    Supports both async coroutines and sync callables with handler error isolation.
    """

    def __init__(self, history_limit: int = 200) -> None:
        self._subscribers: dict[str, list[tuple[str, EventHandler]]] = {}
        self._history_limit = history_limit
        self._history: deque[Event] = deque(maxlen=history_limit)
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> SubscriptionToken:
        """
        Subscribe an async or sync handler to a specific event type.
        Returns a SubscriptionToken used to unsubscribe.
        """
        sub_id = str(uuid.uuid4())
        token = SubscriptionToken(id=sub_id, event_type=event_type)
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append((sub_id, handler))
        logger.debug("Subscribed %s to event %s (id: %s)", handler, event_type, sub_id)
        return token

    def subscribe_all(self, handler: EventHandler) -> SubscriptionToken:
        """Subscribe a handler to all published events (wildcard '*')."""
        return self.subscribe("*", handler)

    def unsubscribe(self, token: SubscriptionToken) -> bool:
        """
        Remove subscription associated with the given SubscriptionToken.
        Returns True if found and removed, False otherwise.
        """
        event_type = token.event_type
        if event_type in self._subscribers:
            initial_len = len(self._subscribers[event_type])
            self._subscribers[event_type] = [
                (sid, h) for sid, h in self._subscribers[event_type] if sid != token.id
            ]
            if len(self._subscribers[event_type]) < initial_len:
                logger.debug("Unsubscribed token %s from %s", token.id, event_type)
                return True
        return False

    async def publish(self, event: Event) -> None:
        """
        Publish an event asynchronously.
        Executes all matching handlers concurrently with full exception isolation.
        """
        self._history.append(event)
        logger.debug("Publishing event: %s [%s]", event.event_type, event.id)

        # Collect matching handlers
        handlers_to_run: list[EventHandler] = []

        # Specific event subscribers
        if event.event_type in self._subscribers:
            handlers_to_run.extend(h for _, h in self._subscribers[event.event_type])

        # Wildcard subscribers
        if "*" in self._subscribers:
            handlers_to_run.extend(h for _, h in self._subscribers["*"])

        if not handlers_to_run:
            return

        # Execute all handlers with failure isolation
        tasks = [self._execute_handler(h, event) for h in handlers_to_run]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_handler(self, handler: EventHandler, event: Event) -> None:
        """Execute a single handler safely catching any unexpected exceptions."""
        try:
            if inspect.iscoroutinefunction(handler):
                await handler(event)
            else:
                # Run synchronous callable directly (or in thread pool if needed)
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
        except Exception as exc:
            logger.exception(
                "Event handler %s failed while processing event %s [%s]: %s",
                handler,
                event.event_type,
                event.id,
                exc,
            )

    def publish_nowait(self, event: Event) -> None:
        """
        Fire-and-forget publishing when running inside an existing asyncio event loop.
        Schedules publish task on the current loop.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            # Fallback if no loop is currently running
            asyncio.run(self.publish(event))

    def get_history(self, limit: int | None = None) -> list[Event]:
        """Return the most recent published events."""
        events = list(self._history)
        if limit is not None and limit > 0:
            return events[-limit:]
        return events

    def clear_history(self) -> None:
        """Clear recorded event history."""
        self._history.clear()
