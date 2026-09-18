"""
Event definitions and data models for the Kali AI event bus.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Core system and subsystem event types."""
    APPLICATION_STARTED = "application.started"
    APPLICATION_STOPPING = "application.stopping"
    APPLICATION_STOPPED = "application.stopped"
    STATE_CHANGED = "state.changed"
    CONFIG_CHANGED = "config.changed"
    ASSISTANT_NAME_CHANGED = "assistant.name_changed"
    ERROR_OCCURRED = "error.occurred"

    # Voice subsystem events
    VOICE_STARTED = "voice.started"
    VOICE_STOPPED = "voice.stopped"
    WAKE_WORD_DETECTED = "voice.wake_word_detected"
    COMMAND_CAPTURE_STARTED = "voice.command_capture_started"
    COMMAND_CAPTURE_COMPLETED = "voice.command_capture_completed"
    STT_STARTED = "voice.stt_started"
    STT_COMPLETED = "voice.stt_completed"
    VOICE_ERROR = "voice.error"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Event:
    """
    Immutable structured event for the internal event bus.
    """
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    correlation_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to a plain dictionary."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }
