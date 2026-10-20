import unittest

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge


class RecordingCellBridge(HwpBridge):
    def __init__(self):
        super().__init__()
        self.hwp = object()
        self.current = (0, 0)
        self.formatted = []

    def ensure(self):
        return True, "OK"

    def _cell_focus_hwp(self):
        return None

    def cell_validate_range_no_merged_cells(self, *args, **kwargs):
        return None

    def cell_move_to_addr(self, col, row):
        self.current = (int(col), int(row))

    def cell_select_current_text(self):
        return (*self.current, 0)

    def apply_charshape(self, **kwargs):
        self.formatted.append((self.current, kwargs))
        return True, "OK"

    def _cell_try_cmd(self, command, delay=0.0):
        return True

    def _cell_set_pos(self, pos):
        self.current = (int(pos[0]), int(pos[1]))
        return True

    def cell_move_right(self):
        self.current = (self.current[0] + 1, self.current[1])

    def cell_move_left(self):
        self.current = (self.current[0] - 1, self.current[1])

    def cell_move_down(self):
        self.current = (self.current[0], self.current[1] + 1)


class FallbackCellBridge(RecordingCellBridge):
    def _cell_try_cmd(self, command, delay=0.0):
        return command != "TableCellBlockExtend"


class CellRangeCharacterFormattingTests(unittest.TestCase):
    def test_script_mode_is_forwarded_on_block_and_per_cell_paths(self):
        for bridge in (RecordingCellBridge(), FallbackCellBridge()):
            self.assertTrue(bridge.apply_charshape_to_cell_range(1, 1, 2, 2, script_mode="super")[0])
            self.assertTrue(all(kwargs["script_mode"] == "super" for _, kwargs in bridge.formatted))

    def test_applies_once_to_rebuilt_cell_block(self):
        bridge = RecordingCellBridge()

        ok, message = bridge.apply_charshape_to_cell_range(
            2,
            3,
            3,
            4,
            font_name="함초롬바탕",
            font_size_pt=11,
            font_color_rgb=(255, 0, 0),
        )

        self.assertTrue(ok)
        self.assertEqual(message, "표 셀 글자 적용 완료: 4개 셀")
        self.assertEqual([position for position, _kwargs in bridge.formatted], [(3, 4)])
        self.assertEqual(bridge.formatted[0][1]["font_name"], "함초롬바탕")

    def test_falls_back_to_each_cell_when_block_extension_fails(self):
        bridge = FallbackCellBridge()

        ok, message = bridge.apply_charshape_to_cell_range(
            2,
            3,
            3,
            4,
            font_name="함초롬바탕",
            font_size_pt=11,
            font_color_rgb=(255, 0, 0),
        )

        self.assertTrue(ok)
        self.assertEqual(message, "표 셀 글자 적용 완료: 4개 셀")
        self.assertEqual(
            [position for position, _kwargs in bridge.formatted],
            [(2, 3), (3, 3), (2, 4), (3, 4)],
        )


if __name__ == "__main__":
    unittest.main()
