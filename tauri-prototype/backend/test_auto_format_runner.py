import unittest
import tempfile
import uuid
from pathlib import Path

from backend.server import _auto_title_template_records
from backend.auto_format_runner import (
    apply_auto_format_role,
    copy_report_prompt_to_clipboard,
    run_auto_format,
)


class FakeAutoFormatBridge:
    def __init__(self, selected_text, inspection=None):
        self.selected_text = selected_text
        self.inspection = inspection if inspection is not None else (True, {})
        if self.inspection[0]:
            self.inspection[1].setdefault("controls_complete", True)
        self.calls = []
        self.checkpoint_path = str(Path(tempfile.gettempdir()) / f"test-auto-format-{uuid.uuid4().hex}.hwp")

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

    def create_auto_format_checkpoint(self):
        self.calls.append(("checkpoint",))
        return True, {"path": self.checkpoint_path, "start": (0, 0, 0)}

    def restore_auto_format_checkpoint(self, checkpoint, *, original_range=False):
        self.calls.append(("restore", checkpoint["path"], original_range))
        return True, "restored"

    def restore_page_setup(self, checkpoint):
        self.calls.append(("restore_page_setup", checkpoint["path"]))
        return True, "page restored"

    def begin_auto_format_rewrite(self, checkpoint):
        self.calls.append(("begin_rewrite",))
        return True, object()

    def commit_auto_format_rewrite(self, transaction):
        self.calls.append(("commit_rewrite",))
        return True, "committed"

    def rollback_auto_format_rewrite(self, transaction):
        self.calls.append(("rollback_rewrite",))
        return True, "source retained"

    def ensure_cursor_outside_table(self):
        self.calls.append(("outside_table",))
        return True, "outside"

    def run_first_supported(self, commands):
        self.calls.append(("cancel_table_selection", tuple(commands)))
        return True, commands[0]

    def insert_document_title_box(self, file_path, title_text, **style):
        self.calls.append(("document_title", file_path, title_text, style))
        return True, "document title"

    def insert_section_title_box(self, file_path, number_text, title_text, **style):
        self.calls.append(("section_title", file_path, number_text, title_text, style))
        return True, "section title"

    def insert_auto_title_template(self, file_path, replacements, **style):
        self.calls.append(("auto_title", file_path, replacements, style))
        return True, "auto title"

    def insert_report_line(self, text, font_name, font_size_pt, bold=False):
        self.calls.append(("report_line", text, font_name, font_size_pt, bold))
        return True, "report line"

    def apply_indent_at_caret_for_current_para(self, caret_offset):
        self.calls.append(("indent", caret_offset))
        return True, "indent"

    def insert_text(self, text):
        self.calls.append(("insert_text", text))
        return True, "text"


    def insert_pipe_table(self, rows, font_name, font_size_pt, bold=False):
        self.calls.append(("pipe_table", rows, font_name, font_size_pt, bold))
        return True, "table"

    def format_native_report_tables(
        self,
        positions,
        font_name="굴림체",
        font_size_pt=12,
        bold=False,
        progress=None,
        cancelled=None,
    ):
        self.calls.append(
            ("native_tables", positions, font_name, font_size_pt, bold)
        )
        if progress:
            progress(1, len(positions))
        return True, "native tables"

    def apply_inferred_report_paragraphs(
        self,
        paragraphs,
        items,
        title_template=None,
        section_template=None,
        progress=None,
        cancelled=None,
    ):
        self.calls.append(
            (
                "inferred_paragraphs",
                len(paragraphs),
                [item.get("tag") for item in items],
                title_template,
                section_template,
            )
        )
        if progress:
            progress(len(paragraphs), len(paragraphs))
        return True, "paragraphs"


