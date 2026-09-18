"""
Default paths, environment variables, and constants for Kali AI.
"""

from __future__ import annotations

import os
from pathlib import Path

# Base directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = Path(os.environ.get("KALI_AI_DATA_DIR", PROJECT_ROOT / "data"))
DEFAULT_LOG_DIR = Path(os.environ.get("KALI_AI_LOG_DIR", PROJECT_ROOT / "logs"))
DEFAULT_CONFIG_DB_PATH = DEFAULT_DATA_DIR / "config.db"
DEFAULT_ARTIFACTS_DIR = DEFAULT_DATA_DIR / "artifacts"

# Environment variables
ENV_LOG_LEVEL = "KALI_AI_LOG_LEVEL"
ENV_CONFIG_PATH = "KALI_AI_CONFIG_PATH"
