# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.features.cell_images import (
    IMAGE_SIZE_FIT_INSIDE,
    IMAGE_SIZE_FIT_WIDTH,
    IMAGE_SIZE_STRETCH_TO_CELL,
    calculate_picture_size,
    sort_image_paths,
)


class _FakeHwp:
    def __init__(self):
        self.insert_calls = []
        self.deleted = []

    def InsertPicture(self, *args):
        self.insert_calls.append(args)
        return object()

    def DeleteCtrl(self, ctrl):
        self.deleted.append(ctrl)


class _FakePictureBridge(HwpBridge):
    def __init__(self, cell_text=None):
        super().__init__()
        self.hwp = _FakeHwp()
        self.col = 1
        self.row = 1
        self.cell_text = cell_text or {}
        self.resize_calls = []

    def _cell_focus_hwp(self):
        return None

    def cell_validate_range_no_merged_cells(self, *_args):
        return None

    def cell_move_to_addr(self, col, row):
        self.col, self.row = int(col), int(row)

    def get_table_cell_addr(self, focus_before=True):
        return self.col, self.row, self.cell_addr_to_text(self.col, self.row)

    def cell_get_current_text(self):
        return self.cell_text.get((self.col, self.row), "")

    def _cell_try_cmd(self, _command, _delay=0.0):
        return True

    def _cell_get_pos(self):
        return self.col, self.row, 0

    def _cell_set_pos(self, pos):
        self.col, self.row = int(pos[0]), int(pos[1])
        return True

    def cell_move_right(self):
        self.col += 1

    def cell_move_left(self):
        self.col -= 1

    def cell_move_down(self):
        self.row += 1

    def cell_get_current_inner_size(self):
        return {"width": 100, "height": 80, "inner_width": 100, "inner_height": 80}

    def _resize_picture_control(self, ctrl, size_mode, cell_size, picture_info=None):
        self.resize_calls.append((ctrl, size_mode, cell_size, picture_info))
        return cell_size["inner_width"], cell_size["inner_height"]


class _FakeParameterSet:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def clone(self):
        values = {}
        for key, value in self.values.items():
            values[key] = value.clone() if isinstance(value, _FakeParameterSet) else value
        return _FakeParameterSet(values)

    def Item(self, name):
        if name not in self.values:
            raise KeyError(name)
        return self.values[name]

    def SetItem(self, name, value):
        self.values[name] = value


class _FakePictureControl:
    CtrlID = "gso"

    def __init__(self, list_id, width, height, original_width, original_height, fail_assign=False):
        self.list_id = int(list_id)
        self.Next = None
        self.fail_assign = fail_assign
        self.assignments = 0
        self._props = _FakeParameterSet({
            "Width": width,
            "Height": height,
            "TreatAsChar": True,
            "ShapeDrawImageAttr": _FakeParameterSet({
                "OriginalSizeX": original_width,
                "OriginalSizeY": original_height,
            }),
        })

    @property
    def Properties(self):
        return self._props.clone()

    @Properties.setter
    def Properties(self, value):
        self.assignments += 1
        if self.fail_assign:
            self.fail_assign = False
            raise RuntimeError("속성 적용 실패")
        self._props = value.clone()

    def GetAnchorPos(self, _anchor_type):
        return _FakeParameterSet({"List": self.list_id, "Para": 0, "Pos": 0})

    def size(self):
        return self._props.Item("Width"), self._props.Item("Height")


class _FakeControlHwp:
    def __init__(self, controls):
        self.HeadCtrl = controls[0] if controls else None
        for current, next_control in zip(controls, controls[1:]):
            current.Next = next_control


class _FakeRefitBridge(HwpBridge):
    def __init__(self, controls, cell_sizes=None):
        super().__init__()
        self.hwp = _FakeControlHwp(controls)
        self.col = 1
        self.row = 1
        self.cell_sizes = cell_sizes or {}

    def _cell_focus_hwp(self):
        return None

    def cell_validate_range_no_merged_cells(self, *_args):
        return None

    def cell_move_to_addr(self, col, row):
        self.col, self.row = int(col), int(row)

    def get_table_cell_addr(self, focus_before=True):
        return self.col, self.row, self.cell_addr_to_text(self.col, self.row)

    def _cell_get_pos(self):
        return self.row * 10 + self.col, 0, 0

    def cell_get_current_inner_size(self):
        width, height = self.cell_sizes.get((self.col, self.row), (100, 80))
        return {"width": width, "height": height, "inner_width": width, "inner_height": height}

    def cell_move_right(self):
        self.col += 1

    def cell_move_left(self):
        self.col -= 1

    def cell_move_down(self):
        self.row += 1


