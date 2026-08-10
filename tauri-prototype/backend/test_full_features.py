import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from backend.full_features import FullFeatureService
from backend.server import REPOSITORY_ROOT, _set_target_mode, dispatch


class FakeTracker:
    processing = False

    def range_values(self):
        return None

    def state(self):
        return {"active": False}


class FakeBridge:
    def ensure(self):
        return True, "ok"

    def reset(self):
        return None

    def connect_without_focus(self):
        return True, "ok"


class FullCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = FullFeatureService(REPOSITORY_ROOT)

    def tearDown(self):
        _set_target_mode("hwp")

    def test_builtin_catalogs_are_complete(self):
        styles = [item for item in self.features.catalog("style") if not item["user_item"]]
        forms = [item for item in self.features.catalog("form") if not item["user_item"]]
        pages = [item for item in self.features.catalog("page") if not item["user_item"]]
        self.assertEqual(len(styles), 7)
        self.assertEqual(len(forms), 4)
        self.assertEqual(len(pages), 1)
        self.assertTrue(all(item["preview"].startswith("data:image/") for item in styles))
        self.assertTrue(all(item["preview"].startswith("data:image/") for item in forms))

        form_records = [
            item for item in self.features.content_records("form") if not item["user_item"]
        ]
        self.assertTrue(
            all(
                Path(item["thumb_path"]).parent.name == "builtin_form_previews"
                for item in form_records
            )
        )
        for item in form_records:
            with Image.open(item["thumb_path"]) as preview:
                self.assertGreater(preview.height, preview.width)

    def test_current_table_catalog_contains_all_20_actions(self):
        items = self.features.table_catalog()
        action_ids = {item["action_id"] for item in items}
        self.assertEqual(len(items), 20)
        self.assertIn("내부세로선없애기", action_ids)
        self.assertIn("내부가로선없애기", action_ids)
        self.assertIn("행높이같게", action_ids)
        self.assertIn("열너비같게", action_ids)
        self.assertIn("한줄로입력설정", action_ids)
        self.assertIn("제목셀해제", action_ids)
        self.assertIn("배경색없애기", action_ids)

    def test_character_and_picture_symbol_catalogs_load(self):
        character_groups = self.features.character_catalog()
        picture_groups = self.features.picture_symbol_catalog()
        self.assertGreaterEqual(len(character_groups), 9)
        self.assertTrue(any(group["title"] == "괄호" for group in character_groups))
        self.assertGreaterEqual(len(picture_groups), 1)
        self.assertTrue(any(group["items"] for group in picture_groups))

    def test_legacy_toggle_hotkey_moves_out_of_feature_hotkeys(self):
        legacy = {
            "global_hotkeys_enabled": False,
            "global_hotkeys": {
                "app.toggle_window": "Ctrl+Shift+J",
                "feature:auto_format_report": "Ctrl+Alt+A",
            },
        }
        with (
            patch("backend.full_features.app_config.load_settings", return_value=legacy),
            patch("backend.full_features.app_config.save_settings") as save_settings,
        ):
            settings = self.features.load_settings()

        self.assertEqual(settings["toggle_hotkey"], "Ctrl+Shift+J")
        self.assertNotIn("app.toggle_window", settings["global_hotkeys"])
        self.assertEqual(
            settings["global_hotkeys"]["feature:auto_format_report"],
            "Ctrl+Alt+A",
        )
        save_settings.assert_called_once()

    def test_update_check_is_ready_without_an_assigned_identifier(self):
        result = self.features.update_status()
        self.assertFalse(result["configured"])
        self.assertEqual(result["current"], "v4.0")
        self.assertIn("고유번호", result["message"])

    def test_dispatch_exposes_form_page_and_table_catalogs(self):
        bridge = FakeBridge()
        tracker = FakeTracker()
        for command, key in (
            ("form_catalog", "items"),
            ("page_catalog", "items"),
            ("table_catalog", "items"),
            ("character_catalog", "groups"),
            ("picture_symbol_catalog", "groups"),
        ):
            result = dispatch(command, {}, bridge, tracker)
            self.assertTrue(result[0], command)
            self.assertTrue(result[2][key], command)


if __name__ == "__main__":
    unittest.main()
