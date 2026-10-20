import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.server import _set_target_mode, dispatch
from backend.tauri_hwp_bridge import TauriHwpBridge
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge


class TableDrawingTests(unittest.TestCase):
    def tearDown(self):
        _set_target_mode("hwp")

    def hwp_bridge(self, result=True):
        bridge = TauriHwpBridge()
        bridge.ensure = Mock(return_value=(True, "OK"))
        bridge.hwp = SimpleNamespace(HAction=Mock(), SetPos=Mock())
        bridge.hwp.HAction.Run.return_value = result
        return bridge

    def test_drawing_runs_on_the_existing_connection_without_a_window_setfocus_method(self):
        bridge = self.hwp_bridge()
        ok, _ = bridge.start_table_drawing()
        self.assertTrue(ok)
        bridge.ensure.assert_called_once()
        bridge.hwp.HAction.Run.assert_called_once_with("TableDrawPen")
        bridge.hwp.HAction.Execute.assert_not_called()
        bridge.hwp.SetPos.assert_not_called()

    def test_connection_failure_does_not_run_the_action(self):
        bridge = self.hwp_bridge()
        bridge.ensure.return_value = (False, "not connected")
        self.assertEqual(bridge.start_table_drawing(), (False, "not connected"))
        bridge.hwp.HAction.Run.assert_not_called()

    def test_false_or_empty_action_result_is_not_reported_as_success(self):
        for result in (False, 0, None):
            with self.subTest(result=result):
                bridge = self.hwp_bridge(result=result)
                self.assertFalse(bridge.start_table_drawing()[0])

    def test_com_exception_is_reported(self):
        bridge = self.hwp_bridge()
        bridge.hwp.HAction.Run.side_effect = RuntimeError("COM failure")
        ok, message = bridge.start_table_drawing()
        self.assertFalse(ok)
        self.assertIn("COM failure", message)

    def test_kedufine_uses_its_existing_com_command_path(self):
        bridge = WxsHwpBridge()
        bridge.ensure = Mock(return_value=(True, "OK"))
        bridge.restore_focus = Mock(return_value=True)
        bridge.run_cmd = Mock(return_value=(True, "OK"))
        self.assertTrue(bridge.start_table_drawing()[0])
        bridge.run_cmd.assert_called_once_with("TableDrawPen")

    def test_kedufine_focus_and_action_failures_are_not_success(self):
        bridge = WxsHwpBridge()
        bridge.ensure = Mock(return_value=(True, "OK"))
        bridge.restore_focus = Mock(return_value=False)
        bridge.run_cmd = Mock(return_value=(False, "unsupported"))
        self.assertFalse(bridge.start_table_drawing()[0])
        bridge.run_cmd.assert_not_called()
        bridge.restore_focus.return_value = True
        self.assertEqual(bridge.start_table_drawing(), (False, "unsupported"))

    def test_dispatch_is_separate_from_cell_tools_and_does_not_require_a_block(self):
        bridge, tracker = Mock(), Mock()
        bridge.start_table_drawing.return_value = (True, "started")
        with patch("backend.server.ui_get_last_hwp_window", return_value={"hwnd": 101}):
            self.assertEqual(dispatch("table_draw", {}, bridge, tracker), (True, "started", {"hwp_hwnd": 101}))
        bridge.apply_table_tool.assert_not_called()
        self.assertEqual(tracker.mock_calls, [])

    def test_dispatch_failure_does_not_transfer_focus(self):
        bridge = Mock()
        bridge.start_table_drawing.return_value = (False, "failed")
        with patch("backend.server.ui_get_last_hwp_window") as window:
            self.assertEqual(dispatch("table_draw", {}, bridge, Mock()), (False, "failed", {"hwp_hwnd": 0}))
        window.assert_not_called()

    def test_dispatch_kedufine_does_not_call_the_desktop_bridge(self):
        _set_target_mode("kedufine")
        desktop, tracker, draft = Mock(), Mock(), Mock()
        draft.start_table_drawing.return_value = (True, "started")
        with patch("backend.server._WXS_BRIDGE", draft):
            self.assertEqual(dispatch("table_draw", {}, desktop, tracker), (True, "started", {"hwp_hwnd": 0}))
        self.assertEqual(desktop.mock_calls, [])
        self.assertEqual(tracker.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
