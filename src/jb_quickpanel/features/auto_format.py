# -*- coding: utf-8 -*-
from src.jb_quickpanel.core.runtime import *
from src.jb_quickpanel.features.auto_format_settings import (
    normalize_auto_format_settings,
)
from src.jb_quickpanel.features.untagged_report import (
    convert_untagged_report_to_tagged_text,
    strip_markdown_emphasis,
    split_pipe_cells,
    _is_markdown_separator,
    _parse_marker,
)


_ROLE_BY_TAG = {
    "문서제목": "document_title",
    "제목": "title",
    "소제목": "subtitle",
    "소소제목": "subsubtitle",
    "본문": "body",
    "참고": "reference",
}
_HANGUL_SEQUENCE = ("가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하")
_CIRCLED_NUMBERS = ("①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳")


def detect_report_tag(line: str):
    s = (line or "").lstrip("﻿")
    for tag in TAG_ORDER + [TABLE_START_TAG, TABLE_END_TAG]:
        prefix = f"({tag})"
        if s.startswith(prefix):
            rest = s[len(prefix):]
            if rest.startswith(" "):
                rest = rest[1:]
            return tag, rest
    return None, line


def parse_pipe_table_lines(lines):
    rows = []
    max_cols = 0
    for line in lines:
        if line is None:
            continue
        raw = str(line).rstrip("\n").strip()
        if raw == "":
            continue
        cols = split_pipe_cells(raw)
        if _is_markdown_separator(cols):
            continue
        cols = [strip_markdown_emphasis(cell) for cell in cols]
        rows.append(cols)
        if len(cols) > max_cols:
            max_cols = len(cols)
    if max_cols <= 0:
        max_cols = 1
    norm_rows = []
    for cols in rows:
        if len(cols) < max_cols:
            cols = cols + ([""] * (max_cols - len(cols)))
        norm_rows.append(cols)
    return norm_rows, max_cols


def normalize_document_title_text(text: str) -> str:
    s = text or ""
    if s.startswith("- "):
        return s[2:]
    if s.startswith("-"):
        return s[1:].lstrip()
    return s


def split_section_title_text(text: str):
    s = (text or "").strip()
    match = re.match(r"^(\d+)\.\s*(.*)$", s)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    match = re.match(r"^(\d+)\s+(.*)$", s)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", s


def calc_indent(tag: str, current_level: str | None) -> int:
    if tag in ("문서제목", "제목"):
        return 0
    if tag == "소제목":
        return 2
    if tag == "소소제목":
        return 4
    if tag == "본문":
        if current_level == "소소제목":
            return 6
        if current_level == "소제목":
            return 4
        return 2
    if tag == "참고":
        if current_level == "소소제목":
            return 8
        if current_level == "소제목":
            return 6
        return 4
    return 0


def _strip_role_marker(tag: str, content: str, custom_marker: str = "") -> str:
    value = (content or "").strip()
    custom = (custom_marker or "").strip()
    if custom and value.startswith(custom) and (
        value == custom or value[len(custom):].startswith(" ")
        or (not custom[-1].isalnum() and not value[len(custom):].startswith(custom))
    ):
        return value[len(custom):].lstrip()
    marker = _parse_marker(value)
    if marker is None:
        return value
    if tag in ("제목", "소제목", "소소제목"):
        return marker.body
    if tag == "본문" and marker.kind in {"dash", "bullet", "circle", "square"}:
        return marker.body
    if tag == "참고" and marker.kind in {"reference", "bullet"}:
        return marker.body
    return value


def _roman_number(value: int) -> str:
    number = max(1, int(value))
    parts = []
    for amount, numeral in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):
        while number >= amount:
            parts.append(numeral)
            number -= amount
    return "".join(parts)


def _unicode_roman(value: int, *, lower: bool = False) -> str:
    upper_values = (
        "Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ", "Ⅷ", "Ⅸ", "Ⅹ",
        "Ⅺ", "Ⅻ", "ⅩⅢ", "ⅩⅣ", "ⅩⅤ", "ⅩⅥ", "ⅩⅦ", "ⅩⅧ", "ⅩⅨ", "ⅩⅩ",
    )
    lower_values = (
        "ⅰ", "ⅱ", "ⅲ", "ⅳ", "ⅴ", "ⅵ", "ⅶ", "ⅷ", "ⅸ", "ⅹ",
        "ⅹⅰ", "ⅹⅱ", "ⅹⅲ", "ⅹⅳ", "ⅹⅴ", "ⅹⅵ", "ⅹⅶ", "ⅹⅷ", "ⅹⅸ", "ⅹⅹ",
    )
    index = max(1, int(value))
    values = lower_values if lower else upper_values
    if index <= len(values):
        return values[index - 1]
    fallback = _roman_number(index)
    return fallback.lower() if lower else fallback


