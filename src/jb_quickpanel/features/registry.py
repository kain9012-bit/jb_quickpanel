# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any


MODE_HWP = "hwp"
MODE_KEDUFINE = "kedufine"
ALL_MODES = (MODE_HWP, MODE_KEDUFINE)


@dataclass(frozen=True)
class FeatureAction:
    id: str
    label: str
    handler: str
    args: tuple[Any, ...] = ()
    modes: tuple[str, ...] = (MODE_HWP,)
    widget_attr: str = ""


@dataclass(frozen=True)
class FontColorAction:
    label: str
    rgb: tuple[int, int, int]
    fg: str
    bg: str


@dataclass(frozen=True)
class FontRow:
    font_name: str
    sizes: tuple[int, ...]


VISIBLE_MAIN_TABS = {
    MODE_HWP: {"style", "edit", "chars", "symbol", "forms", "page", "settings"},
    MODE_KEDUFINE: {"style", "edit", "chars", "settings"},
}

VISIBLE_EDIT_TABS = {
    MODE_HWP: {"table", "cell", "text"},
    MODE_KEDUFINE: {"table", "text"},
}

HIDDEN_TEXT_FONTS_BY_MODE = {
    MODE_HWP: set(),
    MODE_KEDUFINE: {"휴먼명조"},
}

TOP_ROW_ACTIONS = (
    FeatureAction(
        id="auto_format_report",
        label="서식 자동 지정하기",
        handler="on_auto_format_report",
        modes=(MODE_HWP,),
        widget_attr="btn_auto_format",
    ),
    FeatureAction(
        id="copy_report_prompt",
        label="프롬프트 복사",
        handler="on_copy_report_prompt",
        modes=ALL_MODES,
        widget_attr="btn_copy_prompt",
    ),
)

CELL_CLEAN_SPACE_ACTION = FeatureAction(
    id="cell_clean_spaces",
    label="불필요한 앞뒤 공백 제거",
    handler="on_cell_clean_spaces",
)

CELL_FIND_REPLACE_ACTION = FeatureAction(
    id="cell_find_replace",
    label="찾아바꾸기 실행",
    handler="on_cell_find_replace",
)

CELL_ADD_PREFIX_ACTION = FeatureAction(
    id="cell_add_prefix",
    label="내용 앞에 추가",
    handler="on_cell_add_prefix",
)

CELL_ADD_SUFFIX_ACTION = FeatureAction(
    id="cell_add_suffix",
    label="내용 뒤에 추가",
    handler="on_cell_add_suffix",
)

CELL_EXCEL_PASTE_ACTION = FeatureAction(
    id="cell_cleanup_excel_paste",
    label="공백·배경색 한 번에 정리",
    handler="on_cell_cleanup_excel_paste",
)

TABLE_INSERT_IMAGES_ACTION = FeatureAction(
    id="table_insert_images_into_cells",
    label="셀에 그림 넣기",
    handler="on_insert_images_into_cells",
)

TABLE_REFIT_IMAGES_ACTION = FeatureAction(
    id="table_refit_images_in_cells",
    label="기존 그림 다시 맞춤",
    handler="on_refit_images_in_cells",
)

TABLE_FILL_NONE_TOOL = {
    "title": "배경색 없애기",
    "action_id": "배경색없애기",
    "thumb": "table_thumbs/12_fill_none.png",
}

TABLE_V3_TOOLS = (
    (
        {
            "title": "내부 세로선 없애기",
            "action_id": "내부세로선없애기",
            "thumb": "table_thumbs/13_inner_vertical_none.png",
        },
        "표전체선없애기",
    ),
    (
        {
            "title": "내부 가로선 없애기",
            "action_id": "내부가로선없애기",
            "thumb": "table_thumbs/14_inner_horizontal_none.png",
        },
        "표전체선없애기",
    ),
    (
        {
            "title": "행 높이 같게",
            "action_id": "행높이같게",
            "thumb": "table_thumbs/15_equal_row_height.png",
        },
        "하늘색배경채우기",
    ),
    (
        {
            "title": "열 너비 같게",
            "action_id": "열너비같게",
            "thumb": "table_thumbs/16_equal_column_width.png",
        },
        "하늘색배경채우기",
    ),
)

