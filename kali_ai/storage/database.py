"""
SQLite database manager with migration tracking and WAL mode.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Sequence

from kali_ai.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Current schema version
CURRENT_SCHEMA_VERSION = 1


class DatabaseManager:
    """
    Manages SQLite database connections, executes migrations, and enforces WAL mode.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Check if database connection is active."""
        with self._lock:
            return self._is_open and self._conn is not None

    def open(self) -> None:
        """Open database connection and run schema migrations if required."""
        with self._lock:
            if self.is_open:
                return

            try:
                # Ensure parent directory exists
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

                self._conn = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    timeout=30.0,
                    isolation_level=None,  # Autocommit mode by default; manual transactions via BEGIN/COMMIT
                )
                self._conn.row_factory = sqlite3.Row

                # Configure optimal SQLite pragmas for performance & data safety
                cursor = self._conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.execute("PRAGMA busy_timeout=10000;")
                cursor.close()

                self._is_open = True
                logger.info("Connected to database: %s", self.db_path)

                # Execute migrations to ensure tables exist
                self._run_migrations()

            except Exception as exc:
                self._is_open = False
                if self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
                raise DatabaseError(f"Failed to open database at {self.db_path}: {exc}") from exc

    def close(self) -> None:
        """Close the database connection gracefully."""
        with self._lock:
            if not self._is_open or self._conn is None:
                return
            try:
                # Optimize database before closing
                try:
                    self._conn.execute("PRAGMA optimize;")
                except Exception:
                    pass
                self._conn.close()
                logger.info("Database closed: %s", self.db_path)
            except Exception as exc:
                logger.warning("Error closing database %s: %s", self.db_path, exc)
            finally:
                self._conn = None
                self._is_open = False

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """
        Context manager for atomic transactions.
        Begins a transaction, yields the cursor, commits on success, rollbacks on error.
        """
        with self._lock:
            if not self.is_open or self._conn is None:
                raise DatabaseError("Database is not open")

            cursor = self._conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE TRANSACTION;")
                yield cursor
                cursor.execute("COMMIT;")
            except Exception as exc:
                try:
                    cursor.execute("ROLLBACK;")
                except Exception as rb_exc:
                    logger.error("Failed to rollback transaction: %s", rb_exc)
                raise DatabaseError(f"Transaction failed and rolled back: {exc}") from exc
            finally:
                cursor.close()

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement outside explicit transactions."""
        with self._lock:
            if not self.is_open or self._conn is None:
                raise DatabaseError("Database is not open")
            try:
                return self._conn.execute(sql, params)
            except Exception as exc:
                raise DatabaseError(f"SQL execution failed: {sql} | Error: {exc}") from exc

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        """Execute multiple parameterized SQL statements."""
        with self._lock:
            if not self.is_open or self._conn is None:
                raise DatabaseError("Database is not open")
            try:
                return self._conn.executemany(sql, seq_of_params)
            except Exception as exc:
                raise DatabaseError(f"SQL executemany failed: {sql} | Error: {exc}") from exc

    def fetchone(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Row | None:
        """Execute query and fetch a single row."""
        cursor = self.execute(sql, params)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def fetchall(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        """Execute query and fetch all matching rows."""
        cursor = self.execute(sql, params)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def get_schema_version(self) -> int:
        """Return the current schema version from metadata table, or 0 if uninitialized."""
        with self._lock:
            if not self.is_open:
                raise DatabaseError("Database is not open")
            try:
                # Check if schema_metadata exists
                check = self.fetchone(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_metadata';"
                )
                if not check:
                    return 0
                row = self.fetchone(
                    "SELECT MAX(schema_version) as current_version FROM schema_metadata;"
                )
                if row and row["current_version"] is not None:
                    return int(row["current_version"])
                return 0
            except Exception as exc:
                logger.error("Failed to read schema version: %s", exc)
                return 0

    def _run_migrations(self) -> None:
        """Apply incremental migrations up to CURRENT_SCHEMA_VERSION."""
        current_version = self.get_schema_version()
        logger.debug("Current database schema version: %d (target: %d)", current_version, CURRENT_SCHEMA_VERSION)

        if current_version < 1:
            self._apply_migration_v1()

    def _apply_migration_v1(self) -> None:
        """Migration v1: Initialize core configuration, security, and schema metadata tables."""
        logger.info("Applying schema migration v1 to %s", self.db_path)
        with self.transaction() as cur:
            # 1. Schema metadata table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    schema_version INTEGER PRIMARY KEY,
                    migration_timestamp TEXT NOT NULL,
                    description TEXT NOT NULL
                );
                """
            )

            # 2. System configuration table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

            # 3. Security policy table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS security_policy (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

            # Record migration
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute(
                """
                INSERT OR REPLACE INTO schema_metadata (schema_version, migration_timestamp, description)
                VALUES (1, ?, 'Initial v1 schema: metadata, system_config, security_policy');
                """,
                (now_iso,),
            )
        logger.info("Migration v1 applied successfully")
