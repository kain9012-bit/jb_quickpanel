# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge
from src.jb_quickpanel.features import registry


def _fill_attr():
    return SimpleNamespace(
        Type=1,
        WinBrushFaceColor=0x00DFE6F7,
        WinBrushFaceStyle=0,
        WindowsBrush=1,
        GradationBrush=1,
        ImageBrush=1,
    )


class HwpCellFillNoneTests(unittest.TestCase):
    def test_table_action_removes_fill_from_selected_cells(self):
        primary_fill = _fill_attr()
        selected_fill = _fill_attr()
        cell_shape = SimpleNamespace(
            HSet=object(),
            FillAttr=primary_fill,
            SelCellsBorderFill=SimpleNamespace(FillAttr=selected_fill),
        )
        hwp = Mock()
        hwp.HParameterSet = SimpleNamespace(HCellBorderFill=cell_shape)
        hwp.BrushType.return_value = 1
        hwp.HatchStyle.return_value = -1

        bridge = HwpBridge()
        bridge.hwp = hwp
        bridge.ensure = Mock(return_value=(True, "OK"))

        ok, message = bridge.apply_table_tool("배경색없애기")

        self.assertTrue(ok)
        self.assertEqual(message, "셀 배경색 제거 완료")
        for fill in (primary_fill, selected_fill):
            self.assertEqual(fill.WinBrushFaceColor, 0xFFFFFFFF)
            self.assertEqual(fill.WinBrushFaceStyle, -1)
            self.assertEqual(fill.WindowsBrush, 0)
            self.assertEqual(fill.GradationBrush, 0)
            self.assertEqual(fill.ImageBrush, 0)
        self.assertEqual(
            hwp.HAction.GetDefault.call_args_list,
            [
                call("CellBorder", cell_shape.HSet),
                call("CellFill", cell_shape.HSet),
            ],
        )
        hwp.HAction.Execute.assert_called_once_with("CellFill", cell_shape.HSet)


class WxsCellFillNoneTests(unittest.TestCase):
    def test_fill_none_parameter_set_uses_no_color_values(self):
        bridge = object.__new__(WxsHwpBridge)
        fill = object()
        bridge._create_item_set = Mock(return_value=fill)
        bridge._set_item = Mock()
        pset = object()

        bridge._set_fill_none_params(pset)

        bridge._create_item_set.assert_called_once_with(pset, "FillAttr", "DrawFillAttr")
        self.assertEqual(
            bridge._set_item.call_args_list,
            [
                call(fill, "Type", 1),
                call(fill, "WinBrushFaceStyle", 0xFFFFFFFF),
                call(fill, "WinBrushHatchColor", 0x00000000),
                call(fill, "WinBrushFaceColor", 0xFFFFFFFF),
                call(fill, "WindowsBrush", 0),
                call(fill, "GradationBrush", 0),
                call(fill, "ImageBrush", 0),
            ],
        )

    def test_table_action_routes_to_fill_none(self):
        bridge = object.__new__(WxsHwpBridge)
        bridge.ensure = Mock(return_value=(True, "OK"))
        bridge._apply_cell_fill_none = Mock(return_value=(True, "removed"))

        result = bridge.apply_table_tool("배경색없애기")

        self.assertEqual(result, (True, "removed"))
        bridge._apply_cell_fill_none.assert_called_once_with()


class TableFillNoneRegistryTests(unittest.TestCase):
    def test_tool_is_inserted_before_red_border_without_mutating_config(self):
        source = [
            {"title": "노랑", "action_id": "연한노랑색배경채우기"},
            {"title": "빨간선", "action_id": "빨간색강조선넣기"},
        ]

        result = registry.with_table_fill_none_tool(source)

        self.assertEqual(
            [item["action_id"] for item in result],
            ["연한노랑색배경채우기", "배경색없애기", "빨간색강조선넣기"],
        )
        self.assertEqual(len(source), 2)
        self.assertEqual(result[1]["title"], "배경색 없애기")


if __name__ == "__main__":
    unittest.main()
