import unittest
from unittest.mock import patch

from backend.server import FEATURES, _set_target_mode, dispatch


class FakeTracker:
    pass


class FakeBridge:
    def __init__(self):
        self.inserted = []

    def insert_text(self, text):
        self.inserted.append(text)
        return True, "ok"


class KedufineFormTests(unittest.TestCase):
    def tearDown(self):
        _set_target_mode("hwp")

    def test_builtin_catalog_is_text_grouped_into_three_internal_and_eight_outgoing(self):
        with patch("full_features.UserContentStore") as store_type:
            store_type.return_value.list_items.return_value = []
            forms = FEATURES.kedufine_form_catalog()
        self.assertEqual(len(forms), 11)
        self.assertEqual(sum(item["category"] == "internal" for item in forms), 3)
        self.assertEqual(sum(item["category"] == "outgoing" for item in forms), 8)
        self.assertEqual(forms[0]["preview"], "가. 추진 기간\n나. 추진 대상\n다. 주요 내용\n라. 추진 방법")
        for form in forms:
            self.assertTrue(form["body"].startswith("1. 관련:"))
            self.assertIn("\n2. ", form["body"])
            self.assertNotIn("file_path", form)
            self.assertNotIn("[", form["preview"])

    def test_kedufine_inserts_body_text_only(self):
        bridge = FakeBridge()
        _set_target_mode("kedufine")
        with patch("backend.server._WXS_BRIDGE", bridge), patch("full_features.UserContentStore") as store_type:
            store_type.return_value.list_items.return_value = []
            ok, _, data = dispatch("kedufine_form_catalog", {}, bridge, FakeTracker())
            self.assertTrue(ok)
            self.assertEqual(len(data["items"]), 11)
            self.assertNotIn("document_title", data["items"][0])
            first = data["items"][0]
            ok, _, _ = dispatch("insert_kedufine_form", {"item_key": first["key"]}, bridge, FakeTracker())
            self.assertTrue(ok)
            self.assertEqual(bridge.inserted, [first["body"].replace("\n", "\r\n")])
            ok, _, _ = dispatch("copy_kedufine_form_title", {"item_key": first["key"]}, bridge, FakeTracker())
            self.assertFalse(ok)

        _set_target_mode("hwp")
        ok, _, _ = dispatch("insert_kedufine_form", {"item_key": first["key"]}, bridge, FakeTracker())
        self.assertFalse(ok)
        self.assertEqual(len(bridge.inserted), 1)

    def test_user_text_and_legacy_form_catalog(self):
        records = [
            {"id": "text", "title": "내 기안문", "category": "internal", "body": "1. 관련: 예시\n2. 본문"},
            {"id": "old", "title": "옛 기안문", "file": "C:/old.hwp"},
        ]
        with patch("full_features.UserContentStore") as store_type:
            store_type.return_value.list_items.return_value = records
            forms = FEATURES.kedufine_form_catalog()
        text, legacy = forms[-2:]
        self.assertEqual(text["category"], "internal")
        self.assertEqual(text["body"], records[0]["body"])
        self.assertEqual(text["preview"], "1. 관련\n2. 본문")
        self.assertFalse(text["legacy"])
        self.assertEqual(legacy["category"], "legacy")
        self.assertTrue(legacy["legacy"])
        self.assertNotIn("file_path", legacy)

        bridge = FakeBridge()
        _set_target_mode("kedufine")
        with patch("backend.server._WXS_BRIDGE", bridge), patch.object(FEATURES, "kedufine_form_catalog", return_value=forms):
            ok, message, _ = dispatch("insert_kedufine_form", {"item_key": legacy["key"]}, bridge, FakeTracker())
        self.assertFalse(ok)
        self.assertIn("텍스트", message)
        self.assertEqual(bridge.inserted, [])

    def test_save_user_text_form_passes_body_and_category(self):
        item = {"id": "new", "title": "내 양식"}
        with patch.object(FEATURES, "save_kedufine_text_form", return_value=item) as save:
            ok, _, _ = dispatch("user_save_kedufine_form", {
                "item_id": "", "title": "내 양식", "category": "outgoing", "body": "1. 관련: 예시",
            }, FakeBridge(), FakeTracker())
        self.assertTrue(ok)
        save.assert_called_once_with("", "내 양식", "outgoing", "1. 관련: 예시")


if __name__ == "__main__":
    unittest.main()
