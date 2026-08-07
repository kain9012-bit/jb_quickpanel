import re
import unittest
from pathlib import Path

from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.ui import app_window


ROOT = Path(__file__).resolve().parents[1]


class VersionSnapshotTests(unittest.TestCase):
    def test_current_and_preserved_entry_points_use_separate_packages(self):
        current = (ROOT / "app(v3.4).py").read_text(encoding="utf-8")
        preserved_v33 = (ROOT / "app(v3.3).py").read_text(encoding="utf-8")
        preserved_v32 = (ROOT / "app(v3.2).py").read_text(encoding="utf-8")

        self.assertIn("src.jb_quickpanel.ui.app_window", current)
        self.assertIn("src.jb_quickpanel_v33.ui.app_window", preserved_v33)
        self.assertIn("src.jb_quickpanel_v32.ui.app_window", preserved_v32)
        self.assertEqual(app_window.APP_VERSION, "v3.4")

    def test_v32_snapshot_does_not_import_current_package(self):
        current_import = re.compile(r"src\.jb_quickpanel(?!_v32)")
        snapshot = ROOT / "src" / "jb_quickpanel_v32"

        for source_path in snapshot.rglob("*.py"):
            self.assertIsNone(current_import.search(source_path.read_text(encoding="utf-8")), str(source_path))

    def test_default_settings_include_empty_enabled_global_hotkeys(self):
        self.assertTrue(app_config.DEFAULT_SETTINGS["global_hotkeys_enabled"])
        self.assertEqual(app_config.DEFAULT_SETTINGS["global_hotkeys"], {})

    def test_build_script_has_snapshot_mappings_and_v34_default(self):
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")

        self.assertIn('[string]$Version = "v3.4"', build)
        self.assertIn('$Version -eq "v3.3"', build)
        self.assertIn(r"src\jb_quickpanel_v33", build)
        self.assertIn('$Version -eq "v3.2"', build)
        self.assertIn(r"src\jb_quickpanel_v32", build)


if __name__ == "__main__":
    unittest.main()
