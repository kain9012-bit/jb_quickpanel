# -*- coding: utf-8 -*-
from src.jb_quickpanel_v22.core.runtime import *

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
        # 양끝 파이프는 있으면 제거
        if raw.startswith("|"):
            raw = raw[1:].lstrip()
        if raw.endswith("|"):
            raw = raw[:-1].rstrip()
        # Markdown 구분선은 제외
        compact = raw.replace(" ", "")
        if compact and set(compact) <= set("|-:"):
            continue
        cols = [c.strip() for c in raw.split("|")]
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
    s = (text or "")
    if s.startswith("- "):
        return s[2:]
    if s.startswith("-"):
        return s[1:].lstrip()
    return s
def split_section_title_text(text: str):
    s = (text or "").strip()
    m = re.match(r"^(\d+)\.\s*(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(\d+)\s+(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", s
def calc_indent(tag: str, current_level: str | None) -> int:
    if tag == "문서제목":
        return 0
    if tag == "제목":
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
def transform_report_text(raw_text: str):
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    current_level = None
    results = []
    changed_count = 0
    in_table = False
    table_lines = []

    def flush_table():
        nonlocal table_lines, results
        rows, max_cols = parse_pipe_table_lines(table_lines)
        if rows:
            results.append({
                "tag": "표",
                "text": "",
                "style": None,
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
            else:
                table_lines.append(line)
            continue

        if line == "":
            results.append({"tag": None, "text": "", "style": None})
            continue

        if tag == TABLE_START_TAG:
            changed_count += 1
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
        if tag == "제목":
            current_level = "제목"
        elif tag == "소제목":
            current_level = "소제목"
        elif tag == "소소제목":
            current_level = "소소제목"

        if tag == "문서제목":
            content = normalize_document_title_text(content)

        indent = calc_indent(tag, current_level)
        final_text = (" " * indent) + content
        style = REPORT_TAG_RULES[tag].copy()
        if tag in ("본문", "참고"):
            style["caret_indent_at"] = indent + 2
        else:
            style["caret_indent_at"] = None
        results.append({"tag": tag, "text": final_text, "style": style})

    if in_table:
        flush_table()

    return results, changed_count

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