class AutoFormatRunnerTests(unittest.TestCase):
    def test_structure_failures_and_objects_stop_before_any_document_edit(self):
        for raw in ("(본문) 내용", "1 추진 배경\n- 내용"):
            for inspection in ((False, "scan failed"), (True, {"controls_complete": False}), (True, {"native_object_positions": [(0, 1, 0)]})):
                with self.subTest(raw=raw, inspection=inspection):
                    bridge = FakeAutoFormatBridge(raw, inspection=inspection)
                    ok, message, _ = run_auto_format(bridge, _auto_title_template_records(), cancelled=lambda: False)
                    self.assertFalse(ok)
                    self.assertIn("원문은 변경하지 않았습니다", message)
                    names = [call[0] for call in bridge.calls]
                    for action in ("checkpoint", "page_setup", "delete_selection", "begin_rewrite", "report_line"):
                        self.assertNotIn(action, names)

    def test_tagged_input_cannot_destroy_an_existing_table(self):
        bridge = FakeAutoFormatBridge("(본문) 내용", inspection=(True, {"native_table_positions": [(0, 1, 0)]}))
        ok, _, _ = run_auto_format(bridge, _auto_title_template_records(), cancelled=lambda: False)
        self.assertFalse(ok)
        self.assertNotIn("begin_rewrite", [call[0] for call in bridge.calls])

    def test_inspection_exception_stops_before_any_document_changes(self):
        bridge = FakeAutoFormatBridge("(본문) 내용")
        def fail():
            raise RuntimeError("scan unavailable")
        bridge.inspect_selected_report_content = fail
        ok, message, _ = run_auto_format(bridge, _auto_title_template_records(), cancelled=lambda: False)
        self.assertFalse(ok)
        self.assertIn("원문은 변경하지 않았습니다", message)
        self.assertNotIn("checkpoint", [call[0] for call in bridge.calls])

    def test_write_exception_and_commit_failure_remove_only_new_result(self):
        for stage in ("write", "commit"):
            bridge = FakeAutoFormatBridge("(본문) 내용")
            if stage == "write":
                def fail(*_args, **_kwargs):
                    raise RuntimeError("unexpected write failure")
                bridge.insert_report_line = fail
            else:
                bridge.commit_auto_format_rewrite = lambda _token: (False, "commit failed")
            ok, message, _ = run_auto_format(bridge, _auto_title_template_records(), cancelled=lambda: False)
            self.assertFalse(ok)
            self.assertIn("원문을 유지", message)
            names = [call[0] for call in bridge.calls]
            self.assertIn("rollback_rewrite", names)
            self.assertNotIn("delete_selection", names)
            self.assertNotIn("restore", names)

    def test_direct_role_also_checks_objects_and_keeps_original_until_commit(self):
        bridge = FakeAutoFormatBridge("내용", inspection=(True, {"native_object_positions": [(0, 0, 0)]}))
        self.assertFalse(apply_auto_format_role(bridge, _auto_title_template_records(), "body")[0])
        self.assertNotIn("begin_rewrite", [call[0] for call in bridge.calls])
        bridge = FakeAutoFormatBridge("내용")
        self.assertTrue(apply_auto_format_role(bridge, _auto_title_template_records(), "body")[0])
        names = [call[0] for call in bridge.calls]
        self.assertLess(names.index("begin_rewrite"), names.index("report_line"))
        self.assertGreater(names.index("commit_rewrite"), names.index("report_line"))
        self.assertNotIn("delete_selection", names)

    def test_tagged_report_uses_existing_boxes_and_paragraph_styles(self):
        bridge = FakeAutoFormatBridge(
            "(문서제목) 테스트 계획\n"
            "(제목) 1. 추진 배경\n"
            "(본문) 내용"
        )
        ok, message, data = run_auto_format(
            bridge,
            _auto_title_template_records(),
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
            _auto_title_template_records(),
            cancelled=lambda: False,
            format_settings={
                "roles": {
                    "table": {
                        "font": "맑은 고딕",
                        "size": 10,
                        "bold": True,
                    }
                }
            },
        )
        self.assertTrue(ok, message)
        self.assertEqual(data["mode"], "inferred")
        self.assertEqual(data["native_table_count"], 1)
        call_names = [call[0] for call in bridge.calls]
        self.assertIn("native_tables", call_names)
        native_call = next(call for call in bridge.calls if call[0] == "native_tables")
        self.assertEqual(native_call[2:5], ("맑은 고딕", 10, True))
        self.assertIn("inferred_paragraphs", call_names)
        self.assertNotIn("delete_selection", call_names)

    def test_inferred_report_without_native_table_uses_tagged_rebuild(self):
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
                    "native_table_positions": [],
                },
            ),
        )
        ok, message, data = run_auto_format(
            bridge,
            _auto_title_template_records(),
            cancelled=lambda: False,
        )
        self.assertTrue(ok, message)
        self.assertEqual(data["mode"], "inferred")
        self.assertEqual(data["native_table_count"], 0)
        call_names = [call[0] for call in bridge.calls]
        self.assertNotIn("inferred_paragraphs", call_names)
        self.assertNotIn("delete_selection", call_names)
        self.assertLess(call_names.index("begin_rewrite"), call_names.index("report_line"))
        self.assertGreater(call_names.index("commit_rewrite"), call_names.index("report_line"))
        self.assertLess(call_names.index("inspect"), call_names.index("page_setup"))

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
            _auto_title_template_records(),
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

    def test_generated_table_uses_configured_text_style(self):
        bridge = FakeAutoFormatBridge(
            """(표시작)
항목 | 내용
A | B
(표끝)"""
        )
        ok, message, _data = run_auto_format(
            bridge,
            _auto_title_template_records(),
            cancelled=lambda: False,
            format_settings={
                "roles": {
                    "table": {
                        "font": "맑은 고딕",
                        "size": 9,
                        "bold": True,
                    }
                }
            },
        )
        self.assertTrue(ok, message)
        table_call = next(call for call in bridge.calls if call[0] == "pipe_table")
        self.assertEqual(table_call[2:5], ("맑은 고딕", 9, True))

    def test_cancel_stops_before_selected_text_is_read(self):
        bridge = FakeAutoFormatBridge("(본문) 내용")
        ok, message, data = run_auto_format(
            bridge,
            _auto_title_template_records(),
            cancelled=lambda: True,
        )
        self.assertFalse(ok)
        self.assertTrue(data["cancelled"])
        self.assertEqual(bridge.calls, [])

    def test_cancel_after_replacement_restores_original_selection(self):
        bridge = FakeAutoFormatBridge("(본문) 첫 문장\n(본문) 둘째 문장")
        def cancelled():
            return any(call[0] == "report_line" for call in bridge.calls)
        ok, message, data = run_auto_format(
            bridge, _auto_title_template_records(), cancelled=cancelled,
        )
        self.assertFalse(ok)
        self.assertTrue(data["cancelled"])
        self.assertIn("복구했습니다", message)
        self.assertEqual(len([call for call in bridge.calls if call[0] == "rollback_rewrite"]), 1)

    def test_insert_failure_retains_checkpoint_if_recovery_fails(self):
        bridge = FakeAutoFormatBridge("(본문) 내용")
        def failed_insert(*_args, **_kwargs):
            return False, "insertion failed"
        bridge.insert_report_line = failed_insert
        bridge.rollback_auto_format_rewrite = lambda _transaction: (False, "cleanup failed")
        ok, message, _data = run_auto_format(
            bridge, _auto_title_template_records(), cancelled=lambda: False,
        )
        self.assertFalse(ok)
        self.assertIn(bridge.checkpoint_path, message)

    def test_checkpoint_failure_stops_before_page_setup(self):
        bridge = FakeAutoFormatBridge("(본문) 내용")
        bridge.create_auto_format_checkpoint = lambda: (False, "backup failed")
        ok, message, _data = run_auto_format(
            bridge, _auto_title_template_records(), cancelled=lambda: False,
        )
        self.assertFalse(ok)
        self.assertIn("백업 실패", message)
        self.assertNotIn("page_setup", [call[0] for call in bridge.calls])

    def test_native_table_failure_restores_selected_block_and_page_setup(self):
        bridge = FakeAutoFormatBridge(
            "테스트 계획\n1. 추진 배경\n내용",
            inspection=(True, {
                "paragraphs": [{"text": "테스트 계획"}, {"text": "1. 추진 배경"}, {"text": "내용"}],
                "native_table_positions": [(0, 4, 0)],
            }),
        )
        bridge.format_native_report_tables = lambda *_args, **_kwargs: (False, "table failed")
        ok, message, _data = run_auto_format(
            bridge, _auto_title_template_records(), cancelled=lambda: False,
        )
        self.assertFalse(ok)
        self.assertIn("복구했습니다", message)
        self.assertIn(("restore", bridge.checkpoint_path, True), bridge.calls)
        self.assertIn(("restore_page_setup", bridge.checkpoint_path), bridge.calls)

    def test_native_paragraph_failure_keeps_checkpoint_and_restores_page_setup(self):
        bridge = FakeAutoFormatBridge(
            "테스트 계획\n1. 추진 배경\n내용",
            inspection=(True, {
                "paragraphs": [{"text": "테스트 계획"}, {"text": "1. 추진 배경"}, {"text": "내용"}],
                "native_table_positions": [(0, 4, 0)],
            }),
        )
        bridge.apply_inferred_report_paragraphs = lambda *_args, **_kwargs: (False, "paragraph failed")
        ok, message, _data = run_auto_format(
            bridge, _auto_title_template_records(), cancelled=lambda: False,
        )
        self.assertFalse(ok)
        self.assertIn("문서 일부가 변경되었을 수 있습니다", message)
        self.assertIn(bridge.checkpoint_path, message)
        self.assertNotIn("restore", [call[0] for call in bridge.calls])
        self.assertIn(("restore_page_setup", bridge.checkpoint_path), bridge.calls)

    def test_native_table_cancel_request_reaches_table_formatter(self):
        bridge = FakeAutoFormatBridge(
            "테스트 계획\n1. 추진 배경\n내용",
            inspection=(True, {
                "paragraphs": [{"text": "테스트 계획"}, {"text": "1. 추진 배경"}, {"text": "내용"}],
                "native_table_positions": [(0, 4, 0)],
            }),
        )
        def stop_in_table(*_args, cancelled=None, **_kwargs):
            bridge.calls.append(("native_tables",))
            return (False, "CANCELLED") if cancelled() else (True, "ok")
        bridge.format_native_report_tables = stop_in_table
        cancelled = lambda: any(call[0] == "native_tables" for call in bridge.calls)
        ok, message, data = run_auto_format(
            bridge, _auto_title_template_records(), cancelled=cancelled,
        )
        self.assertFalse(ok)
        self.assertTrue(data["cancelled"])
        self.assertIn(("restore", bridge.checkpoint_path, True), bridge.calls)

    def test_plain_title_mode_applies_text_style_and_complete_number(self):
        records = _auto_title_template_records()
        bridge = FakeAutoFormatBridge(
            "(문서제목) - 테스트 계획\n"
            "(제목) 1. 추진 배경"
        )
        settings = {
            "document_title_template": "auto-title-none:document_title",
            "title_template": "auto-title-none:title",
            "roles": {
                "document_title": {"font": "맑은 고딕", "size": 22, "bold": True},
                "title": {
                    "font": "굴림체",
                    "size": 15,
                    "bold": False,
                    "marker": "roman_upper_dot",
                },
            },
        }
        ok, message, _data = run_auto_format(
            bridge,
            records,
            cancelled=lambda: False,
            format_settings=settings,
        )
        self.assertTrue(ok, message)
        report_lines = [call for call in bridge.calls if call[0] == "report_line"]
        self.assertEqual(report_lines[0][1:5], ("테스트 계획", "맑은 고딕", 22, True))
        self.assertEqual(report_lines[1][1:5], ("Ⅰ. 추진 배경", "굴림체", 15, False))
        self.assertNotIn("document_title", [call[0] for call in bridge.calls])
        self.assertNotIn("section_title", [call[0] for call in bridge.calls])
        self.assertNotIn("auto_title", [call[0] for call in bridge.calls])

    def test_uses_selected_title_templates_and_body_text_style(self):
        records = _auto_title_template_records()
        builtin_document = next(
            item for item in records if item["role"] == "document_title"
        )
        builtin_title = next(item for item in records if item["role"] == "title")
        document_template = {
            **builtin_document,
            "key": "auto-title-user:document",
            "mode": "placeholder",
            "title_token": "DOC_TOKEN",
        }
        title_template = {
            **builtin_title,
            "key": "auto-title-user:title",
            "mode": "placeholder",
            "number_token": "NUMBER_TOKEN",
            "title_token": "TITLE_TOKEN",
        }
        records.extend([document_template, title_template])
        bridge = FakeAutoFormatBridge(
            "(문서제목) - 테스트 계획\n"
            "(제목) 1. 추진 배경\n"
            "(본문) - 내용"
        )
        settings = {
            "document_title_template": document_template["key"],
            "title_template": title_template["key"],
            "roles": {
                "document_title": {"font": "맑은 고딕", "size": 22, "bold": False},
                "title": {"font": "굴림체", "size": 15, "bold": True},
                "body": {"font": "굴림체", "size": 11, "bold": False, "marker": "asterisk"},
            },
        }
        ok, message, _data = run_auto_format(
            bridge,
            records,
            cancelled=lambda: False,
            format_settings=settings,
        )
        self.assertTrue(ok, message)
        title_calls = [call for call in bridge.calls if call[0] == "auto_title"]
        self.assertEqual(len(title_calls), 2)
        self.assertEqual(title_calls[0][1], document_template["file_path"])
        self.assertEqual(title_calls[0][2], {"DOC_TOKEN": "테스트 계획"})
        self.assertEqual(title_calls[0][3], {
            "font_name": "맑은 고딕", "font_size_pt": 22, "bold": False,
        })
        self.assertEqual(title_calls[1][1], title_template["file_path"])
        self.assertEqual(title_calls[1][2], {
            "NUMBER_TOKEN": "1",
            "TITLE_TOKEN": "추진 배경",
        })
        self.assertEqual(title_calls[1][3], {
            "font_name": "굴림체", "font_size_pt": 15, "bold": True,
        })
        body_call = next(call for call in bridge.calls if call[0] == "report_line")
        self.assertEqual(body_call[1].lstrip(), "* 내용")
        self.assertEqual(body_call[2:5], ("굴림체", 11, False))
    def test_direct_document_title_uses_saved_template_and_style(self):
        records = _auto_title_template_records()
        builtin = next(item for item in records if item["role"] == "document_title")
        template = {
            **builtin,
            "key": "auto-title-user:direct-document",
            "mode": "placeholder",
            "title_token": "DOC_TOKEN",
        }
        records.append(template)
        bridge = FakeAutoFormatBridge("2026년 운영 계획")
        ok, message, data = apply_auto_format_role(
            bridge,
            records,
            "document_title",
            format_settings={
                "document_title_template": template["key"],
                "roles": {
                    "document_title": {"font": "맑은 고딕", "size": 21, "bold": True},
                },
            },
        )
        self.assertTrue(ok, message)
        self.assertEqual(data["role"], "document_title")
        title_call = next(call for call in bridge.calls if call[0] == "auto_title")
        self.assertEqual(title_call[2], {"DOC_TOKEN": "2026년 운영 계획"})
        self.assertEqual(title_call[3], {
            "font_name": "맑은 고딕", "font_size_pt": 21, "bold": True, "append_paragraph_break": False,
        })
        self.assertNotIn("page_setup", [call[0] for call in bridge.calls])

    def test_direct_body_applies_saved_marker_style_and_indent_to_each_paragraph(self):
        bridge = FakeAutoFormatBridge("첫 번째 내용\n두 번째 내용")
        ok, message, data = apply_auto_format_role(
            bridge,
            _auto_title_template_records(),
            "body",
            format_settings={
                "roles": {
                    "body": {
                        "font": "굴림체",
                        "size": 11,
                        "bold": True,
                        "marker": "asterisk",
                    },
                },
            },
        )
        self.assertTrue(ok, message)
        self.assertEqual(data["changed_count"], 2)
        lines = [call for call in bridge.calls if call[0] == "report_line"]
        self.assertEqual([call[1].lstrip() for call in lines], ["* 첫 번째 내용", "* 두 번째 내용"])
        self.assertTrue(all(call[2:5] == ("굴림체", 11, True) for call in lines))
        self.assertEqual(len([call for call in bridge.calls if call[0] == "indent"]), 2)

    def test_direct_level_one_title_uses_configured_number_marker(self):
        bridge = FakeAutoFormatBridge("4. 추진 배경")
        ok, message, _data = apply_auto_format_role(
            bridge,
            _auto_title_template_records(),
            "title",
            format_settings={
                "title_template": "auto-title-none:title",
                "roles": {
                    "title": {
                        "font": "휴먼명조",
                        "size": 15,
                        "bold": False,
                        "marker": "roman_upper_dot",
                    },
                },
            },
        )
        self.assertTrue(ok, message)
        line = next(call for call in bridge.calls if call[0] == "report_line")
        self.assertEqual(line[1:5], ("Ⅳ. 추진 배경", "휴먼명조", 15, False))

    def test_direct_role_without_selection_returns_guide_reason(self):
        bridge = FakeAutoFormatBridge("")
        ok, message, data = apply_auto_format_role(
            bridge,
            _auto_title_template_records(),
            "reference",
        )
        self.assertFalse(ok)
        self.assertIn("블록 지정", message)
        self.assertEqual(data["reason"], "selection_required")
        self.assertNotIn("delete_selection", [call[0] for call in bridge.calls])

    def test_direct_box_title_rejects_multiple_paragraphs(self):
        bridge = FakeAutoFormatBridge("1. 첫 제목\n2. 둘째 제목")
        ok, message, data = apply_auto_format_role(
            bridge,
            _auto_title_template_records(),
            "title",
        )
        self.assertFalse(ok)
        self.assertIn("한 문단", message)
        self.assertEqual(data["reason"], "single_paragraph_required")
        self.assertNotIn("delete_selection", [call[0] for call in bridge.calls])

    def test_prompt_copy_preserves_windows_blank_lines(self):
        copied = []
        ok, message, _ = copy_report_prompt_to_clipboard(copied.append)
        self.assertTrue(ok, message)
        self.assertEqual(len(copied), 1)
        self.assertIn("\r\n", copied[0])
        self.assertNotIn("\n", copied[0].replace("\r\n", ""))


if __name__ == "__main__":
    unittest.main()
