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
    "chapter": 16,
    "section": 18,
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
    "추진배경",
    "추진목적",
    "추진방향",
    "추진방침",
    "세부추진계획",
    "추진일정",
    "소요예산",
    "예산계획",
    "기대효과",
    "성과지표",
    "평가계획",
    "안전관리",
    "홍보계획",
    "업무분장",
    "사업개요",
    "운영개요",
    "안내문안",
)

_AI_PREAMBLE_PATTERNS = (
    r"^(?:다음은|아래는)\s+.*(?:계획서|보고서|초안).*(?:입니다|작성했습니다|정리했습니다)[.!]?$",
    r"^(?:요청하신|말씀하신)\s+.*(?:계획서|보고서|초안).*$",
)

_AI_CLOSING_PATTERNS = (
    r"^(?:필요하시면|원하시면|추가로)\s+.*(?:수정|보완|작성|정리).*(?:드리겠습니다|할 수 있습니다)[.!]?$",
)


def strip_markdown_emphasis(text: str) -> str:
    parts = re.split(r"(`+[^`\n]*`+)", text or "")
    for index in range(0, len(parts), 2):
        value = re.sub(r"(?<![\\*])\*\*(?!\*)(?=\S)(.+?)(?<=\S)(?<!\\)\*\*(?!\*)", r"\1", parts[index])
        parts[index] = re.sub(r"(?<![\w\\_])__(?!_)(?=\S)(.+?)(?<=\S)(?<!\\)__(?![\w_])", r"\1", value)
    return "".join(parts)


