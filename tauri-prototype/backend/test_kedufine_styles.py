import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.server import _set_target_mode, dispatch


class FakeTracker:
    def state(self):
        return {"active": False}


class FakeBridge:
    pass


class FakeKedufineBridge:
    def __init__(self):
        self.inserted = []

    def insert_file(self, path: str):
        self.inserted.append(path)
        return True, "ok"


class KedufineStyleTests(unittest.TestCase):
    def tearDown(self):
        _set_target_mode("hwp")

    def test_style_catalog_keeps_builtin_and_user_styles_in_kedufine(self):
        with tempfile.TemporaryDirectory() as folder:
            builtin = Path(folder) / "builtin.hwp"
            custom = Path(folder) / "custom.hwp"
            builtin.write_bytes(b"test")
            custom.write_bytes(b"test")
            records = [
            {
                "key": "builtin:title",
                "id": "title",
                "title": "제목박스",
                "source": "builtin",
                "user_item": False,
                "file_path": str(builtin),
                "kedufine_file_path": str(builtin),
                "manual_file_path": str(builtin),
                "thumb_path": "",
            },
            {
                "key": "user:custom",
                "id": "custom",
                "title": "내 결재 안내",
                "source": "user",
                "user_item": True,
                "file_path": str(custom),
                "kedufine_file_path": str(custom),
                "manual_file_path": str(custom),
                "thumb_path": "",
            },
            ]
            _set_target_mode("kedufine")
            with patch("backend.server._style_records", return_value=records):
                ok, _message, data = dispatch("style_catalog", {}, FakeBridge(), FakeTracker())

        self.assertTrue(ok)
        self.assertEqual([item["key"] for item in data["items"]], ["builtin:title", "user:custom"])

    def test_user_style_is_inserted_through_kedufine_bridge(self):
        kedufine = FakeKedufineBridge()
        with tempfile.TemporaryDirectory() as temp_dir:
            style_path = Path(temp_dir) / "custom.hwp"
            style_path.write_bytes(b"test")
            record = {
                "key": "user:custom",
                "id": "custom",
                "title": "내 결재 안내",
                "source": "user",
                "user_item": True,
                "file_path": str(style_path),
                "kedufine_file_path": str(style_path),
                "manual_file_path": str(style_path),
                "thumb_path": "",
            }
            _set_target_mode("kedufine")

            with (
                patch("backend.server._WXS_BRIDGE", kedufine),
                patch("backend.server._find_style_record", return_value=record),
            ):
                ok, message, data = dispatch(
                    "insert_style",
                    {"style_key": "user:custom"},
                    FakeBridge(),
                    FakeTracker(),
                )

        self.assertTrue(ok)
        self.assertEqual(message, "서식 삽입 완료: 내 결재 안내")
        self.assertEqual(data["style_key"], "user:custom")
        self.assertEqual(kedufine.inserted, [str(style_path)])

    def test_builtin_style_uses_hwp_in_kedufine(self):
        kedufine = FakeKedufineBridge()
        with tempfile.TemporaryDirectory() as folder:
            hwp = Path(folder) / "builtin.hwp"
            hwp.write_bytes(b"test")
            record = {
                "key": "builtin:title", "id": "title", "title": "제목박스",
                "source": "builtin", "user_item": False,
                "file_path": str(Path(folder) / "builtin.hwpx"),
                "kedufine_file_path": str(hwp), "thumb_path": "",
                "manual_file_path": str(hwp),
            }
            _set_target_mode("kedufine")
            with patch("backend.server._WXS_BRIDGE", kedufine), patch("backend.server._find_style_record", return_value=record):
                ok, _message, _data = dispatch("insert_style", {"style_key": "builtin:title"}, FakeBridge(), FakeTracker())
        self.assertTrue(ok)
        self.assertEqual(kedufine.inserted, [str(hwp)])

    def test_hwpx_only_style_is_hidden_and_cannot_be_inserted_in_kedufine(self):
        kedufine = FakeKedufineBridge()
        with tempfile.TemporaryDirectory() as folder:
            hwpx = Path(folder) / "custom.hwpx"
            hwpx.write_bytes(b"sample")
            record = {
                "key": "user:custom", "id": "custom", "title": "내 HWPX 서식",
                "source": "user", "user_item": True,
                "file_path": str(hwpx), "kedufine_file_path": "", "manual_file_path": "", "thumb_path": "",
            }
            _set_target_mode("kedufine")
            with patch("backend.server._style_records", return_value=[record]):
                ok, _, data = dispatch("style_catalog", {}, FakeBridge(), FakeTracker())
            self.assertTrue(ok)
            self.assertEqual(len(data["items"]), 1)
            self.assertFalse(data["items"][0]["available"])
            with patch("backend.server._WXS_BRIDGE", kedufine), patch("backend.server._find_style_record", return_value=record):
                ok, message, _ = dispatch("insert_style", {"style_key": "user:custom"}, FakeBridge(), FakeTracker())
            self.assertFalse(ok)
            self.assertIn("HWP", message)
            self.assertEqual(kedufine.inserted, [])

    def test_hwpx_style_registration_is_rejected_before_preview(self):
        _set_target_mode("kedufine")
        with patch("backend.server.FEATURES.add_user_file") as add:
            ok, message, _ = dispatch("user_add_file", {"kind": "style", "title": "서식", "source_path": "custom.hwpx"}, FakeBridge(), FakeTracker())
        self.assertFalse(ok)
        self.assertIn("파일에서 추가", message)
        add.assert_not_called()

    def test_block_registration_explains_general_hwp_requirement(self):
        _set_target_mode("kedufine")

        ok, message, _data = dispatch(
            "user_add_block",
            {"kind": "style", "title": "내 서식"},
            FakeBridge(),
            FakeTracker(),
        )

        self.assertFalse(ok)
        self.assertIn("블록 지정한 내용", message)
        self.assertIn("일반 한글", message)


if __name__ == "__main__":
    unittest.main()
