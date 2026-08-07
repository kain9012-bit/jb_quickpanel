import unittest

from src.jb_quickpanel.features.untagged_report import (
    detect_untagged_table_blocks,
    transform_untagged_report_text,
)


class UntaggedTableDetectionTests(unittest.TestCase):
    def test_detects_tab_separated_table(self):
        raw = (
            "일자\t수집 보도자료\t선별·분석 교육동향\t비고\n"
            "7. 27.(월)\t[ ]건\t[ ]건\t최근 72시간 자료 분석\n"
            "합계\t[ ]건\t[ ]건\t일일 11건 이상 제공"
        )
        blocks = detect_untagged_table_blocks(raw.splitlines())
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].cols, 4)
        self.assertEqual(blocks[0].rows[1][0], "7. 27.(월)")

    def test_detects_markdown_table_and_removes_separator_and_wrappers(self):
        raw = (
            "| 일자 | 수집 보도자료 | 비고 |\n"
            "| --- | ---: | --- |\n"
            "| 7. 27.(월) | [ ]건 | 최근 72시간 자료 분석 |\n"
            "| **합계** | **[ ]건** | 일일 11건 이상 제공 |"
        )
        blocks = detect_untagged_table_blocks(raw.splitlines())
        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(blocks[0].rows), 3)
        self.assertEqual(blocks[0].rows[-1][0], "합계")
        self.assertEqual(blocks[0].rows[-1][1], "[ ]건")

    def test_does_not_treat_one_pipe_line_as_table(self):
        self.assertEqual(detect_untagged_table_blocks(["A | B | C", "일반 문장"]), [])


class UntaggedStructureInferenceTests(unittest.TestCase):
    def test_infers_relative_hierarchy_and_document_title(self):
        raw = (
            "2026년 교육동향 분석 운영계획\n"
            "Ⅰ. 추진 개요\n"
            "1. 운영 목적\n"
            "가) 세부 내용\n"
            "- 매일 교육동향 자료를 분석함\n"
            "※ 상황에 따라 일정을 조정함"
        )
        items, changed = transform_untagged_report_text(raw)
        self.assertEqual(changed, 6)
        self.assertEqual(
            [item["tag"] for item in items],
            ["문서제목", "제목", "소제목", "소소제목", "본문", "참고"],
        )
        self.assertEqual(items[1]["number_text"], "Ⅰ")
        self.assertEqual(items[1]["body_text"], "추진 개요")

    def test_does_not_create_document_title_when_selection_starts_with_heading(self):
        items, _ = transform_untagged_report_text("1. 추진 배경\n가. 추진 목적\n- 세부 내용")
        self.assertEqual([item["tag"] for item in items], ["제목", "소제목", "본문"])

    def test_adds_dash_only_to_body_without_an_existing_marker(self):
        items, _ = transform_untagged_report_text(
            "1. 추진 배경\n기호가 없는 본문\n- 기존 대시 본문\n○ 기존 원형 기호 본문"
        )
        self.assertEqual(items[1]["text"].lstrip(), "- 기호가 없는 본문")
        self.assertEqual(items[1]["inserted_prefix"], "- ")
        self.assertEqual(items[2]["text"].lstrip(), "- 기존 대시 본문")
        self.assertEqual(items[2]["inserted_prefix"], "")
        self.assertEqual(items[3]["text"].lstrip(), "○ 기존 원형 기호 본문")
        self.assertEqual(items[3]["inserted_prefix"], "")

    def test_keeps_number_inside_bold_markdown_heading(self):
        items, _ = transform_untagged_report_text("**1. 추진 배경**\n설명 문장")
        self.assertEqual(items[0]["tag"], "제목")
        self.assertEqual(items[0]["number_text"], "1")
        self.assertEqual(items[0]["body_text"], "추진 배경")

    def test_virtual_tags_generate_missing_heading_and_reference_markers(self):
        items, _ = transform_untagged_report_text(
            "## 추진 배경\n### 운영 목적\n#### 세부 내용\n설명 문장\n참고: 일정은 변경될 수 있음"
        )
        self.assertEqual(
            [item["tag"] for item in items],
            ["제목", "소제목", "소소제목", "본문", "참고"],
        )
        self.assertEqual(items[0]["number_text"], "1")
        self.assertEqual(items[0]["body_text"], "추진 배경")
        self.assertEqual(items[1]["text"].lstrip(), "가. 운영 목적")
        self.assertEqual(items[2]["text"].lstrip(), "1) 세부 내용")
        self.assertEqual(items[3]["text"].lstrip(), "- 설명 문장")
        self.assertEqual(items[4]["text"].lstrip(), "※ 참고: 일정은 변경될 수 있음")

    def test_converts_table_block_inside_report(self):
        raw = (
            "2026년 교육동향 분석 계획\n"
            "1. 추진 현황\n"
            "일자\t건수\t비고\n"
            "7. 27.\t10건\t분석 완료\n"
            "7. 28.\t11건\t분석 예정\n"
            "※ 일정은 변경될 수 있음"
        )
        items, _ = transform_untagged_report_text(raw)
        self.assertEqual([item["tag"] for item in items], ["문서제목", "제목", "표", "참고"])
        self.assertEqual(items[2]["cols"], 3)


if __name__ == "__main__":
    unittest.main()
