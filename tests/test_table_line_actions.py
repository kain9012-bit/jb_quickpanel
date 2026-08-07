# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge


LINE_TYPES = {"None": 0, "Solid": 1, "DoubleSlim": 2}
LINE_WIDTHS = {"0.1mm": 10, "0.5mm": 50}


def make_hwp_bridge():
    cell_shape = SimpleNamespace(HSet=object())
    hwp = Mock()
    hwp.HParameterSet = SimpleNamespace(HCellBorderFill=cell_shape)
    hwp.HwpLineType.side_effect = LINE_TYPES.__getitem__
    hwp.HwpLineWidth.side_effect = LINE_WIDTHS.__getitem__
    hwp.RGBColor.side_effect = lambda r, g, b: r | (g << 8) | (b << 16)

    bridge = HwpBridge()
    bridge.hwp = hwp
    bridge.ensure = Mock(return_value=(True, "OK"))
    return bridge, cell_shape, hwp


def make_wxs_bridge():
    pset = {}
    bridge = object.__new__(WxsHwpBridge)
    bridge.ensure = Mock(return_value=(True, "OK"))
    bridge._hwp_line_type = Mock(side_effect=LINE_TYPES.__getitem__)
    bridge._hwp_line_width = Mock(side_effect=LINE_WIDTHS.__getitem__)
    bridge._rgb_color = Mock(side_effect=lambda r, g, b: r | (g << 8) | (b << 16))

    def set_any(target, keys, value):
        for key in keys:
            target[key] = value
        return True

    def execute(action_name, configure):
        configure(pset)
        return True, "표 작업 적용 완료"

    bridge._safe_set_any = set_any
    bridge._execute_table_action = execute
    return bridge, pset


class HwpTableLineActionTests(unittest.TestCase):
    def test_remove_all_lines_also_removes_internal_vertical_lines(self):
        bridge, shape, _ = make_hwp_bridge()

        ok, _ = bridge.apply_table_tool("표전체선없애기")

        self.assertTrue(ok)
        for attr in ["TypeHorz", "TypeVert", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"]:
            self.assertEqual(getattr(shape, attr), LINE_TYPES["None"])

    def test_basic_line_restores_types_widths_and_black_after_other_actions(self):
        bridge, shape, hwp = make_hwp_bridge()
        bridge.apply_table_tool("표전체선없애기")
        bridge.apply_table_tool("빨간색강조선넣기")

        ok, _ = bridge.apply_table_tool("기본선변경하기")

        self.assertTrue(ok)
        for attr in ["TypeVert", "TypeHorz", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"]:
            self.assertEqual(getattr(shape, attr), LINE_TYPES["Solid"])
        for attr in ["WidthVert", "WidthHorz", "BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft"]:
            self.assertEqual(getattr(shape, attr), LINE_WIDTHS["0.1mm"])
        for attr in ["ColorVert", "ColorHorz", "BorderColorBottom", "BorderColorTop", "BorderColorRight", "BorderColorLeft"]:
            self.assertEqual(getattr(shape, attr), 0)
        self.assertEqual(hwp.HAction.Execute.call_count, 3)

    def test_visible_outer_line_actions_restore_line_type_after_remove_all(self):
        cases = [
            ("전체바깥선굵게변경하기", ["BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"], LINE_TYPES["Solid"]),
            ("위쪽바깥선굵게변경하기", ["BorderTypeTop"], LINE_TYPES["Solid"]),
            ("아래쪽바깥선굵게변경하기", ["BorderTypeBottom"], LINE_TYPES["Solid"]),
            ("아래쪽바깥선이중선변경하기", ["BorderTypeBottom"], LINE_TYPES["DoubleSlim"]),
        ]
        for action_id, attrs, expected_type in cases:
            with self.subTest(action_id=action_id):
                bridge, shape, _ = make_hwp_bridge()
                bridge.apply_table_tool("표전체선없애기")
                ok, _ = bridge.apply_table_tool(action_id)
                self.assertTrue(ok)
                for attr in attrs:
                    self.assertEqual(getattr(shape, attr), expected_type)


class WxsTableLineActionTests(unittest.TestCase):
    def test_remove_all_then_basic_line_restores_complete_line_state(self):
        bridge, pset = make_wxs_bridge()
        bridge.apply_table_tool("표전체선없애기")

        ok, _ = bridge.apply_table_tool("기본선변경하기")

        self.assertTrue(ok)
        for key in ["TypeVert", "TypeHorz", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"]:
            self.assertEqual(pset[key], LINE_TYPES["Solid"])
        for key in ["WidthVert", "WidthHorz", "BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft"]:
            self.assertEqual(pset[key], LINE_WIDTHS["0.1mm"])
        for key in ["ColorVert", "ColorHorz", "BorderColorBottom", "BorderColorTop", "BorderColorRight", "BorderColorLeft"]:
            self.assertEqual(pset[key], 0)


if __name__ == "__main__":
    unittest.main()
