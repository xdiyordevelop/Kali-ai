"""
Unit tests for the Application StateMachine.
"""

import unittest
from kali_ai.core.state import ApplicationState, StateMachine
from kali_ai.core.exceptions import StateTransitionError


class TestStateMachine(unittest.TestCase):
    def setUp(self) -> None:
        self.sm = StateMachine(initial_state=ApplicationState.STARTING)

    def test_initial_state(self) -> None:
        self.assertEqual(self.sm.current_state, ApplicationState.STARTING)
        self.assertEqual(len(self.sm.history), 1)

    def test_valid_transitions_lifecycle(self) -> None:
        # STARTING -> IDLE
        self.sm.transition_to(ApplicationState.IDLE, reason="Bootstrap done")
        self.assertEqual(self.sm.current_state, ApplicationState.IDLE)

        # IDLE -> ACTIVE
        self.sm.transition_to(ApplicationState.ACTIVE, reason="Wake detected")
        self.assertEqual(self.sm.current_state, ApplicationState.ACTIVE)

        # ACTIVE -> PROCESSING
        self.sm.transition_to(ApplicationState.PROCESSING, reason="Planning task")
        self.assertEqual(self.sm.current_state, ApplicationState.PROCESSING)

        # PROCESSING -> EXECUTING
        self.sm.transition_to(ApplicationState.EXECUTING, reason="Running step 1")
        self.assertEqual(self.sm.current_state, ApplicationState.EXECUTING)

        # EXECUTING -> PAUSED
        self.sm.transition_to(ApplicationState.PAUSED, reason="Human priority lock")
        self.assertEqual(self.sm.current_state, ApplicationState.PAUSED)

        # PAUSED -> EXECUTING
        self.sm.transition_to(ApplicationState.EXECUTING, reason="User idle, resuming")
        self.assertEqual(self.sm.current_state, ApplicationState.EXECUTING)

        # EXECUTING -> IDLE
        self.sm.transition_to(ApplicationState.IDLE, reason="Task completed")
        self.assertEqual(self.sm.current_state, ApplicationState.IDLE)

        # IDLE -> STOPPING -> STOPPED
        self.sm.transition_to(ApplicationState.STOPPING, reason="SIGINT")
        self.assertEqual(self.sm.current_state, ApplicationState.STOPPING)

        self.sm.transition_to(ApplicationState.STOPPED, reason="Clean exit")
        self.assertEqual(self.sm.current_state, ApplicationState.STOPPED)

    def test_invalid_transition_rejected(self) -> None:
        # STARTING cannot jump directly to EXECUTING
        with self.assertRaises(StateTransitionError):
            self.sm.transition_to(ApplicationState.EXECUTING)

        # STARTING cannot jump directly to PAUSED
        with self.assertRaises(StateTransitionError):
            self.sm.transition_to(ApplicationState.PAUSED)

        # State should still be STARTING
        self.assertEqual(self.sm.current_state, ApplicationState.STARTING)

    def test_error_state_recovery(self) -> None:
        # STARTING -> ERROR
        self.sm.transition_to(ApplicationState.ERROR, reason="Startup failure")
        self.assertEqual(self.sm.current_state, ApplicationState.ERROR)

        # ERROR can recover to IDLE
        self.sm.transition_to(ApplicationState.IDLE, reason="Recovered")
        self.assertEqual(self.sm.current_state, ApplicationState.IDLE)

    def test_transition_callbacks(self) -> None:
        transitions_recorded = []

        def on_transition(from_s, to_s, reason):
            transitions_recorded.append((from_s, to_s, reason))

        self.sm.add_transition_callback(on_transition)
        self.sm.transition_to(ApplicationState.IDLE, reason="Init")

        self.assertEqual(len(transitions_recorded), 1)
        self.assertEqual(transitions_recorded[0], (ApplicationState.STARTING, ApplicationState.IDLE, "Init"))

        # Test callback removal
        self.sm.remove_transition_callback(on_transition)
        self.sm.transition_to(ApplicationState.ACTIVE, reason="Wake")
        self.assertEqual(len(transitions_recorded), 1)  # No new callback fired


if __name__ == "__main__":
    unittest.main()
