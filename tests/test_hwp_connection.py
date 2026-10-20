# -*- coding: utf-8 -*-
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.jb_quickpanel.bridges import hwp_bridge
from src.jb_quickpanel.core import runtime


class ComCacheFallbackTests(unittest.TestCase):
    def setUp(self):
        if runtime.win32com is None:
            self.skipTest("pywin32 is not available")

    def test_repair_removes_only_hwp_generated_cache(self):
        cache_name = runtime._HWP_TYPELIB_CACHE_PREFIX + "x0x1x0"
        error = AttributeError(
            f"module 'win32com.gen_py.{cache_name}' has no attribute 'CLSIDToPackageMap'"
        )

        with TemporaryDirectory() as temp_dir:
            gen_root = Path(temp_dir)
            hwp_cache = gen_root / cache_name
            other_cache = gen_root / "OTHER-COM-CACHE"
            hwp_cache.mkdir()
            other_cache.mkdir()
            (hwp_cache / "broken.pyc").write_bytes(b"broken")
            (gen_root / "dicts.dat").write_bytes(b"stale")

            fake_win32com = SimpleNamespace(__gen_path__=str(gen_root))
            with patch.object(runtime, "win32com", fake_win32com), patch(
                "win32com.client.gencache.Rebuild"
            ) as rebuild:
                repaired = runtime.repair_hwp_win32com_gen_cache(error)

            self.assertTrue(repaired)
            self.assertFalse(hwp_cache.exists())
            self.assertTrue(other_cache.exists())
            self.assertFalse((gen_root / "dicts.dat").exists())
            rebuild.assert_called_once_with(verbose=0)


    def test_broken_gen_cache_uses_dynamic_dispatch(self):
        dispatch = Mock()
        expected = object()
        cache_error = AttributeError(
            "module 'win32com.gen_py.sample' has no attribute 'CLSIDToPackageMap'"
        )

        with patch.object(
            runtime.win32com.client, "Dispatch", side_effect=cache_error
        ), patch.object(
            runtime, "repair_hwp_win32com_gen_cache", return_value=True
        ) as repair_cache, patch.object(
            runtime.win32com.client.dynamic, "Dispatch", return_value=expected
        ) as dynamic_dispatch:
            actual, used_fallback = runtime.dispatch_com_object_safely(dispatch)

        self.assertIs(actual, expected)
        self.assertTrue(used_fallback)
        dynamic_dispatch.assert_called_once_with(dispatch)
        repair_cache.assert_called_once_with(cache_error)

    def test_unrelated_dispatch_error_is_not_hidden(self):
        dispatch = Mock()
        with patch.object(
            runtime.win32com.client, "Dispatch", side_effect=RuntimeError("RPC failed")
        ), patch.object(runtime.win32com.client.dynamic, "Dispatch") as dynamic_dispatch:
            with self.assertRaisesRegex(RuntimeError, "RPC failed"):
                runtime.dispatch_com_object_safely(dispatch)

        dynamic_dispatch.assert_not_called()


class HwpInstanceSelectionTests(unittest.TestCase):
    @staticmethod
    def candidate(index, *, visible, handles=(), pids=(), inspected=True):
        return {
            "version": 110,
            "index": index,
            "name": f"!HwpObject.110.{index}",
            "hwp": object(),
            "used_dynamic_dispatch": False,
            "window_state": {
                "inspected": inspected,
                "visible": visible,
                "handles": tuple(handles),
                "visible_handles": tuple(handles) if visible else (),
                "pids": tuple(pids),
            },
        }

    def test_visible_window_wins_over_newer_hidden_instance(self):
        visible = self.candidate(1, visible=True, handles=(101,), pids=(1001,))
        hidden = self.candidate(9, visible=False, handles=(909,), pids=(9009,))

        selected = runtime._select_running_hwp_candidate([visible, hidden])

        self.assertIs(selected, visible)

    def test_last_active_window_wins_between_visible_instances(self):
        active = self.candidate(1, visible=True, handles=(101,), pids=(1001,))
        newer = self.candidate(9, visible=True, handles=(909,), pids=(9009,))

        selected = runtime._select_running_hwp_candidate(
            [active, newer], preferred_hwnd=101, preferred_pid=1001
        )

        self.assertIs(selected, active)

    def test_all_known_hidden_instances_are_rejected(self):
        hidden = self.candidate(9, visible=False, handles=(909,), pids=(9009,))

        selected = runtime._select_running_hwp_candidate([hidden])

        self.assertIsNone(selected)

    def test_uninspectable_legacy_instance_keeps_compatibility_fallback(self):
        legacy = self.candidate(2, visible=False, inspected=False)

        selected = runtime._select_running_hwp_candidate([legacy])

        self.assertIs(selected, legacy)

    def test_bridge_reconnects_when_cached_object_is_not_visible_target(self):
        stale = object()
        current = object()
        bridge = hwp_bridge.HwpBridge()
        bridge.hwp = stale

        with patch.object(
            hwp_bridge,
            "hwp_connection_matches_visible_target",
            return_value=False,
        ), patch.object(
            hwp_bridge,
            "get_running_hwp_from_rot",
            return_value=(True, current, "connected"),
        ):
            ok, message = bridge.ensure()

        self.assertTrue(ok)
        self.assertEqual(message, "connected")
        self.assertIs(bridge.hwp, current)


