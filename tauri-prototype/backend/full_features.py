# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from src.jb_quickpanel.features import registry as feature_registry
from src.jb_quickpanel.features.document_preview import create_document_preview
from src.jb_quickpanel.services import app_config
from src.jb_quickpanel.services.user_content import (
    DEFAULT_PAGE_MARGINS,
    UserContentError,
    UserContentStore,
)

APP_VERSION = "v4.0"
APP_TITLE = "전북교육 한글 서식도우미"


class FullFeatureService:
    def __init__(self, repository_root: str | os.PathLike[str]):
        self.root = Path(repository_root).resolve()
        self.config_path = self.root / "config" / "config.json"

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
        return groups

    def picture_symbol_catalog(self) -> list[dict[str, Any]]:
        config = self.config()
        symbol_root = self.checked_repository_file(
            str((config.get("settings") or {}).get("symbols_root") or "symbols")
        )
        result = []
        if not symbol_root.is_dir():
            return result
        supported = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
        for folder in sorted(symbol_root.iterdir(), key=lambda path: path.name.casefold()):
            if not folder.is_dir():
                continue
            items = []
            for file_path in sorted(folder.iterdir(), key=lambda path: path.name.casefold()):
                if file_path.is_file() and file_path.suffix.lower() in supported:
                    items.append(
                        {
                            "key": str(file_path.resolve()),
                            "title": file_path.stem,
                            "preview": self.preview_data_url(file_path),
                            "preview_on_dark": "하양" in file_path.stem,
                        }
                    )
            result.append({"title": folder.name, "items": items})
        return result

    def find_picture_symbol(self, key: str) -> Path:
        candidate = Path(str(key or "")).resolve()
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
            if kind == "images":
                paths = filedialog.askopenfilenames(
                    parent=root,
                    title="셀에 넣을 그림 선택",
                    filetypes=(
                        ("그림 파일", "*.png *.jpg *.jpeg *.gif *.bmp"),
                        ("모든 파일", "*.*"),
                    ),
                )
                return [str(Path(path).resolve()) for path in paths]
            raise RuntimeError("지원하지 않는 파일 선택 종류입니다.")
        finally:
            root.destroy()

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
    ) -> tuple[dict[str, Any], str]:
        store, preview, message, pending = self._create_preview(kind, source_path)
        try:
            item = store.add_file(kind, title, source_path, preview_path=preview)
            note = "" if preview else f" 미리보기는 만들지 못했습니다: {message}"
            return item, note
        finally:
            pending.unlink(missing_ok=True)

    def add_user_block(self, kind: str, title: str, bridge):
        store = UserContentStore()
        pending = store.pending_file_path(".hwp")
        preview_pending = None
        try:
            ok, message = bridge.save_selected_block(str(pending))
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

    def save_page(self, item_id: str, title: str, margins: dict[str, Any]):
        store = UserContentStore()
        if item_id:
            return store.update_item("page", item_id, title=title, margins=margins)
        return store.add_page(title, margins)

    def update_user_title(self, kind: str, item_id: str, title: str):
        return UserContentStore().update_item(kind, item_id, title=title)

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
        return store.add_symbol_group(title, chars)

    def delete_symbol_group(self, item_id: str):
        return UserContentStore().delete_symbol_group(item_id)

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
        hotkeys = dict(values.get("global_hotkeys") or {})
        legacy_toggle = str(hotkeys.pop("app.toggle_window", "") or "").strip()
        if legacy_toggle:
            values["toggle_hotkey"] = legacy_toggle
            values["global_hotkeys"] = hotkeys
            app_config.save_settings(values)
        defaults = self.config().get("settings") or {}
        values.setdefault("always_on_top", bool(defaults.get("always_on_top", True)))
        values.setdefault("target_mode", values.get("start_mode", "hwp"))
        values.setdefault(
            "tab_order",
            ["style", "edit", "chars", "symbol", "forms", "page"],
        )
        values.setdefault("last_geometry", "")
        return values

    def save_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
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
            "tab_order",
            "last_geometry",
        }
        settings = self.load_settings()
        for key, value in changes.items():
            if key in allowed:
                settings[key] = value
        if settings.get("target_mode") not in ("hwp", "kedufine"):
            settings["target_mode"] = "hwp"
        app_config.save_settings(settings)
        return settings

    def reset_settings(self) -> dict[str, Any]:
        settings = dict(app_config.DEFAULT_SETTINGS)
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

        result = update_checker.check_update(app_id, APP_VERSION.lstrip("vV"))
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
        return self._start_menu_folder() / f"{APP_TITLE} ({APP_VERSION}).lnk"

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
        prefix = f"{APP_TITLE} (v"
        for path in folder.glob("*.lnk"):
            if path.name == f"{APP_TITLE}.lnk" or (
                path.name.startswith(prefix) and path.name.endswith(").lnk")
            ):
                path.unlink(missing_ok=True)
        if enabled:
            import win32com.client

            shortcut_path = folder / f"{APP_TITLE} ({APP_VERSION}).lnk"
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(str(shortcut_path))
            shortcut.TargetPath = str(Path(executable).resolve())
            shortcut.WorkingDirectory = str(Path(executable).resolve().parent)
            shortcut.Description = f"{APP_TITLE} {APP_VERSION}"
            shortcut.IconLocation = str(Path(executable).resolve())
            shortcut.Save()
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
        docs_root = Path(__file__).resolve().parent.parent
        paths = {
            "settings": app_config.app_data_dir(),
            "crash": app_config.crash_log_path(),
            "readme": docs_root / "README.md",
            "changelog": docs_root / "CHANGELOG.md",
        }
        path = paths.get(kind)
        if path is None:
            raise RuntimeError("지원하지 않는 경로입니다.")
        if kind == "crash" and not path.exists():
            path.write_text("아직 기록된 오류가 없습니다.\n", encoding="utf-8")
        if not path.exists():
            raise RuntimeError(f"파일 또는 폴더를 찾지 못했습니다: {path}")
        app_config.open_path(path)
        return str(path)
