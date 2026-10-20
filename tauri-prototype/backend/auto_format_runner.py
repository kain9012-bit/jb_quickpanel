# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from src.jb_quickpanel.features.auto_format import (
    read_report_prompt,
    split_section_title_text,
    transform_auto_format_text,
    transform_report_text,
    transform_untagged_as_tagged_text,
)
from src.jb_quickpanel.features.auto_format_settings import normalize_auto_format_settings


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


def _template_record(
    template_records,
    preferred_key: str,
    role: str,
) -> dict[str, Any] | None:
    key = str(preferred_key or "").strip()
    candidates = [
        record for record in template_records
        if str(record.get("role") or "") == role
    ]
    for record in candidates:
        file_path = Path(str(record.get("file_path") or ""))
        available = record.get("mode") == "plain" or file_path.is_file()
        if str(record.get("key") or "") == key and available:
            return record
    builtin_key = f"auto-title-builtin:{role}"
    for record in candidates:
        file_path = Path(str(record.get("file_path") or ""))
        if str(record.get("key") or "") == builtin_key and file_path.is_file():
            return record
    return None


def _insert_document_title(bridge, template, text: str, style, *, append_paragraph_break: bool = True):
    file_path = str(template.get("file_path") or "")
    if template.get("mode") == "plain":
        ok, message = bridge.insert_report_line(
            text.strip(),
            font_name=str(style["font"]),
            font_size_pt=int(style["size"]),
            bold=bool(style.get("bold", False)),
        )
        if not ok or not append_paragraph_break:
            return ok, message
        return bridge.insert_text("\r\n")
    if template.get("mode") == "placeholder":
        return bridge.insert_auto_title_template(
            file_path,
            {
                str(template.get("title_token") or ""): text.strip(),
            },
            font_name=str(style["font"]),
            font_size_pt=int(style["size"]),
            bold=bool(style.get("bold", False)),
            **({"append_paragraph_break": False} if not append_paragraph_break else {}),
        )
    return bridge.insert_document_title_box(
        file_path,
        text.strip(),
        font_name=str(style["font"]),
        font_size_pt=int(style["size"]),
        bold=bool(style.get("bold", False)),
        **({"append_paragraph_break": False} if not append_paragraph_break else {}),
    )


def _insert_section_title(
    bridge,
    template,
    number_text: str,
    title_text: str,
    style,
    line_text: str | None = None,
    *,
    append_paragraph_break: bool = True,
):
    file_path = str(template.get("file_path") or "")
    if template.get("mode") == "plain":
        plain_text = str(line_text or "").strip() or " ".join(
            part for part in (number_text.strip(), title_text.strip()) if part
        )
        ok, message = bridge.insert_report_line(
            plain_text,
            font_name=str(style["font"]),
            font_size_pt=int(style["size"]),
            bold=bool(style.get("bold", False)),
        )
        if not ok or not append_paragraph_break:
            return ok, message
        return bridge.insert_text("\r\n")
    if template.get("mode") == "placeholder":
        return bridge.insert_auto_title_template(
            file_path,
            {
                str(template.get("number_token") or ""): number_text,
                str(template.get("title_token") or ""): title_text,
            },
            font_name=str(style["font"]),
            font_size_pt=int(style["size"]),
            bold=bool(style.get("bold", False)),
            **({"append_paragraph_break": False} if not append_paragraph_break else {}),
        )
    return bridge.insert_section_title_box(
        file_path,
        number_text,
        title_text,
        font_name=str(style["font"]),
        font_size_pt=int(style["size"]),
        bold=bool(style.get("bold", False)),
        **({"append_paragraph_break": False} if not append_paragraph_break else {}),
    )

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


def _finish_with_checkpoint(bridge, checkpoint, result, *, restore=False, discard_unmodified=False):
    ok, message, data = result
    path = Path(checkpoint["path"])
    if ok:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return result
    restored = False
    if restore:
        try:
            if restore == "original":
                restored, restore_message = bridge.restore_auto_format_checkpoint(
                    checkpoint, original_range=True
                )
            else:
                restored, restore_message = bridge.restore_auto_format_checkpoint(checkpoint)
        except Exception as exc:
            restored, restore_message = False, str(exc)
        if not restored:
            message = f"{message} 선택 영역 자동 복구 실패: {restore_message}"
    try:
        page_restored, page_message = bridge.restore_page_setup(checkpoint)
    except Exception as exc:
        page_restored, page_message = False, str(exc)
    if not page_restored:
        message = f"{message} 편집용지 자동 복구 실패: {page_message}"
    if page_restored and (restored or discard_unmodified):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        suffix = "원본 선택 영역과 편집용지를 복구했습니다." if restored else "편집용지를 복구했습니다."
        return False, f"{message} {suffix}", data
    if not restore and not discard_unmodified:
        message = f"{message} 문서 일부가 변경되었을 수 있습니다."
    return False, f"{message} 원본 선택 영역 복구 파일: {path}", data


