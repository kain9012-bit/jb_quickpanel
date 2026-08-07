# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from src.jb_quickpanel.core.runtime import REPORT_TAG_RULES


@dataclass(frozen=True)
class Marker:
    kind: str
    token: str
    body: str


@dataclass(frozen=True)
class TableBlock:
    start: int
    end: int
    rows: list[list[str]]
    cols: int


_STRUCTURAL_ORDER = {
    "md_heading_1": 10,
    "md_heading_2": 11,
    "md_heading_3": 12,
    "md_heading_4": 13,
    "md_heading_5": 14,
    "md_heading_6": 15,
    "roman_dot": 20,
    "number_dot": 30,
    "hangul_dot": 40,
    "number_paren": 50,
    "hangul_paren": 60,
    "circled_number": 70,
    "square": 80,
    "bold_heading": 90,
    "plain_heading": 100,
}

_INDENT_BY_TAG = {
    "문서제목": 0,
    "제목": 0,
    "소제목": 2,
    "소소제목": 4,
    "본문": 6,
    "참고": 8,
}

_PLAIN_HEADING_WORDS = (
    "개요",
    "배경",
    "목적",
    "방향",
    "방침",
    "계획",
    "현황",
    "내용",
    "방법",
    "대상",
    "기간",
    "장소",
    "절차",
    "일정",
    "예산",
    "역할",
    "추진체계",
    "세부계획",
    "운영계획",
    "행정사항",
    "협조사항",
    "기대효과",
    "향후계획",
)


def _unwrap_markdown_cell(text: str) -> str:
    value = (text or "").strip()
    changed = True
    while changed and len(value) >= 2:
        changed = False
        for wrapper in ("**", "__", "`"):
            if value.startswith(wrapper) and value.endswith(wrapper) and len(value) > len(wrapper) * 2:
                value = value[len(wrapper):-len(wrapper)].strip()
                changed = True
                break
    return value


def _pipe_cells(line: str) -> list[str] | None:
    raw = (line or "").strip()
    if raw.count("|") < 2:
        return None
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    cells = [cell.strip() for cell in raw.split("|")]
    return cells if len(cells) >= 2 else None


def _tab_cells(line: str) -> list[str] | None:
    raw = (line or "").rstrip("\r\n")
    if "\t" not in raw:
        return None
    cells = [cell.strip() for cell in raw.split("\t")]
    return cells if len(cells) >= 2 else None


def _is_markdown_separator(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) is not None for cell in cells)


def _normalize_table_rows(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    cleaned = [[_unwrap_markdown_cell(cell) for cell in row] for row in rows]
    cols = max((len(row) for row in cleaned), default=0)
    normalized = [row + ([""] * (cols - len(row))) for row in cleaned]
    return normalized, cols


def _validated_table_block(lines: list[str], start: int, kind: str) -> TableBlock | None:
    parser = _pipe_cells if kind == "pipe" else _tab_cells
    parsed: list[list[str]] = []
    end = start
    while end < len(lines):
        cells = parser(lines[end])
        if cells is None:
            break
        parsed.append(cells)
        end += 1

    data_rows = [row for row in parsed if not (kind == "pipe" and _is_markdown_separator(row))]
    if len(data_rows) < 2:
        return None

    counts = Counter(len(row) for row in data_rows)
    common_cols, common_count = counts.most_common(1)[0]
    if common_cols < 2 or common_count < max(2, len(data_rows) - 1):
        return None

    normalized, cols = _normalize_table_rows(data_rows)
    return TableBlock(start=start, end=end, rows=normalized, cols=cols)


def detect_untagged_table_blocks(lines: list[str]) -> list[TableBlock]:
    blocks: list[TableBlock] = []
    index = 0
    while index < len(lines):
        block = None
        if _pipe_cells(lines[index]) is not None:
            block = _validated_table_block(lines, index, "pipe")
        if block is None and _tab_cells(lines[index]) is not None:
            block = _validated_table_block(lines, index, "tab")
        if block is None:
            index += 1
            continue
        blocks.append(block)
        index = block.end
    return blocks


def _parse_marker(text: str) -> Marker | None:
    value = (text or "").strip()
    if not value:
        return None

    match = re.match(r"^(#{1,6})\s+(.+)$", value)
    if match:
        level = len(match.group(1))
        return Marker(f"md_heading_{level}", match.group(1), match.group(2).strip())

    if ((value.startswith("**") and value.endswith("**")) or
            (value.startswith("__") and value.endswith("__"))):
        body = _unwrap_markdown_cell(value)
        if body:
            return Marker("bold_heading", "", body)

    patterns = (
        ("reference", r"^(※|주\)|\*\))\s*(.*)$"),
        ("roman_dot", r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫIVX]+)\.\s+(.+)$"),
        ("number_dot", r"^(\d{1,3})\.\s+(.+)$"),
        ("hangul_dot", r"^([가-하])\.\s+(.+)$"),
        ("number_paren", r"^(\(?\d{1,3}\))\s+(.+)$"),
        ("hangul_paren", r"^(\(?[가-하]\))\s+(.+)$"),
        ("circled_number", r"^([①-⑳])\s+(.+)$"),
        ("square", r"^([□■▣◇◆ㅁ])\s*(.+)$"),
        ("circle", r"^([○●◦ㅇ])\s*(.+)$"),
        ("dash", r"^([-–—·ㆍ•])\s+(.+)$"),
    )
    for kind, pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return Marker(kind, match.group(1), match.group(2).strip())
    return None


