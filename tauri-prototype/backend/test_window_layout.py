import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.server import _set_target_mode, dispatch


class WindowLayoutTargetTests(unittest.TestCase):
    def tearDown(self):
        _set_target_mode("hwp")

    def resolve(self, handles, preferred=None, connected=True):
        bridge = SimpleNamespace(hwp=object(), ensure=Mock(return_value=(connected, "connection result")))
        tracker = Mock()
        with patch("backend.server.inspect_hwp_windows", return_value={"visible_handles": handles}), \
                patch("backend.server.ui_get_last_hwp_window", return_value=preferred), \
                patch("backend.server.win32gui", IsWindowVisible=Mock(return_value=True)), \
                patch("backend.server.win32process", GetWindowThreadProcessId=Mock(return_value=(10, 123))):
            result = dispatch("window_layout_target", {}, bridge, tracker)
        self.assertEqual(tracker.mock_calls, [])
        return result, bridge

    def test_uses_remembered_window_only_when_owned_by_current_com_connection(self):
        result, _ = self.resolve([101, 102], {"hwnd": 102})
        self.assertEqual(result[2], {"hwnd": 102, "pid": 123})

    def test_one_visible_window_is_safe_fallback_without_remembered_handle(self):
        result, _ = self.resolve([101])
        self.assertTrue(result[0])
        self.assertEqual(result[2]["hwnd"], 101)

    def test_mismatched_remembered_window_never_falls_back_to_another_document(self):
        result, _ = self.resolve([101], {"hwnd": 999})
        self.assertFalse(result[0])
        self.assertEqual(result[2], {})

    def test_does_not_guess_between_multiple_documents_or_select_hidden_process(self):
        for handles in ([], [101, 102]):
            result, _ = self.resolve(handles, {"hwnd": 999})
            self.assertFalse(result[0])
            self.assertEqual(result[2], {})

    def test_connection_failure_does_not_inspect_or_move_windows(self):
        result, _ = self.resolve([101], connected=False)
        self.assertEqual(result, (False, "connection result", {}))

    def test_kedufine_mode_rejects_before_any_bridge_or_tracker_access(self):
        _set_target_mode("kedufine")
        bridge, tracker, draft = Mock(), Mock(), Mock()
        with patch("backend.server._WXS_BRIDGE", draft):
            result = dispatch("window_layout_target", {}, bridge, tracker)
        self.assertFalse(result[0])
        self.assertEqual(bridge.mock_calls, [])
        self.assertEqual(tracker.mock_calls, [])
        self.assertEqual(draft.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
