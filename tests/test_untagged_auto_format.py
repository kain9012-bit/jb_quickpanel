import unittest
from pathlib import Path

from src.jb_quickpanel.features.auto_format import transform_auto_format_text

from src.jb_quickpanel.features.untagged_report import (
    detect_untagged_table_blocks,
    transform_untagged_report_text,
    strip_markdown_emphasis,
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

    def test_detects_two_columns_without_outer_pipes(self):
        blocks = detect_untagged_table_blocks([
            "빅데이터팀 | 도구 발굴, 사전 검토",
            "소관 부서 | 업무 적합성 확정",
        ])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].cols, 2)
        self.assertEqual(blocks[0].rows[0], ["빅데이터팀", "도구 발굴, 사전 검토"])

    def test_keeps_single_pipe_sentence_as_body(self):
        self.assertEqual(detect_untagged_table_blocks(["선택: A | B", "다음 문장"]), [])

    def test_removes_inline_emphasis_inside_cells(self):
        blocks = detect_untagged_table_blocks([
            "부서 | 역할",
            "**팀**과 **부서** | 검토 후 **공식 안내**",
        ])
        self.assertEqual(blocks[0].rows[1], ["팀과 부서", "검토 후 공식 안내"])


class UntaggedStructureInferenceTests(unittest.TestCase):
    def test_field_feedback_draft_keeps_all_seven_headings_and_both_tables(self):
        raw = (Path(__file__).parent / "fixtures" / "field_feedback_draft.txt").read_text(encoding="utf-8")
        items, _, mode = transform_auto_format_text(raw)
        self.assertEqual(mode, "inferred")
        headings = [item for item in items if item["tag"] == "제목"]
        self.assertEqual([item["number_text"] for item in headings], [str(n) for n in range(1, 8)])
        self.assertEqual([item["body_text"] for item in headings], [
            "추진 배경 및 목적", "추진 방향", "역할 분담", "연계 대상 선별 기준",
            "사전 검토 (담당 부서 연결 전, 운영팀)", "운영 절차", "추진 일정",
        ])
        tables = [item for item in items if item["tag"] == "표"]
        self.assertEqual([(len(item["rows"]), item["cols"]) for item in tables], [(4, 2), (7, 4)])
        self.assertEqual(tables[1]["rows"][0][0], "① 발굴")
        self.assertEqual(tables[1]["rows"][-1][0], "⑦ 공식 안내")
        self.assertEqual(sum(item["tag"] == "본문" for item in items), 24)
        self.assertEqual(sum(item["tag"] == "참고" for item in items), 2)

    def test_mixed_number_spacing_and_dot_are_same_heading_level(self):
        items, _, _ = transform_auto_format_text(
            "1 추진 배경\n- 내용\n2. 역할 분담\n- 내용\n3 사전 검토\n- 내용"
        )
        headings = [item for item in items if item["tag"] == "제목"]
        self.assertEqual([item["body_text"] for item in headings], ["추진 배경", "역할 분담", "사전 검토"])
        self.assertEqual([item["number_text"] for item in headings], ["1", "2", "3"])
        self.assertFalse(any(item["tag"] == "문서제목" for item in items))

    def test_numeric_quantities_and_year_are_not_headings(self):
        items, _ = transform_untagged_report_text("1. 추진 대상\n10 명 참석\n10   명 참석\n2026 년 시행")
        self.assertEqual([item["tag"] for item in items], ["제목", "본문", "본문", "본문"])

    def test_inline_emphasis_is_removed_but_user_format_settings_are_kept(self):
        items, _, _ = transform_auto_format_text(
            "# **운영 계획**\n## **1 추진 배경**\n"
            "- **(현장 의견)** 담당 부서의 **공식 안내** 필요\n"
            "※ __확인 후__ 진행",
            {"roles": {"body": {"font": "굴림체", "size": 11, "bold": False, "marker": "asterisk"}}},
        )
        headings = [item for item in items if item["tag"] == "제목"]
        self.assertEqual(headings[0]["body_text"], "추진 배경")
        body = next(item for item in items if item["tag"] == "본문")
        self.assertEqual(body["text"].strip(), "* (현장 의견) 담당 부서의 공식 안내 필요")
        self.assertEqual((body["style"]["font"], body["style"]["size"], body["style"]["bold"]), ("굴림체", 11, False))
        self.assertTrue(all("**" not in item["text"] and "__" not in item["text"] for item in items))

    def test_emphasized_sentence_is_not_promoted_to_heading(self):
        items, _ = transform_untagged_report_text("1. 추진 배경\n**담당자가 확인합니다.**")
        self.assertEqual([item["tag"] for item in items], ["제목", "본문"])
        self.assertEqual(items[-1]["text"].strip(), "- 담당자가 확인합니다.")

    def test_removes_only_paired_emphasis_not_literal_asterisks(self):
        for text in ["* 앞 기호", "2 ** 3", "미완성 **표시", r"\**강조 아님\**", "항목_이름"]:
            with self.subTest(text=text):
                self.assertEqual(strip_markdown_emphasis(text), text)
        self.assertEqual(strip_markdown_emphasis("**확인**과 **검토**"), "확인과 검토")

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

    def test_normalizes_gpt_markdown_draft_and_removes_wrapper_text(self):
        raw = (
            "다음은 요청하신 계획서 초안입니다.\n"
            "```markdown\n"
            "# 2026년 교육동향 분석 운영계획\n"
            "## 1. 추진 배경\n"
            "### 가. 추진 목적\n"
            "사업을 안정적으로 운영합니다.\n"
            "```\n"
            "필요하시면 내용을 보완해 드리겠습니다."
        )
        items, changed = transform_untagged_report_text(raw)
        self.assertGreaterEqual(changed, 6)
        self.assertEqual(
            [item["tag"] for item in items],
            ["문서제목", "제목", "소제목", "본문"],
        )
        self.assertEqual(items[-1]["text"].lstrip(), "- 사업을 안정적으로 운영합니다.")
        output = "\n".join(item["text"] for item in items)
        self.assertNotIn("요청하신", output)
        self.assertNotIn("필요하시면", output)
        self.assertNotIn("```", output)

    def test_uses_first_appearance_to_infer_plain_heading_hierarchy(self):
        raw = (
            "2026년 운영계획\n"
            "추진 배경\n"
            "1. 현황 분석\n"
            "- 세부 내용\n"
            "추진 내용\n"
            "1. 추진 일정"
        )
        items, _ = transform_untagged_report_text(raw)
        self.assertEqual(
            [item["tag"] for item in items],
            ["문서제목", "제목", "소제목", "본문", "제목", "소제목"],
        )

    def test_recognizes_chapter_section_and_keeps_checkboxes_as_body(self):
        raw = (
            "2026년 운영계획\n"
            "제1장 추진 개요\n"
            "제1절 운영 목적\n"
            "[ ] 담당자 확인\n"
            "* 일정 점검"
        )
        items, _ = transform_untagged_report_text(raw)
        self.assertEqual(
            [item["tag"] for item in items],
            ["문서제목", "제목", "소제목", "본문", "본문"],
        )
        self.assertEqual(items[3]["text"].lstrip(), "[ ] 담당자 확인")
        self.assertEqual(items[4]["text"].lstrip(), "* 일정 점검")

    def test_recognizes_unnumbered_notice_copy_as_subheading(self):
        raw = (
            "2026년 찾아가는 교육 운영 계획\n"
            "1. 교육 참석 안내사항\n"
            "교육 희망자는 신청 기간 내 신청합니다.\n"
            "참석자 안내 문안\n"
            "이번 교육은 실습을 포함하여 운영합니다.\n"
            "2. 기대효과\n"
            "업무 활용 역량을 강화합니다."
        )
        items, _ = transform_untagged_report_text(raw)
        self.assertEqual(
            [item["tag"] for item in items],
            ["문서제목", "제목", "본문", "소제목", "본문", "제목", "본문"],
        )
        self.assertEqual(items[3]["text"].lstrip(), "가. 참석자 안내 문안")
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
