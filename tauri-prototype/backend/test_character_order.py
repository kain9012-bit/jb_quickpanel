import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.full_features import FullFeatureService
from backend.server import REPOSITORY_ROOT, dispatch
from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.services.user_backup import create_user_backup, restore_user_backup
from src.jb_quickpanel.services.user_content import UserContentStore


class CharacterGroupOrderTests(unittest.TestCase):
    def test_new_group_is_first_and_preserves_existing_custom_order(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            initial = [group["id"] for group in service.character_catalog()]
            previous = list(reversed(initial))
            service.save_settings({"character_group_order": previous})
            first = service.save_symbol_group("", "첫 문자표", "★\n◇")
            second = service.save_symbol_group("", "새 문자표", "□")
            self.assertEqual(service.load_settings()["character_group_order"], [second["id"], first["id"], *previous])
            self.assertEqual(FullFeatureService(REPOSITORY_ROOT).load_settings()["character_group_order"],
                             [second["id"], first["id"], *previous])

    def test_new_group_materializes_unsaved_fallback_order(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            ids = [group["id"] for group in service.character_catalog()]
            service.save_settings({"character_group_order": ["removed-group", ids[-1]]})
            item = service.save_symbol_group("", "맨 위", "※")
            self.assertEqual(service.load_settings()["character_group_order"],
                             [item["id"], ids[-1], *ids[:-1]])

    def test_editing_group_does_not_move_it_to_first(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            item = service.save_symbol_group("", "기존", "★")
            order = list(reversed(service.load_settings()["character_group_order"]))
            service.save_settings({"character_group_order": order})
            service.save_symbol_group(item["id"], "수정", "◇")
            self.assertEqual(service.load_settings()["character_group_order"], order)

    def test_order_write_failure_rolls_back_only_new_group(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            existing = service.save_symbol_group("", "보존", "★")
            order = service.load_settings()["character_group_order"]
            with patch.object(service, "save_settings", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    service.save_symbol_group("", "저장 실패", "◇")
            self.assertEqual(service.load_settings()["character_group_order"], order)
            self.assertEqual([item["id"] for item in UserContentStore().list_symbol_groups()], [existing["id"]])

    def test_registration_returns_order_without_using_document_bridge(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            bridge, tracker = Mock(), Mock()
            ok, _, data = dispatch("user_save_symbol_group", {"title": "추가", "chars": "★"}, bridge, tracker)
            self.assertTrue(ok)
            self.assertEqual(data["character_group_order"][0], data["item"]["id"])
            self.assertEqual(bridge.mock_calls, [])
            self.assertEqual(tracker.mock_calls, [])

    def test_existing_and_malformed_settings_have_safe_unique_order(self):
        self.assertEqual(app_config._merged_settings({})["character_group_order"], [])
        for raw, expected in ((None, []), ("builtin:0", []),
                              (["builtin:0", "", None, {}, "builtin:0", "user:1"], ["builtin:0", "user:1"])):
            self.assertEqual(app_config._merged_settings({"character_group_order": raw})["character_group_order"], expected)

    def test_order_survives_restart_and_unrelated_settings_save(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            expected = ["builtin:square:numbers", "user:example", "builtin:0"]
            self.assertEqual(service.save_settings({"character_group_order": expected})["character_group_order"], expected)
            restarted = FullFeatureService(REPOSITORY_ROOT)
            restarted.save_settings({"always_on_top": False})
            self.assertEqual(restarted.load_settings()["character_group_order"], expected)
            self.assertFalse(restarted.load_settings()["always_on_top"])
            self.assertEqual(restarted.reset_settings()["character_group_order"], [])

    def test_normalized_save_response_matches_disk(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            response = service.save_settings({"character_group_order": ["builtin:0", "builtin:0", None, "user:1"]})
            self.assertEqual(response["character_group_order"], ["builtin:0", "user:1"])
            self.assertEqual(response["character_group_order"], app_config.load_settings()["character_group_order"])

    def test_backup_restore_preserves_order_on_another_computer(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            expected = ["builtin:2", "builtin:0", "user:example"]
            service.save_settings({"character_group_order": expected})
            backup = Path(folder) / "transfer.jbhbackup"
            create_user_backup(backup, app_root=app_config.app_data_dir())
            destination = Path(folder) / "new_computer"
            restore_user_backup(backup, app_root=destination)
            with patch.object(app_config, "app_data_dir", return_value=destination):
                self.assertEqual(service.load_settings()["character_group_order"], expected)

    def test_order_save_does_not_use_document_bridge_or_selection_tracker(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            bridge, tracker = Mock(), Mock()
            ok, _, data = dispatch("settings_save", {"changes": {"character_group_order": ["builtin:1", "builtin:0"]}}, bridge, tracker)
            self.assertTrue(ok)
            self.assertEqual(data["settings"]["character_group_order"], ["builtin:1", "builtin:0"])
            self.assertEqual(bridge.mock_calls, [])
            self.assertEqual(tracker.mock_calls, [])

    def test_write_failure_preserves_previous_order(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            service = FullFeatureService(REPOSITORY_ROOT)
            service.save_settings({"character_group_order": ["builtin:0", "builtin:1"]})
            with patch.object(app_config.os, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    service.save_settings({"character_group_order": ["builtin:1", "builtin:0"]})
            self.assertEqual(service.load_settings()["character_group_order"], ["builtin:0", "builtin:1"])


if __name__ == "__main__":
    unittest.main()
