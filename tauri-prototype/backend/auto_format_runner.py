# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from src.jb_quickpanel.features.auto_format import (
    read_report_prompt,
    split_section_title_text,
    transform_auto_format_text,
)
from src.jb_quickpanel.features.untagged_report import transform_untagged_report_text


AUTO_FORMAT_CANCEL_FILE = (
    Path(tempfile.gettempdir()) / "jb_hwp_helper_tauri_auto_format.cancel"
)


def clear_cancel_request() -> None:
    try:
        AUTO_FORMAT_CANCEL_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def cancel_requested() -> bool:
    return AUTO_FORMAT_CANCEL_FILE.is_file()


def copy_report_prompt_to_clipboard(set_clipboard_text: Callable[[str], None]):
    ok, prompt_or_message = read_report_prompt()
    if not ok:
        return False, prompt_or_message, {}
    normalized = str(prompt_or_message).replace("\r\n", "\n").replace("\r", "\n")
    set_clipboard_text(normalized.replace("\n", "\r\n"))
    return True, "공문서 초안 작성 프롬프트를 클립보드에 복사했습니다.", {}


def _template_file_by_title(style_records, wanted_title: str) -> str | None:
    wanted = str(wanted_title or "").strip().replace(" ", "")
    for record in style_records:
        title = str(record.get("title") or "").strip().replace(" ", "")
        file_path = Path(str(record.get("file_path") or ""))
        if title == wanted and file_path.is_file():
            return str(file_path)
    return None


def _cancelled_result(mode: str, changed_count: int = 0):
    return False, "서식 자동 지정을 중지했습니다.", {
        "cancelled": True,
        "mode": mode,
        "changed_count": changed_count,
    }


def _failure(message: str, mode: str = "", changed_count: int = 0):
    return False, str(message), {
        "cancelled": False,
        "mode": mode,
        "changed_count": changed_count,
    }


def _notify(progress, message: str) -> None:
    if callable(progress):
        progress(message)


def _settle_cursor_after_inserted_table(bridge):
    # 한글이 표 선택 해제 상태를 반영하기 전에 다음 문단을 넣으면
    # 마지막 셀 안에 이어 붙을 수 있어, 선택 해제와 이탈 확인을 한 번 더 수행한다.
    time.sleep(0.08)
    run_supported = getattr(bridge, "run_first_supported", None)
    if callable(run_supported):
        run_supported(["Cancel", "CloseEx", "Esc"])

    for attempt in range(2):
        ok, message = bridge.ensure_cursor_outside_table()
        if not ok:
            return False, message
        if attempt == 0:
            time.sleep(0.04)
    return True, "OK"


def _run_inferred_with_native_tables(
    bridge,
    transformed,
    inspection,
    style_records,
    cancelled,
    progress,
):
    paragraphs = list(inspection.get("paragraphs") or [])
    table_positions = list(inspection.get("native_table_positions") or [])
    paragraph_items = [
        item
        for item in transformed
        if item.get("style") is not None and item.get("tag") != "표"
    ]

    if len(paragraph_items) != len(paragraphs):
        body_text = "\n".join(
            str(paragraph.get("text") or "") for paragraph in paragraphs
        )
        body_transformed, _ = transform_untagged_report_text(
            body_text,
            has_external_table=bool(table_positions),
        )
        paragraph_items = [
            item
            for item in body_transformed
            if item.get("style") is not None and item.get("tag") != "표"
        ]

    if len(paragraph_items) != len(paragraphs):
        return _failure(
            "표 밖 문단의 위치를 정확히 연결하지 못했습니다. "
            "원본 표를 보호하기 위해 작업을 중단했습니다.",
            "inferred",
        )

    title_box_file = _template_file_by_title(style_records, "제목박스")
    section_box_file = _template_file_by_title(style_records, "소제목박스")
    if any(item.get("tag") == "문서제목" for item in paragraph_items):
        if not title_box_file:
            return _failure(
                "서식 탭에서 '제목박스' 파일을 찾지 못했습니다.",
                "inferred",
            )
    if any(item.get("tag") == "제목" for item in paragraph_items):
        if not section_box_file:
            return _failure(
                "서식 탭에서 '소제목박스' 파일을 찾지 못했습니다.",
                "inferred",
            )
    if cancelled():
        return _cancelled_result("inferred")

    def table_progress(current, total):
        _notify(progress, f"한글 표 서식 지정 중... ({current}/{total})")

    ok, message = bridge.format_native_report_tables(
        table_positions,
        progress=table_progress,
        cancelled=cancelled,
    )
    if not ok:
        if message == "CANCELLED" or cancelled():
            return _cancelled_result("inferred")
        return _failure(message, "inferred")

    def paragraph_progress(current, total):
        _notify(progress, f"표 밖 문단 서식 지정 중... ({current}/{total})")

    ok, message = bridge.apply_inferred_report_paragraphs(
        paragraphs,
        paragraph_items,
        title_box_file=title_box_file,
        section_box_file=section_box_file,
        progress=paragraph_progress,
        cancelled=cancelled,
    )
    if not ok:
        if message == "CANCELLED" or cancelled():
            return _cancelled_result("inferred")
        return _failure(message, "inferred")

    changed_count = len(paragraph_items) + len(table_positions)
    return True, f"서식 자동 지정 완료 ({changed_count}개 문단·표)", {
        "cancelled": False,
        "mode": "inferred",
        "changed_count": changed_count,
        "native_table_count": len(table_positions),
    }


