import unittest

from src.jb_quickpanel.features.auto_format import (
    transform_auto_format_text,
    transform_report_text,
)
from src.jb_quickpanel.features.untagged_report import (
    convert_untagged_report_to_tagged_text,
)
from src.jb_quickpanel.features.auto_format_settings import (
    normalize_auto_format_profile_state,
    normalize_auto_format_settings,
)


class AutoFormatModeTests(unittest.TestCase):
    def test_tagged_draft_removes_inline_bold_from_text_and_table_cells(self):
        items, _, mode = transform_auto_format_text(
            "(문서제목) - **운영 계획**\n(제목) 1. **추진 배경**\n"
            "(본문) - 검토 후 **공식 안내**\n(참고) ※ __확인 필요__\n"
            "(표시작)\n부서 | 역할\n**팀**과 **부서** | **검토** 후 안내\n(표끝)"
        )
        self.assertEqual(mode, "tagged")
        self.assertEqual(items[0]["text"], "운영 계획")
        self.assertEqual(items[1]["body_text"], "추진 배경")
        self.assertEqual(items[-1]["rows"][-1], ["팀과 부서", "검토 후 안내"])
        self.assertNotIn("**", "\n".join(item["text"] for item in items))

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
        self.assertEqual([item["tag"] for item in items], ["문서제목", None, "제목", "본문"])


    def test_plain_draft_is_first_converted_to_prompt_tag_format(self):
        raw = (
            "2026년 찾아가는 교육 운영 계획\n"
            "1. 추진 배경\n"
            "교육 활용 역량 강화 필요\n"
            "참석자 안내 문안\n"
            "교육 당일 개인 기기를 지참합니다.\n"
            "구분\t내용\n"
            "교육명\t찾아가는 교육\n"
            "2. 기대효과\n"
            "업무 활용 역량을 강화합니다."
        )
        virtual_text, _ = convert_untagged_report_to_tagged_text(raw)
        expected = (
            "(문서제목) - 2026년 찾아가는 교육 운영 계획\n"
            "\n"
            "(제목) 1. 추진 배경\n"
            "(본문) - 교육 활용 역량 강화 필요\n"
            "\n"
            "(소제목) 가. 참석자 안내 문안\n"
            "(본문) - 교육 당일 개인 기기를 지참합니다.\n"
            "(표시작)\n"
            "구분 | 내용\n"
            "교육명 | 찾아가는 교육\n"
            "(표끝)\n"
            "\n"
            "(제목) 2. 기대효과\n"
            "(본문) - 업무 활용 역량을 강화합니다."
        )
        self.assertEqual(virtual_text, expected)

        inferred_items, _, mode = transform_auto_format_text(raw)
        tagged_items, _ = transform_report_text(expected)
        self.assertEqual(mode, "inferred")
        self.assertEqual(inferred_items, tagged_items)
    def test_applies_saved_font_size_bold_and_marker_settings(self):
        settings = {
            "roles": {
                "document_title": {"font": "맑은 고딕", "size": 22, "bold": False},
                "title": {"font": "맑은 고딕", "size": 15, "bold": True},
                "subtitle": {"font": "굴림체", "size": 13, "bold": False, "marker": "hangul_paren"},
                "subsubtitle": {"font": "굴림체", "size": 12, "bold": False, "marker": "number_circle"},
                "body": {"font": "굴림체", "size": 11, "bold": True, "marker": "asterisk"},
                "table": {"font": "맑은 고딕", "size": 9, "bold": True},
                "reference": {"font": "굴림체", "size": 10, "bold": False, "marker": "none"},
            }
        }
        items, _, _ = transform_auto_format_text(
            "(문서제목) - 계획\n"
            "(제목) 1. 배경\n"
            "(소제목) 가. 목적\n"
            "(소소제목) 1) 세부\n"
            "(본문) - 내용\n"
            "(표시작)\n항목 | 내용\nA | B\n(표끝)\n"
            "(참고) ※ 참고 내용",
            settings,
        )
        styled = [item for item in items if item.get("style")]
        self.assertEqual(styled[0]["style"], {
            "font": "맑은 고딕", "size": 22, "bold": False, "caret_indent_at": None,
        })
        self.assertEqual(styled[2]["text"].lstrip(), "가) 목적")
        self.assertEqual(styled[3]["text"].lstrip(), "① 세부")
        self.assertEqual(styled[4]["text"].lstrip(), "* 내용")
        self.assertEqual(styled[4]["style"]["font"], "굴림체")
        self.assertEqual(styled[4]["style"]["size"], 11)
        self.assertTrue(styled[4]["style"]["bold"])
        self.assertEqual(styled[4]["style"]["caret_indent_at"], 8)
        table_item = next(item for item in items if item.get("tag") == "표")
        self.assertEqual(table_item["style"]["font"], "맑은 고딕")
        self.assertEqual(table_item["style"]["size"], 9)
        self.assertTrue(table_item["style"]["bold"])
        reference_item = next(item for item in items if item.get("tag") == "참고")
        self.assertEqual(reference_item["text"].strip(), "참고 내용")
        self.assertEqual(reference_item["style"]["caret_indent_at"], 8)
    def test_body_without_marker_keeps_paragraph_indent(self):
        items, _ = transform_report_text(
            "(제목) 1. 추진 배경\n"
            "(본문) - 기호 없는 본문",
            {"roles": {"body": {"marker": "none"}}},
        )
        body = next(item for item in items if item.get("tag") == "본문")
        self.assertEqual(body["text"], "  기호 없는 본문")
        self.assertEqual(body["style"]["caret_indent_at"], 2)

    def test_applies_roman_heading_numbers_and_repeats_custom_symbols(self):
        settings = {
            "roles": {
                "title": {"marker": "roman_upper_dot"},
                "subtitle": {"marker": "roman_lower_dot"},
                "subsubtitle": {"marker": "custom", "custom_marker": "▶"},
                "body": {"marker": "custom", "custom_marker": "◆"},
                "reference": {"marker": "custom", "custom_marker": "☆"},
            }
        }
        items, _ = transform_report_text(
            "(제목) 1. 첫째\n"
            "(소제목) 가. 세부\n"
            "(소소제목) 1) 항목 하나\n"
            "(소소제목) 2) 항목 둘\n"
            "(본문) - 내용 하나\n"
            "(본문) - 내용 둘\n"
            "(참고) ※ 확인\n"
            "(제목) 2. 둘째",
            settings,
        )
        titles = [item for item in items if item.get("tag") == "제목"]
        self.assertEqual([item["number_text"] for item in titles], ["Ⅰ", "Ⅱ"])
        subtitle = next(item for item in items if item.get("tag") == "소제목")
        self.assertEqual(subtitle["text"].strip(), "ⅰ. 세부")
        subsubtitles = [item for item in items if item.get("tag") == "소소제목"]
        self.assertEqual([item["text"].strip() for item in subsubtitles], ["▶ 항목 하나", "▶ 항목 둘"])
        bodies = [item for item in items if item.get("tag") == "본문"]
        self.assertEqual([item["text"].strip() for item in bodies], ["◆ 내용 하나", "◆ 내용 둘"])
        reference = next(item for item in items if item.get("tag") == "참고")
        self.assertEqual(reference["text"].strip(), "☆ 확인")

    def test_duplicate_heading_sequence_is_replaced_at_normalization(self):
        settings = normalize_auto_format_settings({
            "roles": {
                "title": {"marker": "roman_upper_dot"},
                "subtitle": {"marker": "roman_upper_dot"},
                "subsubtitle": {"marker": "number_paren"},
            }
        })
        self.assertEqual(settings["roles"]["title"]["marker"], "roman_upper_dot")
        self.assertEqual(settings["roles"]["subtitle"]["marker"], "hangul_dot")
        self.assertEqual(settings["roles"]["subsubtitle"]["marker"], "number_paren")

    def test_legacy_auto_format_becomes_default_profile(self):
        state = normalize_auto_format_profile_state(
            None,
            None,
            {"roles": {"body": {"font": "맑은 고딕", "size": 11}}},
        )

        self.assertEqual(state["active_auto_format_profile"], "default")
        self.assertEqual(len(state["auto_format_profiles"]), 1)
        profile = state["auto_format_profiles"][0]
        self.assertEqual(profile["name"], "기본 설정")
        self.assertEqual(profile["settings"]["roles"]["body"]["font"], "맑은 고딕")
        self.assertEqual(state["auto_format"], profile["settings"])

    def test_profile_state_uses_selected_profile_and_normalizes_duplicates(self):
        state = normalize_auto_format_profile_state(
            [
                {
                    "id": "school-plan",
                    "name": "계획서",
                    "settings": {"roles": {"body": {"size": 12}}},
                },
                {
                    "id": "school-plan",
                    "name": "계획서",
                    "settings": {"roles": {"body": {"size": 14}}},
                },
            ],
            "profile-2",
            None,
        )

        profiles = state["auto_format_profiles"]
        self.assertEqual([item["id"] for item in profiles], ["school-plan", "profile-2"])
        self.assertEqual([item["name"] for item in profiles], ["계획서", "계획서 (2)"])
        self.assertEqual(state["active_auto_format_profile"], "profile-2")
        self.assertEqual(state["auto_format"]["roles"]["body"]["size"], 14)

    def test_missing_active_profile_falls_back_to_first_profile(self):
        state = normalize_auto_format_profile_state(
            [{"id": "first", "name": "첫 설정", "settings": {}}],
            "missing",
            None,
        )

        self.assertEqual(state["active_auto_format_profile"], "first")
        self.assertEqual(state["auto_format"], state["auto_format_profiles"][0]["settings"])

if __name__ == "__main__":
    unittest.main()
