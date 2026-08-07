# -*- coding: utf-8 -*-
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from src.jb_quickpanel_v29.services import app_config


LIBRARY_VERSION = 1
KIND_KEYS = {
    "style": "styles",
    "form": "forms",
    "page": "pages",
}
FILE_KINDS = {"style", "form"}
SUPPORTED_HWP_EXTENSIONS = {".hwp", ".hwpx"}
PAGE_MARGIN_FIELDS = (
    "top",
    "header",
    "left",
    "gutter",
    "right",
    "footer",
    "bottom",
)
DEFAULT_PAGE_MARGINS = {
    "top": 10.0,
    "header": 10.0,
    "left": 20.0,
    "gutter": 0.0,
    "right": 20.0,
    "footer": 10.0,
    "bottom": 15.0,
}


class UserContentError(ValueError):
    pass


class UserContentStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else app_config.app_data_dir() / "user_content"
        self.root.mkdir(parents=True, exist_ok=True)
        self.library_path = self.root / "library.json"
        self._library = self._load_library()

    def _empty_library(self):
        return {
            "version": LIBRARY_VERSION,
            "styles": [],
            "forms": [],
            "pages": [],
        }

    def _load_library(self):
        if not self.library_path.exists():
            return self._empty_library()
        try:
            with self.library_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, dict):
                raise ValueError("library root is not an object")
            library = self._empty_library()
            for key in ("styles", "forms", "pages"):
                values = raw.get(key, [])
                if isinstance(values, list):
                    library[key] = [item for item in values if isinstance(item, dict)]
            return library
        except Exception:
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.library_path.replace(self.root / f"library.broken_{stamp}.json")
            except Exception:
                pass
            return self._empty_library()

    def _save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.library_path.with_suffix(".tmp")
        try:
            with temp.open("w", encoding="utf-8") as file:
                json.dump(self._library, file, ensure_ascii=False, indent=2)
            os.replace(temp, self.library_path)
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except Exception:
                pass

    def _key(self, kind):
        try:
            return KIND_KEYS[str(kind)]
        except KeyError as exc:
            raise UserContentError(f"지원하지 않는 사용자 항목 종류입니다: {kind}") from exc

    def _clean_title(self, title):
        value = " ".join(str(title or "").strip().split())
        if not value:
            raise UserContentError("이름을 입력하세요.")
        if len(value) > 40:
            raise UserContentError("이름은 40자 이내로 입력하세요.")
        return value

    def _ensure_unique_title(self, kind, title, exclude_id=None):
        title_key = title.casefold()
        for item in self._library[self._key(kind)]:
            if item.get("id") == exclude_id:
                continue
            if str(item.get("title", "")).casefold() == title_key:
                raise UserContentError("같은 이름의 사용자 항목이 이미 있습니다.")

    def _new_id(self):
        return uuid.uuid4().hex[:12]

    def list_items(self, kind):
        key = self._key(kind)
        result = []
        for item in self._library[key]:
            current = dict(item)
            current["user_item"] = True
            current["kind"] = kind
            if kind in FILE_KINDS:
                rel_path = str(current.get("file", ""))
                current["file"] = str((self.root / rel_path).resolve()) if rel_path else ""
            result.append(current)
        return result

    def pending_file_path(self, extension=".hwp"):
        ext = str(extension or ".hwp").lower()
        if ext not in SUPPORTED_HWP_EXTENSIONS:
            ext = ".hwp"
        folder = self.root / "pending"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"pending_{uuid.uuid4().hex}{ext}"

    def add_file(self, kind, title, source_path):
        if kind not in FILE_KINDS:
            raise UserContentError("파일로 등록할 수 없는 항목입니다.")
        title = self._clean_title(title)
        self._ensure_unique_title(kind, title)
        source = Path(source_path)
        if not source.is_file():
            raise UserContentError("등록할 한글 파일을 찾지 못했습니다.")
        extension = source.suffix.lower()
        if extension not in SUPPORTED_HWP_EXTENSIONS:
            raise UserContentError("HWP 또는 HWPX 파일만 등록할 수 있습니다.")

        item_id = self._new_id()
        folder_name = "styles" if kind == "style" else "forms"
        destination_dir = self.root / folder_name
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{item_id}{extension}"
        shutil.copy2(source, destination)
        item = {
            "id": item_id,
            "title": title,
            "file": destination.relative_to(self.root).as_posix(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._library[self._key(kind)].append(item)
        try:
            self._save()
        except Exception:
            try:
                destination.unlink()
            except Exception:
                pass
            self._library[self._key(kind)].remove(item)
            raise
        return dict(item)

    def normalize_page_margins(self, margins):
        values = {}
        source = margins if isinstance(margins, dict) else {}
        for field in PAGE_MARGIN_FIELDS:
            try:
                value = round(float(source.get(field, DEFAULT_PAGE_MARGINS[field])), 1)
            except Exception as exc:
                raise UserContentError("용지 여백은 숫자로 입력하세요.") from exc
            if value < 0 or value > 100:
                raise UserContentError("용지 여백은 0~100mm 범위로 입력하세요.")
            values[field] = value
        return values

    def add_page(self, title, margins):
        title = self._clean_title(title)
        self._ensure_unique_title("page", title)
        item = {
            "id": self._new_id(),
            "title": title,
            "margins": self.normalize_page_margins(margins),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._library["pages"].append(item)
        try:
            self._save()
        except Exception:
            self._library["pages"].remove(item)
            raise
        return dict(item)

    def update_item(self, kind, item_id, title=None, margins=None):
        key = self._key(kind)
        target = next((item for item in self._library[key] if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("사용자 항목을 찾지 못했습니다.")
        updates = {}
        if title is not None:
            clean_title = self._clean_title(title)
            self._ensure_unique_title(kind, clean_title, exclude_id=item_id)
            updates["title"] = clean_title
        if kind == "page" and margins is not None:
            updates["margins"] = self.normalize_page_margins(margins)
        previous = dict(target)
        target.update(updates)
        try:
            self._save()
        except Exception:
            target.clear()
            target.update(previous)
            raise
        return dict(target)

    def delete_item(self, kind, item_id):
        key = self._key(kind)
        items = self._library[key]
        target = next((item for item in items if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("사용자 항목을 찾지 못했습니다.")
        items.remove(target)
        try:
            self._save()
        except Exception:
            items.append(target)
            raise
        if kind in FILE_KINDS and target.get("file"):
            try:
                path = (self.root / str(target["file"])).resolve()
                root = self.root.resolve()
                if root == path.parent or root in path.parents:
                    path.unlink(missing_ok=True)
            except Exception:
                pass
        return dict(target)