def _marker_prefix(tag: str, marker: str, count: int, custom_marker: str = "") -> str:
    if marker == "none":
        return ""
    if marker == "custom":
        custom = (custom_marker or "").strip()
        return f"{custom} " if custom else ""

    index = max(1, int(count or 1))
    if marker == "number_dot":
        return f"{index}. "
    if marker == "number_paren":
        return f"{index}) "
    if marker in ("hangul_dot", "hangul_paren"):
        letter = _HANGUL_SEQUENCE[min(index, len(_HANGUL_SEQUENCE)) - 1]
        return f"{letter}) " if marker == "hangul_paren" else f"{letter}. "
    if marker == "roman_upper_dot":
        return f"{_unicode_roman(index)}. "
    if marker == "roman_lower_dot":
        return f"{_unicode_roman(index, lower=True)}. "
    if marker == "number_circle":
        return _CIRCLED_NUMBERS[min(index, len(_CIRCLED_NUMBERS)) - 1] + " "

    symbols = {
        "dash": "- ",
        "asterisk": "* ",
        "circle": "○ ",
        "square": "□ ",
        "bullet": "• ",
        "reference": "※ ",
    }
    return symbols.get(marker, "")


def _section_number_text(marker: str, marker_prefix: str) -> str:
    value = marker_prefix.strip()
    if marker in {"number_dot", "hangul_dot", "roman_upper_dot", "roman_lower_dot"}:
        return value.removesuffix(".")
    return value


def transform_report_text(raw_text: str, format_settings=None):
    options = normalize_auto_format_settings(format_settings)
    roles = options["roles"]
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    current_level = None
    results = []
    changed_count = 0
    in_table = False
    table_lines = []
    heading_counts = {"제목": 0, "소제목": 0, "소소제목": 0}

    def flush_table():
        nonlocal table_lines, results
        rows, max_cols = parse_pipe_table_lines(table_lines)
        if rows:
            table_style = roles["table"]
            results.append({
                "tag": "표",
                "text": "",
                "style": {
                    "font": table_style["font"],
                    "size": int(table_style["size"]),
                    "bold": bool(table_style.get("bold", False)),
                    "caret_indent_at": None,
                },
                "rows": rows,
                "cols": max_cols,
            })
        table_lines = []

    for line in lines:
        tag, content = detect_report_tag(line)

        if in_table:
            if tag == TABLE_END_TAG:
                changed_count += 1
                flush_table()
                in_table = False
                if content.strip():
                    results.append({"tag": None, "text": content, "style": None})
                continue
            if tag is None:
                table_lines.append(line)
                continue
            flush_table()
            in_table = False
        if line == "":
            results.append({"tag": None, "text": "", "style": None})
            continue
        if tag == TABLE_START_TAG:
            changed_count += 1
            if content.strip():
                results.append({"tag": None, "text": content, "style": None})
            in_table = True
            table_lines = []
            continue
        if tag == TABLE_END_TAG:
            changed_count += 1
            continue
        if tag is None:
            results.append({"tag": None, "text": line, "style": None})
            continue

        changed_count += 1
        content = strip_markdown_emphasis(content)
        if tag == "제목":
            current_level = "제목"
            heading_counts["제목"] += 1
            heading_counts["소제목"] = 0
            heading_counts["소소제목"] = 0
        elif tag == "소제목":
            current_level = "소제목"
            heading_counts["소제목"] += 1
            heading_counts["소소제목"] = 0
        elif tag == "소소제목":
            current_level = "소소제목"
            heading_counts["소소제목"] += 1

        marker_prefix = ""
        marker = "none"
        marker_content = content
        if tag == "문서제목":
            content = normalize_document_title_text(content)
        elif tag in ("제목", "소제목", "소소제목", "본문", "참고"):
            role = _ROLE_BY_TAG[tag]
            marker = str(roles[role].get("marker") or "none")
            custom_marker = str(roles[role].get("custom_marker") or "")
            marker_content = _strip_role_marker(tag, content, custom_marker)
            marker_prefix = _marker_prefix(
                tag,
                marker,
                heading_counts.get(tag, 0),
                custom_marker,
            )
            content = marker_prefix + marker_content

        indent = calc_indent(tag, current_level)
        final_text = (" " * indent) + content
        role_style = roles[_ROLE_BY_TAG[tag]]
        style = {
            "font": role_style["font"],
            "size": int(role_style["size"]),
            "bold": bool(role_style.get("bold", False)),
        }
        if tag in ("본문", "참고"):
            style["caret_indent_at"] = indent + len(marker_prefix)
        else:
            style["caret_indent_at"] = None
        result = {"tag": tag, "text": final_text, "style": style}
        if tag == "제목":
            result["number_text"] = _section_number_text(marker, marker_prefix)
            result["body_text"] = marker_content.strip()
        results.append(result)

    if in_table:
        flush_table()
    return results, changed_count