def split_pipe_cells(line: str) -> list[str]:
    raw = (line or "").strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        backslashes = len(raw[:-1]) - len(raw[:-1].rstrip("\\"))
        if backslashes % 2 == 0:
            raw = raw[:-1]
    cells, cell = [], []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\":
            end = index
            while end < len(raw) and raw[end] == "\\":
                end += 1
            count = end - index
            if end < len(raw) and raw[end] == "|":
                cell.append("\\" * (count // 2))
                if count % 2:
                    cell.append("|")
                    index = end + 1
                    continue
                index = end
                continue
            cell.append(raw[index:end])
            index = end
            continue
        if char == "|":
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(char)
        index += 1
    cells.append("".join(cell).strip())
    return cells


def escape_pipe_cell(text: str) -> str:
    return re.sub(r"(\\*)\|", lambda match: "\\" * (2 * len(match.group(1)) + 1) + "|", str(text))


def _unwrap_markdown_cell(text: str) -> str:
    value = (text or "").strip()
    changed = True
    while changed and len(value) >= 2:
        changed = False
        for wrapper in ("**", "__", "`"):
            if value.startswith(wrapper) and value.endswith(wrapper) and len(value) > len(wrapper) * 2:
                inner = value[len(wrapper):-len(wrapper)].strip()
                if wrapper != "`" and wrapper in inner:
                    continue
                value = inner
                changed = True
                break
    return strip_markdown_emphasis(value)


def _pipe_cells(line: str) -> list[str] | None:
    raw = (line or "").strip()
    if "|" not in raw:
        return None
    cells = split_pipe_cells(raw)
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
        return Marker(f"md_heading_{level}", match.group(1), strip_markdown_emphasis(match.group(2).strip()))

    if re.fullmatch(r"(?:\*\*[^*]+\*\*|__[^_]+__)", value):
        body = _unwrap_markdown_cell(value)
        if body and not re.search(r"(합니다|됩니다|있습니다|없습니다|한다|된다|있다|없다|함|임)\.?$", body):
            return Marker("bold_heading", "", body)

    value = strip_markdown_emphasis(value)

    patterns = (
        ("chapter", r"^(제\s*\d+\s*장)\s*[:：.]?\s*(.+)$"),
        ("section", r"^(제\s*\d+\s*절)\s*[:：.]?\s*(.+)$"),
        ("reference", r"^(※|주\)|\*\))\s*(.*)$"),
        ("roman_dot", r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ]+)\.\s+(.+)$"),
        ("roman_dot", r"^([IVXLCDMivxlcdm]+)\.\s+([가-힣].*)$"),
        ("number_dot", r"^(\d{1,3})\.\s+(?=\S)(?!\d{1,2}\.(?:\s|\(|$))(.+)$"),
        ("number_dot", r"^(\d{1,3})\s+(?!(?:명|개|건|회|쪽|페이지|일|개월|년|시간|분|초|원)(?:\s|$))(\S.*)$"),
        ("hangul_dot", r"^([가-하])\.\s+(.+)$"),
        ("number_paren", r"^(\(?\d{1,3}\))\s+(.+)$"),
        ("hangul_paren", r"^(\(?[가-하]\))\s+(.+)$"),
        ("circled_number", r"^([①-⑳])\s+(.+)$"),
        ("square", r"^([□■▣◇◆ㅁ])(?!\1)\s*(.+)$"),
        ("circle", r"^([○●◦ㅇ])(?!\1)\s*(.+)$"),
        ("dash", r"^([-–—·ㆍ•])\s+(.+)$"),
        ("check", r"^(\[(?: |x|X|v|V|✓)?\]|☐|☑|✓|✔)\s*(.+)$"),
        ("bullet", r"^([*+])\s+(.+)$"),
    )
    for kind, pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return Marker(kind, match.group(1), strip_markdown_emphasis(match.group(2).strip()))
    return None


def _looks_like_plain_heading(text: str) -> bool:
    value = strip_markdown_emphasis(text).strip()
    value = re.sub(r"\s*[:：]\s*$", "", value)
    if not value or len(value) > 40:
        return False
    if re.search(r"(합니다|됩니다|있습니다|없습니다|한다|된다|있다|없다|함|임)\.?$", value):
        return False
    compact = re.sub(r"\s+", "", value)
    return any(compact.endswith(word) for word in _PLAIN_HEADING_WORDS)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    value = (text or "").strip()
    return any(re.match(pattern, value, re.IGNORECASE) is not None for pattern in patterns)


def _normalize_ai_draft_lines(raw_text: str) -> tuple[list[str], set[int]]:
    normalized = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    removed: set[int] = set()
    meaningful = [index for index, line in enumerate(lines) if line.strip()]

    for index in meaningful[:2]:
        if _matches_any(lines[index], _AI_PREAMBLE_PATTERNS):
            removed.add(index)
    for index in meaningful[-2:]:
        if _matches_any(lines[index], _AI_CLOSING_PATTERNS):
            removed.add(index)

    for index, line in enumerate(lines):
        value = line.strip()
        if re.fullmatch(r"\x60\x60\x60(?:markdown|md|text|plaintext)?", value, re.IGNORECASE):
            removed.add(index)
        elif re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", value):
            removed.add(index)
        elif value.startswith("> "):
            lines[index] = value[2:].strip()
    return lines, removed


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
        if marker.kind == "md_heading_1":
            return _parse_marker(marker.body) is None
        if marker.kind == "bold_heading":
            return _parse_marker(marker.body) is None
        return False
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
        return strip_markdown_emphasis(marker.body)
    if marker is not None and marker.kind == "bold_heading":
        return marker.body
    return strip_markdown_emphasis(original).strip()


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
    lines, removed_indexes = _normalize_ai_draft_lines(raw_text)
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
        if index in removed_indexes or index in table_line_indexes or not line.strip():
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

    observed_keys = list(
        dict.fromkeys(
            heading_keys[index]
            for index in meaningful_indexes
            if index in heading_keys
        )
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
        if index in removed_indexes:
            changed_count += 1
            index += 1
            continue

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


def _virtual_tag_body(item: dict) -> str:
    value = str(item.get("text") or "").strip()
    marker = _parse_marker(value)
    if marker is not None:
        return marker.body.strip()
    return value


def convert_untagged_report_to_tagged_text(
    raw_text: str, *, has_external_table: bool = False
) -> tuple[str, int]:
    """Convert a plain AI draft to the canonical tag format used by the formatter."""
    items, inferred_count = transform_untagged_report_text(
        raw_text,
        has_external_table=has_external_table,
    )
    lines: list[str] = []
    previous_tag: str | None = None
    heading_counts = {"제목": 0, "소제목": 0, "소소제목": 0}

    def append_blank() -> None:
        if lines and lines[-1] != "":
            lines.append("")

    for item in items:
        tag = item.get("tag")
        if tag is None:
            continue

        if tag == "표":
            lines.append("(표시작)")
            for row in item.get("rows") or []:
                lines.append(" | ".join(escape_pipe_cell(str(cell).strip()) for cell in row))
            lines.append("(표끝)")
            append_blank()
            previous_tag = "표끝"
            continue

        if tag == "제목":
            append_blank()
        elif tag in ("소제목", "소소제목") and previous_tag in (
            "본문",
            "참고",
            "표끝",
        ):
            append_blank()

        if tag == "문서제목":
            body = _virtual_tag_body(item)
            content = f"- {body}"
        elif tag in ("제목", "소제목", "소소제목"):
            heading_counts[tag] += 1
            if tag == "제목":
                heading_counts["소제목"] = 0
                heading_counts["소소제목"] = 0
            elif tag == "소제목":
                heading_counts["소소제목"] = 0
            body = _virtual_tag_body(item)
            content = _next_heading_prefix(tag, heading_counts[tag]) + body
        elif tag == "본문":
            content = f"- {_virtual_tag_body(item)}"
        elif tag == "참고":
            content = f"※ {_virtual_tag_body(item)}"
        else:
            continue

        lines.append(f"({tag}) {content}".rstrip())
        previous_tag = str(tag)

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines), inferred_count
