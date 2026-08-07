# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.ui.app_window import APP_VERSION, App


class _FakeShortcut:
    def __init__(self, path, fail=False):
        self.path = Path(path)
        self.fail = fail
        self.TargetPath = ""
        self.Arguments = ""
        self.WorkingDirectory = ""
        self.Description = ""
        self.IconLocation = ""

    def Save(self):
        if self.fail:
            raise RuntimeError("save failed")
        self.path.write_text(self.TargetPath, encoding="utf-8")


class _FakeShell:
    def __init__(self, fail=False):
        self.fail = fail
        self.shortcut = None

    def CreateShortcut(self, path):
        self.shortcut = _FakeShortcut(path, fail=self.fail)
        return self.shortcut


class VersionedStartMenuTests(unittest.TestCase):
    def test_shortcut_name_contains_version(self):
        self.assertEqual(
            app_config.start_menu_shortcut_name("v2.6"),
            "전북교육 한글 서식도우미 (v2.6).lnk",
        )

    def test_remove_registration_deletes_only_this_apps_shortcuts(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            menu = app_config.start_menu_shortcut_path("v2.6").parent
            legacy = menu / "전북교육 한글 서식도우미.lnk"
            old = menu / "전북교육 한글 서식도우미 (v2.5).lnk"
            unrelated = menu / "전북교육 한글 서식도우미 자료.lnk"
            for path in (legacy, old, unrelated):
                path.write_text("test", encoding="utf-8")

            app_config.set_start_menu_registered(False, "v2.6")

            self.assertFalse(legacy.exists())
            self.assertFalse(old.exists())
            self.assertTrue(unrelated.exists())

    def test_register_creates_current_version_then_removes_old_shortcuts(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            old = app_config.start_menu_shortcut_path("v2.5")
            old.write_text("old", encoding="utf-8")
            shell = _FakeShell()
            with patch("win32com.client.Dispatch", return_value=shell), patch.object(
                app_config,
                "launch_parts",
                return_value=(r"C:\Apps\helper_v2.6.exe", "", r"C:\Apps"),
            ), patch.object(app_config, "launch_icon_path", return_value=r"C:\Apps\helper_v2.6.exe"):
                app_config.set_start_menu_registered(True, "v2.6")

            current = app_config.start_menu_shortcut_path("v2.6")
            self.assertTrue(current.exists())
            self.assertFalse(old.exists())
            self.assertEqual(shell.shortcut.Description, "전북교육 한글 서식도우미 v2.6")

    def test_failed_registration_keeps_old_shortcut(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            old = app_config.start_menu_shortcut_path("v2.5")
            old.write_text("old", encoding="utf-8")
            shell = _FakeShell(fail=True)
            with patch("win32com.client.Dispatch", return_value=shell), patch.object(
                app_config,
                "launch_parts",
                return_value=(r"C:\Apps\helper_v2.6.exe", "", r"C:\Apps"),
            ), patch.object(app_config, "launch_icon_path", return_value=r"C:\Apps\helper_v2.6.exe"):
                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    app_config.set_start_menu_registered(True, "v2.6")

            self.assertTrue(old.exists())

    def test_manual_unregistered_state_is_not_recreated_after_path_change(self):
        app = object.__new__(App)
        app.app_settings = {
            "start_menu_auto_done": True,
            "start_menu_signature": "old-path|v2.6",
        }
        app._register_start_menu = Mock()
        app._save_app_settings = Mock()
        app._refresh_start_menu_status = Mock()

        with patch.object(app_config, "start_menu_signature", return_value="new-path|v2.6"), patch.object(
            app_config, "is_start_menu_registered", return_value=False
        ), patch.object(app_config, "has_any_start_menu_shortcut", return_value=False), patch.object(
            app_config, "has_obsolete_start_menu_shortcuts", return_value=False
        ):
            App._ensure_first_run_start_menu_registration(app)

        app._register_start_menu.assert_not_called()
        self.assertEqual(app.app_settings["start_menu_signature"], "new-path|v2.6")
        app._save_app_settings.assert_called_once()

    def test_existing_old_shortcut_is_replaced_for_current_version(self):
        app = object.__new__(App)
        app.app_settings = {
            "start_menu_auto_done": True,
            "start_menu_signature": "old-path|v2.5",
        }
        app._register_start_menu = Mock()
        app._save_app_settings = Mock()
        app._refresh_start_menu_status = Mock()

        with patch.object(app_config, "start_menu_signature", return_value="new-path|v2.6"), patch.object(
            app_config, "is_start_menu_registered", return_value=False
        ), patch.object(app_config, "has_any_start_menu_shortcut", return_value=True), patch.object(
            app_config, "has_obsolete_start_menu_shortcuts", return_value=True
        ):
            App._ensure_first_run_start_menu_registration(app)

        app._register_start_menu.assert_called_once_with(show_result=False)


if __name__ == "__main__":
    unittest.main()