class HwpSecurityModuleTests(unittest.TestCase):
    def test_connect_does_not_register_external_security_module(self):
        hwp = Mock()
        bridge = hwp_bridge.HwpBridge()

        with patch.object(
            hwp_bridge, "bring_last_hwp_to_front_if_any", return_value=(True, "OK")
        ), patch.object(
            hwp_bridge,
            "get_running_hwp_from_rot",
            return_value=(True, hwp, "connected"),
        ), patch.object(hwp_bridge.time, "sleep"):
            ok, message = bridge.connect()

        self.assertTrue(ok)
        self.assertEqual(message, "connected")
        hwp.RegisterModule.assert_not_called()

    def test_focusless_connect_does_not_register_external_security_module(self):
        hwp = Mock()
        bridge = hwp_bridge.HwpBridge()

        with patch.object(
            hwp_bridge,
            "get_running_hwp_from_rot",
            return_value=(True, hwp, "connected"),
        ):
            ok, message = bridge.connect_without_focus()

        self.assertTrue(ok)
        self.assertEqual(message, "connected")
        hwp.RegisterModule.assert_not_called()


class InsertFileOptionsTests(unittest.TestCase):
    def test_insert_file_reports_explicit_com_failure(self):
        parameter_set = SimpleNamespace(HSet=object())
        action = Mock()
        action.Execute.return_value = False
        bridge = hwp_bridge.HwpBridge()
        bridge.hwp = SimpleNamespace(
            HAction=action,
            HParameterSet=SimpleNamespace(HInsertFile=parameter_set),
        )
        with patch.object(bridge, "ensure", return_value=(True, "connected")), patch.object(
            hwp_bridge.os.path, "exists", return_value=True
        ):
            ok, message = bridge.insert_file("form.hwpx")
        self.assertFalse(ok)
        self.assertIn("삽입 실패", message)

    def test_insert_text_reports_explicit_com_failure(self):
        parameter_set = SimpleNamespace(HSet=object(), Text="")
        action = Mock()
        action.Execute.return_value = 0
        bridge = hwp_bridge.HwpBridge()
        bridge.hwp = SimpleNamespace(
            HAction=action,
            HParameterSet=SimpleNamespace(HInsertText=parameter_set),
        )
        with patch.object(bridge, "ensure", return_value=(True, "connected")):
            ok, message = bridge.insert_text("※")
        self.assertFalse(ok)
        self.assertIn("문자 삽입 실패", message)

    def test_form_content_can_be_preserved_without_importing_section_layout(self):
        parameter_set = SimpleNamespace(HSet=object())
        action = Mock()
        bridge = hwp_bridge.HwpBridge()
        bridge.hwp = SimpleNamespace(
            HAction=action,
            HParameterSet=SimpleNamespace(HInsertFile=parameter_set),
        )
        bridge.run_first_supported = Mock()
        bridge.insert_paragraph_break = Mock()

        with patch.object(bridge, "ensure", return_value=(True, "connected")), patch.object(
            hwp_bridge.os.path, "exists", return_value=True
        ):
            ok, message = bridge.insert_file(
                "form.hwpx",
                preserve_document=True,
                preserve_section=False,
            )

        self.assertTrue(ok)
        self.assertEqual(message, "삽입 완료")
        self.assertEqual(parameter_set.KeepCharshape, 1)
        self.assertEqual(parameter_set.KeepParashape, 1)
        self.assertEqual(parameter_set.KeepStyle, 1)
        self.assertEqual(parameter_set.KeepNumbering, 1)
        self.assertEqual(parameter_set.KeepSection, 0)
        action.Execute.assert_called_once_with("InsertFile", parameter_set.HSet)
        bridge.run_first_supported.assert_not_called()
        bridge.insert_paragraph_break.assert_not_called()


class ManualStyleInsertionTests(unittest.TestCase):
    @patch.object(hwp_bridge.time, "sleep")
    def test_manual_style_runs_end_then_enter_after_insertion(self, _sleep):
        bridge = hwp_bridge.HwpBridge()
        calls = []
        bridge.insert_file = Mock(
            side_effect=lambda path: calls.append(("insert_file", path)) or (True, "inserted")
        )
        bridge.run_first_supported = Mock(
            side_effect=lambda commands: calls.append(("run", commands)) or (True, "MoveLineEnd")
        )
        bridge.insert_paragraph_break = Mock(
            side_effect=lambda: calls.append(("break",)) or (True, "OK")
        )

        ok, message = bridge.insert_manual_style("style.hwpx")

        self.assertTrue(ok)
        self.assertEqual(message, "서식 삽입 완료")
        self.assertEqual(
            calls,
            [
                ("insert_file", "style.hwpx"),
                ("run", ["MoveLineEnd"]),
                ("break",),
            ],
        )


class SelectionModeTests(unittest.TestCase):
    def test_text_selection_uses_low_selection_mode_bits(self):
        bridge = hwp_bridge.HwpBridge()
        bridge.hwp = SimpleNamespace(SelectionMode=1)
        with patch.object(bridge, "ensure", return_value=(True, "connected")):
            self.assertTrue(bridge.has_active_text_selection())

    def test_non_text_selection_does_not_use_low_selection_mode_bits(self):
        bridge = hwp_bridge.HwpBridge()
        bridge.hwp = SimpleNamespace(SelectionMode=0x10)
        with patch.object(bridge, "ensure", return_value=(True, "connected")):
            self.assertFalse(bridge.has_active_text_selection())
if __name__ == "__main__":
    unittest.main()
