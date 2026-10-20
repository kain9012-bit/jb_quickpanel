import os
import unittest
import tempfile
from unittest.mock import Mock, patch
from pathlib import Path

from PIL import Image

from backend.full_features import APP_VERSION, FullFeatureService
from backend.server import REPOSITORY_ROOT, _set_target_mode, dispatch
from src.jb_quickpanel.services.user_content import UserContentStore


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
        self.assertEqual(len(pages), 2)
        self.assertEqual([page["orientation"] for page in pages], ["portrait", "landscape"])
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

    def test_style_block_is_saved_as_hwp(self):
        with tempfile.TemporaryDirectory() as folder:
            store = UserContentStore(Path(folder) / "data")
            bridge = Mock()

            def save_block(path, format_name):
                self.assertEqual(format_name, "HWP")
                self.assertEqual(Path(path).suffix, ".hwp")
                Path(path).write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1sample")
                return True, "ok"

            bridge.save_selected_block.side_effect = save_block
            with patch("backend.full_features.UserContentStore", return_value=store), patch.object(
                self.features, "_create_preview",
                return_value=(store, None, "", store.pending_preview_path()),
            ):
                self.features.add_user_block("style", "내 서식", bridge)
            self.assertEqual(Path(store.list_items("style")[0]["file"]).suffix, ".hwp")

    def test_start_menu_shortcut_uses_fixed_unversioned_name(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder}
        ):
            path = self.features._start_menu_path()

        self.assertEqual(path.name, "JBEdu FORM (JB에듀 폼).lnk")
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

    def test_auto_format_settings_are_normalized_and_saved(self):
        legacy = {
            "auto_format": {
                "document_title_template": "user:custom-title",
                "roles": {
                    "body": {
                        "font": "굴림체",
                        "size": 999,
                        "bold": True,
                        "marker": "unknown",
                    }
                },
            }
        }
        with (
            patch("backend.full_features.app_config.load_settings", return_value=legacy),
            patch("backend.full_features.app_config.save_settings") as save_settings,
        ):
            settings = self.features.load_settings()

        auto_format = settings["auto_format"]
        self.assertEqual(auto_format["document_title_template"], "auto-title-builtin:document_title")
        self.assertEqual(auto_format["title_template"], "auto-title-builtin:title")
        self.assertEqual(auto_format["roles"]["body"]["font"], "굴림체")
        self.assertEqual(auto_format["roles"]["body"]["size"], 72)
        self.assertTrue(auto_format["roles"]["body"]["bold"])
        self.assertEqual(auto_format["roles"]["body"]["marker"], "dash")
        self.assertIn("reference", auto_format["roles"])
        self.assertEqual(auto_format["roles"]["table"]["font"], "굴림체")
        self.assertEqual(settings["active_auto_format_profile"], "default")
        self.assertEqual(len(settings["auto_format_profiles"]), 1)
        self.assertEqual(settings["auto_format_profiles"][0]["settings"], auto_format)
        save_settings.assert_called_once()

    def test_auto_format_profiles_cannot_exceed_ten(self):
        profiles = [
            {"id": f"profile-{index}", "name": f"설정 {index}", "settings": {}}
            for index in range(11)
        ]
        with patch("backend.full_features.app_config.save_settings") as save_settings:
            with self.assertRaisesRegex(ValueError, "최대 10개"):
                self.features.save_settings({"auto_format_profiles": profiles})
        save_settings.assert_not_called()

    def test_existing_extra_profiles_are_not_silently_deleted_on_load(self):
        profiles = [
            {"id": f"profile-{index}", "name": f"설정 {index}", "settings": {}}
            for index in range(11)
        ]
        with (
            patch("backend.full_features.app_config.load_settings", return_value={
                "auto_format_profiles": profiles,
                "active_auto_format_profile": "profile-10",
            }),
            patch("backend.full_features.app_config.save_settings"),
        ):
            settings = self.features.load_settings()
        self.assertEqual(len(settings["auto_format_profiles"]), 11)
        self.assertEqual(settings["active_auto_format_profile"], "profile-10")
    def test_update_check_is_ready_without_an_assigned_identifier(self):
        result = self.features.update_status()
        self.assertFalse(result["configured"])
        self.assertEqual(result["current"], APP_VERSION)
        self.assertIn("고유번호", result["message"])

    def test_dispatch_exposes_form_page_and_table_catalogs(self):
        bridge = FakeBridge()
        tracker = FakeTracker()
        for command, key in (
            ("form_catalog", "items"),
            ("page_catalog", "items"),
            ("table_catalog", "items"),
            ("font_catalog", "fonts"),
            ("character_catalog", "groups"),
            ("picture_symbol_catalog", "groups"),
        ):
            result = dispatch(command, {}, bridge, tracker)
            self.assertTrue(result[0], command)
            self.assertTrue(result[2][key], command)


    def test_open_form_working_copy_preserves_registered_master(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "master.hwp"
            source.write_bytes(b"registered form")
            opened = []
            with (
                patch("backend.full_features.app_config.app_data_dir", return_value=root / "appdata"),
                patch("backend.full_features.app_config.open_path", side_effect=lambda path: opened.append(Path(path))),
            ):
                working_path = Path(
                    self.features.open_form_working_copy(
                        {"file_path": str(source), "title": "계획서:양식"}
                    )
                )

            self.assertTrue(working_path.is_file())
            self.assertEqual(working_path.read_bytes(), source.read_bytes())
            self.assertNotEqual(working_path, source)
            self.assertNotIn(":", working_path.name)
            self.assertEqual(opened, [working_path])


if __name__ == "__main__":
    unittest.main()
