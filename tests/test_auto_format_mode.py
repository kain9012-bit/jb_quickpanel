import unittest

from src.jb_quickpanel.features.auto_format import transform_auto_format_text


class AutoFormatModeTests(unittest.TestCase):
    def test_keeps_existing_tag_mode_as_first_priority(self):
        items, changed, mode = transform_auto_format_text(
            "(본문) - 태그가 있는 문단\n1. 태그가 없는 문단"
        )
        self.assertEqual(mode, "tagged")
        self.assertEqual(changed, 1)
        self.assertEqual(items[0]["tag"], "본문")
        self.assertIsNone(items[1]["tag"])

    def test_uses_inference_only_when_no_tag_exists(self):
        items, changed, mode = transform_auto_format_text(
            "2026년 운영계획\n1. 추진 배경\n- 세부 내용"
        )
        self.assertEqual(mode, "inferred")
        self.assertEqual(changed, 3)
        self.assertEqual([item["tag"] for item in items], ["문서제목", "제목", "본문"])


if __name__ == "__main__":
    unittest.main()