def _with_recovery_stage(result, stage):
    result[2]["recovery_stage"] = stage
    return result


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
    format_settings,
):
    paragraphs = list(inspection.get("paragraphs") or [])
    table_positions = list(inspection.get("native_table_positions") or [])
    paragraph_items = _inferred_paragraph_items(transformed)

    if len(paragraph_items) != len(paragraphs):
        body_text = "\n".join(
            str(paragraph.get("text") or "") for paragraph in paragraphs
        )
        body_transformed, _ = transform_untagged_as_tagged_text(
            body_text,
            has_external_table=bool(table_positions),
            format_settings=format_settings,
        )
        paragraph_items = _inferred_paragraph_items(body_transformed)

    if len(paragraph_items) != len(paragraphs):
        return _failure(
            "표 밖 문단의 위치를 정확히 연결하지 못했습니다. "
            "원본 표를 보호하기 위해 작업을 중단했습니다.",
            "inferred",
        )

    title_template = _template_record(
        style_records, format_settings["document_title_template"], "document_title"
    )
    section_template = _template_record(
        style_records, format_settings["title_template"], "title"
    )
    if any(item.get("tag") == "문서제목" for item in paragraph_items):
        if not title_template:
            return _failure(
                "자동 서식 설정에서 사용할 문서제목 예시를 찾지 못했습니다.",
                "inferred",
            )
    if any(item.get("tag") == "제목" for item in paragraph_items):
        if not section_template:
            return _failure(
                "자동 서식 설정에서 사용할 1단계 제목 예시를 찾지 못했습니다.",
                "inferred",
            )
    if cancelled():
        return _cancelled_result("inferred")

    def table_progress(current, total):
        _notify(progress, f"한글 표 서식 지정 중... ({current}/{total})")

    table_style = format_settings["roles"]["table"]
    ok, message = bridge.format_native_report_tables(
        table_positions,
        font_name=str(table_style["font"]),
        font_size_pt=int(table_style["size"]),
        bold=bool(table_style.get("bold", False)),
        progress=table_progress,
        cancelled=cancelled,
    )
    if not ok:
        if message == "CANCELLED" or cancelled():
            return _with_recovery_stage(_cancelled_result("inferred"), "tables")
        return _with_recovery_stage(_failure(message, "inferred"), "tables")

    def paragraph_progress(current, total):
        _notify(progress, f"표 밖 문단 서식 지정 중... ({current}/{total})")

    ok, message = bridge.apply_inferred_report_paragraphs(
        paragraphs,
        paragraph_items,
        title_template=title_template,
        section_template=section_template,
        progress=paragraph_progress,
        cancelled=cancelled,
    )
    if not ok:
        if message == "CANCELLED" or cancelled():
            return _with_recovery_stage(_cancelled_result("inferred"), "paragraphs")
        return _with_recovery_stage(_failure(message, "inferred"), "paragraphs")

    changed_count = len(paragraph_items) + len(table_positions)
    return True, f"서식 자동 지정 완료 ({changed_count}개 문단·표)", {
        "cancelled": False,
        "mode": "inferred",
        "changed_count": changed_count,
        "native_table_count": len(table_positions),
    }


def _inferred_paragraph_items(transformed):
    return [
        item
        for item in transformed
        if item.get("tag") != "표"
        and (item.get("style") is not None or str(item.get("text") or "").strip())
    ]


def _inspect_auto_format_selection(bridge):
    try:
        ok, inspection = bridge.inspect_selected_report_content()
    except Exception:
        ok, inspection = False, None
    if not ok or not isinstance(inspection, dict) or not inspection.get("controls_complete", False):
        return False, "선택 영역의 표·그림·도형을 정확히 확인하지 못해 작업을 중단했습니다. 원문은 변경하지 않았습니다."
    if inspection.get("native_object_positions"):
        return False, "그림·도형 등의 개체가 함께 선택되어 작업을 중단했습니다. 개체를 제외하고 글만 블록 지정해 주세요. 원문은 변경하지 않았습니다."
    return True, inspection


def _begin_rewrite(bridge, checkpoint, mode, changed_count):
    ok, transaction = bridge.begin_auto_format_rewrite(checkpoint)
    if not ok:
        return None, _finish_with_checkpoint(
            bridge, checkpoint, _failure(transaction, mode, changed_count),
        )
    return transaction, None


