# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import contextlib
import json
import mimetypes
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any


for stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, OSError):
        pass


BACKEND_ROOT = os.path.abspath(os.path.dirname(__file__))
PROTOTYPE_ROOT = os.path.abspath(os.path.join(BACKEND_ROOT, os.pardir))
if getattr(sys, "frozen", False):
    REPOSITORY_ROOT = os.path.abspath(
        getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    )
else:
    REPOSITORY_ROOT = os.path.abspath(os.path.join(PROTOTYPE_ROOT, os.pardir))
for import_root in (REPOSITORY_ROOT, BACKEND_ROOT):
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge  # noqa: E402
from src.jb_quickpanel.core.runtime import (  # noqa: E402
    pythoncom,
    inspect_hwp_windows,
    set_clipboard_text,
    ui_get_last_hwp_window,
    ui_get_process_path,
    ui_remember_foreground_hwp,
    win32api,
    win32con,
    win32gui,
    win32process,
)
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge  # noqa: E402
from src.jb_quickpanel.features.cell_images import sort_image_paths  # noqa: E402
from src.jb_quickpanel.features.character_effects import compose_parameters, script_parameters  # noqa: E402
from src.jb_quickpanel.features.cell_text import (  # noqa: E402
    cell_replace_text_plain,
)
from src.jb_quickpanel.services.app_config import (  # noqa: E402
    log_command_failure,
    settings_path,
)
from src.jb_quickpanel.services.user_content import UserContentStore  # noqa: E402

from auto_format_runner import (  # noqa: E402
    apply_auto_format_role,
    clear_cancel_request,
    cancel_requested,
    copy_report_prompt_to_clipboard,
    run_auto_format,
)
from tauri_hwp_bridge import TauriHwpBridge  # noqa: E402
from full_features import FullFeatureService  # noqa: E402


FEATURES = FullFeatureService(REPOSITORY_ROOT)
ALLOWED_TABLE_ACTIONS = {
    item["action_id"] for item in FEATURES.table_catalog() if item.get("action_id")
}
_TARGET_MODE = "hwp"
_WXS_BRIDGE = WxsHwpBridge()


def _set_target_mode(mode: str) -> str:
    global _TARGET_MODE
    _TARGET_MODE = "kedufine" if str(mode) == "kedufine" else "hwp"
    return _TARGET_MODE


def _active_bridge(hwp_bridge):
    return _WXS_BRIDGE if _TARGET_MODE == "kedufine" else hwp_bridge


def _checked_repository_file(relative_path: str) -> Path:
    root = Path(REPOSITORY_ROOT).resolve()
    candidate = (root / str(relative_path or "")).resolve()
    if root != candidate.parent and root not in candidate.parents:
        raise RuntimeError("서식 파일 경로가 저장소 밖을 가리킵니다.")
    return candidate


def _preview_data_url(path_value: str | os.PathLike[str]) -> str:
    path = Path(path_value)
    if not path.is_file():
        return ""
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    if not mime_type.startswith("image/"):
        return ""
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    except Exception:
        return ""


def _style_records() -> list[dict[str, Any]]:
    config_path = Path(REPOSITORY_ROOT) / "config" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise RuntimeError(f"기본 서식 설정을 읽지 못했습니다: {error}") from error

    records = []
    for item in config.get("blocks", []):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not item_id or not title:
            continue
        file_path = _checked_repository_file(str(item.get("file") or ""))
        thumb_path = _checked_repository_file(str(item.get("thumb") or ""))
        records.append({
            "key": f"builtin:{item_id}",
            "id": item_id,
            "title": title,
            "source": "builtin",
            "user_item": False,
            "file_path": str(file_path),
            "kedufine_file_path": str(_checked_repository_file(str(item.get("kedufine_file") or ""))),
            "manual_file_path": str(_checked_repository_file(str(item.get("kedufine_file") or ""))),
            "thumb_path": str(thumb_path),
        })

    store = UserContentStore()
    for item in store.list_items("style"):
        item_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not item_id or not title:
            continue
        source_path = str(item.get("file") or "")
        kedufine_path = str(item.get("kedufine_file") or "")
        if Path(kedufine_path).suffix.lower() != ".hwp":
            kedufine_path = source_path if Path(source_path).suffix.lower() == ".hwp" else ""
        records.append({
            "key": f"user:{item_id}",
            "id": item_id,
            "title": title,
            "source": "user",
            "user_item": True,
            "file_path": source_path,
            "kedufine_file_path": kedufine_path,
            "manual_file_path": kedufine_path,
            "thumb_path": str(item.get("thumb") or ""),
        })
    return records


def _auto_title_template_records() -> list[dict[str, Any]]:
    records = []
    builtin_roles = {
        "document_title": ("b01", "기본 문서제목"),
        "title": ("b04", "기본 1단계 제목"),
    }
    styles_by_id = {str(item.get("id") or ""): item for item in _style_records()}
    for role, (style_id, title) in builtin_roles.items():
        source = styles_by_id.get(style_id)
        if source:
            records.append({
                "key": f"auto-title-builtin:{role}",
                "id": f"builtin-{role}",
                "role": role,
                "title": title,
                "source": "builtin",
                "user_item": False,
                "mode": "legacy",
                "file_path": source["file_path"],
                "thumb_path": source.get("thumb_path") or "",
                "title_token": "",
                "number_token": "",
            })
        records.append({
            "key": f"auto-title-none:{role}",
            "id": f"none-{role}",
            "role": role,
            "title": "표 서식 없음",
            "source": "builtin",
            "user_item": False,
            "mode": "plain",
            "file_path": "",
            "thumb_path": "",
            "title_token": "",
            "number_token": "",
        })

    for item in UserContentStore().list_auto_title_templates():
        item_id = str(item.get("id") or "").strip()
        role = str(item.get("role") or "").strip()
        title = str(item.get("title") or "").strip()
        if not item_id or role not in {"document_title", "title"} or not title:
            continue
        records.append({
            "key": f"auto-title-user:{item_id}",
            "id": item_id,
            "role": role,
            "title": title,
            "source": "user",
            "user_item": True,
            "mode": "placeholder",
            "file_path": str(item.get("file") or ""),
            "thumb_path": str(item.get("thumb") or ""),
            "title_token": str(item.get("title_token") or ""),
            "number_token": str(item.get("number_token") or ""),
        })
    return records


def _public_auto_title_item(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": record["key"],
        "id": record["id"],
        "role": record["role"],
        "title": record["title"],
        "source": record["source"],
        "user_item": bool(record["user_item"]),
        "preview": _preview_data_url(record.get("thumb_path") or ""),
    }


def _public_style_item(record: dict[str, Any]) -> dict[str, Any]:
    manual = Path(str(record.get("manual_file_path") or ""))
    return {
        "key": record["key"],
        "id": record["id"],
        "title": record["title"],
        "source": record["source"],
        "user_item": bool(record["user_item"]),
        "preview": _preview_data_url(record.get("thumb_path") or ""),
        "available": manual.suffix.lower() == ".hwp" and manual.is_file(),
    }


def _find_style_record(style_key: str) -> dict[str, Any]:
    key = str(style_key or "").strip()
    for record in _style_records():
        if record["key"] == key:
            return record
    raise RuntimeError("선택한 서식을 찾지 못했습니다. 목록을 새로 불러오세요.")

class CellSelectionTracker:
    def __init__(self, bridge: HwpBridge):
        self.bridge = bridge
        self.mouse_down_prev = False
        self.drag_start = None
        self.drag_last = None
        self.recorded_start = None
        self.recorded_end = None
        self.recorded_text_selection = False
        self.drag_context = None
        self.recorded_context = None
        self.processing = False

    def _selection_context(self):
        window = ui_get_last_hwp_window() or {}
        hwnd = int(window.get("hwnd") or 0)
        pid = int(window.get("pid") or 0)
        title = str(window.get("title") or "").lstrip("* ")
        anchor = None
        anchor_reader = getattr(self.bridge, "_current_table_anchor", None)
        if callable(anchor_reader):
            anchor = anchor_reader()
        return (hwnd, pid, title, id(self.bridge.hwp) if not hwnd else 0, anchor)

    def _is_hwp_window_handle(self, hwnd) -> bool:
        if win32gui is None or win32process is None or not hwnd:
            return False
        try:
            title = win32gui.GetWindowText(hwnd) or ""
            cls = win32gui.GetClassName(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = (ui_get_process_path(pid) or "").lower().replace("/", "\\")
            if exe.endswith("\\hwp.exe") or exe.endswith("hwp.exe"):
                return True
            if "hwp" in cls.lower():
                return True
            title_l = title.lower()
            if "- 한글" in title or ".hwp" in title_l or ".hwpx" in title_l:
                return True
            last = ui_get_last_hwp_window()
            return bool(last and int(last.get("pid") or -1) == int(pid))
        except Exception:
            return False

    def _pointer_is_over_hwp_window(self) -> bool:
        if win32gui is None:
            return False
        try:
            return self._is_hwp_window_handle(win32gui.WindowFromPoint(win32gui.GetCursorPos()))
        except Exception:
            return False

    def poll(self) -> None:
        if self.processing or win32api is None or win32con is None:
            return
        ui_remember_foreground_hwp()
        left_down = bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)

        if left_down:
            if self.drag_start is not None or self._pointer_is_over_hwp_window():
                try:
                    address = self.bridge.get_table_cell_addr(focus_before=False)
                    if not self.mouse_down_prev:
                        self.drag_start = address
                        self.drag_last = address
                        self.drag_context = self._selection_context()
                    else:
                        if self.drag_start is None:
                            self.drag_start = address
                            self.drag_context = self._selection_context()
                        self.drag_last = address
                except Exception:
                    pass
            self.mouse_down_prev = self.drag_start is not None
        elif self.mouse_down_prev:
            if self.drag_start and self.drag_last:
                if self.drag_context == self._selection_context():
                    self.recorded_start = self.drag_start
                    self.recorded_end = self.drag_last
                    self.recorded_text_selection = self.bridge.has_active_text_selection()
                    self.recorded_context = self.drag_context
                else:
                    self.clear()
            self.drag_start = None
            self.drag_last = None
            self.drag_context = None
            self.mouse_down_prev = False
        else:
            self.mouse_down_prev = False
            self.drag_start = None
            self.drag_last = None
            self.drag_context = None

    def clear(self) -> None:
        self.recorded_start = None
        self.recorded_end = None
        self.recorded_text_selection = False
        self.recorded_context = None

    def has_recorded_text_selection(self):
        return bool(self.recorded_text_selection)

    def range_values(self):
        if not self.recorded_start or not self.recorded_end:
            return None
        if self.recorded_context != self._selection_context():
            self.clear()
            return None
        start_col, start_row, _ = self.recorded_start
        end_col, end_row, _ = self.recorded_end
        return int(start_col), int(start_row), int(end_col), int(end_row)

    def state(self) -> dict[str, Any]:
        if self.drag_start and self.drag_last:
            return {
                "active": False,
                "dragging": True,
                "label": f"{self.drag_start[2]} → {self.drag_last[2]}",
            }
        values = self.range_values()
        if values is None:
            return {"active": False, "dragging": False, "label": "선택된 셀 범위 없음"}
        start_col, start_row, end_col, end_row = values
        left_col, right_col = sorted((start_col, end_col))
        top_row, bottom_row = sorted((start_row, end_row))
        start = self.bridge.cell_addr_to_text(left_col, top_row)
        end = self.bridge.cell_addr_to_text(right_col, bottom_row)
        return {
            "active": True,
            "dragging": False,
            "label": f"선택됨: {start} ~ {end}",
            "start": start,
            "end": end,
            "rows": bottom_row - top_row + 1,
            "columns": right_col - left_col + 1,
        }


