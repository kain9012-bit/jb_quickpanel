import unittest

from backend.server import _style_records
from backend.auto_format_runner import (
    copy_report_prompt_to_clipboard,
    run_auto_format,
)


class FakeAutoFormatBridge:
    def __init__(self, selected_text, inspection=None):
        self.selected_text = selected_text
        self.inspection = inspection or (False, {})
        self.calls = []

    def apply_basic_report_page_setup(self):
        self.calls.append(("page_setup",))
        return True, "page setup"

    def get_selected_text(self):
        self.calls.append(("get_selected_text",))
        return True, self.selected_text

    def inspect_selected_report_content(self):
        self.calls.append(("inspect",))
        return self.inspection

    def delete_selection(self):
        self.calls.append(("delete_selection",))
        return True, "deleted"

    def ensure_cursor_outside_table(self):
        self.calls.append(("outside_table",))
        return True, "outside"

    def run_first_supported(self, commands):
        self.calls.append(("cancel_table_selection", tuple(commands)))
        return True, commands[0]

    def insert_document_title_box(self, file_path, title_text):
        self.calls.append(("document_title", file_path, title_text))
        return True, "document title"

    def insert_section_title_box(self, file_path, number_text, title_text):
        self.calls.append(("section_title", file_path, number_text, title_text))
        return True, "section title"

    def insert_report_line(self, text, font_name, font_size_pt, bold=False):
        self.calls.append(("report_line", text, font_name, font_size_pt, bold))
        return True, "report line"

    def apply_indent_at_caret_for_current_para(self, caret_offset):
        self.calls.append(("indent", caret_offset))
        return True, "indent"

    def insert_text(self, text):
        self.calls.append(("insert_text", text))
        return True, "text"

    def insert_pipe_table(self, rows, font_name, font_size_pt):
        self.calls.append(("pipe_table", rows, font_name, font_size_pt))
        return True, "table"

    def format_native_report_tables(self, positions, progress=None, cancelled=None):
        self.calls.append(("native_tables", positions))
        if progress:
            progress(1, len(positions))
        return True, "native tables"

    def apply_inferred_report_paragraphs(
        self,
        paragraphs,
        items,
        title_box_file=None,
        section_box_file=None,
        progress=None,
        cancelled=None,
    ):
        self.calls.append(
            (
                "inferred_paragraphs",
                len(paragraphs),
                [item.get("tag") for item in items],
                title_box_file,
                section_box_file,
            )
        )
        if progress:
            progress(len(paragraphs), len(paragraphs))
        return True, "paragraphs"


class AutoFormatRunnerTests(unittest.TestCase):
    def test_tagged_report_uses_existing_boxes_and_paragraph_styles(self):
        bridge = FakeAutoFormatBridge(
            "(문서제목) 테스트 계획\n"
            "(제목) 1. 추진 배경\n"
            "(본문) 내용"
        )
        ok, message, data = run_auto_format(
            bridge,
            _style_records(),
            cancelled=lambda: False,
        )
        self.assertTrue(ok, message)
        self.assertEqual(data["mode"], "tagged")
        call_names = [call[0] for call in bridge.calls]
        self.assertIn("document_title", call_names)
        self.assertIn("section_title", call_names)
        self.assertIn("report_line", call_names)
        self.assertIn("indent", call_names)

    def test_inferred_report_preserves_and_formats_native_tables(self):
        paragraphs = [
            {"text": "테스트 계획"},
            {"text": "1. 추진 배경"},
            {"text": "- 내용"},
        ]
        bridge = FakeAutoFormatBridge(
            "테스트 계획\n1. 추진 배경\n- 내용",
            inspection=(
                True,
                {
                    "paragraphs": paragraphs,
                    "native_table_positions": [(0, 4, 0)],
                },
            ),
        )
        ok, message, data = run_auto_format(
            bridge,
            _style_records(),
            cancelled=lambda: False,
        )
        self.assertTrue(ok, message)
        self.assertEqual(data["mode"], "inferred")
        self.assertEqual(data["native_table_count"], 1)
        call_names = [call[0] for call in bridge.calls]
        self.assertIn("native_tables", call_names)
        self.assertIn("inferred_paragraphs", call_names)
        self.assertNotIn("delete_selection", call_names)

    def test_table_exit_is_settled_before_following_paragraph(self):
        bridge = FakeAutoFormatBridge(
            "(표시작)\n"
            "항목 | 내용\n"
            "A | B\n"
            "(표끝)\n"
            "(본문) 표 다음 문장"
        )
        ok, message, data = run_auto_format(
            bridge,
            _style_records(),
            cancelled=lambda: False,
        )
        self.assertTrue(ok, message)
        self.assertEqual(data["mode"], "tagged")

        call_names = [call[0] for call in bridge.calls]
        table_index = call_names.index("pipe_table")
        following_line_index = call_names.index("report_line")
        between = call_names[table_index + 1:following_line_index]
        self.assertEqual(
            between[:3],
            ["cancel_table_selection", "outside_table", "outside_table"],
        )

    def test_cancel_stops_before_selected_text_is_read(self):
        bridge = FakeAutoFormatBridge("(본문) 내용")
        ok, message, data = run_auto_format(
            bridge,
            _style_records(),
            cancelled=lambda: True,
        )
        self.assertFalse(ok)
        self.assertTrue(data["cancelled"])
        self.assertEqual(bridge.calls, [("page_setup",)])

    def test_prompt_copy_preserves_windows_blank_lines(self):
        copied = []
        ok, message, _ = copy_report_prompt_to_clipboard(copied.append)
        self.assertTrue(ok, message)
        self.assertEqual(len(copied), 1)
        self.assertIn("\r\n", copied[0])
        self.assertNotIn("\n", copied[0].replace("\r\n", ""))


if __name__ == "__main__":
    unittest.main()