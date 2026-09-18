"""
Core package for Kali AI: application lifecycle, state machine, event bus, and exceptions.
"""

from kali_ai.core.state import ApplicationState, StateMachine
from kali_ai.core.events import Event, EventType
from kali_ai.core.event_bus import EventBus
from kali_ai.core.exceptions import (
    KaliAIError,
    StateTransitionError,
    ConfigurationError,
    DatabaseError,
    SecurityPolicyError,
    EventBusError,
)

__all__ = [
    "ApplicationState",
    "StateMachine",
    "Event",
    "EventType",
    "EventBus",
    "KaliAIError",
    "StateTransitionError",
    "ConfigurationError",
    "DatabaseError",
    "SecurityPolicyError",
    "EventBusError",
]
