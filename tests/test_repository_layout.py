import unittest
from pathlib import Path

from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.ui import app_window


ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_public_entry_point_uses_current_package(self):
        entry = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("src.jb_quickpanel.ui.app_window", entry)
        self.assertEqual(app_window.APP_VERSION, "v3.4")

    def test_requirements_document_runtime_and_build_dependencies(self):
        runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        build = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
        self.assertIn("Pillow", runtime)
        self.assertIn("pywin32", runtime)
        self.assertIn("-r requirements.txt", build)
        self.assertIn("PyInstaller", build)

    def test_gitignore_keeps_legacy_and_generated_files_out_of_main(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/app(*).py", ignore)
        self.assertIn("/src/jb_quickpanel_v*/", ignore)
        self.assertIn("/vendor/", ignore)
        self.assertIn("/build_packages/", ignore)
        self.assertIn("!/전북교육_한글_서식도우미_v3.4.spec", ignore)

    def test_default_settings_include_empty_enabled_global_hotkeys(self):
        self.assertTrue(app_config.DEFAULT_SETTINGS["global_hotkeys_enabled"])
        self.assertEqual(app_config.DEFAULT_SETTINGS["global_hotkeys"], {})


if __name__ == "__main__":
    unittest.main()