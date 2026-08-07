# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge


class ParagraphBackgroundTests(unittest.TestCase):
    def _make_bridge(self):
        fill_attr = SimpleNamespace(
            Type=7,
            WindowsBrush=1,
            GradationBrush=1,
            ImageBrush=1,
            WinBrushFaceColor=0x00FFFFFF,
        )
        para_shape = SimpleNamespace(
            HSet=object(),
            BorderFill=SimpleNamespace(FillAttr=fill_attr),
        )
        hwp = Mock()
        hwp.HParameterSet = SimpleNamespace(HParaShape=para_shape)
        hwp.BrushType.side_effect = lambda name: 1 if name == "NullBrush|WinBrush" else 0
        hwp.HatchStyle.side_effect = lambda name: -1 if name == "None" else 0

        bridge = HwpBridge()
        bridge.hwp = hwp
        return bridge, hwp, para_shape, fill_attr

    def _assert_no_fill(self, hwp, para_shape, fill_attr):
        self.assertEqual(fill_attr.Type, 1)
        self.assertEqual(fill_attr.WindowsBrush, 0)
        self.assertEqual(fill_attr.GradationBrush, 0)
        self.assertEqual(fill_attr.ImageBrush, 0)
        self.assertEqual(fill_attr.WinBrushFaceColor, 0xFFFFFFFF)
        self.assertEqual(fill_attr.WinBrushFaceStyle, -1)
        hwp.BrushType.assert_called_once_with("NullBrush|WinBrush")
        hwp.HatchStyle.assert_called_once_with("None")
        hwp.HAction.GetDefault.assert_called_once_with("ParagraphShape", para_shape.HSet)
        hwp.HAction.Execute.assert_called_once_with("ParagraphShape", para_shape.HSet)

    def test_selected_paragraph_background_becomes_no_fill(self):
        bridge, hwp, para_shape, fill_attr = self._make_bridge()

        ok, _message = bridge.clear_selected_paragraph_background(ensure_before=False)

        self.assertTrue(ok)
        self._assert_no_fill(hwp, para_shape, fill_attr)

    def test_current_paragraph_background_becomes_no_fill(self):
        bridge, hwp, para_shape, fill_attr = self._make_bridge()

        ok, _message = bridge.clear_current_paragraph_background_at_caret()

        self.assertTrue(ok)
        self._assert_no_fill(hwp, para_shape, fill_attr)


if __name__ == "__main__":
    unittest.main()
