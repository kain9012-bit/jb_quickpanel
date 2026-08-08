import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VersionV34Tests(unittest.TestCase):
    def test_entry_point_and_source_version_are_current(self):
        entry = (ROOT / "app.py").read_text(encoding="utf-8")
        source = (ROOT / "src" / "jb_quickpanel" / "ui" / "app_window.py").read_text(encoding="utf-8")
        self.assertIn("src.jb_quickpanel.ui.app_window", entry)
        self.assertIn('APP_VERSION = "v3.4"', source)

    def test_v34_spec_is_portable_and_uses_versioned_assets(self):
        spec = (ROOT / "전북교육_한글_서식도우미_v3.4.spec").read_text(encoding="utf-8")
        self.assertIn("['app.py']", spec)
        self.assertIn("pathex=['.']", spec)
        self.assertNotIn("C:\\work", spec)
        self.assertNotIn("vendor\\pywin32", spec)
        self.assertIn("name='전북교육_한글_서식도우미_v3.4'", spec)
        self.assertIn("assets/splash/app_splash_v3.4.png", spec)
        data = (ROOT / "assets" / "splash" / "app_splash_v3.4.png").read_bytes()
        self.assertEqual(struct.unpack(">II", data[16:24]), (480, 270))

    def test_build_defaults_to_v34_without_machine_specific_paths(self):
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$Version = "v3.4"', build)
        self.assertIn('Join-Path $Root ".venv\\Scripts\\python.exe"', build)
        self.assertNotIn("C:\\Users\\kain9", build)
        self.assertNotIn("C:\\work", build)
        self.assertNotIn("jb_quickpanel_v33", build)
        self.assertIn("--workpath $WorkDir --distpath $DistDir", build)

    def test_user_character_groups_are_composed_before_builtins(self):
        source = (ROOT / "src" / "jb_quickpanel" / "ui" / "app_window.py").read_text(encoding="utf-8")
        custom = source.index("self.user_content_store.list_symbol_groups()")
        builtins = source.index("groups.extend(self.symbols_text.items())")
        self.assertLess(custom, builtins)

    def test_only_user_forms_use_zoomed_card_preview(self):
        source = (ROOT / "src" / "jb_quickpanel" / "ui" / "app_window.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("preview_zoom=2.5"), 2)
        self.assertIn("zoom=preview_zoom if is_user_item else 1.0", source)
        self.assertIn("anchor_y=preview_anchor_y if is_user_item else 0.5", source)


if __name__ == "__main__":
    unittest.main()