def _looks_like_plain_heading(text: str) -> bool:
    value = (text or "").strip()
    if not value or len(value) > 32:
        return False
    if re.search(r"(합니다|됩니다|있습니다|없습니다|한다|된다|있다|없다|함|임)\.?$", value):
        return False
    compact = re.sub(r"\s+", "", value)
    return any(compact.endswith(word) for word in _PLAIN_HEADING_WORDS)


_HANGUL_SEQUENCE = ("가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하")


def _looks_like_unmarked_reference(text: str) -> bool:
    value = (text or "").strip()
    return re.match(r"^(참고|주의|유의|비고)(사항)?(?:\s*[:：-]\s*|\s+).+", value) is not None


def _effective_heading_marker(marker: Marker | None) -> Marker | None:
    if marker is None:
        return None
    if marker.kind.startswith("md_heading_") or marker.kind == "bold_heading":
        nested = _parse_marker(marker.body)
        if nested is not None and nested.kind in _STRUCTURAL_ORDER:
            return nested
        return None
    return marker if marker.kind in _STRUCTURAL_ORDER else None


def _next_heading_prefix(tag: str, count: int) -> str:
    if tag == "제목":
        return f"{count}. "
    if tag == "소제목":
        index = min(max(1, count), len(_HANGUL_SEQUENCE)) - 1
        return f"{_HANGUL_SEQUENCE[index]}. "
    if tag == "소소제목":
        return f"{count}) "
    return ""


def _title_candidate(text: str, marker: Marker | None, has_following_structure: bool) -> bool:
    if not has_following_structure:
        return False
    if marker is not None:
        return marker.kind in ("md_heading_1", "bold_heading")
    value = (text or "").strip()
    if not (2 <= len(value) <= 80):
        return False
    if "\t" in value or "|" in value:
        return False
    if re.match(r"^(붙임|첨부|참고|담당|작성자|수신)\b", value):
        return False
    if re.search(r"(합니다|됩니다|있습니다|없습니다|한다|된다|있다|없다|함|임)\.?$", value):
        return False
    return True


def _display_text(original: str, marker: Marker | None) -> str:
    if marker is not None and marker.kind.startswith("md_heading_"):
        return marker.body
    if marker is not None and marker.kind == "bold_heading":
        return marker.body
    return (original or "").strip()


def _heading_key(text: str, marker: Marker | None) -> str | None:
    if marker is not None and marker.kind in _STRUCTURAL_ORDER:
        return marker.kind
    if marker is None and _looks_like_plain_heading(text):
        return "plain_heading"
    return None


def _section_box_parts(display_text: str, marker: Marker | None) -> tuple[str, str]:
    effective = _effective_heading_marker(marker)
    if effective is None:
        return "", display_text
    token = effective.token.strip().rstrip(".")
    if token.startswith("(") and token.endswith(")"):
        token = token[1:-1]
    elif token.endswith(")"):
        token = token[:-1]
    return token, effective.body