def transform_untagged_as_tagged_text(
    raw_text: str, *, has_external_table: bool = False, format_settings=None
):
    virtual_tagged_text, _ = convert_untagged_report_to_tagged_text(
        raw_text,
        has_external_table=has_external_table,
    )
    return transform_report_text(virtual_tagged_text, format_settings)


def transform_auto_format_text(raw_text: str, format_settings=None):
    tagged_items, tagged_count = transform_report_text(raw_text, format_settings)
    if tagged_count > 0:
        return tagged_items, tagged_count, "tagged"
    inferred_items, inferred_count = transform_untagged_as_tagged_text(
        raw_text,
        format_settings=format_settings,
    )
    return inferred_items, inferred_count, "inferred"

PROMPT_FILENAME = "report_format_prompt.txt"
UI_SETTINGS_FILENAME = "hwp_helper_ui_settings.json"
KEDUFIN_SUPPORTED_BLOCK_TITLES = {"표박스", "참고박스", "3단계절차박스", "4단계절차박스"}


def external_base_dir() -> str:
    """
    사용자가 수정할 수 있는 외부 파일 기준 경로.
    - .py 실행: 현재 py 파일 폴더
    - PyInstaller EXE 실행: exe 파일이 있는 폴더
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return resource_base_dir()


def external_path(rel_path: str) -> str:
    return os.path.abspath(os.path.join(external_base_dir(), rel_path))


def prompt_candidate_paths():
    """
    프롬프트 파일 후보 경로.
    1순위: EXE 옆 외부 txt(나중에 프롬프트만 교체할 때 사용)
    2순위: PyInstaller onefile 내부에 포함된 txt(_MEIPASS)
    3순위: 개발 중 현재 py 파일 폴더의 txt
    """
    paths = []

    # EXE 옆 외부 파일: 있으면 내장 파일보다 우선 사용
    paths.append(external_path(PROMPT_FILENAME))

    # PyInstaller --add-data로 EXE 내부에 포함된 파일
    paths.append(resource_path(PROMPT_FILENAME))

    unique = []
    seen = set()
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen:
            unique.append(ap)
            seen.add(ap)
    return unique


def read_report_prompt():
    """별도 txt 파일에서 프롬프트를 읽는다. 빈 줄은 그대로 유지한다."""
    tried = prompt_candidate_paths()
    found_path = None
    for path in tried:
        if os.path.exists(path):
            found_path = path
            break

    if not found_path:
        return False, (
            "프롬프트 파일을 찾지 못했습니다.\n\n"
            f"EXE 내부 또는 EXE와 같은 폴더에 '{PROMPT_FILENAME}' 파일이 필요합니다.\n"
            "확인한 위치:\n- " + "\n- ".join(tried)
        )

    try:
        # utf-8-sig: 메모장 등에서 BOM이 붙어도 첫 글자가 깨지지 않게 처리
        # newline=None: CRLF/LF 모두 읽되, 아래 복사 단계에서 다시 CRLF로 맞춤
        with open(found_path, "r", encoding="utf-8-sig", newline=None) as f:
            prompt = f.read()
        if not prompt.strip():
            return False, f"프롬프트 파일이 비어 있습니다.\n\n파일 위치: {found_path}"
        return True, prompt
    except Exception as e:
        return False, f"프롬프트 파일 읽기 실패: {e}\n\n파일 위치: {found_path}"



def copy_text_preserve_blank_lines(root: tk.Tk, text: str):
    """빈 줄 유지를 위해 Windows 클립보드용 CRLF 줄바꿈으로 복사한다."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    windows_text = normalized.replace("\n", "\r\n")

    if win32clipboard is not None:
        set_clipboard_text(windows_text)
    else:
        root.clipboard_clear()
        root.clipboard_append(windows_text)
        root.update_idletasks()
