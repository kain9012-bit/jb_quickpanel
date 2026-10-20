import unittest

from src.jb_quickpanel.features.auto_format import transform_auto_format_text, parse_pipe_table_lines
from src.jb_quickpanel.features.untagged_report import strip_markdown_emphasis


class AutoFormatContentSafetyTests(unittest.TestCase):
    def test_repeated_symbols_in_names_are_not_removed(self):
        for content in ("○○부에서 확인", "ㅇㅇ협회 협조", "□□기관 안내"):
            for prefix in ("1 추진 배경\n", "(본문) "):
                with self.subTest(content=content, prefix=prefix):
                    items, _, _ = transform_auto_format_text(prefix + content)
                    self.assertIn(content, items[-1]["text"])

    def test_dates_and_english_names_are_not_headings(self):
        for value in ("9. 30.(수) 안내 예정", "9.   30.(수) 안내 예정", "11. 5. 안내", "I. Introduction", "V. Sharma 참석"):
            with self.subTest(value=value):
                items, _, _ = transform_auto_format_text("1 추진 일정\n" + value)
                self.assertEqual(items[-1]["tag"], "본문")
                self.assertIn(value, items[-1]["text"])

    def test_negative_numbers_keep_their_sign_in_both_input_modes(self):
        for content in ("-3.5%p 감소", "-5℃ 기준"):
            for prefix in ("1 추진 배경\n", "(본문) "):
                with self.subTest(content=content, prefix=prefix):
                    items, _, _ = transform_auto_format_text(prefix + content)
                    self.assertIn(content, items[-1]["text"])

    def test_existing_bullets_and_custom_markers_still_work(self):
        for content in ("- 본문", "* 본문", "○ 본문", "ㅇ 본문", "□ 본문"):
            items, _, _ = transform_auto_format_text("(본문) " + content)
            self.assertEqual(items[-1]["text"].strip(), "- 본문")
        for content in ("◆ 내용", "◆내용"):
            items, _, _ = transform_auto_format_text("(본문) " + content, {"roles": {"body": {"marker": "custom", "custom_marker": "◆"}}})
            self.assertEqual(items[-1]["text"].strip(), "◆ 내용")

    def test_emphasis_preserves_filenames_and_code(self):
        source = "report__final__v2.pdf와 `a**b**c` 및 `__name__`"
        self.assertEqual(strip_markdown_emphasis(source), source)
        self.assertEqual(strip_markdown_emphasis("**중요**합니다. __확인 필요__"), "중요합니다. 확인 필요")

    def test_dash_data_row_is_not_a_markdown_separator(self):
        rows, cols = parse_pipe_table_lines(["| 항목 | 값 |", "| :--- | ---: |", "| - | - |"])
        self.assertEqual((rows, cols), ([["항목", "값"], ["-", "-"]], 2))
        for prefix, suffix in (("1 역할\n", ""), ("(표시작)\n", "\n(표끝)")):
            items, _, _ = transform_auto_format_text(prefix + "항목 | 값\n- | -" + suffix)
            self.assertEqual(next(item for item in items if item["tag"] == "표")["rows"][-1], ["-", "-"])

    def test_escaped_pipes_and_windows_paths_roundtrip(self):
        lines = ["항목 | 설명", r"A | 조건 A\|B", r"B | C:\work\file.txt", r"C | 끝\|", r"D | \\server\share"]
        expected = [["항목", "설명"], ["A", "조건 A|B"], ["B", r"C:\work\file.txt"], ["C", "끝|"], ["D", r"\\server\share"]]
        for source in ("1 역할\n" + "\n".join(lines), "(표시작)\n" + "\n".join(lines) + "\n(표끝)"):
            items, _, _ = transform_auto_format_text(source)
            table = next(item for item in items if item["tag"] == "표")
            self.assertEqual(table["cols"], 2)
            self.assertEqual(table["rows"], expected)

    def test_table_caption_and_missing_end_tag_do_not_swallow_body(self):
        items, _, _ = transform_auto_format_text("(표시작) 표 설명\n항목 | 값\nA | B\n(본문) 다음 문장\n(참고) ※ 확인")
        self.assertEqual(items[0]["text"], "표 설명")
        self.assertEqual(items[1]["rows"], [["항목", "값"], ["A", "B"]])
        self.assertEqual([item["tag"] for item in items[-2:]], ["본문", "참고"])


if __name__ == "__main__":
    unittest.main()
