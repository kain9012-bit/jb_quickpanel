import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SplashConfigurationTests(unittest.TestCase):
    def test_splash_asset_has_expected_dimensions(self):
        splash_path = ROOT / "assets" / "splash" / "app_splash.png"
        data = splash_path.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (480, 270))

    def test_v34_spec_uses_pyinstaller_splash(self):
        spec = (ROOT / "전북교육_한글_서식도우미_v3.4.spec").read_text(encoding="utf-8")
        self.assertIn("splash = Splash(", spec)
        self.assertIn("'assets/splash/app_splash_v3.4.png'", spec)
        self.assertIn("splash.binaries", spec)

    def test_app_closes_splash_for_ready_duplicate_and_error_paths(self):
        source = (
            ROOT / "src" / "jb_quickpanel" / "ui" / "app_window.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def close_splash():", source)
        self.assertIn("self.after(80, close_splash)", source)
        self.assertGreaterEqual(source.count("close_splash()"), 3)


if __name__ == "__main__":
    unittest.main()
