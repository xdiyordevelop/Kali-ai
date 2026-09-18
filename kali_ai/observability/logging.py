"""
Structured logging and sensitive data redaction for Kali AI.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Sensitive pattern regexes for automatic redaction
REDACTION_PATTERNS = [
    # OpenAI, Anthropic, Google, generic sk- keys
    (re.compile(r"(sk-[a-zA-Z0-9_-]{16,})", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"(AIzaSy[a-zA-Z0-9_-]{33})", re.IGNORECASE), "[REDACTED_GOOGLE_KEY]"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9._~+/-]{16,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Passwords in query strings or json/yaml: password=xyz or "password": "xyz"
    (
        re.compile(
            r"""(["']?(?:password|token|secret|api_key|access_token|private_key)["']?\s*[:=]\s*["'])([^"'\s]{3,})(["'])""",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]\3",
    ),
    # Private Key blocks
    (
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL),
        "[REDACTED_PRIVATE_KEY]",
    ),
]


def redact_sensitive_text(text: str) -> str:
    """Scan and redact known API keys, tokens, and passwords from string."""
    if not text or not isinstance(text, str):
        return text
    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    """
    Log formatter that intercepts record messages and redacts secrets before emission.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Format message first
        original_msg = record.getMessage()
        record.msg = redact_sensitive_text(original_msg)
        record.args = None  # Clear args since msg is now fully formatted & redacted
        return super().format(record)


class JsonLogFormatter(logging.Formatter):
    """
    JSON log formatter producing machine-parsable, structured logs.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        message = redact_sensitive_text(record.getMessage())

        log_payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "message": message,
            "logger": record.name,
            "line": record.lineno,
            "module": record.module,
        }

        # Optional task and correlation IDs
        if hasattr(record, "task_id") and record.task_id:
            log_payload["task_id"] = record.task_id
        if hasattr(record, "correlation_id") and record.correlation_id:
            log_payload["correlation_id"] = record.correlation_id
        if hasattr(record, "event") and record.event:
            log_payload["event"] = record.event

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, default=str)


def setup_logging(
    log_level: str = "INFO",
    log_dir: Path | str | None = None,
    console_output: bool = True,
    json_format: bool = False,
) -> logging.Logger:
    """
    Configure root application logging for Kali AI.
    Sets up a redacting console handler and a rotating file handler under log_dir.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger("kali_ai")
    root_logger.setLevel(level)
    root_logger.propagate = False

    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    # 1. Console Handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_fmt = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
        console_handler.setFormatter(RedactingFormatter(console_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
        root_logger.addHandler(console_handler)

    # 2. File Handler
    if log_dir is not None:
        target_dir = Path(log_dir)
    else:
        # Default to logs/ in project root
        target_dir = Path(__file__).resolve().parent.parent.parent / "logs"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        log_file = target_dir / "kali_ai.log"

        # Rotating file handler: 10MB per file, keeping 5 backup files
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)

        if json_format:
            file_handler.setFormatter(JsonLogFormatter())
        else:
            file_fmt = "%(asctime)s [%(levelname)s] [%(name)s] [%(module)s:%(lineno)d] %(message)s"
            file_handler.setFormatter(RedactingFormatter(file_fmt, datefmt="%Y-%m-%d %H:%M:%S"))

        root_logger.addHandler(file_handler)
    except Exception as exc:
        root_logger.warning("Could not setup file logging at %s: %s", target_dir, exc)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Helper to retrieve a child logger under the 'kali_ai' namespace."""
    if name.startswith("kali_ai.") or name == "kali_ai":
        return logging.getLogger(name)
    return logging.getLogger(f"kali_ai.{name}")