def _styled_item(
    tag: str,
    original: str,
    marker: Marker | None,
    generated_prefix: str = "",
) -> dict:
    display = _display_text(original, marker)
    inserted_prefix = generated_prefix
    if inserted_prefix:
        display = inserted_prefix + display
    indent = _INDENT_BY_TAG[tag]
    final_text = (" " * indent) + display
    style = REPORT_TAG_RULES[tag].copy()
    marker_width = len(marker.token) + 1 if marker is not None and marker.token else len(inserted_prefix)
    if tag in ("본문", "참고"):
        style["caret_indent_at"] = indent + marker_width
    else:
        style["caret_indent_at"] = None
    item = {
        "tag": tag,
        "text": final_text,
        "style": style,
        "source_caret_offset": marker_width,
        "inserted_prefix": inserted_prefix,
    }
    if tag == "제목":
        if generated_prefix:
            item["number_text"] = generated_prefix.strip().rstrip(".")
            item["body_text"] = _display_text(original, marker)
        else:
            number_text, body_text = _section_box_parts(display, marker)
            item["number_text"] = number_text
            item["body_text"] = body_text
    return item


def transform_untagged_report_text(
    raw_text: str, *, has_external_table: bool = False
) -> tuple[list[dict], int]:
    normalized = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    table_blocks = detect_untagged_table_blocks(lines)
    table_by_start = {block.start: block for block in table_blocks}
    table_line_indexes = {
        index
        for block in table_blocks
        for index in range(block.start, block.end)
    }

    markers: dict[int, Marker | None] = {}
    heading_keys: dict[int, str] = {}
    meaningful_indexes: list[int] = []
    for index, line in enumerate(lines):
        if index in table_line_indexes or not line.strip():
            continue
        meaningful_indexes.append(index)
        marker = _parse_marker(line)
        markers[index] = marker
        key = _heading_key(line, marker)
        if key is not None:
            heading_keys[index] = key

    first_index = meaningful_indexes[0] if meaningful_indexes else None
    has_following_structure = bool(table_blocks) or bool(has_external_table)
    if first_index is not None:
        has_following_structure = has_following_structure or any(
            index != first_index for index in heading_keys
        )

    document_title_index = None
    if first_index is not None and _title_candidate(
        lines[first_index], markers.get(first_index), has_following_structure
    ):
        document_title_index = first_index
        heading_keys.pop(first_index, None)

    observed_keys = sorted(
        set(heading_keys.values()),
        key=lambda key: _STRUCTURAL_ORDER.get(key, 999),
    )
    heading_tags = {
        key: ("제목" if level == 0 else "소제목" if level == 1 else "소소제목")
        for level, key in enumerate(observed_keys)
    }

    results: list[dict] = []
    changed_count = 0
    heading_counts = {"제목": 0, "소제목": 0, "소소제목": 0}
    index = 0
    while index < len(lines):
        block = table_by_start.get(index)
        if block is not None:
            results.append({
                "tag": "표",
                "text": "",
                "style": None,
                "rows": block.rows,
                "cols": block.cols,
            })
            changed_count += 1
            index = block.end
            continue

        line = lines[index]
        if not line.strip():
            results.append({"tag": None, "text": "", "style": None})
            index += 1
            continue

        marker = markers.get(index)
        if index == document_title_index:
            tag = "문서제목"
        elif marker is not None and marker.kind == "reference":
            tag = "참고"
        elif marker is None and _looks_like_unmarked_reference(line):
            tag = "참고"
        else:
            key = heading_keys.get(index)
            tag = heading_tags.get(key, "본문")

        generated_prefix = ""
        if tag in ("제목", "소제목", "소소제목"):
            heading_counts[tag] += 1
            if tag == "제목":
                heading_counts["소제목"] = 0
                heading_counts["소소제목"] = 0
            elif tag == "소제목":
                heading_counts["소소제목"] = 0
            if _effective_heading_marker(marker) is None:
                generated_prefix = _next_heading_prefix(tag, heading_counts[tag])
        elif tag == "본문" and marker is None:
            generated_prefix = "- "
        elif tag == "참고" and marker is None:
            generated_prefix = "※ "

        results.append(_styled_item(tag, line, marker, generated_prefix))
        changed_count += 1
        index += 1

    return results, changed_count