def result_tuple(result, *, data: dict[str, Any] | None = None):
    if not isinstance(result, tuple) or len(result) < 2:
        return False, "올바르지 않은 작업 결과입니다.", data or {}
    return bool(result[0]), str(result[1]), data or {}


def check_connection(bridge):
    ok, message = bridge.ensure()
    if not ok:
        return False, message
    if bridge is _WXS_BRIDGE:
        return True, "K-에듀파인 기안창에 연결했습니다."
    try:
        bridge.hwp.KeyIndicator()
        return True, "한글 프로그램에 연결했습니다."
    except Exception:
        bridge.reset()
        ok, message = bridge.connect_without_focus()
        return bool(ok), "한글 프로그램에 연결했습니다." if ok else message


def require_selection(tracker: CellSelectionTracker):
    values = tracker.range_values()
    if values is None:
        raise RuntimeError("한글 표에서 적용할 셀 범위를 먼저 드래그하세요.")
    return values


def dispatch(command: str, args: dict[str, Any], bridge: HwpBridge, tracker: CellSelectionTracker):
    work_bridge = _active_bridge(bridge)
    if command == "ping":
        return True, "Python COM 서버가 응답했습니다.", {
            "backend": "persistent-python",
            "target_mode": _TARGET_MODE,
        }
    if command == "settings_get":
        had_user_data = settings_path().exists()
        settings = FEATURES.load_settings()
        tracker.clear()
        _set_target_mode(str(settings.get("start_mode") or "hwp"))
        settings["target_mode"] = _TARGET_MODE
        return True, "설정을 불러왔습니다.", {
            "settings": settings,
            "integration": FEATURES.integration_status(),
            "had_user_data": had_user_data,
        }
    if command == "card_favorite_toggle":
        favorites = FEATURES.toggle_card_favorite(str(args.get("kind") or ""), args.get("key"))
        return True, "즐겨찾기를 저장했습니다.", {"card_favorites": favorites}
    if command == "settings_save":
        settings = FEATURES.save_settings(dict(args.get("changes") or {}))
        settings["target_mode"] = _TARGET_MODE
        return True, "설정을 저장했습니다.", {
            "settings": settings,
            "integration": FEATURES.integration_status(),
        }
    if command == "settings_reset":
        settings = FEATURES.reset_settings()
        _set_target_mode(str(settings.get("target_mode") or "hwp"))
        tracker.clear()
        return True, "설정을 기본값으로 되돌렸습니다.", {
            "settings": settings,
            "integration": FEATURES.integration_status(),
        }
    if command == "update_check":
        result = FEATURES.update_status()
        if not result.get("configured"):
            return True, str(result.get("message") or "업데이트 정보가 설정되지 않았습니다."), {
                "update": result,
            }
        if not result.get("ok"):
            return False, "업데이트 정보를 확인하지 못했습니다.", {"update": result}
        if result.get("is_newer"):
            message = f"새 버전 {result.get('version', '')}을 사용할 수 있습니다."
        else:
            message = f"최신 버전을 사용 중입니다. ({result.get('current', '')})"
        return True, message, {"update": result}
    if command == "set_target_mode":
        tracker.clear()
        mode = _set_target_mode(str(args.get("mode") or "hwp"))
        active = _active_bridge(bridge)
        active.reset()
        ok, message = check_connection(active)
        return ok, message, {
            "connected": ok,
            "target_mode": mode,
            "selection": tracker.state(),
        }
    if command == "window_layout_target":
        if _TARGET_MODE != "hwp":
            return False, "창 분할 배치는 일반 한글에서만 사용할 수 있습니다.", {}
        ok, message = bridge.ensure()
        if not ok:
            return False, message, {}
        windows = inspect_hwp_windows(bridge.hwp)
        handles = list(windows.get("visible_handles") or [])
        target = ui_get_last_hwp_window() or {}
        hwnd = int(target.get("hwnd") or 0)
        if hwnd and hwnd not in handles:
            return False, "한글 연결 대상이 다릅니다. 대상 한글 창을 클릭하고 다시 연결하세요.", {}
        if not hwnd:
            hwnd = int(handles[0]) if len(handles) == 1 else 0
        if not hwnd or win32gui is None or win32process is None or not win32gui.IsWindowVisible(hwnd):
            return False, "배치할 한글 창을 먼저 클릭한 뒤 다시 시도하세요.", {}
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return True, "배치할 한글 창을 확인했습니다.", {"hwnd": hwnd, "pid": int(pid)}
    if command == "status":
        ok, message = check_connection(work_bridge)
        return ok, message, {
            "connected": ok,
            "target_mode": _TARGET_MODE,
            "selection": tracker.state(),
        }
    if command == "connect":
        tracker.clear()
        work_bridge.reset()
        ok, message = check_connection(work_bridge)
        return ok, message, {
            "connected": ok,
            "target_mode": _TARGET_MODE,
            "selection": tracker.state(),
        }
    if command == "style_catalog":
        records = _style_records()
        items = [_public_style_item(record) for record in records]
        return True, f"서식 {len(items)}개를 불러왔습니다.", {"items": items}
    if command == "auto_title_template_catalog":
        items = [_public_auto_title_item(record) for record in _auto_title_template_records()]
        return True, f"자동 서식 제목 {len(items)}개를 불러왔습니다.", {"items": items}
    if command == "form_catalog":
        items = FEATURES.catalog("form")
        return True, f"양식 {len(items)}개를 불러왔습니다.", {"items": items}
    if command == "kedufine_form_catalog":
        items = [
            {key: record[key] for key in ("key", "id", "title", "category", "preview", "body", "user_item", "legacy")}
            for record in FEATURES.kedufine_form_catalog()
        ]
        return True, f"기안문 양식 {len(items)}개를 불러왔습니다.", {"items": items}
    if command == "page_catalog":
        items = FEATURES.catalog("page")
        return True, f"편집용지 {len(items)}개를 불러왔습니다.", {"items": items}
    if command == "table_catalog":
        items = FEATURES.table_catalog()
        return True, f"표 작업 {len(items)}개를 불러왔습니다.", {"items": items}
    if command == "font_catalog":
        fonts = FEATURES.font_catalog()
        return True, f"설치 글꼴 {len(fonts)}개를 불러왔습니다.", {"fonts": fonts}
    if command == "character_catalog":
        groups = FEATURES.character_catalog()
        return True, f"문자표 {len(groups)}개를 불러왔습니다.", {"groups": groups}
    if command == "picture_symbol_catalog":
        groups = FEATURES.picture_symbol_catalog()
        return True, f"심볼 {len(groups)}개 그룹을 불러왔습니다.", {"groups": groups}
    if command == "insert_style":
        record = _find_style_record(str(args.get("style_key") or ""))
        source = record["manual_file_path"]
        if Path(source).suffix.lower() != ".hwp":
            return False, "서식 탭에서는 HWP 서식만 사용할 수 있습니다.", {}
        file_path = Path(source)
        if not file_path.is_file():
            return False, f"서식 파일을 찾지 못했습니다: {record['title']}", {}
        if _TARGET_MODE == "hwp":
            ok, message = bridge.insert_manual_style(str(file_path))
        else:
            ok, message = work_bridge.insert_file(str(file_path))
        if ok:
            message = f"서식 삽입 완료: {record['title']}"
        return ok, message, {"style_key": record["key"], "selection": tracker.state()}
    if command == "insert_form":
        if _TARGET_MODE == "kedufine":
            return False, "양식 삽입은 일반 한글에서만 사용할 수 있습니다.", {}
        record = FEATURES.find_content("form", str(args.get("item_key") or ""))
        file_path = Path(record["file_path"])
        record["file_path"] = str(file_path)
        if not file_path.is_file():
            return False, f"양식 파일을 찾지 못했습니다: {record['title']}", {}
        mode = str(args.get("mode") or "insert").strip().lower()
        if mode == "new_document":
            working_path = FEATURES.open_form_working_copy(record)
            return True, f"새 문서로 열기 완료: {record['title']}", {"working_path": working_path}
        if mode != "insert":
            return False, "지원하지 않는 양식 사용 방식입니다.", {}
        ok, message = bridge.insert_file(
            str(file_path),
            preserve_document=True,
            preserve_section=False,
        )
        return ok, f"양식 삽입 완료: {record['title']}" if ok else message, {}
    if command == "insert_kedufine_form":
        if _TARGET_MODE != "kedufine":
            return False, "K-에듀파인 기안창 모드에서만 사용할 수 있습니다.", {}
        record = next(
            (item for item in FEATURES.kedufine_form_catalog()
             if item["key"] == str(args.get("item_key") or "")),
            None,
        )
        if record is None:
            return False, "기안문 양식을 찾지 못했습니다.", {}
        if record["legacy"]:
            return False, "이전 파일 양식은 본문 텍스트로 수정한 뒤 사용할 수 있습니다.", {}
        ok, message = work_bridge.insert_text(record["body"].replace("\n", "\r\n"))
        return ok, f"본문 삽입 완료: {record['title']}" if ok else message, {}
    if command == "compose_characters":
        value, shape = args.get("value"), args.get("shape")
        try:
            compose_parameters(value, shape)
        except ValueError as error:
            return False, str(error), {}
        ok, message = work_bridge.compose_characters(value, shape)
        target = ui_get_last_hwp_window() if ok and _TARGET_MODE == "hwp" else None
        return ok, message, {"hwp_hwnd": int(target.get("hwnd") or 0) if target else 0}
    if command == "insert_character":
        value = str(args.get("value") or "")
        if not value or len(value) > 12:
            return False, "삽입할 문자 또는 기호를 확인하세요.", {}
        ok, message = work_bridge.insert_text(value)
        target = ui_get_last_hwp_window() if _TARGET_MODE == "hwp" else None
        return ok, f"문자 삽입 완료: {value}" if ok else message, {
            "hwp_hwnd": int(target.get("hwnd") or 0) if target else 0,
        }
    if command == "insert_picture_symbol":
        if _TARGET_MODE == "kedufine":
            return False, "심볼 삽입은 일반 한글에서만 사용할 수 있습니다.", {}
        path = FEATURES.find_picture_symbol(str(args.get("item_key") or ""))
        ok, message = bridge.insert_picture_clipboard(str(path))
        return ok, f"심볼 삽입 완료: {path.stem}" if ok else message, {}
    if command == "apply_page":
        if _TARGET_MODE == "kedufine":
            return False, "편집용지는 일반 한글에서만 사용할 수 있습니다.", {}
        record = FEATURES.find_content("page", str(args.get("item_key") or ""))
        scope = str(args.get("scope") or "document")
        options = {"paper_size": record["paper_size"]} if record.get("paper_size") else {}
        ok, message = bridge.apply_page_preset(
            record.get("margins") or {}, record.get("orientation", "portrait"), scope, **options,
        )
        return ok, f"{message}: {record['title']}" if ok else message, {}
    if command == "copy_report_prompt":
        ok, message, data = copy_report_prompt_to_clipboard(set_clipboard_text)
        return ok, message, data
    if command == "auto_format_report":
        if _TARGET_MODE == "kedufine":
            return False, "서식 자동 지정은 일반 한글에서만 사용할 수 있습니다.", {}
        tracker.processing = True
        clear_cancel_request()
        try:
            settings = FEATURES.load_settings()
            ok, message, data = run_auto_format(
                bridge,
                _auto_title_template_records(),
                format_settings=settings.get("auto_format"),
            )
            data["selection"] = tracker.state()
            return ok, message, data
        finally:
            clear_cancel_request()
            tracker.processing = False
    if command == "auto_format_apply_role":
        if _TARGET_MODE == "kedufine":
            return False, "선택 영역 서식 적용은 일반 한글에서만 사용할 수 있습니다.", {}
        settings = FEATURES.load_settings()
        return apply_auto_format_role(
            bridge,
            _auto_title_template_records(),
            str(args.get("role") or ""),
            format_settings=settings.get("auto_format"),
        )
    if command == "selection_state":
        return True, "셀 범위 감시 중", {"selection": tracker.state()}
    if command == "clear_selection":
        tracker.clear()
        return True, "기록된 셀 범위를 해제했습니다.", {"selection": tracker.state()}
    if command == "apply_charshape":
        script_mode = args.get("script_mode")
        if script_mode is not None:
            try:
                script_parameters(script_mode)
            except ValueError as error:
                return False, str(error), {}
        script_args = {"script_mode": script_mode} if script_mode is not None else {}
        font_name = str(args.get("font_name") or "").strip() or None
        font_size = args.get("font_size_pt")
        font_size = int(font_size) if font_size is not None else None
        color = args.get("font_color_rgb")
        color_rgb = None
        if isinstance(color, (list, tuple)) and len(color) == 3:
            color_rgb = tuple(max(0, min(255, int(value))) for value in color)
        values = tracker.range_values() if _TARGET_MODE == "hwp" else None
        has_text_selection = False
        if values is not None:
            try:
                has_text_selection = tracker.has_recorded_text_selection()
            except Exception:
                has_text_selection = False
            if not has_text_selection:
                has_text_selection = bridge.has_active_text_selection()

        use_recorded_cells = False
        if values is not None and not has_text_selection:
            try:
                bridge.get_table_cell_addr(focus_before=False)
                use_recorded_cells = True
            except Exception:
                use_recorded_cells = False
        if use_recorded_cells:
            tracker.processing = True
            try:
                ok, message = bridge.apply_charshape_to_cell_range(
                    *values,
                    font_name=font_name,
                    font_size_pt=font_size,
                    font_color_rgb=color_rgb,
                    **script_args,
                )
            finally:
                tracker.processing = False
        else:
            ok, message = work_bridge.apply_charshape(
                font_name=font_name,
                font_size_pt=font_size,
                font_color_rgb=color_rgb,
                **script_args,
            )
        return ok, message, {"selection": tracker.state()}
    if command == "spacing_cleanup":
        if _TARGET_MODE == "kedufine":
            return False, "자간 정리는 일반 한글에서만 사용할 수 있습니다.", {}
        adjust_count = max(1, min(10, int(args.get("adjust_count") or 3)))
        values = tracker.range_values()
        has_text_selection = values is not None and (
            tracker.has_recorded_text_selection() or bridge.has_active_text_selection()
        )
        use_recorded_cells = False
        if values is not None and not has_text_selection:
            try:
                bridge.get_table_cell_addr(focus_before=False)
                use_recorded_cells = True
            except Exception:
                use_recorded_cells = False
        clear_cancel_request()
        tracker.processing = True
        try:
            if use_recorded_cells:
                result = bridge.cleanup_cell_range_line_spacing(*values, adjust_count=adjust_count, cancelled=cancel_requested)
            else:
                result = bridge.cleanup_line_spacing(adjust_count, cancelled=cancel_requested)
        finally:
            tracker.processing = False
            clear_cancel_request()
        return result_tuple(result, data={"selection": tracker.state()})
    if command == "spacing_reset":
        if _TARGET_MODE == "kedufine":
            return False, "자간 초기화는 일반 한글에서만 사용할 수 있습니다.", {}
        return result_tuple(bridge.reset_selected_char_spacing(), data={"selection": tracker.state()})
    if command == "object_treat_as_char":
        enabled = args.get("enabled")
        if not isinstance(enabled, bool):
            return False, "글자처럼 취급 설정값을 확인하세요.", {}
        return result_tuple(work_bridge.set_object_treat_as_char(enabled))
    if command == "table_draw":
        ok, message = work_bridge.start_table_drawing()
        target = ui_get_last_hwp_window() if ok and _TARGET_MODE == "hwp" else None
        return ok, message, {"hwp_hwnd": int(target.get("hwnd") or 0) if target else 0}
    if command == "table_tool":
        action_id = str(args.get("action_id") or "")
        if action_id not in ALLOWED_TABLE_ACTIONS:
            return False, "지원하지 않는 표 작업입니다.", {"selection": tracker.state()}
        return result_tuple(work_bridge.apply_table_tool(action_id), data={"selection": tracker.state()})
    if command == "cell_clean_spaces":
        values = require_selection(tracker)
        tracker.processing = True
        try:
            result = bridge.process_recorded_cell_range(
                start_col=values[0], start_row=values[1], end_col=values[2], end_row=values[3],
                cell_operation=bridge.cell_trim_current,
            )
            changed = int(result.get("changed", 0))
            return True, f"앞뒤 공백 정리 완료: {changed}개 셀 변경", {"result": result, "selection": tracker.state()}
        finally:
            tracker.processing = False
    if command == "cell_cleanup_excel":
        values = require_selection(tracker)
        tracker.processing = True
        try:
            result = bridge.cleanup_excel_pasted_cell_range(*values)
            message = (
                "공백·배경색 정리 완료: "
                f"공백 {int(result.get('text_changed', 0))} · "
                f"문단 배경 {int(result.get('background_changed', 0))} · "
                f"글자색/음영 {int(result.get('charshape_changed', 0))}개 셀"
            )
            return True, message, {"result": result, "selection": tracker.state()}
        finally:
            tracker.processing = False
    if command == "cell_text_action":
        if _TARGET_MODE == "kedufine":
            return False, "셀 정리는 일반 한글에서만 사용할 수 있습니다.", {}
        values = require_selection(tracker)
        action = str(args.get("action") or "")
        value = str(args.get("value") or "")
        replacement = str(args.get("replacement") or "")
        if action == "find_replace":
            if value == "":
                return False, "찾을 내용을 입력하세요.", {}
            transform = lambda text: cell_replace_text_plain(text, value, replacement)
            title = "찾아바꾸기"
        elif action == "prefix":
            if value == "":
                return False, "추가할 문자를 입력하세요.", {}
            title = "앞에 문자 추가"
        elif action == "suffix":
            if value == "":
                return False, "추가할 문자를 입력하세요.", {}
            title = "뒤에 문자 추가"
        else:
            return False, "지원하지 않는 셀 문자 작업입니다.", {}
        tracker.processing = True
        try:
            operation = {}
            if action in {"prefix", "suffix"}:
                operation["cell_operation"] = lambda: bridge.cell_affix_current(value, at_end=action == "suffix")
            else:
                operation["transform_func"] = transform
            result = bridge.process_recorded_cell_range(
                start_col=values[0],
                start_row=values[1],
                end_col=values[2],
                end_row=values[3],
                **operation,
            )
            changed = int(result.get("changed", 0))
            return True, f"{title} 완료: {changed}개 셀 변경", {
                "result": result,
                "selection": tracker.state(),
            }
        finally:
            tracker.processing = False
    if command == "pick_files":
        kind = str(args.get("kind") or "")
        paths = FEATURES.pick_files(kind)
        return True, "파일을 선택했습니다." if paths else "파일 선택을 취소했습니다.", {
            "paths": paths,
            "suggested_title": Path(paths[0]).stem if paths else "",
        }
    if command == "insert_cell_images":
        if _TARGET_MODE == "kedufine":
            return False, "셀에 그림 넣기는 일반 한글에서만 사용할 수 있습니다.", {}
        values = require_selection(tracker)
        paths = sort_image_paths(args.get("paths") or [])
        if not paths:
            return False, "넣을 그림 파일을 선택하세요.", {}
        cell_count = (abs(values[2] - values[0]) + 1) * (abs(values[3] - values[1]) + 1)
        if len(paths) > cell_count:
            return False, f"선택한 셀은 {cell_count}개인데 그림은 {len(paths)}개입니다.", {}
        tracker.processing = True
        try:
            result = bridge.insert_pictures_into_cell_range(
                image_paths=paths,
                start_col=values[0],
                start_row=values[1],
                end_col=values[2],
                end_row=values[3],
                size_mode=str(args.get("size_mode") or "fit_inside"),
            )
            inserted = int(result.get("inserted", 0))
            return True, f"셀에 그림 넣기 완료: {inserted}장", {
                "result": result,
                "selection": tracker.state(),
            }
        finally:
            tracker.processing = False
    if command == "refit_cell_images":
        if _TARGET_MODE == "kedufine":
            return False, "기존 그림 다시 맞춤은 일반 한글에서만 사용할 수 있습니다.", {}
        values = require_selection(tracker)
        tracker.processing = True
        try:
            result = bridge.refit_pictures_in_cell_range(
                start_col=values[0],
                start_row=values[1],
                end_col=values[2],
                end_row=values[3],
                size_mode=str(args.get("size_mode") or "fit_inside"),
            )
            message = f"기존 그림 다시 맞춤 완료: {int(result.get('resized', 0))}장"
            skipped = int(result.get("multiple", 0)) + int(result.get("unreadable", 0))
            if skipped:
                message += f" · 건너뜀 {skipped}칸"
            return True, message, {"result": result, "selection": tracker.state()}
        finally:
            tracker.processing = False
    if command == "user_add_file":
        kind = str(args.get("kind") or "")
        source_path = str(args.get("source_path") or "")
        if kind != "form":
            return False, "파일에서 추가는 일반 한글 양식에서만 사용할 수 있습니다.", {}
        item, note = FEATURES.add_user_file(
            kind,
            str(args.get("title") or ""),
            source_path,
        )
        return True, f"내 {kind} 추가 완료: {item.get('title', '')}.{note}", {"item": item}
    if command == "user_save_kedufine_form":
        item = FEATURES.save_kedufine_text_form(
            str(args.get("item_id") or ""),
            str(args.get("title") or ""),
            str(args.get("category") or ""),
            str(args.get("body") or ""),
        )
        return True, f"기안창 양식 저장 완료: {item.get('title', '')}", {"item": item}
    if command == "user_add_block":
        if _TARGET_MODE == "kedufine":
            return False, "블록 지정한 내용의 등록은 일반 한글에서만 사용할 수 있습니다.", {}
        kind = str(args.get("kind") or "")
        item, note = FEATURES.add_user_block(
            kind,
            str(args.get("title") or ""),
            bridge,
        )
        return True, f"블록 지정한 내용 등록 완료: {item.get('title', '')}.{note}", {"item": item}
    if command == "auto_title_template_analyze":
        if _TARGET_MODE == "kedufine":
            return False, "기존 제목 양식 추가는 일반 한글에서만 사용할 수 있습니다.", {}
        analysis = FEATURES.analyze_auto_title_block(
            str(args.get("role") or ""), bridge
        )
        return True, "제목 양식에서 번호와 제목 위치를 확인했습니다.", analysis
    if command == "auto_title_template_register":
        item, note = FEATURES.register_auto_title_block(
            str(args.get("role") or ""),
            str(args.get("title") or ""),
            str(args.get("pending_id") or ""),
            str(args.get("title_sample") or ""),
            str(args.get("number_sample") or ""),
        )
        return True, f"제목 양식 등록 완료: {item.get('title', '')}.{note}", {"item": item}
    if command == "auto_title_template_discard":
        FEATURES.discard_auto_title_block(str(args.get("pending_id") or ""))
        return True, "제목 양식 추가를 취소했습니다.", {}
    if command == "auto_title_template_update":
        item = FEATURES.update_auto_title_template(
            str(args.get("item_id") or ""), str(args.get("title") or "")
        )
        return True, f"제목 양식 이름 수정 완료: {item.get('title', '')}", {"item": item}
    if command == "auto_title_template_delete":
        item = FEATURES.delete_auto_title_template(str(args.get("item_id") or ""))
        return True, f"제목 양식 삭제 완료: {item.get('title', '')}", {"item": item}
    if command == "user_save_page":
        item = FEATURES.save_page(
            str(args.get("item_id") or ""),
            str(args.get("title") or ""),
            dict(args.get("margins") or {}),
            str(args.get("orientation") or "portrait"),
        )
        return True, f"편집용지 저장 완료: {item.get('title', '')}", {"item": item}
    if command == "user_update_title":
        item = FEATURES.update_user_title(
            str(args.get("kind") or ""),
            str(args.get("item_id") or ""),
            str(args.get("title") or ""),
        )
        return True, f"이름 수정 완료: {item.get('title', '')}", {"item": item}
    if command == "user_delete":
        kind = str(args.get("kind") or "")
        item = FEATURES.delete_user_item(kind, str(args.get("item_id") or ""))
        return True, f"사용자 항목 삭제 완료: {item.get('title', '')}", {"item": item}
    if command == "user_save_symbol_group":
        item = FEATURES.save_symbol_group(
            str(args.get("item_id") or ""),
            str(args.get("title") or ""),
            args.get("chars") or [],
        )
        return True, f"내 문자표 저장 완료: {item.get('title', '')}", {
            "item": item,
            "character_group_order": FEATURES.load_settings()["character_group_order"],
        }
    if command == "user_delete_symbol_group":
        item = FEATURES.delete_symbol_group(str(args.get("item_id") or ""))
        return True, f"내 문자표 삭제 완료: {item.get('title', '')}", {"item": item}
    if command == "user_add_picture_symbols":
        items = FEATURES.add_picture_symbols(args.get("paths") or [])
        return True, f"내 심볼 {len(items)}개를 추가했습니다.", {"items": items}
    if command == "user_update_picture_symbol":
        item = FEATURES.update_picture_symbol(
            str(args.get("item_id") or ""), str(args.get("title") or "")
        )
        return True, f"심볼 이름 수정 완료: {item.get('title', '')}", {"item": item}
    if command == "user_delete_picture_symbol":
        item = FEATURES.delete_picture_symbol(str(args.get("item_id") or ""))
        return True, f"내 심볼 삭제 완료: {item.get('title', '')}", {"item": item}
    if command == "user_update_preview":
        item, note = FEATURES.update_preview(
            str(args.get("kind") or ""),
            str(args.get("item_id") or ""),
            str(args.get("mode") or ""),
            str(args.get("source_path") or ""),
        )
        return True, "미리보기를 변경했습니다." + note, {"item": item}
    if command == "user_data_backup":
        result = FEATURES.backup_user_data()
        if result.get("cancelled"):
            return True, "백업을 취소했습니다.", {"backup": result}
        return True, "설정과 내 자료를 백업했습니다.", {"backup": result}
    if command == "user_data_restore":
        result, settings = FEATURES.restore_user_data()
        if result.get("cancelled"):
            return True, "복원을 취소했습니다.", {
                "restore": result,
                "settings": settings,
                "integration": FEATURES.integration_status(),
            }
        _set_target_mode(str(settings.get("target_mode") or settings.get("start_mode") or "hwp"))
        tracker.clear()
        settings["target_mode"] = _TARGET_MODE
        return True, "설정과 내 자료를 복원했습니다.", {
            "restore": result,
            "settings": settings,
            "integration": FEATURES.integration_status(),
        }
    if command == "integration_prepare":
        return True, "Windows 통합 상태를 준비했습니다.", {
            "integration": FEATURES.prepare_integrations(),
        }
    if command == "integration_status":
        return True, "Windows 통합 상태를 확인했습니다.", {
            "integration": FEATURES.integration_status(),
        }
    if command == "integration_set":
        kind = str(args.get("kind") or "")
        enabled = bool(args.get("enabled"))
        if kind == "startup":
            FEATURES.set_startup(enabled, bool(args.get("start_minimized")))
        elif kind == "start_menu":
            FEATURES.set_start_menu(enabled)
        else:
            return False, "지원하지 않는 Windows 통합 항목입니다.", {}
        return True, "Windows 통합 설정을 변경했습니다.", {
            "integration": FEATURES.integration_status(),
        }
    if command == "open_update_url":
        url = FEATURES.open_update_url(str(args.get("url") or ""))
        return True, "업데이트 안내 페이지를 열었습니다.", {"url": url}
    if command == "open_support":
        path = FEATURES.open_support_path(str(args.get("kind") or ""))
        return True, "요청한 항목을 열었습니다.", {"path": path}
    if command == "open_manual":
        url = FEATURES.open_manual(str(args.get("section") or ""))
        return True, "사용자 매뉴얼을 열었습니다.", {"url": url}
    if command == "shutdown":
        return True, "Python COM 서버를 종료합니다.", {"shutdown": True}
    return False, f"알 수 없는 명령입니다: {command}", {}


