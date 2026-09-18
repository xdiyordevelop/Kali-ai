"""
Unit tests for Configuration schemas and ConfigManager.
"""

import tempfile
import unittest
from pathlib import Path

from kali_ai.config.manager import ConfigManager
from kali_ai.config.schema import AppConfig, CapabilityRole, SystemConfig
from kali_ai.core.exceptions import ConfigurationError
from kali_ai.security.policy import PermissionTier
from kali_ai.storage.database import DatabaseManager
from kali_ai.storage.repositories import ConfigRepository, SecurityPolicyRepository


class TestConfigManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_config.db"
        self.db = DatabaseManager(self.db_path)
        self.db.open()
        self.config_repo = ConfigRepository(self.db)
        self.policy_repo = SecurityPolicyRepository(self.db)
        self.mgr = ConfigManager(self.config_repo, self.policy_repo)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_default_config_loading(self) -> None:
        cfg = self.mgr.load()
        self.assertEqual(cfg.system.language, "en")
        self.assertEqual(cfg.system.timezone, "UTC")
        self.assertEqual(cfg.security.default_tier, PermissionTier.TIER_1_STANDARD)
        self.assertIn(CapabilityRole.REASONING.value, cfg.models)
        self.assertIn(CapabilityRole.VISION.value, cfg.models)

    def test_update_and_persistence(self) -> None:
        # Load and modify
        self.mgr.update_system(language="es", timezone="America/New_York")

        # Create a fresh manager on the same DB to verify disk persistence
        mgr2 = ConfigManager(self.config_repo, self.policy_repo)
        cfg2 = mgr2.load()
        self.assertEqual(cfg2.system.language, "es")
        self.assertEqual(cfg2.system.timezone, "America/New_York")

    def test_assistant_name_update(self) -> None:
        self.mgr.set_assistant_name("Valkyrie", customized=True)
        self.assertEqual(self.mgr.config.system.assistant_name, "Valkyrie")
        self.assertTrue(self.mgr.config.system.customized)

        # Verify persisted to DB
        self.assertEqual(self.config_repo.get("assistant.name"), "Valkyrie")
        self.assertEqual(self.config_repo.get("assistant.customized"), True)

    def test_validation_rejects_bad_system_config(self) -> None:
        bad_sys = SystemConfig(assistant_name="", log_level="INFO")
        with self.assertRaises(ConfigurationError):
            bad_sys.validate()

        bad_sys2 = SystemConfig(assistant_name="Sandy", log_level="INVALID_LEVEL")
        with self.assertRaises(ConfigurationError):
            bad_sys2.validate()

    def test_reset_to_defaults(self) -> None:
        self.mgr.update_system(language="fr")
        self.assertEqual(self.mgr.config.system.language, "fr")

        self.mgr.reset_to_defaults()
        self.assertEqual(self.mgr.config.system.language, "en")


if __name__ == "__main__":
    unittest.main()
