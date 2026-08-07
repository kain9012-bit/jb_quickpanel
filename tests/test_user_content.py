# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from pathlib import Path

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.services.user_content import UserContentError, UserContentStore


class UserContentStoreTests(unittest.TestCase):
    def test_added_hwp_file_is_copied_and_survives_original_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            source = Path(folder) / "원본.hwp"
            source.write_bytes(b"hwp-test")
            store = UserContentStore(root)

            item = store.add_file("style", "내 서식", source)
            source.unlink()
            listed = store.list_items("style")

            self.assertEqual(item["title"], "내 서식")
            self.assertEqual(len(listed), 1)
            self.assertTrue(Path(listed[0]["file"]).is_file())
            self.assertEqual(Path(listed[0]["file"]).read_bytes(), b"hwp-test")

    def test_duplicate_title_is_rejected_and_delete_removes_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "양식.hwpx"
            source.write_bytes(b"hwpx-test")
            store = UserContentStore(Path(folder) / "data")
            item = store.add_file("form", "회의 양식", source)
            copied = Path(store.list_items("form")[0]["file"])

            with self.assertRaisesRegex(UserContentError, "같은 이름"):
                store.add_file("form", "회의 양식", source)

            store.delete_item("form", item["id"])
            self.assertFalse(copied.exists())
            self.assertEqual(store.list_items("form"), [])

    def test_page_preset_add_update_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = UserContentStore(Path(folder) / "data")
            item = store.add_page(
                "보고서 여백",
                {
                    "top": 10,
                    "header": 9.95,
                    "left": 20,
                    "gutter": 0,
                    "right": 20,
                    "footer": 10,
                    "bottom": 15,
                },
            )
            self.assertEqual(store.list_items("page")[0]["margins"]["header"], 9.9)

            store.update_item("page", item["id"], title="수정 여백", margins={
                "top": 11,
                "header": 10,
                "left": 21,
                "gutter": 1,
                "right": 22,
                "footer": 9,
                "bottom": 16,
            })
            updated = store.list_items("page")[0]
            self.assertEqual(updated["title"], "수정 여백")
            self.assertEqual(updated["margins"]["gutter"], 1.0)

            invalid = dict(updated["margins"])
            invalid["left"] = 101
            with self.assertRaisesRegex(UserContentError, "0~100mm"):
                store.update_item("page", item["id"], title="적용되면 안 됨", margins=invalid)
            self.assertEqual(store.list_items("page")[0]["title"], "수정 여백")

    def test_save_failures_roll_back_in_memory_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            store = UserContentStore(Path(folder) / "data")
            item = store.add_page("기존 여백", {})

            original_save = store._save
            store._save = lambda: (_ for _ in ()).throw(RuntimeError("save failed"))
            try:
                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    store.add_page("추가 실패", {})
                self.assertEqual([entry["title"] for entry in store.list_items("page")], ["기존 여백"])

                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    store.update_item("page", item["id"], title="수정 실패")
                self.assertEqual(store.list_items("page")[0]["title"], "기존 여백")

                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    store.delete_item("page", item["id"])
                self.assertEqual(store.list_items("page")[0]["title"], "기존 여백")
            finally:
                store._save = original_save


class _FakeFileOpenSave:
    def __init__(self):
        self.HSet = object()
        self.FileName = ""
        self.Format = ""
        self.Attributes = 0


class _FakePageDef:
    pass


class _FakeSecDef:
    def __init__(self):
        self.HSet = object()
        self.PageDef = _FakePageDef()


class _FakeParameterSet:
    def __init__(self):
        self.HFileOpenSave = _FakeFileOpenSave()
        self.HSecDef = _FakeSecDef()


class _FakeAction:
    def __init__(self, owner):
        self.owner = owner
        self.calls = []

    def GetDefault(self, action, _hset):
        self.calls.append(("default", action))
        return True

    def Execute(self, action, _hset):
        self.calls.append(("execute", action))
        if action == "FileSaveBlock_S":
            path = self.owner.HParameterSet.HFileOpenSave.FileName
            Path(path).write_bytes(b"saved-block")
        return True


class _FakeHwp:
    def __init__(self, selection_mode=1):
        self.SelectionMode = selection_mode
        self.HParameterSet = _FakeParameterSet()
        self.HAction = _FakeAction(self)

    def MiliToHwpUnit(self, value):
        return int(float(value) * 100)


class HwpUserContentTests(unittest.TestCase):
    def test_selected_block_is_saved_only_when_selection_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            selected_bridge = HwpBridge()
            selected_bridge.hwp = _FakeHwp(selection_mode=1)
            path = os.path.join(folder, "block.hwp")
            ok, _msg = selected_bridge.save_selected_block(path)
            self.assertTrue(ok)
            self.assertEqual(Path(path).read_bytes(), b"saved-block")

            empty_bridge = HwpBridge()
            empty_bridge.hwp = _FakeHwp(selection_mode=0)
            ok, msg = empty_bridge.save_selected_block(os.path.join(folder, "empty.hwp"))
            self.assertFalse(ok)
            self.assertIn("블록 지정", msg)

    def test_page_margins_apply_only_margin_fields(self):
        bridge = HwpBridge()
        bridge.hwp = _FakeHwp()
        margins = {
            "top": 10,
            "header": 9,
            "left": 20,
            "gutter": 1,
            "right": 21,
            "footer": 8,
            "bottom": 15,
        }
        ok, _msg = bridge.apply_page_margins(margins)
        self.assertTrue(ok)
        page = bridge.hwp.HParameterSet.HSecDef.PageDef
        self.assertEqual(page.LeftMargin, 2000)
        self.assertEqual(page.RightMargin, 2100)
        self.assertEqual(page.TopMargin, 1000)
        self.assertEqual(page.BottomMargin, 1500)
        self.assertEqual(page.HeaderLen, 900)
        self.assertEqual(page.FooterLen, 800)
        self.assertEqual(page.GutterLen, 100)


if __name__ == "__main__":
    unittest.main()
