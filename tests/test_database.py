"""
Unit tests for DatabaseManager and SQLite Repositories.
"""

import tempfile
import unittest
from pathlib import Path

from kali_ai.core.exceptions import DatabaseError
from kali_ai.storage.database import CURRENT_SCHEMA_VERSION, DatabaseManager
from kali_ai.storage.repositories import ConfigRepository, SecurityPolicyRepository


class TestDatabaseManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_storage.db"
        self.db = DatabaseManager(self.db_path)
        self.db.open()

    def tearDown(self) -> None:
        if self.db.is_open:
            self.db.close()
        self.temp_dir.cleanup()

    def test_initialization_and_version(self) -> None:
        self.assertTrue(self.db.is_open)
        self.assertEqual(self.db.get_schema_version(), CURRENT_SCHEMA_VERSION)

    def test_reopening_database(self) -> None:
        # Insert data
        repo = ConfigRepository(self.db)
        repo.set("persist_test", "hello_world")

        # Close and reopen
        self.db.close()
        self.assertFalse(self.db.is_open)

        self.db.open()
        self.assertTrue(self.db.is_open)

        repo2 = ConfigRepository(self.db)
        self.assertEqual(repo2.get("persist_test"), "hello_world")

    def test_transaction_commit(self) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO system_config (key, value, value_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                ("t_commit", "committed", "str", "now", "now"),
            )

        row = self.db.fetchone("SELECT value FROM system_config WHERE key = ?;", ("t_commit",))
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "committed")

    def test_transaction_rollback(self) -> None:
        try:
            with self.db.transaction() as cur:
                cur.execute(
                    "INSERT INTO system_config (key, value, value_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?);",
                    ("t_rollback", "rolled", "str", "now", "now"),
                )
                raise RuntimeError("Simulated crash inside transaction")
        except DatabaseError:
            pass

        # Must NOT have been committed
        row = self.db.fetchone("SELECT value FROM system_config WHERE key = ?;", ("t_rollback",))
        self.assertIsNone(row)

    def test_typed_repository_serialization(self) -> None:
        repo = ConfigRepository(self.db)

        # bool
        repo.set("flag_true", True)
        repo.set("flag_false", False)
        self.assertIs(repo.get("flag_true"), True)
        self.assertIs(repo.get("flag_false"), False)

        # int & float
        repo.set("num_int", 42)
        repo.set("num_float", 3.1415)
        self.assertEqual(repo.get("num_int"), 42)
        self.assertAlmostEqual(repo.get("num_float"), 3.1415)

        # list & dict
        repo.set("data_list", ["a", "b", "c"])
        repo.set("data_dict", {"nested": 123})
        self.assertEqual(repo.get("data_list"), ["a", "b", "c"])
        self.assertEqual(repo.get("data_dict"), {"nested": 123})

        # None
        repo.set("empty_val", None)
        self.assertIsNone(repo.get("empty_val"))


if __name__ == "__main__":
    unittest.main()
