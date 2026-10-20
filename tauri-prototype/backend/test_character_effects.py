import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.server import FEATURES, _set_target_mode, dispatch
from backend.tauri_hwp_bridge import TauriHwpBridge
from backend.test_server import FakeBridge, FakeTracker
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge
from src.jb_quickpanel.features.character_effects import compose_parameters, script_parameters


class CharacterEffectsTests(unittest.TestCase):
    def tearDown(self):
        _set_target_mode("hwp")

    def composition_bridge(self, native=True, execute=True):
        params = SimpleNamespace(SetItem=Mock())
        action = SimpleNamespace(CreateSet=Mock(return_value=params),
                                 GetDefault=Mock(), Execute=Mock(return_value=execute))
        if native:
            bridge = TauriHwpBridge()
            bridge.hwp = SimpleNamespace(CreateAction=Mock(return_value=action))
        else:
            bridge = WxsHwpBridge()
            bridge._create_action = Mock(return_value=action)
            bridge._action_create_set = lambda value: value.CreateSet()
            bridge._action_get_default = lambda value, pset: value.GetDefault(pset)
            bridge._action_execute = lambda value, pset: value.Execute(pset)
            bridge._set_item = lambda pset, key, value: pset.SetItem(key, value)
            bridge.restore_focus = Mock()
        bridge.ensure = Mock(return_value=(True, "OK"))
        return bridge, params, action

    def test_scripts_are_explicit_mutually_exclusive_settings(self):
        for mode, expected in (("super", (1, 0)), ("sub", (0, 1)), ("normal", (0, 0))):
            self.assertEqual(script_parameters(mode), dict(zip(("SuperScript", "SubScript"), expected)))

    def test_composition_uses_documented_action_and_nonoverlapping_characters(self):
        for native in (True, False):
            for value, shape, circle_type in (("30", "circle", 1), ("1", "square", 3),
                                               ("가", "square", 3), ("A", "square", 3)):
                with self.subTest(native=native, value=value):
                    bridge, params, action = self.composition_bridge(native)
                    self.assertTrue(bridge.compose_characters(value, shape)[0])
                    create = bridge.hwp.CreateAction if native else bridge._create_action
                    create.assert_called_once_with("ComposeChars")
                    writes = dict(call.args for call in params.SetItem.call_args_list)
                    self.assertEqual(writes["Chars"], value)
                    self.assertEqual(writes["CircleType"], circle_type)
                    self.assertEqual(writes["CheckCompose"], 0)
                    action.Execute.assert_called_once_with(params)

    def test_false_execute_is_a_failure(self):
        for native in (True, False):
            bridge, _, _ = self.composition_bridge(native, execute=False)
            self.assertFalse(bridge.compose_characters("30", "circle")[0])
            if not native:
                bridge.restore_focus.assert_not_called()

    def test_invalid_composition_does_not_connect_or_modify_document(self):
        for native in (True, False):
            bridge, params, action = self.composition_bridge(native)
            for value, shape in (("", "circle"), (" ", "circle"), ("1234567890", "circle"),
                                 ("a\nb", "circle"), ("\x00", "square"), (30, "circle"),
                                 ("30", "invalid"), ("30", [])):
                self.assertFalse(bridge.compose_characters(value, shape)[0])
            bridge.ensure.assert_not_called()
            params.SetItem.assert_not_called()
            action.Execute.assert_not_called()

    def test_native_script_reset_preserves_other_character_properties(self):
        params = SimpleNamespace(HSet=object(), Bold=1, Height=1200, TextColor=123)
        bridge = TauriHwpBridge()
        bridge.hwp = SimpleNamespace(HParameterSet=SimpleNamespace(HCharShape=params),
                                    HAction=SimpleNamespace(GetDefault=Mock(), Execute=Mock(return_value=True)))
        bridge.ensure = Mock(return_value=(True, "OK"))
        for mode in ("super", "super", "sub", "normal"):
            self.assertTrue(bridge.apply_charshape(script_mode=mode)[0])
            self.assertEqual((params.SuperScript, params.SubScript), tuple(script_parameters(mode).values()))
            self.assertEqual((params.Bold, params.Height, params.TextColor), (1, 1200, 123))

    def test_drafting_script_reset_writes_only_script_flags(self):
        bridge, params, _ = self.composition_bridge(native=False)
        self.assertTrue(bridge.apply_charshape(script_mode="normal")[0])
        self.assertEqual([call.args for call in params.SetItem.call_args_list],
                         [("SuperScript", 0), ("SubScript", 0)])

    def test_dispatch_keeps_partial_text_and_cell_selection_separate(self):
        for partial_text in (False, True):
            bridge = FakeBridge(in_table=True, text_selection=partial_text)
            tracker = FakeTracker((1, 1, 2, 2))
            self.assertTrue(dispatch("apply_charshape", {"script_mode": "sub"}, bridge, tracker)[0])
            self.assertEqual(bridge.calls[0][0], "text_charshape" if partial_text else "cell_charshape")
            self.assertEqual(bridge.calls[0][-1]["script_mode"], "sub")
            self.assertFalse(tracker.processing)

    def test_bad_script_mode_is_rejected_before_tracker_access(self):
        bridge, tracker = Mock(), Mock()
        for mode in ("toggle", 1, [], {}):
            self.assertFalse(dispatch("apply_charshape", {"script_mode": mode}, bridge, tracker)[0])
        self.assertEqual(bridge.mock_calls, [])
        self.assertEqual(tracker.mock_calls, [])

    def test_composition_dispatch_uses_correct_editor_and_returns_native_focus_only(self):
        for mode in ("hwp", "kedufine"):
            _set_target_mode(mode)
            desktop, draft, tracker = Mock(), Mock(), Mock()
            desktop.compose_characters.return_value = draft.compose_characters.return_value = (True, "OK")
            with patch("backend.server._WXS_BRIDGE", draft), patch("backend.server.ui_get_last_hwp_window", return_value={"hwnd": 123}):
                ok, _, data = dispatch("compose_characters", {"value": "30", "shape": "circle"}, desktop, tracker)
            self.assertTrue(ok)
            self.assertEqual(data["hwp_hwnd"], 123 if mode == "hwp" else 0)
            active, inactive = (desktop, draft) if mode == "hwp" else (draft, desktop)
            active.compose_characters.assert_called_once_with("30", "circle")
            inactive.compose_characters.assert_not_called()
            self.assertEqual(tracker.mock_calls, [])

    def test_square_catalog_does_not_renumber_existing_builtin_groups(self):
        symbols = {"원문자-흰색": ["①"], "원문자-검정": ["❶"], "기호": ["※"]}
        with patch.object(FEATURES, "config", return_value={"symbols": symbols}), patch("backend.full_features.UserContentStore") as store:
            store.return_value.list_symbol_groups.return_value = []
            groups = FEATURES.character_catalog()
        self.assertEqual([item["id"] for item in groups],
                         ["builtin:0", "builtin:1", "builtin:square:numbers", "builtin:2"])
        self.assertEqual(groups[2]["chars"], [str(number) for number in range(1, 21)])
        self.assertEqual([group["title"] for group in groups if group.get("presentation") == "square"], ["네모문자-숫자"])


if __name__ == "__main__":
    unittest.main()
