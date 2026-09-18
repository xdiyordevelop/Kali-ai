"""
Custom exception classes for Kali AI.
"""


class KaliAIError(Exception):
    """Base exception class for all Kali AI errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class StateTransitionError(KaliAIError):
    """Raised when an invalid state transition is requested."""

    def __init__(self, from_state: str, to_state: str, reason: str = "") -> None:
        msg = f"Cannot transition from {from_state} to {to_state}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, {"from_state": from_state, "to_state": to_state, "reason": reason})
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason


class ConfigurationError(KaliAIError):
    """Raised when configuration validation or persistence fails."""
    pass


class DatabaseError(KaliAIError):
    """Raised when a database operation fails."""
    pass


class SecurityPolicyError(KaliAIError):
    """Raised when a security policy violation or invalid configuration occurs."""
    pass


class EventBusError(KaliAIError):
    """Raised when event publishing or handling encounters an unrecoverable error."""
    pass
