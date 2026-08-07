# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge


class _GeneratedFillAttr:
    """makepy가 생성한 HDrawFillAttr처럼 소문자 type만 허용한다."""

    __slots__ = (
        "type",
        "WinBrushFaceColor",
        "WinBrushFaceStyle",
        "WindowsBrush",
        "GradationBrush",
        "ImageBrush",
    )

    def __init__(self):
        self.type = 1
        self.WinBrushFaceColor = 0x00112233
        self.WinBrushFaceStyle = 0
        self.WindowsBrush = 1
        self.GradationBrush = 1
        self.ImageBrush = 1


class CellCleanupFormatTests(unittest.TestCase):
    def test_only_text_and_shade_colors_are_normalized(self):
        char_shape = SimpleNamespace(
            HSet=object(),
            TextColor=0x00663399,
            ShadeColor=0x00112233,
            FaceNameHangul="함초롬바탕",
            Height=1200,
            Bold=1,
            SpacingHangul=-3,
        )
        hwp = Mock()
        fill_attr = _GeneratedFillAttr()
        para_shape = SimpleNamespace(
            HSet=object(),
            BorderFill=SimpleNamespace(FillAttr=fill_attr),
        )
        hwp.HParameterSet = SimpleNamespace(
            HParaShape=para_shape,
            HCharShape=char_shape,
        )
        hwp.RGBColor.return_value = 0
        hwp.BrushType.return_value = 1
        hwp.HatchStyle.return_value = -1

        bridge = HwpBridge()
        bridge.hwp = hwp
        bridge.cell_select_current_text = Mock(return_value=(1, 2, 3))
        bridge._cell_try_cmd = Mock(return_value=True)
        bridge._cell_set_pos = Mock()

        ok, _message = bridge.normalize_current_cell_pasted_format()

        self.assertTrue(ok)
        self.assertEqual(fill_attr.type, 1)
        self.assertEqual(fill_attr.WinBrushFaceColor, 0xFFFFFFFF)
        self.assertEqual(fill_attr.WinBrushFaceStyle, -1)
        self.assertEqual(fill_attr.WindowsBrush, 0)
        self.assertEqual(fill_attr.GradationBrush, 0)
        self.assertEqual(fill_attr.ImageBrush, 0)
        self.assertEqual(char_shape.TextColor, 0)
        self.assertEqual(char_shape.ShadeColor, 0xFFFFFFFF)
        self.assertEqual(char_shape.FaceNameHangul, "함초롬바탕")
        self.assertEqual(char_shape.Height, 1200)
        self.assertEqual(char_shape.Bold, 1)
        self.assertEqual(char_shape.SpacingHangul, -3)
        self.assertEqual(
            hwp.HAction.GetDefault.call_args_list,
            [
                unittest.mock.call("ParagraphShape", para_shape.HSet),
                unittest.mock.call("CharShape", char_shape.HSet),
            ],
        )
        self.assertEqual(
            hwp.HAction.Execute.call_args_list,
            [
                unittest.mock.call("ParagraphShape", para_shape.HSet),
                unittest.mock.call("CharShape", char_shape.HSet),
            ],
        )
        bridge._cell_try_cmd.assert_called_once_with("Cancel", 0.005)
        bridge._cell_set_pos.assert_called_once_with((1, 2, 3))


if __name__ == "__main__":
    unittest.main()
