# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from src.jb_quickpanel.features import registry as feature_registry
from src.jb_quickpanel.features.document_preview import create_document_preview
from src.jb_quickpanel.features.auto_format_settings import (
    MAX_AUTO_FORMAT_PROFILES,
    normalize_auto_format_profile_state,
)
from src.jb_quickpanel.features.auto_title_templates import (
    AutoTitleTemplateError,
    analyze_example_text,
    normalize_role as normalize_auto_title_role,
    prepare_hwpx_template,
)
from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.services.user_content import (
    DEFAULT_PAGE_MARGINS,
    UserContentError,
    UserContentStore,
)
from src.jb_quickpanel.services.user_backup import (
    BACKUP_EXTENSION,
    create_user_backup,
    restore_user_backup,
)

APP_VERSION = "v.0.0.7"
APP_TITLE = app_config.APP_TITLE

_FALLBACK_FONT_FAMILIES = ("HY헤드라인M", "휴먼명조", "맑은 고딕", "굴림체")


def default_windows_browser() -> str:
    import ctypes
    from ctypes import wintypes

    query = ctypes.windll.shlwapi.AssocQueryStringW
    query.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    query.restype = ctypes.c_long
    output = ctypes.create_unicode_buffer(32768)
    length = wintypes.DWORD(len(output))
    # Resolve the current user's HTTPS browser, not the .html file association.
    result = query(0x1000, 2, "https", "open", output, ctypes.byref(length))
    if result != 0 or not output.value or not Path(output.value).is_file():
        raise RuntimeError("기본 웹브라우저를 확인하지 못했습니다. Windows 기본 앱 설정을 확인해 주세요.")
    return output.value


def installed_font_families() -> list[str]:
    names = set(_FALLBACK_FONT_FAMILIES)
    if os.name != "nt":
        return sorted(names, key=lambda value: value.casefold())
    try:
        import ctypes
        from ctypes import wintypes

        class LogFontW(ctypes.Structure):
            _fields_ = [
                ("lfHeight", wintypes.LONG),
                ("lfWidth", wintypes.LONG),
                ("lfEscapement", wintypes.LONG),
                ("lfOrientation", wintypes.LONG),
                ("lfWeight", wintypes.LONG),
                ("lfItalic", wintypes.BYTE),
                ("lfUnderline", wintypes.BYTE),
                ("lfStrikeOut", wintypes.BYTE),
                ("lfCharSet", wintypes.BYTE),
                ("lfOutPrecision", wintypes.BYTE),
                ("lfClipPrecision", wintypes.BYTE),
                ("lfQuality", wintypes.BYTE),
                ("lfPitchAndFamily", wintypes.BYTE),
                ("lfFaceName", wintypes.WCHAR * 32),
            ]

        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.POINTER(LogFontW),
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.LPARAM,
        )

        @callback_type
        def collect(logfont, _metric, _font_type, _param):
            name = str(logfont.contents.lfFaceName or "").strip()
            if name and not name.startswith("@"):
                names.add(name)
            return 1

        hdc = ctypes.windll.user32.GetDC(None)
        if hdc:
            try:
                query = LogFontW()
                query.lfCharSet = 1
                ctypes.windll.gdi32.EnumFontFamiliesExW(
                    hdc, ctypes.byref(query), collect, 0, 0
                )
            finally:
                ctypes.windll.user32.ReleaseDC(None, hdc)
    except Exception:
        pass
    return sorted(names, key=lambda value: value.casefold())


