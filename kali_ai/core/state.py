"""
Formal application lifecycle and state machine for Kali AI.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from kali_ai.core.exceptions import StateTransitionError

logger = logging.getLogger(__name__)


class ApplicationState(str, Enum):
    """Lifecycle states of the Kali AI Assistant."""
    STARTING = "STARTING"
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StateTransitionRecord:
    """Immutable audit record of an individual state transition."""
    from_state: ApplicationState
    to_state: ApplicationState
    timestamp: float
    reason: str


class StateMachine:
    """
    Thread-safe state machine managing application lifecycle transitions.
    """

    # Comprehensive transition validation matrix
    VALID_TRANSITIONS: dict[ApplicationState, set[ApplicationState]] = {
        ApplicationState.STARTING: {
            ApplicationState.IDLE,
            ApplicationState.ERROR,
            ApplicationState.STOPPING,
        },
        ApplicationState.IDLE: {
            ApplicationState.ACTIVE,
            ApplicationState.STOPPING,
            ApplicationState.ERROR,
        },
        ApplicationState.ACTIVE: {
            ApplicationState.PROCESSING,
            ApplicationState.IDLE,
            ApplicationState.STOPPING,
            ApplicationState.ERROR,
        },
        ApplicationState.PROCESSING: {
            ApplicationState.EXECUTING,
            ApplicationState.IDLE,
            ApplicationState.STOPPING,
            ApplicationState.ERROR,
        },
        ApplicationState.EXECUTING: {
            ApplicationState.IDLE,
            ApplicationState.PAUSED,
            ApplicationState.PROCESSING,
            ApplicationState.STOPPING,
            ApplicationState.ERROR,
        },
        ApplicationState.PAUSED: {
            ApplicationState.EXECUTING,
            ApplicationState.IDLE,
            ApplicationState.STOPPING,
            ApplicationState.ERROR,
        },
        ApplicationState.STOPPING: {
            ApplicationState.STOPPED,
            ApplicationState.ERROR,
        },
        ApplicationState.STOPPED: {
            ApplicationState.STARTING,
        },
        ApplicationState.ERROR: {
            ApplicationState.IDLE,
            ApplicationState.STOPPING,
            ApplicationState.STOPPED,
        },
    }

    def __init__(self, initial_state: ApplicationState = ApplicationState.STARTING) -> None:
        self._current_state: ApplicationState = initial_state
        self._lock = threading.RLock()
        self._history: list[StateTransitionRecord] = [
            StateTransitionRecord(
                from_state=initial_state,
                to_state=initial_state,
                timestamp=time.time(),
                reason="Initial state",
            )
        ]
        self._callbacks: list[Callable[[ApplicationState, ApplicationState, str], None]] = []

    @property
    def current_state(self) -> ApplicationState:
        """Return the current application state."""
        with self._lock:
            return self._current_state

    @property
    def history(self) -> list[StateTransitionRecord]:
        """Return a copy of the transition history."""
        with self._lock:
            return list(self._history)

    def can_transition_to(self, target_state: ApplicationState) -> bool:
        """Check if transition from current state to target state is legally allowed."""
        with self._lock:
            valid_targets = self.VALID_TRANSITIONS.get(self._current_state, set())
            return target_state in valid_targets

    def add_transition_callback(
        self, callback: Callable[[ApplicationState, ApplicationState, str], None]
    ) -> None:
        """Register a callback to be notified on state transitions: callback(from_state, to_state, reason)."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def remove_transition_callback(
        self, callback: Callable[[ApplicationState, ApplicationState, str], None]
    ) -> None:
        """Unregister a state transition callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def transition_to(self, target_state: ApplicationState, reason: str = "") -> None:
        """
        Transition to target state if legally allowed.
        Raises StateTransitionError if the transition is invalid.
        """
        with self._lock:
            from_state = self._current_state
            if target_state == from_state:
                logger.debug("State transition ignored: already in %s", from_state)
                return

            if not self.can_transition_to(target_state):
                err_msg = (
                    f"Invalid state transition requested: {from_state.value} -> {target_state.value}. "
                    f"Allowed targets: {[s.value for s in self.VALID_TRANSITIONS.get(from_state, set())]}"
                )
                logger.error(err_msg)
                raise StateTransitionError(from_state.value, target_state.value, reason or err_msg)

            self._current_state = target_state
            record = StateTransitionRecord(
                from_state=from_state,
                to_state=target_state,
                timestamp=time.time(),
                reason=reason or f"Transitioned from {from_state} to {target_state}",
            )
            self._history.append(record)
            logger.info(
                "State changed: %s -> %s (reason: %s)",
                from_state.value,
                target_state.value,
                record.reason,
            )

            # Invoke callbacks safely
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb(from_state, target_state, reason)
            except Exception as ex:
                logger.exception("Error executing state transition callback: %s", ex)
