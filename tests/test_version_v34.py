import re
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VersionV34Tests(unittest.TestCase):
    def test_v33_and_v34_entry_points_are_separated(self):
        v33 = (ROOT / "app(v3.3).py").read_text(encoding="utf-8")
        v34 = (ROOT / "app(v3.4).py").read_text(encoding="utf-8")
        self.assertIn("src.jb_quickpanel_v33.ui.app_window", v33)
        self.assertIn("src.jb_quickpanel.ui.app_window", v34)

    def test_current_and_preserved_versions_are_correct(self):
        current = (ROOT / "src" / "jb_quickpanel" / "ui" / "app_window.py").read_text(encoding="utf-8")
        preserved = (ROOT / "src" / "jb_quickpanel_v33" / "ui" / "app_window.py").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "v3.4"', current)
        self.assertIn('APP_VERSION = "v3.3"', preserved)
        self.assertNotRegex(preserved, r"from src\.jb_quickpanel\.(?!_v33)")

    def test_v34_spec_and_splash_match_version(self):
        spec = (ROOT / "전북교육_한글_서식도우미_v3.4.spec").read_text(encoding="utf-8")
        self.assertIn("['app(v3.4).py']", spec)
        self.assertIn("name='전북교육_한글_서식도우미_v3.4'", spec)
        self.assertIn("assets/splash/app_splash_v3.4.png", spec)
        data = (ROOT / "assets" / "splash" / "app_splash_v3.4.png").read_bytes()
        self.assertEqual(struct.unpack(">II", data[16:24]), (480, 270))

    def test_build_defaults_to_v34_and_preserves_v33_mapping(self):
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$Version = "v3.4"', build)
        self.assertRegex(build, re.compile(r'v3\.3"\) \{\s+Join-Path \$Root "src\\jb_quickpanel_v33"'))

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
