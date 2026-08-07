import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.jb_quickpanel.features.global_hotkeys import HotkeyAction
from src.jb_quickpanel.ui.app_window import App


class GlobalHotkeyDispatchTests(unittest.TestCase):
    def make_app(self, action):
        return SimpleNamespace(
            _hotkey_action_running=False,
            _hotkey_action_by_id={action.id: action},
            _hotkey_feature_by_id={},
            _rebuild_global_hotkey_catalog=Mock(),
            _foreground_matches_hotkey_target=Mock(return_value=True),
            var_target_mode=SimpleNamespace(get=lambda: "hwp"),
            status_var=SimpleNamespace(set=Mock()),
            is_kedufine_mode=Mock(return_value=False),
            _run_table_tool_action=Mock(),
            _toggle_window_from_hotkey=Mock(),
        )

    def test_dispatches_table_action_to_same_runner_as_button(self):
        action = HotkeyAction("table:test", "표 작업", "테스트", "table", "표동작")
        app = self.make_app(action)

        App._execute_global_hotkey(app, action.id)

        app._run_table_tool_action.assert_called_once_with("표동작", "테스트")
        self.assertFalse(app._hotkey_action_running)

    def test_does_not_run_document_action_when_target_is_not_foreground(self):
        action = HotkeyAction("table:test", "표 작업", "테스트", "table", "표동작")
        app = self.make_app(action)
        app._foreground_matches_hotkey_target.return_value = False

        App._execute_global_hotkey(app, action.id)

        app._run_table_tool_action.assert_not_called()

    def test_window_toggle_does_not_require_document_focus(self):
        action = HotkeyAction(
            "app.toggle_window",
            "프로그램",
            "서식도우미 열기/숨기기",
            "app",
            requires_target=False,
        )
        app = self.make_app(action)
        app._foreground_matches_hotkey_target.return_value = False

        App._execute_global_hotkey(app, action.id)

        app._toggle_window_from_hotkey.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
