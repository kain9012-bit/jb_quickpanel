# -*- coding: utf-8 -*-
import json
import math
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from src.jb_quickpanel.services import app_config

def _valid_hwp(path):
    try:
        with path.open("rb") as file:
            return file.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except OSError:
        return False


def _valid_hwpx(path):
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if not any(name.startswith("Contents/section") and name.endswith(".xml") for name in names):
                return False
            if "mimetype" in names and archive.read("mimetype").strip() != b"application/hwp+zip":
                return False
            return archive.testzip() is None
    except (OSError, zipfile.BadZipFile):
        return False


LIBRARY_VERSION = 5
KIND_KEYS = {
    "style": "styles",
    "form": "forms",
    "kedufine_form": "kedufine_forms",
    "page": "pages",
}
FILE_KINDS = {"style", "form", "kedufine_form"}
SUPPORTED_HWP_EXTENSIONS = {".hwp", ".hwpx"}
SUPPORTED_PREVIEW_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
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
            "kedufine_forms": [],
            "pages": [],
            "auto_title_templates": [],
            "symbol_groups": [],
            "picture_symbols": [],
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
            for key in ("styles", "forms", "kedufine_forms", "pages", "auto_title_templates", "symbol_groups", "picture_symbols"):
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
                for field in ("kedufine_file", "hwpx_file"):
                    rel_path = str(current.get(field, ""))
                    current[field] = str((self.root / rel_path).resolve()) if rel_path else ""
            thumb_path = str(current.get("thumb", ""))
            current["thumb"] = str((self.root / thumb_path).resolve()) if thumb_path else ""
            result.append(current)
        return result

    def pending_file_path(self, extension=".hwp"):
        ext = str(extension or ".hwp").lower()
        if ext not in SUPPORTED_HWP_EXTENSIONS:
            ext = ".hwp"
        folder = self.root / "pending"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"pending_{uuid.uuid4().hex}{ext}"

    def pending_preview_path(self):
        folder = self.root / "pending"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"preview_{uuid.uuid4().hex}.png"

    def _validate_preview_source(self, source_path):
        source = Path(source_path)
        if not source.is_file():
            raise UserContentError("미리보기 이미지 파일을 찾지 못했습니다.")
        extension = source.suffix.lower()
        if extension not in SUPPORTED_PREVIEW_EXTENSIONS:
            raise UserContentError("PNG, JPG, BMP 또는 GIF 이미지만 미리보기로 사용할 수 있습니다.")
        return source, extension

    def _copy_preview(self, item_id, source_path, *, unique=False):
        source, extension = self._validate_preview_source(source_path)
        destination_dir = self.root / "previews"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_name = f"{item_id}_{uuid.uuid4().hex}" if unique else item_id
        destination = destination_dir / f"{destination_name}{extension}"
        temp = destination_dir / f".{item_id}_{uuid.uuid4().hex}{extension}"
        shutil.copy2(source, temp)
        os.replace(temp, destination)
        return destination, destination.relative_to(self.root).as_posix()

    def _delete_relative_file(self, relative_path):
        if not relative_path:
            return
        try:
            path = (self.root / str(relative_path)).resolve()
            root = self.root.resolve()
            if root == path.parent or root in path.parents:
                path.unlink(missing_ok=True)
        except Exception:
            pass

    def add_file(self, kind, title, source_path, preview_path=None, document_title=None):
        if kind == "kedufine_form":
            raise UserContentError("기안문 양식은 본문 텍스트로 등록하세요.")
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
        if extension == ".hwp" and not _valid_hwp(source):
            raise UserContentError("올바른 HWP 파일이 아닙니다.")
        if extension == ".hwpx" and not _valid_hwpx(source):
            raise UserContentError("올바른 HWPX 파일이 아닙니다.")

        item_id = self._new_id()
        folder_name = {"style": "styles", "form": "forms"}[kind]
        destination_dir = self.root / folder_name
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{item_id}{extension}"
        try:
            shutil.copy2(source, destination)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise UserContentError(f"한글 파일을 등록하지 못했습니다: {exc}") from exc
        preview_destination = None
        item = {
            "id": item_id,
            "title": title,
            "file": destination.relative_to(self.root).as_posix(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            if preview_path:
                preview_destination, preview_relative = self._copy_preview(item_id, preview_path)
                item["thumb"] = preview_relative
            self._library[self._key(kind)].append(item)
            self._save()
        except Exception:
            self._delete_relative_file(item.get("file"))
            self._delete_relative_file(item.get("kedufine_file"))
            self._delete_relative_file(item.get("hwpx_file"))
            self._delete_relative_file(item.get("thumb"))
            if item in self._library[self._key(kind)]:
                self._library[self._key(kind)].remove(item)
            raise
        return dict(item)

    def _clean_kedufine_body(self, body):
        value = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not value:
            raise UserContentError("기안문 본문을 입력하세요.")
        if len(value) > 20000:
            raise UserContentError("기안문 본문은 20,000자 이내로 입력하세요.")
        return value

    def _clean_kedufine_category(self, category):
        if category not in {"internal", "outgoing"}:
            raise UserContentError("기안문 양식 분류를 선택하세요.")
        return category

    def add_kedufine_text_form(self, title, category, body):
        title = self._clean_title(title)
        self._ensure_unique_title("kedufine_form", title)
        item = {
            "id": self._new_id(),
            "title": title,
            "category": self._clean_kedufine_category(category),
            "body": self._clean_kedufine_body(body),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._library["kedufine_forms"].append(item)
        try:
            self._save()
        except Exception:
            self._library["kedufine_forms"].remove(item)
            raise
        return dict(item)

    def update_kedufine_text_form(self, item_id, title, category, body):
        target = next((item for item in self._library["kedufine_forms"] if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("사용자 기안문 양식을 찾지 못했습니다.")
        title = self._clean_title(title)
        self._ensure_unique_title("kedufine_form", title, exclude_id=item_id)
        previous = dict(target)
        target.update({
            "title": title,
            "category": self._clean_kedufine_category(category),
            "body": self._clean_kedufine_body(body),
        })
        if target.get("file"):
            if not target.get("legacy_file"):
                target["legacy_file"] = target["file"]
            target.pop("file")
        try:
            self._save()
        except Exception:
            target.clear()
            target.update(previous)
            raise
        return dict(target)

    def _ensure_unique_auto_title(self, role, title, exclude_id=None):
        title_key = title.casefold()
        for item in self._library["auto_title_templates"]:
            if item.get("id") == exclude_id or str(item.get("role") or "") != role:
                continue
            if str(item.get("title", "")).casefold() == title_key:
                raise UserContentError("같은 종류에 같은 이름의 제목 양식이 있습니다. 다른 이름을 입력하세요.")

    def list_auto_title_templates(self, role=None):
        result = []
        for item in self._library["auto_title_templates"]:
            if role and str(item.get("role") or "") != str(role):
                continue
            current = dict(item)
            current["user_item"] = True
            rel_path = str(current.get("file", ""))
            current["file"] = str((self.root / rel_path).resolve()) if rel_path else ""
            thumb_path = str(current.get("thumb", ""))
            current["thumb"] = str((self.root / thumb_path).resolve()) if thumb_path else ""
            result.append(current)
        return result

    def add_auto_title_template(
        self,
        role,
        title,
        source_path,
        *,
        title_token,
        number_token="",
        preview_path=None,
    ):
        role = str(role or "").strip()
        if role not in {"document_title", "title"}:
            raise UserContentError("지원하지 않는 자동 서식 제목 종류입니다.")
        title = self._clean_title(title)
        self._ensure_unique_auto_title(role, title)
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() != ".hwpx":
            raise UserContentError("제목 양식은 HWPX 형식으로 등록해야 합니다.")

        item_id = self._new_id()
        destination_dir = self.root / "auto_title_templates"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{item_id}.hwpx"
        shutil.copy2(source, destination)
        item = {
            "id": item_id,
            "role": role,
            "title": title,
            "file": destination.relative_to(self.root).as_posix(),
            "title_token": str(title_token or ""),
            "number_token": str(number_token or ""),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            if preview_path:
                _preview, preview_relative = self._copy_preview(item_id, preview_path)
                item["thumb"] = preview_relative
            self._library["auto_title_templates"].append(item)
            self._save()
        except Exception:
            self._delete_relative_file(item.get("file"))
            self._delete_relative_file(item.get("thumb"))
            if item in self._library["auto_title_templates"]:
                self._library["auto_title_templates"].remove(item)
            raise
        return dict(item)

    def update_auto_title_template(self, item_id, title):
        target = next(
            (item for item in self._library["auto_title_templates"] if item.get("id") == item_id),
            None,
        )
        if target is None:
            raise UserContentError("자동 서식 제목 항목을 찾지 못했습니다.")
        clean_title = self._clean_title(title)
        self._ensure_unique_auto_title(
            str(target.get("role") or ""), clean_title, exclude_id=item_id
        )
        previous = dict(target)
        target["title"] = clean_title
        try:
            self._save()
        except Exception:
            target.clear()
            target.update(previous)
            raise
        return dict(target)

    def delete_auto_title_template(self, item_id):
        items = self._library["auto_title_templates"]
        target = next((item for item in items if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("자동 서식 제목 항목을 찾지 못했습니다.")
        items.remove(target)
        try:
            self._save()
        except Exception:
            items.append(target)
            raise
        self._delete_relative_file(target.get("file"))
        self._delete_relative_file(target.get("thumb"))
        return dict(target)

    def normalize_page_margins(self, margins):
        values = {}
        source = margins if isinstance(margins, dict) else {}
        for field in PAGE_MARGIN_FIELDS:
            try:
                value = round(float(source.get(field, DEFAULT_PAGE_MARGINS[field])), 1)
            except Exception as exc:
                raise UserContentError("용지 여백은 숫자로 입력하세요.") from exc
            if not math.isfinite(value) or value < 0 or value > 100:
                raise UserContentError("용지 여백은 0~100mm 범위로 입력하세요.")
            values[field] = value
        return values

    def normalize_page_orientation(self, orientation):
        if orientation not in ("portrait", "landscape"):
            raise UserContentError("용지 방향을 선택하세요.")
        return orientation

    def add_page(self, title, margins, orientation="portrait"):
        title = self._clean_title(title)
        self._ensure_unique_title("page", title)
        item = {
            "id": self._new_id(),
            "title": title,
            "margins": self.normalize_page_margins(margins),
            "orientation": self.normalize_page_orientation(orientation),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._library["pages"].append(item)
        try:
            self._save()
        except Exception:
            self._library["pages"].remove(item)
            raise
        return dict(item)

    def update_preview(self, kind, item_id, source_path=None):
        if kind not in FILE_KINDS:
            raise UserContentError("미리보기를 변경할 수 없는 항목입니다.")
        key = self._key(kind)
        target = next((item for item in self._library[key] if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("사용자 항목을 찾지 못했습니다.")

        previous = dict(target)
        new_destination = None
        new_relative = ""
        try:
            if source_path:
                new_destination, new_relative = self._copy_preview(item_id, source_path, unique=True)
                target["thumb"] = new_relative
            else:
                target.pop("thumb", None)
            self._save()
        except Exception:
            target.clear()
            target.update(previous)
            if new_destination is not None and str(previous.get("thumb", "")) != new_relative:
                try:
                    new_destination.unlink(missing_ok=True)
                except Exception:
                    pass
            raise

        previous_thumb = str(previous.get("thumb", ""))
        current_thumb = str(target.get("thumb", ""))
        if previous_thumb and previous_thumb != current_thumb:
            self._delete_relative_file(previous_thumb)
        return dict(target)

    def update_item(self, kind, item_id, title=None, margins=None, document_title=None, orientation=None):
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
        if kind == "page" and orientation is not None:
            updates["orientation"] = self.normalize_page_orientation(orientation)
        if kind == "kedufine_form" and document_title is not None:
            updates["document_title"] = self._clean_title(document_title)
        previous = dict(target)
        target.update(updates)
        try:
            self._save()
        except Exception:
            target.clear()
            target.update(previous)
            raise
        return dict(target)

    def _clean_symbol_items(self, values):
        if isinstance(values, str):
            source = re.split(r"[\s,，]+", values.strip())
        elif isinstance(values, (list, tuple)):
            source = values
        else:
            source = []
        result = []
        seen = set()
        for value in source:
            item = str(value or "").strip()
            if not item or item in seen:
                continue
            if len(item) > 12:
                raise UserContentError("문자표의 각 항목은 12자 이내로 입력하세요.")
            seen.add(item)
            result.append(item)
        if not result:
            raise UserContentError("추가할 문자나 기호를 입력하세요.")
        if len(result) > 100:
            raise UserContentError("하나의 문자표 그룹에는 최대 100개까지 등록할 수 있습니다.")
        return result

    def _ensure_unique_symbol_title(self, title, exclude_id=None):
        title_key = title.casefold()
        for item in self._library["symbol_groups"]:
            if item.get("id") == exclude_id:
                continue
            if str(item.get("title", "")).casefold() == title_key:
                raise UserContentError("같은 이름의 사용자 문자표가 이미 있습니다.")

    def list_symbol_groups(self):
        return [dict(item, user_item=True) for item in self._library["symbol_groups"]]

    def add_symbol_group(self, title, values):
        title = self._clean_title(title)
        self._ensure_unique_symbol_title(title)
        item = {
            "id": self._new_id(),
            "title": title,
            "chars": self._clean_symbol_items(values),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._library["symbol_groups"].append(item)
        try:
            self._save()
        except Exception:
            self._library["symbol_groups"].remove(item)
            raise
        return dict(item)

    def update_symbol_group(self, item_id, title, values):
        target = next((item for item in self._library["symbol_groups"] if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("사용자 문자표를 찾지 못했습니다.")
        title = self._clean_title(title)
        self._ensure_unique_symbol_title(title, exclude_id=item_id)
        previous = dict(target)
        target.update({"title": title, "chars": self._clean_symbol_items(values)})
        try:
            self._save()
        except Exception:
            target.clear()
            target.update(previous)
            raise
        return dict(target)

    def delete_symbol_group(self, item_id):
        items = self._library["symbol_groups"]
        target = next((item for item in items if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("사용자 문자표를 찾지 못했습니다.")
        items.remove(target)
        try:
            self._save()
        except Exception:
            items.append(target)
            raise
        return dict(target)

    def _ensure_unique_picture_symbol_title(self, title, exclude_id=None):
        title_key = title.casefold()
        for item in self._library["picture_symbols"]:
            if item.get("id") == exclude_id:
                continue
            if str(item.get("title", "")).casefold() == title_key:
                raise UserContentError("같은 이름의 사용자 심볼이 이미 있습니다.")

    def _available_picture_symbol_title(self, title):
        base = self._clean_title(title)
        existing = {
            str(item.get("title", "")).casefold()
            for item in self._library["picture_symbols"]
        }
        if base.casefold() not in existing:
            return base
        index = 2
        while True:
            suffix = f" ({index})"
            candidate = f"{base[:40 - len(suffix)]}{suffix}"
            if candidate.casefold() not in existing:
                return candidate
            index += 1

    def list_picture_symbols(self):
        result = []
        for item in self._library["picture_symbols"]:
            current = dict(item)
            relative_path = str(current.get("file", ""))
            current["file"] = str((self.root / relative_path).resolve()) if relative_path else ""
            current["user_item"] = True
            result.append(current)
        return result

    def add_picture_symbol(self, source_path, title=None):
        source = Path(source_path)
        if not source.is_file():
            raise UserContentError("등록할 심볼 이미지 파일을 찾지 못했습니다.")
        extension = source.suffix.lower()
        if extension not in SUPPORTED_PREVIEW_EXTENSIONS:
            raise UserContentError("PNG, JPG, BMP 또는 GIF 이미지만 심볼로 등록할 수 있습니다.")

        clean_title = self._available_picture_symbol_title(title or source.stem)
        item_id = self._new_id()
        destination_dir = self.root / "picture_symbols"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{item_id}{extension}"
        shutil.copy2(source, destination)
        item = {
            "id": item_id,
            "title": clean_title,
            "file": destination.relative_to(self.root).as_posix(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            self._library["picture_symbols"].append(item)
            self._save()
        except Exception:
            self._delete_relative_file(item.get("file"))
            if item in self._library["picture_symbols"]:
                self._library["picture_symbols"].remove(item)
            raise
        return dict(item)

    def update_picture_symbol(self, item_id, title):
        target = next(
            (item for item in self._library["picture_symbols"] if item.get("id") == item_id),
            None,
        )
        if target is None:
            raise UserContentError("사용자 심볼을 찾지 못했습니다.")
        clean_title = self._clean_title(title)
        self._ensure_unique_picture_symbol_title(clean_title, exclude_id=item_id)
        previous = dict(target)
        target["title"] = clean_title
        try:
            self._save()
        except Exception:
            target.clear()
            target.update(previous)
            raise
        return dict(target)

    def delete_picture_symbol(self, item_id):
        items = self._library["picture_symbols"]
        target = next((item for item in items if item.get("id") == item_id), None)
        if target is None:
            raise UserContentError("사용자 심볼을 찾지 못했습니다.")
        items.remove(target)
        try:
            self._save()
        except Exception:
            items.append(target)
            raise
        self._delete_relative_file(target.get("file"))
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
        if kind in FILE_KINDS:
            self._delete_relative_file(target.get("file"))
            self._delete_relative_file(target.get("kedufine_file"))
            self._delete_relative_file(target.get("hwpx_file"))
            self._delete_relative_file(target.get("legacy_file"))
            self._delete_relative_file(target.get("thumb"))
        return dict(target)