def reader_loop(requests: queue.Queue):
    for raw_line in sys.stdin.buffer:
        try:
            requests.put(json.loads(raw_line.decode("utf-8")))
        except Exception as error:
            requests.put({"id": 0, "command": "__parse_error__", "error": str(error)})
    requests.put(None)


def write_response(
    request_id: int,
    ok: bool,
    message: str,
    data: dict[str, Any] | None = None,
) -> bool:
    payload = {"id": request_id, "ok": bool(ok), "message": str(message), "data": data or {}}
    try:
        sys.stdout.write(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        sys.stdout.flush()
        return True
    except (BrokenPipeError, OSError, ValueError):
        return False


def record_command_failure(
    command: str,
    message: str,
    tracker: CellSelectionTracker,
    *,
    exception: BaseException | None = None,
) -> None:
    try:
        log_command_failure(
            command,
            message,
            context={"target_mode": _TARGET_MODE, "selection": tracker.state()},
            exception=exception,
        )
    except Exception:
        pass

def main() -> int:
    requests: queue.Queue = queue.Queue()
    reader = threading.Thread(target=reader_loop, args=(requests,), daemon=True)
    reader.start()

    if pythoncom is not None:
        pythoncom.CoInitialize()
    bridge = TauriHwpBridge()
    tracker = CellSelectionTracker(bridge)
    running = True
    try:
        while running:
            try:
                request = requests.get(timeout=0.025)
            except queue.Empty:
                tracker.poll()
                continue
            if request is None:
                break

            request_id = int(request.get("id") or 0)
            command = str(request.get("command") or "")
            args = request.get("args") if isinstance(request.get("args"), dict) else {}
            if command == "__parse_error__":
                if not write_response(request_id, False, f"요청을 읽지 못했습니다: {request.get('error', '')}"):
                    running = False
                continue
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    ok, message, data = dispatch(command, args, bridge, tracker)
                if not ok:
                    record_command_failure(command, message, tracker)
                if command == "shutdown" and ok and bool(args.get("silent")):
                    running = False
                    continue
                if not write_response(request_id, ok, message, data):
                    running = False
                    continue
                if command == "shutdown" and ok:
                    running = False
            except Exception as error:
                record_command_failure(command, str(error), tracker, exception=error)
                if not write_response(request_id, False, str(error), {"selection": tracker.state()}):
                    running = False
    finally:
        bridge.reset()
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
    if getattr(sys, "frozen", False):
        os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
