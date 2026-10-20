import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.full_features import FullFeatureService
from backend.server import REPOSITORY_ROOT, dispatch
from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.services.user_backup import create_user_backup, restore_user_backup


class CardFavoriteTests(unittest.TestCase):
    def test_favorites_keep_registration_order_across_restart_and_other_setting_changes(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            service.toggle_card_favorite("style", "builtin:first")
            service.toggle_card_favorite("style", "user:second")
            service.toggle_card_favorite("symbol", "builtin:first")
            service.save_settings({"always_on_top": False})
            restarted = FullFeatureService(REPOSITORY_ROOT)
            favorites = restarted.load_settings()["card_favorites"]
            self.assertEqual(favorites["style"], ["builtin:first", "user:second"])
            self.assertEqual(favorites["symbol"], ["builtin:first"])
            restarted.toggle_card_favorite("style", "builtin:first")
            reloaded = app_config.load_settings()
            self.assertEqual(reloaded["card_favorites"]["style"], ["user:second"])
            self.assertEqual(reloaded["card_favorites"]["symbol"], ["builtin:first"])
            self.assertFalse(reloaded["always_on_top"])
            restarted.toggle_card_favorite("style", "builtin:first")
            self.assertEqual(app_config.load_settings()["card_favorites"]["style"], ["user:second", "builtin:first"])

    def test_favorites_survive_transfer_backup_restore(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            for kind in app_config.CARD_FAVORITE_KINDS:
                service.toggle_card_favorite(kind, "user:example")
            expected = service.load_settings()["card_favorites"]
            destination = Path(folder) / "new_computer"
            backup = Path(folder) / "transfer.jbhbackup"
            create_user_backup(backup, app_root=app_config.app_data_dir())
            restore_user_backup(backup, app_root=destination)
            with patch("src.jb_quickpanel.services.app_config.app_data_dir", return_value=destination):
                self.assertEqual(service.load_settings()["card_favorites"], expected)

    def test_legacy_settings_and_malformed_favorites_are_normalized(self):
        self.assertEqual(app_config._merged_settings({"version": 10})["card_favorites"],
                         {kind: [] for kind in app_config.CARD_FAVORITE_KINDS})
        favorites = app_config._merged_settings({"card_favorites": {
            "style": ["a", "a", None, {}, "", "b"], "form": "invalid", "symbol": ["user:1"],
        }})["card_favorites"]
        self.assertEqual(favorites, {"style": ["a", "b"], "form": [], "kedufine_form": [], "symbol": ["user:1"], "page": []})

    def test_previous_newest_first_order_is_migrated_only_once(self):
        old = {"version": 11, "card_favorites": {"style": ["c", "b", "a"], "symbol": ["second", "first"]}}
        migrated = app_config._merged_settings(old)
        self.assertEqual(migrated["card_favorites"]["style"], ["a", "b", "c"])
        self.assertEqual(migrated["card_favorites"]["symbol"], ["first", "second"])
        self.assertEqual(migrated["card_favorites"]["page"], [])
        self.assertEqual(app_config._merged_settings(migrated), migrated)
        self.assertEqual(old["card_favorites"]["style"], ["c", "b", "a"])

    def test_toggle_command_does_not_use_hwp_bridge(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            ok, _, data = dispatch("card_favorite_toggle", {"kind": "form", "key": "user:1"}, None, None)
            self.assertTrue(ok)
            self.assertEqual(data["card_favorites"]["form"], ["user:1"])


if __name__ == "__main__":
    unittest.main()
