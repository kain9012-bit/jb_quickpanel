import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.full_features import APP_TITLE, APP_VERSION
from backend.server import REPOSITORY_ROOT
from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.services.user_backup import BACKUP_APP_ID


class BrandingTests(unittest.TestCase):
    def test_product_and_version_match_across_layers(self):
        root = Path(REPOSITORY_ROOT) / "tauri-prototype"
        config = json.loads((root / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(APP_TITLE, "JBEdu FORM (JB에듀 폼)")
        self.assertEqual(config["productName"], APP_TITLE)
        self.assertEqual(package["version"], config["version"])
        self.assertEqual(APP_VERSION, f"v.{config['version']}")
        self.assertEqual(config["app"]["windows"][0]["title"], f"{APP_TITLE} {APP_VERSION}")
        self.assertEqual(config["identifier"], "kr.go.jbe.hwp-helper")

    def test_existing_settings_and_backups_keep_their_identity(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"APPDATA": folder}):
            self.assertEqual(app_config.app_data_dir(), Path(folder) / "JbHwpHelper")
        self.assertEqual(app_config.RUN_VALUE_NAME, "JbHwpHelper")
        self.assertEqual(BACKUP_APP_ID, "JBEDT-0006")
        self.assertEqual(app_config.start_menu_shortcut_name(APP_VERSION), f"{APP_TITLE}.lnk")

    def test_updates_do_not_match_old_trial_release_channel(self):
        config = json.loads((Path(REPOSITORY_ROOT) / "tauri-prototype/update-config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["app"]["app_id"], "JBEDU-FORM")
        self.assertNotEqual(config["app"]["app_id"], BACKUP_APP_ID)

    def test_shortcut_cleanup_recognizes_only_current_and_legacy_app_names(self):
        for name in (
            f"{APP_TITLE}.lnk", f"{APP_TITLE} v.0.0.1.lnk",
            "전북교육 한글 서식도우미.lnk", "전북교육 한글 서식도우미 v.4.2.5.lnk",
            "전북교육 한글 서식도우미 (v3.4).lnk",
        ):
            with self.subTest(name=name):
                self.assertTrue(app_config._is_own_shortcut_name(name))
        for name in ("전북교육 한글 서식도우미 자료.lnk", f"{APP_TITLE} 자료.lnk", "other.lnk"):
            self.assertFalse(app_config._is_own_shortcut_name(name))
