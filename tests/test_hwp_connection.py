# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock, patch

from src.jb_quickpanel.bridges import hwp_bridge
from src.jb_quickpanel.core import runtime


class ComCacheFallbackTests(unittest.TestCase):
    def setUp(self):
        if runtime.win32com is None:
            self.skipTest("pywin32 is not available")

    def test_broken_gen_cache_uses_dynamic_dispatch(self):
        dispatch = Mock()
        expected = object()
        cache_error = AttributeError(
            "module 'win32com.gen_py.sample' has no attribute 'CLSIDToPackageMap'"
        )

        with patch.object(
            runtime.win32com.client, "Dispatch", side_effect=cache_error
        ), patch.object(
            runtime.win32com.client.dynamic, "Dispatch", return_value=expected
        ) as dynamic_dispatch:
            actual, used_fallback = runtime.dispatch_com_object_safely(dispatch)

        self.assertIs(actual, expected)
        self.assertTrue(used_fallback)
        dynamic_dispatch.assert_called_once_with(dispatch)

    def test_unrelated_dispatch_error_is_not_hidden(self):
        dispatch = Mock()
        with patch.object(
            runtime.win32com.client, "Dispatch", side_effect=RuntimeError("RPC failed")
        ), patch.object(runtime.win32com.client.dynamic, "Dispatch") as dynamic_dispatch:
            with self.assertRaisesRegex(RuntimeError, "RPC failed"):
                runtime.dispatch_com_object_safely(dispatch)

        dynamic_dispatch.assert_not_called()


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


if __name__ == "__main__":
    unittest.main()
