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
    label="기록된 범위 공백 제거",
    handler="on_cell_clean_spaces",
)

CELL_FIND_REPLACE_ACTION = FeatureAction(
    id="cell_find_replace",
    label="기록된 범위 찾아바꾸기",
    handler="on_cell_find_replace",
)

CELL_ADD_PREFIX_ACTION = FeatureAction(
    id="cell_add_prefix",
    label="앞에 넣기",
    handler="on_cell_add_prefix",
)

CELL_ADD_SUFFIX_ACTION = FeatureAction(
    id="cell_add_suffix",
    label="뒤에 넣기",
    handler="on_cell_add_suffix",
)

CELL_EXCEL_PASTE_ACTION = FeatureAction(
    id="cell_cleanup_excel_paste",
    label="기록된 범위 엑셀 서식 정리",
    handler="on_cell_cleanup_excel_paste",
)

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
