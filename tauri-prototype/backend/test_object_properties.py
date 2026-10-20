import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.server import _set_target_mode, dispatch
from backend.tauri_hwp_bridge import TauriHwpBridge
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge


class ParameterSet:
    def __init__(self, values):
        self.values = dict(values)
        self.writes = []

    def Item(self, name):
        return self.values.get(name)

    def SetItem(self, name, value):
        self.writes.append((name, value))
        self.values[name] = value


class Control:
    def __init__(self, kind, inline=False, ignore_changes=False):
        self.CtrlID = kind
        self.values = {"TreatAsChar": int(inline), "Width": 12000, "Height": 6000, "TextWrap": 3}
        self.ignore_changes = ignore_changes
        self.applied = []

    @property
    def Properties(self):
        return ParameterSet(self.values)

    @Properties.setter
    def Properties(self, value):
        self.applied.append(value.writes)
        if not self.ignore_changes:
            self.values = dict(value.values)


class ObjectPropertyTests(unittest.TestCase):
    def tearDown(self):
        _set_target_mode("hwp")

    def bridge(self, mode, selected=None, parent=None):
        editor = SimpleNamespace(CurSelectedCtrl=selected, ParentCtrl=parent)
        if mode == "hwp":
            bridge = TauriHwpBridge()
            bridge.hwp = editor
        else:
            bridge = WxsHwpBridge()
            bridge.editor = editor
            bridge._dispatch_obj = Mock(side_effect=lambda value: value)
            bridge._invoke_method = Mock(side_effect=lambda obj, name, args=(), **kwargs: getattr(obj, name)(*args))
            bridge.restore_focus = Mock()
        bridge.ensure = Mock(return_value=(True, "OK"))
        return bridge

    def test_enable_and_disable_only_change_the_requested_property(self):
        for mode in ("hwp", "kedufine"):
            for kind in ("tbl", "gso"):
                with self.subTest(mode=mode, kind=kind):
                    ctrl = Control(kind)
                    bridge = self.bridge(mode, selected=ctrl)
                    self.assertTrue(bridge.set_object_treat_as_char(True)[0])
                    self.assertEqual(ctrl.values, {"TreatAsChar": 1, "Width": 12000, "Height": 6000, "TextWrap": 3})
                    self.assertTrue(bridge.set_object_treat_as_char(False)[0])
                    self.assertEqual(ctrl.values["TreatAsChar"], 0)
                    self.assertEqual(ctrl.applied, [[("TreatAsChar", 1)], [("TreatAsChar", 0)]])

    def test_cursor_inside_table_does_not_require_selecting_the_whole_table(self):
        for mode in ("hwp", "kedufine"):
            ctrl = Control("tbl")
            bridge = self.bridge(mode, parent=ctrl)
            self.assertTrue(bridge.set_object_treat_as_char(True)[0])
            self.assertEqual(ctrl.values["TreatAsChar"], 1)

    def test_selected_picture_takes_priority_over_its_containing_table(self):
        for mode in ("hwp", "kedufine"):
            picture, table = Control("gso"), Control("tbl")
            self.assertTrue(self.bridge(mode, picture, table).set_object_treat_as_char(True)[0])
            self.assertEqual(picture.values["TreatAsChar"], 1)
            self.assertEqual(table.applied, [])

    def test_missing_or_unsupported_selection_is_not_a_success(self):
        for mode in ("hwp", "kedufine"):
            for selected, parent in ((None, None), (None, Control("gso")), (Control("eqed"), Control("tbl"))):
                bridge = self.bridge(mode, selected, parent)
                self.assertFalse(bridge.set_object_treat_as_char(True)[0])
                if selected:
                    self.assertEqual(selected.applied, [])
                if parent:
                    self.assertEqual(parent.applied, [])

    def test_already_matching_state_does_not_write_again(self):
        for mode in ("hwp", "kedufine"):
            ctrl = Control("tbl", inline=True)
            ok, message = self.bridge(mode, ctrl).set_object_treat_as_char(True)
            self.assertTrue(ok)
            self.assertIn("이미", message)
            self.assertEqual(ctrl.applied, [])

    def test_missing_property_is_rejected_without_writing(self):
        for mode in ("hwp", "kedufine"):
            ctrl = Control("tbl")
            del ctrl.values["TreatAsChar"]
            self.assertFalse(self.bridge(mode, ctrl).set_object_treat_as_char(True)[0])
            self.assertEqual(ctrl.applied, [])

    def test_change_ignored_by_hwp_is_reported_as_failure(self):
        for mode in ("hwp", "kedufine"):
            ctrl = Control("tbl", ignore_changes=True)
            ok, message = self.bridge(mode, ctrl).set_object_treat_as_char(True)
            self.assertFalse(ok)
            self.assertIn("반영되지", message)

    def test_connection_failure_does_not_modify_anything(self):
        for mode in ("hwp", "kedufine"):
            ctrl = Control("tbl")
            bridge = self.bridge(mode, ctrl)
            bridge.ensure.return_value = (False, "not connected")
            self.assertEqual(bridge.set_object_treat_as_char(True), (False, "not connected"))
            self.assertEqual(ctrl.applied, [])

    def test_dispatch_validates_boolean_and_does_not_use_cell_tracker(self):
        bridge, tracker = Mock(), Mock()
        for value in (None, "false", 0, 1):
            self.assertFalse(dispatch("object_treat_as_char", {"enabled": value}, bridge, tracker)[0])
        bridge.set_object_treat_as_char.assert_not_called()
        bridge.set_object_treat_as_char.return_value = (True, "done")
        for value in (True, False):
            self.assertEqual(dispatch("object_treat_as_char", {"enabled": value}, bridge, tracker), (True, "done", {}))
        self.assertEqual(tracker.mock_calls, [])
        bridge.set_selected_table_treat_as_char.assert_not_called()

    def test_kedufine_dispatch_does_not_call_desktop_bridge(self):
        _set_target_mode("kedufine")
        desktop, tracker, draft = Mock(), Mock(), Mock()
        draft.set_object_treat_as_char.return_value = (True, "done")
        with patch("backend.server._WXS_BRIDGE", draft):
            self.assertTrue(dispatch("object_treat_as_char", {"enabled": False}, desktop, tracker)[0])
        draft.set_object_treat_as_char.assert_called_once_with(False)
        self.assertEqual(desktop.mock_calls, [])
        self.assertEqual(tracker.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
