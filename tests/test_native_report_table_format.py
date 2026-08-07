import unittest

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge


class NativeReportTableFormatTests(unittest.TestCase):
    def _bridge(self):
        class FakeHwp:
            def SetPos(self, *_args):
                return True

        bridge = HwpBridge()
        bridge.hwp = FakeHwp()
        bridge.ensure = lambda: (True, "OK")
        bridge.run_first_supported = lambda commands: (True, commands[0])
        bridge._select_current_table_whole = lambda: (True, "OK")
        bridge.set_selected_table_treat_as_char = lambda _enabled=True: (True, "OK")
        return bridge

    def test_stops_when_paragraph_shape_reset_fails(self):
        bridge = self._bridge()
        bridge.reset_selected_parashape = lambda: (False, "para shape failed")
        bridge.apply_charshape = lambda **_kwargs: self.fail(
            "Character formatting must not run after paragraph formatting fails."
        )

        ok, message = bridge.format_native_report_tables([(0, 1, 0)])

        self.assertFalse(ok)
        self.assertEqual(message, "para shape failed")

    def test_stops_when_character_shape_apply_fails(self):
        bridge = self._bridge()
        bridge.reset_selected_parashape = lambda: (True, "OK")
        bridge.apply_charshape = lambda **_kwargs: (False, "char shape failed")
        bridge.apply_table_tool = lambda _action: self.fail(
            "Table border formatting must not run after character formatting fails."
        )

        ok, message = bridge.format_native_report_tables([(0, 1, 0)])

        self.assertFalse(ok)
        self.assertEqual(message, "char shape failed")


if __name__ == "__main__":
    unittest.main()