def _abort_rewrite(bridge, checkpoint, transaction, result):
    try:
        restored, message = bridge.rollback_auto_format_rewrite(transaction)
    except Exception as exc:
        restored, message = False, str(exc)
    ok, detail, data = result
    note = "새 결과를 제거하고 원문을 유지했습니다." if restored else f"새 결과 정리 실패: {message}. 원문을 임의로 삭제하지 않았습니다."
    return _finish_with_checkpoint(
        bridge, checkpoint, (ok, f"{detail} {note}", data), discard_unmodified=restored,
    )


def _write_auto_format_items(bridge, transformed, options, title_template, section_template,
                             cancelled, progress=None, *, append_title_break=True):
    try:
        total = len(transformed)
        for index, item in enumerate(transformed):
            if cancelled():
                return False, "", True
            _notify(progress, f"서식 자동 지정 중... ({index + 1}/{total})")
            if index > 0:
                ok, message = bridge.ensure_cursor_outside_table()
                if not ok:
                    return False, message, False
            line_text, tag, style = item["text"], item.get("tag"), item.get("style")
            if tag == "표":
                style = style or options["roles"]["table"]
                ok, message = bridge.insert_pipe_table(
                    item.get("rows") or [], font_name=str(style["font"]),
                    font_size_pt=int(style["size"]), bold=bool(style.get("bold", False)),
                )
                if ok:
                    ok, message = _settle_cursor_after_inserted_table(bridge)
            elif style is None:
                ok, message = bridge.insert_text(line_text)
            elif tag == "문서제목":
                ok, message = _insert_document_title(
                    bridge, title_template, line_text, style,
                    **({"append_paragraph_break": False} if not append_title_break else {}),
                )
            elif tag == "제목":
                number, body = item.get("number_text"), item.get("body_text")
                if number is None or body is None:
                    number, body = split_section_title_text(line_text.strip())
                ok, message = _insert_section_title(
                    bridge, section_template, number, body, style, line_text,
                    **({"append_paragraph_break": False} if not append_title_break else {}),
                )
            else:
                ok, message = bridge.insert_report_line(
                    line_text, font_name=style["font"], font_size_pt=int(style["size"]),
                    bold=bool(style.get("bold", False)),
                )
                if ok and style.get("caret_indent_at") is not None:
                    ok, message = bridge.apply_indent_at_caret_for_current_para(int(style["caret_indent_at"]))
            if not ok:
                return False, message, False
            if cancelled():
                return False, "", True
            if index < total - 1 and tag not in {"문서제목", "제목", "표"}:
                ok, message = bridge.insert_text("\r\n")
                if not ok:
                    return False, message, False
        return True, "OK", False
    except Exception as exc:
        return False, f"서식 작성 중 오류: {exc}", False


