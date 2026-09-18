"""
Repositories for persisting configuration and security policies in SQLite.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from kali_ai.storage.database import DatabaseManager


class ConfigRepository:
    """
    CRUD repository for application configuration key-value storage in system_config.
    Supports typed value serialization (str, int, float, bool, json/dict/list).
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by key, converting it to its native type."""
        row = self.db.fetchone(
            "SELECT value, value_type FROM system_config WHERE key = ?;",
            (key,),
        )
        if not row:
            return default

        raw_val = row["value"]
        val_type = row["value_type"]
        return self._deserialize(raw_val, val_type)

    def set(self, key: str, value: Any) -> None:
        """Persist or update a configuration key-value pair."""
        serialized_val, val_type = self._serialize(value)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO system_config (key, value, value_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    value_type = excluded.value_type,
                    updated_at = excluded.updated_at;
                """,
                (key, serialized_val, val_type, now_iso, now_iso),
            )

    def delete(self, key: str) -> bool:
        """Delete a configuration entry by key."""
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM system_config WHERE key = ?;", (key,))
            return cur.rowcount > 0

    def get_all(self) -> dict[str, Any]:
        """Return all persisted configuration as a key-value dictionary."""
        rows = self.db.fetchall("SELECT key, value, value_type FROM system_config;")
        result: dict[str, Any] = {}
        for row in rows:
            result[row["key"]] = self._deserialize(row["value"], row["value_type"])
        return result

    def _serialize(self, value: Any) -> tuple[str, str]:
        """Convert native Python value to (string_representation, type_tag)."""
        if isinstance(value, bool):
            return ("1" if value else "0", "bool")
        elif isinstance(value, int):
            return (str(value), "int")
        elif isinstance(value, float):
            return (str(value), "float")
        elif isinstance(value, str):
            return (value, "str")
        elif isinstance(value, (list, dict)):
            return (json.dumps(value), "json")
        elif value is None:
            return ("", "none")
        else:
            return (json.dumps(value, default=str), "json")

    def _deserialize(self, value_str: str, val_type: str) -> Any:
        """Convert string representation back to native Python object according to type_tag."""
        if val_type == "bool":
            return value_str == "1" or value_str.lower() in ("true", "yes")
        elif val_type == "int":
            return int(value_str)
        elif val_type == "float":
            return float(value_str)
        elif val_type == "str":
            return value_str
        elif val_type == "json":
            try:
                return json.loads(value_str)
            except Exception:
                return value_str
        elif val_type == "none":
            return None
        return value_str


class SecurityPolicyRepository:
    """
    CRUD repository for security policy rules stored in security_policy.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_policy(self, key: str, default: Any = None) -> Any:
        """Retrieve policy value by key."""
        row = self.db.fetchone(
            "SELECT value FROM security_policy WHERE key = ?;",
            (key,),
        )
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def set_policy(self, key: str, value: Any) -> None:
        """Set or update a security policy setting."""
        now_iso = datetime.now(timezone.utc).isoformat()
        val_str = json.dumps(value) if not isinstance(value, str) else value

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO security_policy (key, value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (key, val_str, now_iso, now_iso),
            )

    def get_all_policies(self) -> dict[str, Any]:
        """Return all persisted policies as a dictionary."""
        rows = self.db.fetchall("SELECT key, value FROM security_policy;")
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except Exception:
                result[row["key"]] = row["value"]
        return result