class FullFeatureService:
    def __init__(self, repository_root: str | os.PathLike[str]):
        self.root = Path(repository_root).resolve()
        self.config_path = self.root / "config" / "config.json"

    def font_catalog(self) -> list[str]:
        return installed_font_families()

    @staticmethod
    def _kedufine_outline(body: str) -> str:
        subheadings = []
        for line in body.splitlines():
            match = re.match(r"^\s*([가-하]\.\s*[^:：\[\]\r\n]+)", line)
            if match:
                subheadings.append(match.group(1).strip())
        if subheadings:
            return "\n".join(subheadings)
        headings = []
        for line in body.splitlines():
            match = re.match(r"^\s*(\d+\.)\s*(.*)", line)
            if match:
                head = match.group(2).split(":", 1)[0].strip()
                headings.append(f"{match.group(1)} {head if ':' in match.group(2) else '본문'}")
        return "\n".join(headings) or "본문"

    def kedufine_form_catalog(self) -> list[dict[str, Any]]:
        source = self.root / "config" / "kedufine_forms.json"
        records = json.loads(source.read_text(encoding="utf-8"))
        items = []
        for record in records:
            item_id = str(record["id"])
            if not re.fullmatch(r"[a-z_]+", item_id):
                raise RuntimeError("K-에듀파인 양식 ID가 올바르지 않습니다.")
            category = str(record.get("category") or "")
            if category not in {"internal", "outgoing"}:
                raise RuntimeError(f"K-에듀파인 양식 분류가 올바르지 않습니다: {item_id}")
            body = "\n".join(str(line) for line in record["body"])
            outline = record.get("outline")
            if not isinstance(outline, list) or not outline or not all(isinstance(line, str) and line.strip() for line in outline):
                raise RuntimeError(f"K-에듀파인 양식 목차가 올바르지 않습니다: {item_id}")
            items.append({
                "key": item_id,
                "id": item_id,
                "title": str(record["title"]),
                "category": category,
                "preview": "\n".join(outline),
                "body": body,
                "user_item": False,
                "legacy": False,
            })
        for record in UserContentStore().list_items("kedufine_form"):
            body = str(record.get("body") or "")
            legacy = not body
            items.append({
                "key": f"user:{record['id']}",
                "id": str(record["id"]),
                "title": str(record["title"]),
                "category": "legacy" if legacy else str(record.get("category") or "outgoing"),
                "preview": self._kedufine_outline(body) if body else "",
                "body": body,
                "user_item": True,
                "legacy": legacy,
            })
        return items

    def config(self) -> dict[str, Any]:
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as error:
            raise RuntimeError(f"기본 설정을 읽지 못했습니다: {error}") from error

    def checked_repository_file(self, relative_path: str) -> Path:
        candidate = (self.root / str(relative_path or "")).resolve()
        if self.root != candidate.parent and self.root not in candidate.parents:
            raise RuntimeError("파일 경로가 저장소 밖을 가리킵니다.")
        return candidate

    def preview_data_url(self, path_value: str | os.PathLike[str]) -> str:
        import base64

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

    def builtin_form_preview(
        self,
        item_id: str,
        source_path: Path,
        fallback_path: Path,
    ) -> Path:
        cache_dir = app_config.app_data_dir() / "builtin_form_previews"
        cache_path = cache_dir / f"{item_id}.png"
        dependencies = [path for path in (source_path, fallback_path) if path.is_file()]
        newest_source = max((path.stat().st_mtime for path in dependencies), default=0)
        if cache_path.is_file() and cache_path.stat().st_mtime >= newest_source:
            return cache_path

        cache_dir.mkdir(parents=True, exist_ok=True)
        pending = cache_path.with_name(f".{cache_path.stem}.pending.png")
        pending.unlink(missing_ok=True)
        try:
            ok, _message = create_document_preview(source_path, pending)
            if not ok and fallback_path.is_file():
                from PIL import Image

                with Image.open(fallback_path) as image:
                    preview = image.convert("RGB")
                    preview.thumbnail((640, 880), Image.Resampling.LANCZOS)
                    page = Image.new("RGB", (724, 1024), "white")
                    x = (page.width - preview.width) // 2
                    y = max(52, (page.height - preview.height) // 3)
                    page.paste(preview, (x, y))
                    page.save(pending, format="PNG", optimize=True)
            if pending.is_file() and pending.stat().st_size > 0:
                os.replace(pending, cache_path)
        finally:
            pending.unlink(missing_ok=True)
        return cache_path if cache_path.is_file() else fallback_path

    def content_records(self, kind: str) -> list[dict[str, Any]]:
        if kind not in ("style", "form", "page"):
            raise RuntimeError(f"지원하지 않는 콘텐츠 종류입니다: {kind}")
        config = self.config()
        config_key = {"style": "blocks", "form": "forms", "page": "page_items"}[kind]
        records: list[dict[str, Any]] = []

        for item in config.get(config_key, []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not item_id or not title:
                continue
            record = {
                "key": f"builtin:{item_id}",
                "id": item_id,
                "title": title,
                "source": "builtin",
                "user_item": False,
            }
            if kind in ("style", "form"):
                record["file_path"] = str(
                    self.checked_repository_file(str(item.get("file") or ""))
                )
                configured_thumb = self.checked_repository_file(
                    str(item.get("thumb") or "")
                )
                if kind == "form":
                    record["thumb_path"] = str(
                        self.builtin_form_preview(
                            item_id,
                            Path(record["file_path"]),
                            configured_thumb,
                        )
                    )
                else:
                    record["thumb_path"] = str(configured_thumb)
            else:
                thumb_name = str(item.get("thumb") or "")
                thumb_root = str(config.get("page_thumbs_root") or "page_thumbs")
                record["thumb_path"] = str(
                    self.checked_repository_file(str(Path(thumb_root) / thumb_name))
                )
                record["margins"] = dict(DEFAULT_PAGE_MARGINS)
                record["orientation"] = item.get("orientation", "portrait")
                if item.get("paper_size"):
                    record["paper_size"] = dict(item["paper_size"])
            records.append(record)

        store = UserContentStore()
        for item in store.list_items(kind):
            item_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not item_id or not title:
                continue
            record = {
                "key": f"user:{item_id}",
                "id": item_id,
                "title": title,
                "source": "user",
                "user_item": True,
                "thumb_path": str(item.get("thumb") or ""),
            }
            if kind in ("style", "form"):
                record["file_path"] = str(item.get("file") or "")
            else:
                record["margins"] = dict(item.get("margins") or DEFAULT_PAGE_MARGINS)
                record["orientation"] = item.get("orientation", "portrait")
            records.append(record)
        return records

    def public_content_item(self, record: dict[str, Any]) -> dict[str, Any]:
        public = {
            "key": record["key"],
            "id": record["id"],
            "title": record["title"],
            "source": record["source"],
            "user_item": bool(record["user_item"]),
            "preview": self.preview_data_url(record.get("thumb_path") or ""),
        }
        if "margins" in record:
            public["margins"] = dict(record["margins"])
            public["orientation"] = record.get("orientation", "portrait")
        return public

    def catalog(self, kind: str) -> list[dict[str, Any]]:
        return [self.public_content_item(item) for item in self.content_records(kind)]

    def find_content(self, kind: str, key: str) -> dict[str, Any]:
        for record in self.content_records(kind):
            if record["key"] == str(key or "").strip():
                return record
        raise RuntimeError("선택한 항목을 찾지 못했습니다. 목록을 새로 불러오세요.")

    def table_catalog(self) -> list[dict[str, Any]]:
        tools = feature_registry.with_current_table_tools(
            self.config().get("table_tools", [])
        )
        result = []
        for item in tools:
            if not isinstance(item, dict):
                continue
            thumb = self.checked_repository_file(str(item.get("thumb") or ""))
            result.append(
                {
                    "action_id": str(item.get("action_id") or ""),
                    "title": str(item.get("title") or ""),
                    "preview": self.preview_data_url(thumb),
                }
            )
        return result

    def character_catalog(self) -> list[dict[str, Any]]:
        from src.jb_quickpanel.features.character_effects import square_character_groups
        store = UserContentStore()
        groups = [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "chars": [str(value) for value in item.get("chars", [])],
                "user_item": True,
            }
            for item in store.list_symbol_groups()
        ]
        symbols = self.config().get("symbols", {})
        if isinstance(symbols, dict):
            groups.extend(
                {
                    "id": f"builtin:{index}",
                    "title": str(title),
                    "chars": [str(value) for value in (values or [])],
                    "user_item": False,
                }
                for index, (title, values) in enumerate(symbols.items())
            )
        square_index = next((index + 1 for index, group in enumerate(groups)
                             if group["title"] == "원문자-검정"), len(groups))
        groups[square_index:square_index] = square_character_groups()
        return groups

    def picture_symbol_catalog(self) -> list[dict[str, Any]]:
        supported = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
        result = []
        user_items = []
        for item in UserContentStore().list_picture_symbols():
            file_path = Path(str(item.get("file") or ""))
            if not file_path.is_file() or file_path.suffix.lower() not in supported:
                continue
            user_items.append(
                {
                    "id": str(item.get("id") or ""),
                    "key": f"user:{item.get('id', '')}",
                    "favorite_key": f"user:{item.get('id', '')}",
                    "title": str(item.get("title") or file_path.stem),
                    "preview": self.preview_data_url(file_path),
                    "preview_on_dark": "하양" in file_path.stem,
                    "user_item": True,
                }
            )
        if user_items:
            result.append({"title": "내 심볼", "items": user_items, "user_group": True})

        config = self.config()
        symbol_root = self.checked_repository_file(
            str((config.get("settings") or {}).get("symbols_root") or "symbols")
        )
        if not symbol_root.is_dir():
            return result
        for folder in sorted(symbol_root.iterdir(), key=lambda path: path.name.casefold()):
            if not folder.is_dir():
                continue
            items = []
            for file_path in sorted(folder.iterdir(), key=lambda path: path.name.casefold()):
                if file_path.is_file() and file_path.suffix.lower() in supported:
                    items.append(
                        {
                            "key": str(file_path.resolve()),
                            "favorite_key": f"builtin:{file_path.relative_to(symbol_root).as_posix()}",
                            "title": file_path.stem,
                            "preview": self.preview_data_url(file_path),
                            "preview_on_dark": "하양" in file_path.stem,
                            "user_item": False,
                        }
                    )
            result.append({"title": folder.name, "items": items, "user_group": False})
        return result

    def find_picture_symbol(self, key: str) -> Path:
        key_value = str(key or "")
        if key_value.startswith("user:"):
            item_id = key_value.partition(":")[2]
            item = next(
                (
                    value
                    for value in UserContentStore().list_picture_symbols()
                    if str(value.get("id") or "") == item_id
                ),
                None,
            )
            if item is None:
                raise RuntimeError("선택한 사용자 심볼을 찾지 못했습니다.")
            candidate = Path(str(item.get("file") or "")).resolve()
            if not candidate.is_file():
                raise RuntimeError("선택한 사용자 심볼 이미지 파일을 찾지 못했습니다.")
            return candidate

        candidate = Path(key_value).resolve()
        symbol_root = self.checked_repository_file(
            str((self.config().get("settings") or {}).get("symbols_root") or "symbols")
        )
        if symbol_root not in candidate.parents or not candidate.is_file():
            raise RuntimeError("선택한 심볼 이미지를 찾지 못했습니다.")
        return candidate
    def pick_files(self, kind: str) -> list[str]:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as error:
            raise RuntimeError(f"파일 선택 창을 열 수 없습니다: {error}") from error

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
            root.update()
            if kind == "hwp":
                path = filedialog.askopenfilename(
                    parent=root,
                    title="등록할 한글 파일 선택",
                    filetypes=(("한글 문서", "*.hwp *.hwpx"), ("모든 파일", "*.*")),
                )
                return [str(Path(path).resolve())] if path else []
            if kind == "preview":
                path = filedialog.askopenfilename(
                    parent=root,
                    title="미리보기 이미지 선택",
                    filetypes=(
                        ("이미지", "*.png *.jpg *.jpeg *.bmp *.gif"),
                        ("모든 파일", "*.*"),
                    ),
                )
                return [str(Path(path).resolve())] if path else []
            if kind in {"images", "picture_symbols"}:
                paths = filedialog.askopenfilenames(
                    parent=root,
                    title="추가할 심볼 이미지 선택" if kind == "picture_symbols" else "셀에 넣을 그림 선택",
                    filetypes=(
                        ("그림 파일", "*.png *.jpg *.jpeg *.gif *.bmp"),
                        ("모든 파일", "*.*"),
                    ),
                )
                return [str(Path(path).resolve()) for path in paths]
            raise RuntimeError("지원하지 않는 파일 선택 종류입니다.")
        finally:
            root.destroy()

    def _pick_user_backup_path(self, mode: str) -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as error:
            raise RuntimeError(f"백업 파일 선택 창을 열 수 없습니다: {error}") from error

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
            root.update()
            documents = Path.home() / "Documents"
            initial_dir = str(documents if documents.is_dir() else Path.home())
            if mode == "save":
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = filedialog.asksaveasfilename(
                    parent=root,
                    title="JB에듀 폼 설정과 내 자료 백업",
                    initialdir=initial_dir,
                    initialfile=f"JBEdu_FORM_백업_{stamp}{BACKUP_EXTENSION}",
                    defaultextension=BACKUP_EXTENSION,
                    filetypes=(
                        ("JB에듀 폼 백업", f"*{BACKUP_EXTENSION}"),
                        ("모든 파일", "*.*"),
                    ),
                )
            elif mode == "open":
                path = filedialog.askopenfilename(
                    parent=root,
                    title="복원할 JB에듀 폼 백업 파일 선택",
                    initialdir=initial_dir,
                    filetypes=(
                        ("JB에듀 폼 백업", f"*{BACKUP_EXTENSION}"),
                        ("모든 파일", "*.*"),
                    ),
                )
            else:
                raise RuntimeError("지원하지 않는 백업 파일 선택 방식입니다.")
            return str(Path(path).resolve()) if path else ""
        finally:
            root.destroy()

    def backup_user_data(self) -> dict[str, Any]:
        destination = self._pick_user_backup_path("save")
        if not destination:
            return {"cancelled": True}
        result = create_user_backup(
            destination,
            app_version=APP_VERSION,
            integration=self.integration_status(),
        )
        result["cancelled"] = False
        return result

    def restore_user_data(self) -> tuple[dict[str, Any], dict[str, Any]]:
        source = self._pick_user_backup_path("open")
        if not source:
            return {"cancelled": True}, self.load_settings()
        result = restore_user_backup(
            source,
            app_version=APP_VERSION,
            integration=self.integration_status(),
        )
        result["cancelled"] = False
        return result, self.load_settings()

    def _create_preview(self, kind: str, source_path: str):
        store = UserContentStore()
        pending = store.pending_preview_path()
        ok, message = create_document_preview(
            source_path,
            pending,
            crop_content=(kind == "style"),
        )
        return store, pending if ok else None, message, pending

    def add_user_file(
        self,
        kind: str,
        title: str,
        source_path: str,
        document_title: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        store, preview, message, pending = self._create_preview(kind, source_path)
        try:
            item = store.add_file(
                kind, title, source_path, preview_path=preview,
                document_title=document_title,
            )
            note = "" if preview else f" 미리보기는 만들지 못했습니다: {message}"
            return item, note
        finally:
            pending.unlink(missing_ok=True)

    def add_user_block(self, kind: str, title: str, bridge):
        store = UserContentStore()
        extension = ".hwp" if kind == "style" else ".hwpx"
        pending = store.pending_file_path(extension)
        preview_pending = None
        try:
            ok, message = bridge.save_selected_block(
                str(pending), format_name="HWP" if kind == "style" else "HWPX"
            )
            if not ok:
                raise RuntimeError(message)
            _store, preview, preview_message, preview_pending = self._create_preview(
                kind, str(pending)
            )
            item = store.add_file(kind, title, str(pending), preview_path=preview)
            note = (
                ""
                if preview
                else f" 미리보기는 만들지 못했습니다: {preview_message}"
            )
            return item, note
        finally:
            pending.unlink(missing_ok=True)
            if preview_pending is not None:
                preview_pending.unlink(missing_ok=True)

    def analyze_auto_title_block(self, role: str, bridge):
        role = normalize_auto_title_role(role)
        ok, selected_text = bridge.get_selected_text()
        if not ok:
            raise RuntimeError(selected_text)
        analysis = analyze_example_text(role, selected_text)
        store = UserContentStore()
        pending = store.pending_file_path(".hwpx")
        preview_pending = None
        try:
            ok, message = bridge.save_selected_block(str(pending), format_name="HWPX")
            if not ok:
                raise RuntimeError(message)
            import zipfile

            if not zipfile.is_zipfile(pending):
                raise RuntimeError(
                    "예시 블록을 HWPX로 저장하지 못했습니다. 한글 문서를 HWPX로 저장할 수 있는지 확인하세요."
                )
            _store, preview, _preview_message, preview_pending = self._create_preview(
                "style", str(pending)
            )
            return {
                **analysis,
                "pending_id": pending.name,
                "preview": self.preview_data_url(preview) if preview else "",
            }
        except Exception:
            pending.unlink(missing_ok=True)
            raise
        finally:
            if preview_pending is not None:
                preview_pending.unlink(missing_ok=True)

    def _pending_auto_title_path(self, pending_id: str) -> Path:
        name = Path(str(pending_id or "")).name
        if not re.fullmatch(r"pending_[0-9a-f]{32}\.hwpx", name):
            raise UserContentError("등록 대기 중인 제목 예시를 찾지 못했습니다.")
        store = UserContentStore()
        path = (store.root / "pending" / name).resolve()
        pending_root = (store.root / "pending").resolve()
        if path.parent != pending_root or not path.is_file():
            raise UserContentError("등록 대기 중인 제목 예시가 만료되었습니다. 다시 블록 지정하세요.")
        return path

    def register_auto_title_block(
        self,
        role: str,
        title: str,
        pending_id: str,
        title_sample: str,
        number_sample: str = "",
    ):
        role = normalize_auto_title_role(role)
        source = self._pending_auto_title_path(pending_id)
        store = UserContentStore()
        prepared = store.pending_file_path(".hwpx")
        preview_pending = None
        registered = False
        try:
            _store, preview, preview_message, preview_pending = self._create_preview(
                "style", str(source)
            )
            tokens = prepare_hwpx_template(
                source,
                prepared,
                role=role,
                title_sample=title_sample,
                number_sample=number_sample,
            )
            item = store.add_auto_title_template(
                role,
                title,
                prepared,
                title_token=tokens["title_token"],
                number_token=tokens["number_token"],
                preview_path=preview,
            )
            registered = True
            note = "" if preview else f" 미리보기는 만들지 못했습니다: {preview_message}"
            return item, note
        finally:
            if registered:
                source.unlink(missing_ok=True)
            prepared.unlink(missing_ok=True)
            if preview_pending is not None:
                preview_pending.unlink(missing_ok=True)

    def discard_auto_title_block(self, pending_id: str):
        path = self._pending_auto_title_path(pending_id)
        path.unlink(missing_ok=True)
        return True

    def update_auto_title_template(self, item_id: str, title: str):
        return UserContentStore().update_auto_title_template(item_id, title)

    def delete_auto_title_template(self, item_id: str):
        return UserContentStore().delete_auto_title_template(item_id)

    def save_page(self, item_id: str, title: str, margins: dict[str, Any], orientation="portrait"):
        store = UserContentStore()
        if item_id:
            return store.update_item("page", item_id, title=title, margins=margins, orientation=orientation)
        return store.add_page(title, margins, orientation)

    def update_user_title(self, kind: str, item_id: str, title: str):
        return UserContentStore().update_item(kind, item_id, title=title)

    def save_kedufine_text_form(self, item_id: str, title: str, category: str, body: str):
        store = UserContentStore()
        if item_id:
            return store.update_kedufine_text_form(item_id, title, category, body)
        return store.add_kedufine_text_form(title, category, body)

    def delete_user_item(self, kind: str, item_id: str):
        return UserContentStore().delete_item(kind, item_id)

    def save_symbol_group(
        self,
        item_id: str,
        title: str,
        chars: list[str] | str,
    ):
        store = UserContentStore()
        if item_id:
            return store.update_symbol_group(item_id, title, chars)
        settings = self.load_settings()
        ranks = {key: index for index, key in enumerate(settings["character_group_order"])}
        groups = self.character_catalog()
        existing_order = [group["id"] for _, group in sorted(
            enumerate(groups), key=lambda entry: ranks.get(entry[1]["id"], len(ranks) + entry[0])
        )]
        item = store.add_symbol_group(title, chars)
        try:
            self.save_settings({"character_group_order": [item["id"], *existing_order]})
        except Exception:
            store.delete_symbol_group(item["id"])
            raise
        return item

    def delete_symbol_group(self, item_id: str):
        return UserContentStore().delete_symbol_group(item_id)

    def add_picture_symbols(self, source_paths: list[str] | tuple[str, ...]):
        paths = [str(value or "").strip() for value in source_paths if str(value or "").strip()]
        if not paths:
            raise UserContentError("추가할 심볼 이미지를 선택하세요.")
        if len(paths) > 50:
            raise UserContentError("심볼 이미지는 한 번에 최대 50개까지 추가할 수 있습니다.")
        store = UserContentStore()
        return [store.add_picture_symbol(path) for path in paths]

    def update_picture_symbol(self, item_id: str, title: str):
        return UserContentStore().update_picture_symbol(item_id, title)

    def delete_picture_symbol(self, item_id: str):
        return UserContentStore().delete_picture_symbol(item_id)
    def update_preview(
        self,
        kind: str,
        item_id: str,
        mode: str,
        source_path: str = "",
    ):
        store = UserContentStore()
        if mode == "remove":
            return store.update_preview(kind, item_id, None), ""
        if mode == "image":
            return store.update_preview(kind, item_id, source_path), ""
        if mode != "auto":
            raise RuntimeError("지원하지 않는 미리보기 변경 방식입니다.")
        item = next(
            (
                value
                for value in store.list_items(kind)
                if str(value.get("id") or "") == item_id
            ),
            None,
        )
        if item is None:
            raise UserContentError("사용자 항목을 찾지 못했습니다.")
        _store, preview, message, pending = self._create_preview(
            kind, str(item.get("file") or "")
        )
        try:
            if preview is None:
                raise RuntimeError(message)
            return store.update_preview(kind, item_id, str(preview)), ""
        finally:
            pending.unlink(missing_ok=True)

    def load_settings(self) -> dict[str, Any]:
        values = app_config.load_settings()
        needs_save = False
        normalized_profile_state = normalize_auto_format_profile_state(
            values.get("auto_format_profiles"),
            values.get("active_auto_format_profile"),
            values.get("auto_format"),
        )
        if any(values.get(key) != value for key, value in normalized_profile_state.items()):
            values.update(normalized_profile_state)
            needs_save = True
        hotkeys = dict(values.get("global_hotkeys") or {})
        legacy_toggle = str(hotkeys.pop("app.toggle_window", "") or "").strip()
        if legacy_toggle:
            values["toggle_hotkey"] = legacy_toggle
            values["global_hotkeys"] = hotkeys
            needs_save = True
        if needs_save:
            app_config.save_settings(values)
        defaults = self.config().get("settings") or {}
        values.setdefault("always_on_top", bool(defaults.get("always_on_top", True)))
        values.setdefault("target_mode", values.get("start_mode", "hwp"))
        values.setdefault(
            "tab_order",
            ["style", "edit", "chars", "symbol", "forms", "page"],
        )
        values.setdefault("last_geometry", "")
        values["card_favorites"] = app_config.normalize_card_favorites(values.get("card_favorites"))
        return values

    def toggle_card_favorite(self, kind: str, key: str) -> dict[str, list[str]]:
        if kind not in app_config.CARD_FAVORITE_KINDS:
            raise ValueError("즐겨찾기 종류가 올바르지 않습니다.")
        if not isinstance(key, str) or not key.strip() or len(key) > 512:
            raise ValueError("즐겨찾기 항목이 올바르지 않습니다.")
        settings = self.load_settings()
        favorites = settings["card_favorites"]
        if key in favorites[kind]:
            favorites[kind].remove(key)
        else:
            favorites[kind].append(key)
        settings["card_favorites"] = favorites
        app_config.save_settings(settings)
        return favorites

    def save_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        profiles = changes.get("auto_format_profiles")
        if isinstance(profiles, list) and len(profiles) > MAX_AUTO_FORMAT_PROFILES:
            raise ValueError(f"자동 서식 설정은 최대 {MAX_AUTO_FORMAT_PROFILES}개까지 저장할 수 있습니다.")
        allowed = {
            "always_on_top",
            "target_mode",
            "start_mode",
            "start_position",
            "remember_window_position",
            "close_to_tray",
            "start_minimized",
            "tutorial_completed",
            "check_updates_on_startup",
            "toggle_hotkey",
            "global_hotkeys_enabled",
            "global_hotkeys",
            "auto_format",
            "active_auto_format_profile",
            "auto_format_profiles",
            "tab_order",
            "last_geometry",
            "character_group_order",
        }
        settings = self.load_settings()
        for key, value in changes.items():
            if key in allowed:
                settings[key] = value
        if "auto_format" in changes and "auto_format_profiles" not in changes:
            active_id = str(settings.get("active_auto_format_profile") or "")
            settings["auto_format_profiles"] = [
                {
                    **profile,
                    "settings": changes["auto_format"],
                }
                if str(profile.get("id") or "") == active_id
                else profile
                for profile in settings.get("auto_format_profiles") or []
                if isinstance(profile, dict)
            ]
        if settings.get("target_mode") not in ("hwp", "kedufine"):
            settings["target_mode"] = "hwp"
        settings.update(
            normalize_auto_format_profile_state(
                settings.get("auto_format_profiles"),
                settings.get("active_auto_format_profile"),
                settings.get("auto_format"),
            )
        )
        settings["character_group_order"] = app_config.normalize_character_group_order(settings.get("character_group_order"))
        app_config.save_settings(settings)
        return settings

    def reset_settings(self) -> dict[str, Any]:
        settings = deepcopy(app_config.DEFAULT_SETTINGS)
        settings["always_on_top"] = bool(
            (self.config().get("settings") or {}).get("always_on_top", True)
        )
        settings["target_mode"] = settings.get("start_mode", "hwp")
        settings["tab_order"] = ["style", "edit", "chars", "symbol", "forms", "page"]
        app_config.save_settings(settings)
        return self.load_settings()

    def update_status(self) -> dict[str, Any]:
        app_id = str(self.config().get("update_app_id") or "").strip()
        if not app_id:
            return {
                "configured": False,
                "current": APP_VERSION,
                "message": "업데이트 정보 고유번호가 아직 설정되지 않았습니다.",
            }
        from src.jb_quickpanel.services import update_checker

        result = update_checker.check_update(app_id, APP_VERSION.lstrip("vV."))
        result["configured"] = True
        result["current"] = APP_VERSION
        return result

    def _start_menu_folder(self) -> Path:
        return (
            Path(os.environ.get("APPDATA") or Path.home())
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )

    def _start_menu_path(self) -> Path:
        return self._start_menu_folder() / f"{APP_TITLE}.lnk"

    def _start_menu_signature(self) -> str:
        executable = os.environ.get("JB_TAURI_EXE", "").strip()
        return f"{Path(executable).resolve() if executable else ''}|{APP_VERSION}"

    def integration_status(self) -> dict[str, Any]:
        return {
            "startup": app_config.is_windows_startup_enabled(),
            "start_menu": self._start_menu_path().exists() if os.name == "nt" else False,
            "settings_dir": str(app_config.app_data_dir()),
        }

    def prepare_integrations(self) -> dict[str, Any]:
        if os.name != "nt" or os.environ.get("JB_TAURI_DEV") == "1":
            return self.integration_status()
        settings = self.load_settings()
        signature = self._start_menu_signature()
        previous_signature = str(settings.get("start_menu_signature") or "")
        current_registered = self._start_menu_path().exists()
        any_registered = app_config.has_any_start_menu_shortcut()
        obsolete_registered = app_config.has_obsolete_start_menu_shortcuts(APP_VERSION)
        auto_done = bool(settings.get("start_menu_auto_done", False))
        should_register = (
            (previous_signature != signature and (any_registered or not auto_done))
            or (current_registered and obsolete_registered)
            or (not current_registered and any_registered)
            or not auto_done
        )
        if should_register:
            self.set_start_menu(True)
        elif previous_signature != signature:
            settings["start_menu_signature"] = signature
            app_config.save_settings(settings)
        if app_config.is_windows_startup_enabled():
            self.set_startup(True, bool(settings.get("start_minimized", False)))
        return self.integration_status()

    def set_startup(self, enabled: bool, start_minimized: bool):
        executable = os.environ.get("JB_TAURI_EXE", "").strip()
        if not executable:
            raise RuntimeError("현재 Tauri 실행 파일 경로를 확인하지 못했습니다.")
        if os.name != "nt":
            raise RuntimeError("Windows에서만 사용할 수 있습니다.")
        import winreg

        command = f'"{Path(executable).resolve()}"'
        if start_minimized:
            command += " --tray"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    app_config.RUN_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    command,
                )
            else:
                try:
                    winreg.DeleteValue(key, app_config.RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass

    def set_start_menu(self, enabled: bool):
        if os.name != "nt":
            raise RuntimeError("Windows에서만 사용할 수 있습니다.")
        executable = os.environ.get("JB_TAURI_EXE", "").strip()
        if not executable:
            raise RuntimeError("현재 Tauri 실행 파일 경로를 확인하지 못했습니다.")
        folder = (
            Path(os.environ.get("APPDATA") or Path.home())
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )
        folder.mkdir(parents=True, exist_ok=True)
        shortcut_path = folder / f"{APP_TITLE}.lnk"
        if enabled:
            import win32com.client

            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(str(shortcut_path))
            shortcut.TargetPath = str(Path(executable).resolve())
            shortcut.WorkingDirectory = str(Path(executable).resolve().parent)
            shortcut.Description = APP_TITLE
            shortcut.IconLocation = str(Path(executable).resolve())
            shortcut.Save()
            for path in app_config.start_menu_shortcut_paths():
                if path.resolve() != shortcut_path.resolve():
                    path.unlink(missing_ok=True)
        else:
            for path in app_config.start_menu_shortcut_paths():
                path.unlink(missing_ok=True)
        settings = self.load_settings()
        settings["start_menu_auto_done"] = True
        settings["start_menu_signature"] = self._start_menu_signature()
        app_config.save_settings(settings)

    def open_update_url(self, url: str):
        from urllib.parse import urlparse
        import webbrowser

        target = str(url or "").strip()
        parsed = urlparse(target)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise RuntimeError("올바른 업데이트 안내 주소가 아닙니다.")
        if not webbrowser.open(target):
            raise RuntimeError("업데이트 안내 페이지를 열지 못했습니다.")
        return target

    def open_support_path(self, kind: str):
        if kind in {"manual", "readme"}:
            return self.open_manual()
        paths = {
            "settings": app_config.app_data_dir(),
            "crash": app_config.crash_log_path(),
            "changelog": self.support_resource_root() / "support" / "CHANGELOG.md",
        }
        path = paths.get(kind)
        if path is None:
            raise RuntimeError("지원하지 않는 경로입니다.")
        if kind == "crash" and not path.exists():
            path.write_text("아직 기록된 오류가 없습니다.\n", encoding="utf-8")
        if not path.exists():
            if kind == "changelog":
                raise RuntimeError("변경 기록 파일을 찾지 못했습니다. 프로그램을 다시 설치해 주세요.")
            raise RuntimeError(f"파일 또는 폴더를 찾지 못했습니다: {path}")
        app_config.open_path(path)
        return str(path)

    def support_resource_root(self) -> Path:
        resource_dir = os.environ.get("JB_APP_RESOURCE_DIR")
        if resource_dir:
            return Path(resource_dir).resolve()
        executable = os.environ.get("JB_TAURI_EXE")
        if executable and os.environ.get("JB_TAURI_DEV") != "1":
            return Path(executable).resolve().parent
        return self.root / "tauri-prototype" / "src-tauri"

    def open_manual(self, section: str = "") -> str:
        import webbrowser

        if section and not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", section):
            raise RuntimeError("지원하지 않는 매뉴얼 항목입니다.")
        path = self.support_resource_root() / "manual" / "index.html"
        if not path.is_file():
            raise RuntimeError("사용자 매뉴얼 파일을 찾지 못했습니다. 프로그램을 다시 설치해 주세요.")
        browser_path = str(path.resolve())
        # Tauri's Windows resource directory may use a filesystem-only namespace.
        if browser_path[:8].upper() == "\\\\?\\UNC\\":
            browser_path = "\\\\" + browser_path[8:]
        elif browser_path.startswith("\\\\?\\"):
            browser_path = browser_path[4:]
        url = Path(browser_path).as_uri() + (f"#{section}" if section else "")
        if os.name == "nt":
            browser = default_windows_browser()
            try:
                subprocess.Popen(
                    [browser, url], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except OSError as error:
                raise RuntimeError("사용자 매뉴얼을 열지 못했습니다. 기본 웹브라우저를 확인해 주세요.") from error
        elif not webbrowser.open(url):
            raise RuntimeError("사용자 매뉴얼을 열지 못했습니다. 기본 웹브라우저를 확인해 주세요.")
        return url

    def open_form_working_copy(self, record: dict[str, Any]) -> str:
        source = Path(str(record.get("file_path") or "")).resolve()
        if not source.is_file():
            raise RuntimeError("양식 파일을 찾지 못했습니다.")
        title = re.sub(r'[<>:"/\\|?*]+', "_", str(record.get("title") or source.stem)).strip(" ._")
        title = title or "양식"
        destination_dir = app_config.app_data_dir() / "working_documents"
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = destination_dir / f"{title}_{stamp}{source.suffix.lower()}"
        shutil.copy2(source, destination)
        app_config.open_path(destination)
        return str(destination)