TABLE_V31_TOOLS = (
    (
        {
            "title": "한 줄로 입력 설정",
            "action_id": "한줄로입력설정",
            "thumb": "table_thumbs/17_single_line_on.png",
        },
        "하늘색배경채우기",
    ),
    (
        {
            "title": "한 줄로 입력 해제",
            "action_id": "한줄로입력해제",
            "thumb": "table_thumbs/18_single_line_off.png",
        },
        "하늘색배경채우기",
    ),
    (
        {
            "title": "제목 셀 설정",
            "action_id": "제목셀설정",
            "thumb": "table_thumbs/19_header_cell_on.png",
        },
        "하늘색배경채우기",
    ),
    (
        {
            "title": "제목 셀 해제",
            "action_id": "제목셀해제",
            "thumb": "table_thumbs/20_header_cell_off.png",
        },
        "하늘색배경채우기",
    ),
)




def with_table_fill_none_tool(items):
    """v2.9 표 작업을 추가하되 공유 config의 원본 목록은 변경하지 않는다."""
    tools = [dict(item) for item in (items or [])]
    if any(item.get("action_id") == TABLE_FILL_NONE_TOOL["action_id"] for item in tools):
        return tools
    insert_at = next(
        (i for i, item in enumerate(tools) if item.get("action_id") == "빨간색강조선넣기"),
        len(tools),
    )
    tools.insert(insert_at, dict(TABLE_FILL_NONE_TOOL))
    return tools


def with_current_table_tools(items):
    """v3.1 표 작업을 추가하되 공유 config와 이전 버전 목록은 변경하지 않는다."""
    tools = with_table_fill_none_tool(items)
    action_ids = {item.get("action_id") for item in tools}
    for tool, before_action_id in TABLE_V3_TOOLS + TABLE_V31_TOOLS:
        if tool["action_id"] in action_ids:
            continue
        insert_at = next(
            (i for i, item in enumerate(tools) if item.get("action_id") == before_action_id),
            len(tools),
        )
        tools.insert(insert_at, dict(tool))
        action_ids.add(tool["action_id"])
    return tools

TEXT_COLOR_ACTIONS = (
    FontColorAction("검정", (0, 0, 0), "#000000", "#ffffff"),
    FontColorAction("빨강", (220, 0, 0), "#dc0000", "#ffffff"),
    FontColorAction("파랑", (0, 70, 200), "#0046c8", "#ffffff"),
    FontColorAction("흰색", (255, 255, 255), "#ffffff", "#444444"),
)

TEXT_FONT_ROWS = (
    FontRow("HY헤드라인M", (15, 16, 17, 18, 20, 25, 30)),
    FontRow("휴먼명조", (11, 12, 13, 14, 15, 17, 20)),
    FontRow("맑은 고딕", (9, 10, 11, 12, 13, 14, 15)),
    FontRow("굴림체", (9, 10, 11, 12, 13, 14, 15)),
)

TEXT_SPACING_ANCHOR_FONT = "굴림체"
TEXT_SPACING_ACTIONS = (
    FeatureAction(
        id="char_spacing_cleanup_level_1",
        label="자간 정리 1단계",
        handler="on_cleanup_line_spacing",
        args=(3,),
    ),
    FeatureAction(
        id="char_spacing_cleanup_level_2",
        label="자간 정리 2단계",
        handler="on_cleanup_line_spacing",
        args=(5,),
    ),
    FeatureAction(
        id="char_spacing_reset",
        label="자간 초기화",
        handler="on_reset_char_spacing",
    ),
)