def run_auto_format(
    bridge,
    style_records: list[dict[str, Any]],
    *,
    cancelled: Callable[[], bool] = cancel_requested,
    progress: Callable[[str], None] | None = None,
    format_settings=None,
):
    options = normalize_auto_format_settings(format_settings)
    if cancelled():
        return _cancelled_result("")

    _notify(progress, "선택 영역 읽는 중...")
    ok, raw_text = bridge.get_selected_text()
    if not ok:
        return _failure(raw_text)

    transformed, changed_count, format_mode = transform_auto_format_text(
        raw_text, options
    )
    if changed_count == 0:
        return True, "선택한 영역에서 서식을 적용할 문단을 찾지 못했습니다.", {
            "cancelled": False,
            "mode": format_mode,
            "changed_count": 0,
        }

    _notify(progress, "선택 영역의 표·그림·도형 확인 중...")
    inspected, inspection = _inspect_auto_format_selection(bridge)
    if not inspected:
        return _failure(inspection, format_mode, changed_count)
    inferred_inspection = None
    if inspection.get("native_table_positions"):
        if format_mode != "inferred":
            return _failure("한글 표가 함께 선택되어 작업을 중단했습니다. 표를 제외하고 글만 블록 지정해 주세요. 원문은 변경하지 않았습니다.", format_mode, changed_count)
        if format_mode == "inferred":
            inferred_inspection = inspection
            paragraph_count = len(inspection.get("paragraphs") or [])
            item_count = len(_inferred_paragraph_items(transformed))
            if paragraph_count != item_count:
                return _failure(
                    "표 밖 문단의 위치를 정확히 연결하지 못했습니다. "
                    "원본 표를 보호하기 위해 작업을 중단했습니다.",
                    "inferred",
                    changed_count,
                )

    title_template = _template_record(
        style_records, options["document_title_template"], "document_title"
    )
    section_template = _template_record(
        style_records, options["title_template"], "title"
    )
    if any(item.get("tag") == "문서제목" for item in transformed):
        if not title_template:
            return _failure(
                "자동 서식 설정에서 사용할 문서제목 예시를 찾지 못했습니다.",
                format_mode,
                changed_count,
            )
    if any(item.get("tag") == "제목" for item in transformed):
        if not section_template:
            return _failure(
                "자동 서식 설정에서 사용할 1단계 제목 예시를 찾지 못했습니다.",
                format_mode,
                changed_count,
            )

    if cancelled():
        return _cancelled_result(format_mode, changed_count)

    ok, checkpoint = bridge.create_auto_format_checkpoint()
    if not ok:
        return _failure(f"원본 선택 영역 백업 실패: {checkpoint}", format_mode, changed_count)

    _notify(progress, "기본 보고서 편집용지 적용 중...")
    ok, message = bridge.apply_basic_report_page_setup()
    if not ok:
        return _finish_with_checkpoint(
            bridge, checkpoint,
            _failure(f"기본 보고서 편집용지 적용 실패: {message}", format_mode, changed_count),
            discard_unmodified=True,
        )

    if inferred_inspection is not None:
        result = _run_inferred_with_native_tables(
            bridge,
            transformed,
            inferred_inspection,
            style_records,
            cancelled,
            progress,
            options,
        )
        stage = result[2].get("recovery_stage")
        return _finish_with_checkpoint(
            bridge, checkpoint, result,
            restore="original" if stage == "tables" else False,
            discard_unmodified=not result[0] and stage is None,
        )

    if cancelled():
        return _finish_with_checkpoint(
            bridge, checkpoint, _cancelled_result(format_mode, changed_count),
            discard_unmodified=True,
        )

    _notify(progress, "선택 영역을 새 서식으로 교체하는 중...")
    transaction, failure = _begin_rewrite(bridge, checkpoint, format_mode, changed_count)
    if failure is not None:
        return failure

    def abort(result):
        return _abort_rewrite(bridge, checkpoint, transaction, result)

    ok, message, stopped = _write_auto_format_items(
        bridge, transformed, options, title_template, section_template, cancelled, progress,
    )
    if not ok:
        return abort(_cancelled_result(format_mode, changed_count) if stopped else _failure(message, format_mode, changed_count))

    if cancelled():
        return abort(_cancelled_result(format_mode, changed_count))
    ok, message = bridge.commit_auto_format_rewrite(transaction)
    if not ok:
        return abort(_failure(message, format_mode, changed_count))
    return _finish_with_checkpoint(bridge, checkpoint, (True, f"서식 자동 지정 완료 ({changed_count}개 문단)", {
        "cancelled": False,
        "mode": format_mode,
        "changed_count": changed_count,
        "native_table_count": 0,
    }), restore=False)

_DIRECT_ROLE_TAGS = {
    "document_title": "문서제목",
    "title": "제목",
    "subtitle": "소제목",
    "subsubtitle": "소소제목",
    "body": "본문",
    "reference": "참고",
}
_DIRECT_ROLE_LABELS = {
    "document_title": "문서제목",
    "title": "1단계 제목",
    "subtitle": "2단계 제목",
    "subsubtitle": "3단계 제목",
    "body": "본문",
    "reference": "참고",
}
_DIRECT_HANGUL_SEQUENCE = "가나다라마바사아자차카타파하"
_DIRECT_ROMAN_UPPER = (
    "Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ", "Ⅷ", "Ⅸ", "Ⅹ",
    "Ⅺ", "Ⅻ", "ⅩⅢ", "ⅩⅣ", "ⅩⅤ", "ⅩⅥ", "ⅩⅦ", "ⅩⅧ", "ⅩⅨ", "ⅩⅩ",
)
_DIRECT_ROMAN_LOWER = tuple(value.lower() for value in _DIRECT_ROMAN_UPPER)
_DIRECT_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _selected_heading_index(text: str) -> int:
    value = str(text or "").strip()
    match = re.match(r"^(\d+)[.)]\s*", value)
    if match:
        return max(1, int(match.group(1)))
    match = re.match(r"^([가-하])[.)]\s*", value)
    if match and match.group(1) in _DIRECT_HANGUL_SEQUENCE:
        return _DIRECT_HANGUL_SEQUENCE.index(match.group(1)) + 1
    if value:
        if value[0] in _DIRECT_CIRCLED:
            return _DIRECT_CIRCLED.index(value[0]) + 1
        for markers in (_DIRECT_ROMAN_UPPER, _DIRECT_ROMAN_LOWER):
            for index in range(len(markers), 0, -1):
                marker = markers[index - 1]
                if re.match(rf"^{re.escape(marker)}(?:[.)]|\s)", value):
                    return index
        ascii_match = re.match(r"^([IVXLCDMivxlcdm]+)[.)]\s*", value)
        if ascii_match:
            values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
            total = 0
            previous = 0
            for letter in reversed(ascii_match.group(1).upper()):
                current = values[letter]
                total += -current if current < previous else current
                previous = max(previous, current)
            return max(1, total)
    return 1