class CellImageTests(unittest.TestCase):
    def test_natural_filename_order(self):
        ordered = sort_image_paths(["그림10.png", "그림2.png", "그림1.png"])
        self.assertEqual([os.path.basename(path) for path in ordered], ["그림1.png", "그림2.png", "그림10.png"])

    def test_insert_uses_selected_cells_in_row_order(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for name in ("1.png", "2.png", "3.png"):
                path = os.path.join(folder, name)
                open(path, "wb").close()
                paths.append(path)

            bridge = _FakePictureBridge()
            result = bridge.insert_pictures_into_cell_range(paths, 1, 1, 2, 2)

        self.assertEqual(result["inserted"], 3)
        self.assertEqual([call[0] for call in bridge.hwp.insert_calls], paths)
        self.assertTrue(all(call[1:] == (True, 3, False, False, 0) for call in bridge.hwp.insert_calls))

    def test_nonempty_cell_stops_before_insertion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "1.png")
            open(path, "wb").close()
            bridge = _FakePictureBridge({(1, 1): "기존 내용"})
            with self.assertRaisesRegex(RuntimeError, "A1 셀에 내용"):
                bridge.insert_pictures_into_cell_range([path], 1, 1, 1, 1)

        self.assertEqual(bridge.hwp.insert_calls, [])

    def test_picture_size_modes(self):
        self.assertEqual(calculate_picture_size(IMAGE_SIZE_FIT_INSIDE, 100, 80, 200, 100), (100, 50))
        self.assertEqual(calculate_picture_size(IMAGE_SIZE_FIT_WIDTH, 100, 80, 200, 100), (100, 50))
        self.assertEqual(calculate_picture_size(IMAGE_SIZE_STRETCH_TO_CELL, 100, 80, 200, 100), (100, 80))
        self.assertEqual(calculate_picture_size(IMAGE_SIZE_FIT_INSIDE, 100, 80, 100, 200), (40, 80))
        self.assertEqual(calculate_picture_size(IMAGE_SIZE_FIT_WIDTH, 100, 80, 100, 200), (100, 200))

    def test_stretch_insert_uses_exact_cell_size_option(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "1.png")
            open(path, "wb").close()
            bridge = _FakePictureBridge()
            bridge.insert_pictures_into_cell_range(
                [path], 1, 1, 1, 1, size_mode=IMAGE_SIZE_STRETCH_TO_CELL
            )

        self.assertEqual(bridge.hwp.insert_calls[0][2], 2)


    def test_fit_width_insert_resizes_after_safe_cell_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "1.png")
            open(path, "wb").close()
            bridge = _FakePictureBridge()
            bridge.insert_pictures_into_cell_range(
                [path], 1, 1, 1, 1, size_mode=IMAGE_SIZE_FIT_WIDTH
            )

        self.assertEqual(bridge.hwp.insert_calls[0][2], 3)
        self.assertEqual(len(bridge.resize_calls), 1)
        self.assertEqual(bridge.resize_calls[0][1], IMAGE_SIZE_FIT_WIDTH)

    def test_refit_resizes_one_picture_and_skips_empty_or_multiple_cells(self):
        first = _FakePictureControl(11, 50, 25, 200, 100)
        multiple_a = _FakePictureControl(21, 20, 20, 100, 100)
        multiple_b = _FakePictureControl(21, 30, 30, 100, 100)
        last = _FakePictureControl(22, 30, 60, 100, 200)
        bridge = _FakeRefitBridge([first, multiple_a, multiple_b, last])
        progress = []

        result = bridge.refit_pictures_in_cell_range(
            1, 1, 2, 2, size_mode=IMAGE_SIZE_FIT_INSIDE,
            progress_callback=lambda done, total: progress.append((done, total)),
        )

        self.assertEqual(first.size(), (100, 50))
        self.assertEqual(last.size(), (40, 80))
        self.assertEqual(result["resized"], 2)
        self.assertEqual(result["empty"], 1)
        self.assertEqual(result["multiple"], 1)
        self.assertEqual(progress[-1], (4, 4))

    def test_refit_rolls_back_previous_picture_when_later_resize_fails(self):
        first = _FakePictureControl(11, 50, 25, 200, 100)
        second = _FakePictureControl(12, 30, 60, 100, 200, fail_assign=True)
        bridge = _FakeRefitBridge([first, second])

        with self.assertRaisesRegex(RuntimeError, "되돌렸습니다"):
            bridge.refit_pictures_in_cell_range(
                1, 1, 2, 1, size_mode=IMAGE_SIZE_STRETCH_TO_CELL
            )

        self.assertEqual(first.size(), (50, 25))


if __name__ == "__main__":
    unittest.main()
