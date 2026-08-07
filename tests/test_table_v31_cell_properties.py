# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge
from src.jb_quickpanel.features import registry


CELL_ACTIONS = (
    ("한줄로입력설정", "LineWrap", 1),
    ("한줄로입력해제", "LineWrap", 0),
    ("제목셀설정", "Header", 1),
    ("제목셀해제", "Header", 0),
)


class TableV31RegistryTests(unittest.TestCase):
    def test_cell_property_tools_are_grouped_before_fill_tools(self):
        source = [
            {"action_id": "표전체선없애기"},
            {"action_id": "하늘색배경채우기"},
            {"action_id": "빨간색강조선넣기"},
        ]

        result = registry.with_current_table_tools(source)
        action_ids = [item["action_id"] for item in result]

        self.assertEqual(
            action_ids[action_ids.index("열너비같게") + 1:action_ids.index("하늘색배경채우기")],
            ["한줄로입력설정", "한줄로입력해제", "제목셀설정", "제목셀해제"],
        )
        self.assertEqual(len(source), 3)


class HwpTableV31CellPropertyTests(unittest.TestCase):
    def test_cell_properties_are_applied_through_table_property_dialog(self):
        for action_id, property_name, value in CELL_ACTIONS:
            with self.subTest(action_id=action_id):
                cell = SimpleNamespace(HSet=object(), LineWrap=0, Header=0)
                shape = SimpleNamespace(HSet=object(), ShapeTableCell=cell)
                hwp = Mock()
                hwp.HParameterSet = SimpleNamespace(HShapeObject=shape)
                hwp.HAction.Execute.return_value = True

                bridge = HwpBridge()
                bridge.hwp = hwp
                bridge.ensure = Mock(return_value=(True, "OK"))

                ok, _ = bridge.apply_table_tool(action_id)

                self.assertTrue(ok)
                self.assertEqual(getattr(cell, property_name), value)
                hwp.HAction.GetDefault.assert_called_once_with("TablePropertyDialog", shape.HSet)
                hwp.HAction.Execute.assert_called_once_with("TablePropertyDialog", shape.HSet)


class WxsTableV31CellPropertyTests(unittest.TestCase):
    def test_cell_properties_are_applied_to_shape_table_cell_set(self):
        for action_id, property_name, value in CELL_ACTIONS:
            with self.subTest(action_id=action_id):
                pset = object()
                cell = {}
                bridge = object.__new__(WxsHwpBridge)
                bridge.ensure = Mock(return_value=(True, "OK"))
                bridge._item = Mock(return_value=cell)
                bridge._set_item = Mock(side_effect=lambda target, key, val: target.__setitem__(key, val))
                bridge._create_item_set = Mock()

                def execute(action_name, configure):
                    self.assertEqual(action_name, "TablePropertyDialog")
                    configure(pset)
                    return True, "OK"

                bridge._execute_table_action = execute

                ok, _ = bridge.apply_table_tool(action_id)

                self.assertTrue(ok)
                self.assertEqual(cell[property_name], value)
                bridge._item.assert_called_once_with(pset, "ShapeTableCell")
                bridge._create_item_set.assert_not_called()
                bridge._set_item.assert_called_once_with(cell, property_name, value)

    def test_missing_shape_table_cell_set_is_created(self):
        pset = object()
        cell = {}
        bridge = object.__new__(WxsHwpBridge)
        bridge.ensure = Mock(return_value=(True, "OK"))
        bridge._item = Mock(return_value=None)
        bridge._create_item_set = Mock(return_value=cell)
        bridge._set_item = Mock(side_effect=lambda target, key, val: target.__setitem__(key, val))

        def execute(_action_name, configure):
            configure(pset)
            return True, "OK"

        bridge._execute_table_action = execute

        ok, _ = bridge.apply_table_tool("제목셀설정")

        self.assertTrue(ok)
        self.assertEqual(cell["Header"], 1)
        bridge._create_item_set.assert_called_once_with(pset, "ShapeTableCell", "Cell")


if __name__ == "__main__":
    unittest.main()