def run_auto_format(
    bridge,
    style_records: list[dict[str, Any]],
    *,
    cancelled: Callable[[], bool] = cancel_requested,
    progress: Callable[[str], None] | None = None,
):
    _notify(progress, "기본 보고서 편집용지 적용 중...")
    ok, message = bridge.apply_basic_report_page_setup()
    if not ok:
        return _failure(f"기본 보고서 편집용지 적용 실패: {message}")

    if cancelled():
        return _cancelled_result("")

    _notify(progress, "선택 영역 읽는 중...")
    ok, raw_text = bridge.get_selected_text()
    if not ok:
        return _failure(raw_text)

    transformed, changed_count, format_mode = transform_auto_format_text(raw_text)
    if changed_count == 0:
        return True, "선택한 영역에서 서식을 적용할 문단을 찾지 못했습니다.", {
            "cancelled": False,
            "mode": format_mode,
            "changed_count": 0,
        }

    if format_mode == "inferred":
        _notify(progress, "태그 없는 문서의 문단 체계와 표 분석 중...")
        inspected, inspection = bridge.inspect_selected_report_content()
        if (
            inspected
            and isinstance(inspection, dict)
            and inspection.get("native_table_positions")
        ):
            return _run_inferred_with_native_tables(
                bridge,
                transformed,
                inspection,
                style_records,
                cancelled,
                progress,
            )

    title_box_file = _template_file_by_title(style_records, "제목박스")
    section_box_file = _template_file_by_title(style_records, "소제목박스")
    if any(item.get("tag") == "문서제목" for item in transformed):
        if not title_box_file:
            return _failure(
                "서식 탭에서 '제목박스' 파일을 찾지 못했습니다.",
                format_mode,
                changed_count,
            )
    if any(item.get("tag") == "제목" for item in transformed):
        if not section_box_file:
            return _failure(
                "서식 탭에서 '소제목박스' 파일을 찾지 못했습니다.",
                format_mode,
                changed_count,
            )

    if cancelled():
        return _cancelled_result(format_mode, changed_count)

    _notify(progress, "선택 영역을 새 서식으로 교체하는 중...")
    ok, message = bridge.delete_selection()
    if not ok:
        return _failure(message, format_mode, changed_count)

    total = len(transformed)
    for index, item in enumerate(transformed):
        if cancelled():
            return _cancelled_result(format_mode, changed_count)

        _notify(progress, f"서식 자동 지정 중... ({index + 1}/{total})")
        if index > 0:
            ok, message = bridge.ensure_cursor_outside_table()
            if not ok:
                return _failure(message, format_mode, changed_count)

        line_text = item["text"]
        tag = item.get("tag")
        if tag == "표":
            ok, message = bridge.insert_pipe_table(
                item.get("rows") or [],
                font_name="굴림체",
                font_size_pt=12,
            )
            if ok:
                ok, message = _settle_cursor_after_inserted_table(bridge)
        elif item["style"] is None:
            ok, message = bridge.insert_text(line_text)
        elif tag == "문서제목":
            ok, message = bridge.insert_document_title_box(
                title_box_file,
                line_text.strip(),
            )
        elif tag == "제목":
            number_text = item.get("number_text")
            body_text = item.get("body_text")
            if number_text is None or body_text is None:
                number_text, body_text = split_section_title_text(line_text.strip())
            ok, message = bridge.insert_section_title_box(
                section_box_file,
                number_text,
                body_text,
            )
        else:
            style = item["style"]
            ok, message = bridge.insert_report_line(
                line_text,
                font_name=style["font"],
                font_size_pt=int(style["size"]),
                bold=bool(style.get("bold", False)),
            )
            if ok and style.get("caret_indent_at") is not None:
                ok, message = bridge.apply_indent_at_caret_for_current_para(
                    int(style.get("caret_indent_at") or 0)
                )

        if not ok:
            return _failure(message, format_mode, changed_count)
        if cancelled():
            return _cancelled_result(format_mode, changed_count)
        if index < total - 1 and tag not in ("문서제목", "제목", "표"):
            ok, message = bridge.insert_text("\r\n")
            if not ok:
                return _failure(message, format_mode, changed_count)

    return True, f"서식 자동 지정 완료 ({changed_count}개 문단)", {
        "cancelled": False,
        "mode": format_mode,
        "changed_count": changed_count,
        "native_table_count": 0,
    }