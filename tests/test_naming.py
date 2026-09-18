"""
Unit tests for the Assistant NamingEngine.
"""

import tempfile
import unittest
from pathlib import Path

from kali_ai.identity.naming import NamingEngine
from kali_ai.storage.database import DatabaseManager
from kali_ai.storage.repositories import ConfigRepository


class TestNamingEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_naming.db"
        self.db = DatabaseManager(self.db_path)
        self.db.open()
        self.config_repo = ConfigRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_hostname_sanitization(self) -> None:
        self.assertEqual(NamingEngine.sanitize_hostname("sandbox.local"), "sandbox")
        self.assertEqual(NamingEngine.sanitize_hostname("kali-workstation.lan"), "kali workstation")
        self.assertEqual(NamingEngine.sanitize_hostname("MY_LAPTOP.internal"), "my laptop")
        self.assertEqual(NamingEngine.sanitize_hostname(""), "kali")

    def test_deterministic_default_name_generation(self) -> None:
        self.assertEqual(NamingEngine.generate_default_name("sandbox"), "Sandy")
        self.assertEqual(NamingEngine.generate_default_name("kali"), "Kallie")
        self.assertEqual(NamingEngine.generate_default_name("localhost"), "Nova")
        self.assertEqual(NamingEngine.generate_default_name("workstation"), "Dexter")
        self.assertEqual(NamingEngine.generate_default_name("my-pc"), "My")

    def test_first_time_name_resolution(self) -> None:
        name, is_new = NamingEngine.resolve_assistant_name(self.config_repo, current_hostname="sandbox")
        self.assertEqual(name, "Sandy")
        self.assertTrue(is_new)
        self.assertEqual(self.config_repo.get("assistant.name"), "Sandy")
        self.assertEqual(self.config_repo.get("assistant.customized"), False)

        # Second call with same hostname -> not new, returns existing
        name2, is_new2 = NamingEngine.resolve_assistant_name(self.config_repo, current_hostname="sandbox")
        self.assertEqual(name2, "Sandy")
        self.assertFalse(is_new2)

    def test_custom_name_preservation_when_hostname_changes(self) -> None:
        # 1. User sets a custom name
        NamingEngine.set_custom_name(self.config_repo, "Cortana")
        self.assertEqual(self.config_repo.get("assistant.name"), "Cortana")
        self.assertTrue(self.config_repo.get("assistant.customized"))

        # 2. Hostname changes on machine from 'sandbox' to 'kali-server'
        resolved_name, is_new = NamingEngine.resolve_assistant_name(
            self.config_repo, current_hostname="kali-server"
        )

        # 3. MUST preserve 'Cortana'!
        self.assertEqual(resolved_name, "Cortana")
        self.assertFalse(is_new)
        self.assertEqual(self.config_repo.get("assistant.name"), "Cortana")

    def test_custom_name_validation(self) -> None:
        with self.assertRaises(ValueError):
            NamingEngine.set_custom_name(self.config_repo, "")

        with self.assertRaises(ValueError):
            NamingEngine.set_custom_name(self.config_repo, "A")  # Too short

        with self.assertRaises(ValueError):
            NamingEngine.set_custom_name(self.config_repo, "A" * 35)  # Too long

        with self.assertRaises(ValueError):
            NamingEngine.set_custom_name(self.config_repo, "Invalid@Name#$")


if __name__ == "__main__":
    unittest.main()
