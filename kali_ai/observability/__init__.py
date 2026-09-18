"""
Observability package for Kali AI: structured logging, log redaction, and metrics foundation.
"""

from kali_ai.observability.logging import setup_logging, redact_sensitive_text, get_logger

__all__ = ["setup_logging", "redact_sensitive_text", "get_logger"]
