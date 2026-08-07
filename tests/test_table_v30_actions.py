# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge
from src.jb_quickpanel.features import registry


LINE_TYPES = {"None": 0, "Solid": 1}


def make_hwp_bridge(run_result=True):
    shape = SimpleNamespace(
        HSet=object(),
        TypeVert=LINE_TYPES["Solid"],
        TypeHorz=LINE_TYPES["Solid"],
        BorderTypeBottom=LINE_TYPES["Solid"],
        BorderTypeTop=LINE_TYPES["Solid"],
        BorderTypeRight=LINE_TYPES["Solid"],
        BorderTypeLeft=LINE_TYPES["Solid"],
    )
    hwp = Mock()
    hwp.HParameterSet = SimpleNamespace(HCellBorderFill=shape)
    hwp.HwpLineType.side_effect = LINE_TYPES.__getitem__
    hwp.HAction.Run.return_value = run_result

    bridge = HwpBridge()
    bridge.hwp = hwp
    bridge.ensure = Mock(return_value=(True, "OK"))
    return bridge, shape, hwp


def make_wxs_line_bridge():
    pset = {"TypeVert": LINE_TYPES["Solid"], "TypeHorz": LINE_TYPES["Solid"]}
    bridge = object.__new__(WxsHwpBridge)
    bridge.ensure = Mock(return_value=(True, "OK"))
    bridge._hwp_line_type = Mock(side_effect=LINE_TYPES.__getitem__)

    def set_any(target, keys, value):
        for key in keys:
            target[key] = value
        return True

    def execute(_action_name, configure):
        configure(pset)
        return True, "OK"

    bridge._safe_set_any = set_any
    bridge._execute_table_action = execute
    return bridge, pset


class TableV30RegistryTests(unittest.TestCase):
    def test_new_tools_are_ordered_before_all_none_and_fill_tools(self):
        source = [
            {"action_id": "오른쪽바깥선없애기"},
            {"action_id": "표전체선없애기"},
            {"action_id": "하늘색배경채우기"},
            {"action_id": "연한노랑색배경채우기"},
            {"action_id": "빨간색강조선넣기"},
        ]

        result = registry.with_current_table_tools(source)

        self.assertEqual(
            [item["action_id"] for item in result],
            [
                "오른쪽바깥선없애기",
                "내부세로선없애기",
                "내부가로선없애기",
                "표전체선없애기",
                "행높이같게",
                "열너비같게",
                "한줄로입력설정",
                "한줄로입력해제",
                "제목셀설정",
                "제목셀해제",
                "하늘색배경채우기",
                "연한노랑색배경채우기",
                "배경색없애기",
                "빨간색강조선넣기",
            ],
        )
        self.assertEqual(len(source), 5)


class HwpTableV30ActionTests(unittest.TestCase):
    def test_internal_vertical_and_horizontal_lines_are_removed_independently(self):
        bridge, shape, hwp = make_hwp_bridge()

        ok_vertical, _ = bridge.apply_table_tool("내부세로선없애기")
        self.assertTrue(ok_vertical)
        self.assertEqual(shape.TypeVert, LINE_TYPES["None"])
        self.assertEqual(shape.TypeHorz, LINE_TYPES["Solid"])

        shape.TypeVert = LINE_TYPES["Solid"]
        ok_horizontal, _ = bridge.apply_table_tool("내부가로선없애기")
        self.assertTrue(ok_horizontal)
        self.assertEqual(shape.TypeVert, LINE_TYPES["Solid"])
        self.assertEqual(shape.TypeHorz, LINE_TYPES["None"])
        self.assertEqual(hwp.HAction.Execute.call_count, 2)

    def test_equal_size_actions_use_hwp_distribution_commands(self):
        bridge, _, hwp = make_hwp_bridge()

        self.assertTrue(bridge.apply_table_tool("행높이같게")[0])
        self.assertTrue(bridge.apply_table_tool("열너비같게")[0])

        self.assertEqual(
            hwp.HAction.Run.call_args_list,
            [call("TableDistributeCellHeight"), call("TableDistributeCellWidth")],
        )

    def test_equal_size_action_reports_invalid_selection(self):
        bridge, _, _ = make_hwp_bridge(run_result=False)

        ok, message = bridge.apply_table_tool("행높이같게")

        self.assertFalse(ok)
        self.assertIn("직사각형 셀 범위", message)


class WxsTableV30ActionTests(unittest.TestCase):
    def test_internal_lines_are_removed_independently(self):
        bridge, pset = make_wxs_line_bridge()

        self.assertTrue(bridge.apply_table_tool("내부세로선없애기")[0])
        self.assertEqual(pset["TypeVert"], LINE_TYPES["None"])
        self.assertEqual(pset["TypeHorz"], LINE_TYPES["Solid"])

        pset["TypeVert"] = LINE_TYPES["Solid"]
        self.assertTrue(bridge.apply_table_tool("내부가로선없애기")[0])
        self.assertEqual(pset["TypeVert"], LINE_TYPES["Solid"])
        self.assertEqual(pset["TypeHorz"], LINE_TYPES["None"])

    def test_equal_size_actions_use_wxs_run_commands(self):
        bridge = object.__new__(WxsHwpBridge)
        bridge.ensure = Mock(return_value=(True, "OK"))
        bridge.run_cmd = Mock(return_value=(True, "OK"))

        self.assertTrue(bridge.apply_table_tool("행높이같게")[0])
        self.assertTrue(bridge.apply_table_tool("열너비같게")[0])

        self.assertEqual(
            bridge.run_cmd.call_args_list,
            [call("TableDistributeCellHeight"), call("TableDistributeCellWidth")],
        )


if __name__ == "__main__":
    unittest.main()
