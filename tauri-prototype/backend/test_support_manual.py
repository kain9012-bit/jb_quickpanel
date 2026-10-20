import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.full_features import FullFeatureService, default_windows_browser
from backend.server import FEATURES, _set_target_mode, dispatch


class SupportManualTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / "설치 자료 #100%"
        self.manual = self.root / "manual" / "index.html"
        self.changelog = self.root / "support" / "CHANGELOG.md"
        self.manual.parent.mkdir(parents=True)
        self.changelog.parent.mkdir(parents=True)
        self.manual.write_text("<!doctype html><html>Manual</html>", encoding="utf-8")
        self.changelog.write_text("# Changes\n", encoding="utf-8")
        self.service = FullFeatureService(Path(self.folder.name) / "extracted-temp")
        environment = patch.dict(os.environ, {"JB_APP_RESOURCE_DIR": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        self.browser_path = str(Path(self.folder.name) / "browser with spaces" / "browser.exe")
        association = patch("backend.full_features.default_windows_browser", return_value=self.browser_path)
        association.start()
        self.addCleanup(association.stop)
        launcher = patch("backend.full_features.subprocess.Popen")
        self.launcher = launcher.start()
        self.addCleanup(launcher.stop)

    def assert_browser_opened(self, url):
        self.launcher.assert_called_once_with(
            [self.browser_path, url], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def test_manual_uses_install_resources_and_default_browser(self):
        with patch("webbrowser.open") as browser:
            url = self.service.open_manual()
        self.assertEqual(url, self.manual.resolve().as_uri())
        self.assert_browser_opened(url)
        browser.assert_not_called()

    def test_manual_can_open_a_section(self):
        url = self.service.open_manual("auto")
        self.assertEqual(url, self.manual.resolve().as_uri() + "#auto")
        self.assert_browser_opened(url)

    def test_tauri_extended_install_path_becomes_a_normal_file_url(self):
        with patch.dict(os.environ, {"JB_APP_RESOURCE_DIR": "\\\\?\\" + str(self.root)}):
            url = self.service.open_manual("auto")
        expected = self.manual.resolve().as_uri() + "#auto"
        self.assertEqual(url, expected)
        self.assertTrue(url.startswith("file:///"))
        self.assertNotIn("%3F", url)
        self.assert_browser_opened(expected)

    def test_installed_executable_location_is_a_fallback(self):
        with patch.dict(os.environ, {
            "JB_APP_RESOURCE_DIR": "", "JB_TAURI_EXE": str(self.root / "helper.exe"), "JB_TAURI_DEV": "0",
        }):
            self.service.open_manual()
        self.assert_browser_opened(self.manual.resolve().as_uri())

    def test_readme_entry_redirects_to_manual(self):
        self.service.open_support_path("readme")
        self.assert_browser_opened(self.manual.resolve().as_uri())

    def test_changelog_uses_installed_file_not_backend_temp(self):
        with patch("backend.full_features.app_config.open_path") as opener:
            path = self.service.open_support_path("changelog")
        self.assertEqual(Path(path), self.changelog)
        opener.assert_called_once_with(self.changelog)

    def test_invalid_section_does_not_open_browser(self):
        with patch("webbrowser.open") as browser:
            for section in ("../../README.md", "https://example.com", "auto#other"):
                with self.assertRaisesRegex(RuntimeError, "매뉴얼 항목"):
                    self.service.open_manual(section)
        browser.assert_not_called()
        self.launcher.assert_not_called()

    def test_missing_resource_is_reported_without_opening_it(self):
        self.manual.unlink()
        self.changelog.unlink()
        with patch("webbrowser.open") as browser, patch("backend.full_features.app_config.open_path") as opener:
            with self.assertRaisesRegex(RuntimeError, "매뉴얼 파일"):
                self.service.open_manual()
            with self.assertRaisesRegex(RuntimeError, "변경 기록 파일"):
                self.service.open_support_path("changelog")
        browser.assert_not_called()
        opener.assert_not_called()
        self.launcher.assert_not_called()

    def test_browser_failure_is_reported(self):
        self.launcher.side_effect = OSError("launch failed")
        with patch("webbrowser.open") as browser:
            with self.assertRaisesRegex(RuntimeError, "기본 웹브라우저"):
                self.service.open_manual()
        browser.assert_not_called()

    def test_unavailable_default_browser_does_not_fall_back_to_edge(self):
        with patch("backend.full_features.default_windows_browser", side_effect=RuntimeError("기본 웹브라우저 오류")), patch("webbrowser.open") as browser:
            with self.assertRaisesRegex(RuntimeError, "기본 웹브라우저"):
                self.service.open_manual()
        self.launcher.assert_not_called()
        browser.assert_not_called()

    def test_browser_choice_is_resolved_again_on_every_click(self):
        with patch("backend.full_features.default_windows_browser", side_effect=["chrome.exe", "firefox.exe"]):
            self.service.open_manual()
            self.service.open_manual("auto")
        self.assertEqual(self.launcher.call_args_list[0].args[0], ["chrome.exe", self.manual.resolve().as_uri()])
        self.assertEqual(self.launcher.call_args_list[1].args[0], ["firefox.exe", self.manual.resolve().as_uri() + "#auto"])

    def test_windows_association_uses_current_user_https_browser(self):
        import ctypes

        executable = self.root / "Chrome with spaces" / "chrome.exe"
        executable.parent.mkdir()
        executable.touch()

        def resolve(flags, kind, protocol, verb, buffer, _length):
            self.assertEqual((flags, kind, protocol, verb), (0x1000, 2, "https", "open"))
            buffer.value = str(executable)
            return 0

        query = Mock(side_effect=resolve)
        with patch.object(ctypes.windll.shlwapi, "AssocQueryStringW", query):
            self.assertEqual(default_windows_browser(), str(executable))

    def test_invalid_windows_association_is_reported(self):
        import ctypes

        with patch.object(ctypes.windll.shlwapi, "AssocQueryStringW", return_value=1):
            with self.assertRaisesRegex(RuntimeError, "기본 웹브라우저"):
                default_windows_browser()

    def test_dispatch_does_not_require_a_hwp_connection(self):
        _set_target_mode("hwp")
        bridge, tracker = Mock(), Mock()
        with patch.object(FEATURES, "open_manual", return_value="file:///manual/index.html#auto") as opener:
            ok, _, data = dispatch("open_manual", {"section": "auto"}, bridge, tracker)
        self.assertTrue(ok)
        self.assertEqual(data["url"], "file:///manual/index.html#auto")
        opener.assert_called_once_with("auto")
        self.assertEqual(bridge.mock_calls, [])
        self.assertEqual(tracker.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