def apply_auto_format_role(
    bridge,
    style_records: list[dict[str, Any]],
    role: str,
    *,
    format_settings=None,
):
    """Replace the selected paragraphs using one saved auto-format role."""
    role_key = str(role or "").strip()
    tag = _DIRECT_ROLE_TAGS.get(role_key)
    if not tag:
        return False, "지원하지 않는 자동 서식 항목입니다.", {
            "reason": "invalid_role",
            "role": role_key,
        }

    ok, raw_text = bridge.get_selected_text()
    if not ok:
        reason = "selection_required" if (
            "블록 지정" in str(raw_text) or "선택한 텍스트" in str(raw_text)
        ) else "read_failed"
        return False, str(raw_text), {"reason": reason, "role": role_key}

    normalized = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.strip("\n")
    nonempty_lines = [line for line in normalized.split("\n") if line.strip()]
    if not nonempty_lines:
        return False, "한글에서 서식을 적용할 텍스트를 먼저 블록 지정하세요.", {
            "reason": "selection_required",
            "role": role_key,
        }
    if role_key in {"document_title", "title"} and len(nonempty_lines) != 1:
        return False, f"{_DIRECT_ROLE_LABELS[role_key]}은 한 문단만 블록 지정해 주세요.", {
            "reason": "single_paragraph_required",
            "role": role_key,
        }

    inspected, inspection = _inspect_auto_format_selection(bridge)
    if not inspected:
        return _failure(inspection)
    if inspection.get("native_table_positions"):
        return _failure("한글 표가 함께 선택되어 작업을 중단했습니다. 표 밖의 글만 블록 지정해 주세요. 원문은 변경하지 않았습니다.")

    selected_lines = normalized.split("\n")
    tagged_lines = [
        f"({tag}) {line.strip()}" if line.strip() else ""
        for line in selected_lines
    ]
    heading_offset = 0
    if role_key in {"title", "subtitle", "subsubtitle"}:
        heading_offset = _selected_heading_index(nonempty_lines[0]) - 1
    tagged_text = "\n".join(
        ([f"({tag}) __sequence_placeholder__"] * heading_offset) + tagged_lines
    )
    options = normalize_auto_format_settings(format_settings)
    transformed, _transformed_count = transform_report_text(tagged_text, options)
    if heading_offset:
        transformed = transformed[heading_offset:]
    changed_count = len(nonempty_lines)
    if changed_count <= 0:
        return False, "선택한 영역에서 서식을 적용할 문단을 찾지 못했습니다.", {
            "reason": "empty_selection",
            "role": role_key,
        }

    title_template = None
    section_template = None
    if role_key == "document_title":
        title_template = _template_record(
            style_records, options["document_title_template"], "document_title"
        )
        if not title_template:
            return _failure("자동 서식 설정에서 사용할 문서제목 양식을 찾지 못했습니다.")
    elif role_key == "title":
        section_template = _template_record(
            style_records, options["title_template"], "title"
        )
        if not section_template:
            return _failure("자동 서식 설정에서 사용할 1단계 제목 양식을 찾지 못했습니다.")

    ok, checkpoint = bridge.create_auto_format_checkpoint()
    if not ok:
        return _failure(f"원본 선택 영역 백업 실패: {checkpoint}")
    transaction, failure = _begin_rewrite(bridge, checkpoint, "role", changed_count)
    if failure is not None:
        return failure
    ok, message, _stopped = _write_auto_format_items(
        bridge, transformed, options, title_template, section_template, lambda: False,
        append_title_break=False,
    )
    if ok:
        ok, message = bridge.commit_auto_format_rewrite(transaction)
    if not ok:
        return _abort_rewrite(bridge, checkpoint, transaction, _failure(message))
    try:
        Path(checkpoint["path"]).unlink(missing_ok=True)
    except OSError:
        pass

    label = _DIRECT_ROLE_LABELS[role_key]
    return True, f"선택 영역에 {label} 서식을 적용했습니다.", {
        "reason": "",
        "role": role_key,
        "changed_count": changed_count,
    }
