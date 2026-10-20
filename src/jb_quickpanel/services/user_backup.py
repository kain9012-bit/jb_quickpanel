# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from src.jb_quickpanel.services import app_config


BACKUP_APP_ID = "JBEDT-0006"
BACKUP_FORMAT_VERSION = 1
BACKUP_EXTENSION = ".jbhbackup"
MAX_BACKUP_FILES = 2000
MAX_BACKUP_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
USER_LIBRARY_KEYS = (
    "styles",
    "forms",
    "kedufine_forms",
    "pages",
    "auto_title_templates",
    "symbol_groups",
    "picture_symbols",
)
EMPTY_LIBRARY = {
    "version": 5,
    "styles": [],
    "forms": [],
    "kedufine_forms": [],
    "pages": [],
    "auto_title_templates": [],
    "symbol_groups": [],
    "picture_symbols": [],
}


class UserBackupError(ValueError):
    pass


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _safe_member_name(name: str) -> PurePosixPath:
    normalized = str(name or "").replace(chr(92), "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise UserBackupError("백업 파일에 안전하지 않은 경로가 포함되어 있습니다.")
    return path


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _validated_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as error:
        raise UserBackupError(f"{label} 정보를 읽지 못했습니다.") from error
    if not isinstance(value, dict):
        raise UserBackupError(f"{label} 정보 형식이 올바르지 않습니다.")
    return value


def _normalized_settings(raw: dict[str, Any]) -> dict[str, Any]:
    settings = app_config._merged_settings(raw)
    settings["last_geometry"] = ""
    settings["start_menu_auto_done"] = False
    settings["start_menu_signature"] = ""
    return settings


def _validated_library(raw: dict[str, Any], members: set[str]) -> dict[str, Any]:
    library = deepcopy(EMPTY_LIBRARY)
    try:
        library["version"] = int(raw.get("version") or EMPTY_LIBRARY["version"])
    except Exception:
        library["version"] = EMPTY_LIBRARY["version"]
    for key in USER_LIBRARY_KEYS:
        values = raw.get(key, [])
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise UserBackupError("사용자 자료 목록 형식이 올바르지 않습니다.")
        library[key] = values

    for key in USER_LIBRARY_KEYS:
        for item in library[key]:
            for field in ("file", "kedufine_file", "hwpx_file", "legacy_file", "thumb"):
                relative = str(item.get(field) or "").strip()
                if not relative:
                    continue
                member = _safe_member_name(f"user_content/{relative}").as_posix()
                if field != "thumb" and member not in members:
                    raise UserBackupError("백업 파일에서 사용자 자료 원본을 찾지 못했습니다.")
    return library


def _iter_user_files(user_root: Path):
    if not user_root.is_dir():
        return
    for path in sorted(user_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(user_root)
        if relative.parts and relative.parts[0].casefold() == "pending":
            continue
        name = path.name.casefold()
        if name.endswith(".tmp") or ".broken_" in name:
            continue
        yield path, relative


def create_user_backup(
    destination: str | os.PathLike[str],
    *,
    app_root: str | os.PathLike[str] | None = None,
    app_version: str = "",
    integration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(app_root) if app_root is not None else app_config.app_data_dir()
    target = Path(destination)
    if target.suffix.casefold() != BACKUP_EXTENSION:
        target = target.with_suffix(BACKUP_EXTENSION)
    target.parent.mkdir(parents=True, exist_ok=True)

    settings_path = root / "settings.json"
    if settings_path.is_file():
        settings = _validated_json(settings_path.read_bytes(), "설정")
    else:
        settings = deepcopy(app_config.DEFAULT_SETTINGS)

    user_root = root / "user_content"
    library_path = user_root / "library.json"
    if library_path.is_file():
        library = _validated_json(library_path.read_bytes(), "사용자 자료")
    else:
        library = deepcopy(EMPTY_LIBRARY)

    manifest = {
        "app_id": BACKUP_APP_ID,
        "format_version": BACKUP_FORMAT_VERSION,
        "app_version": str(app_version or ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "integration": {
            "startup": bool((integration or {}).get("startup", False)),
            "start_menu": bool((integration or {}).get("start_menu", True)),
        },
    }

    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    file_count = 0
    manifest_bytes = _json_bytes(manifest)
    settings_bytes = _json_bytes(settings)
    library_bytes = _json_bytes(library)
    total_bytes = sum(map(len, (manifest_bytes, settings_bytes, library_bytes)))
    if total_bytes > MAX_BACKUP_UNCOMPRESSED_BYTES:
        raise UserBackupError("사용자 자료 크기가 백업 한도를 초과했습니다.")
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", manifest_bytes)
            archive.writestr("settings.json", settings_bytes)
            archive.writestr("user_content/library.json", library_bytes)
            excluded = {target.resolve(), temp.resolve()}
            for source, relative in _iter_user_files(user_root) or ():
                if relative.as_posix() == "library.json" or source.resolve() in excluded:
                    continue
                if source.suffix.casefold() == BACKUP_EXTENSION:
                    continue
                total_bytes += source.stat().st_size
                if total_bytes > MAX_BACKUP_UNCOMPRESSED_BYTES:
                    raise UserBackupError("사용자 자료 크기가 백업 한도를 초과했습니다.")
                archive.write(source, f"user_content/{relative.as_posix()}")
                file_count += 1
                if file_count > MAX_BACKUP_FILES:
                    raise UserBackupError("사용자 자료 파일이 너무 많아 백업을 만들 수 없습니다.")
            if sum(info.file_size for info in archive.infolist()) > MAX_BACKUP_UNCOMPRESSED_BYTES:
                raise UserBackupError("사용자 자료 크기가 백업 한도를 초과했습니다.")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)

    return {
        "path": str(target.resolve()),
        "file_count": file_count,
        "size": target.stat().st_size,
        "created_at": manifest["created_at"],
    }


def _read_backup(
    source: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[tuple[zipfile.ZipInfo, PurePosixPath]]]:
    if not source.is_file():
        raise UserBackupError("선택한 백업 파일을 찾지 못했습니다.")
    try:
        archive = zipfile.ZipFile(source, "r")
    except (OSError, zipfile.BadZipFile) as error:
        raise UserBackupError("올바른 서식도우미 백업 파일이 아닙니다.") from error

    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_BACKUP_FILES + 3:
            raise UserBackupError("백업 파일에 포함된 파일 수가 너무 많습니다.")
        if sum(max(0, info.file_size) for info in infos) > MAX_BACKUP_UNCOMPRESSED_BYTES:
            raise UserBackupError("백업 파일의 압축 해제 크기가 너무 큽니다.")

        validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        member_names: set[str] = set()
        for info in infos:
            if _is_symlink(info):
                raise UserBackupError("백업 파일에 지원하지 않는 링크가 포함되어 있습니다.")
            member = _safe_member_name(info.filename)
            name = member.as_posix()
            if name in member_names:
                raise UserBackupError("백업 파일에 중복된 항목이 있습니다.")
            if name not in {"manifest.json", "settings.json"} and not name.startswith(
                "user_content/"
            ):
                raise UserBackupError("백업 파일에 지원하지 않는 항목이 포함되어 있습니다.")
            member_names.add(name)
            validated.append((info, member))

        required = {"manifest.json", "settings.json", "user_content/library.json"}
        if not required.issubset(member_names):
            raise UserBackupError("백업 파일에 필수 설정 또는 사용자 자료가 없습니다.")

        manifest = _validated_json(archive.read("manifest.json"), "백업")
        if str(manifest.get("app_id") or "") != BACKUP_APP_ID:
            raise UserBackupError("다른 프로그램에서 만든 백업 파일입니다.")
        try:
            format_version = int(manifest.get("format_version") or 0)
        except Exception as error:
            raise UserBackupError("백업 파일 버전을 확인하지 못했습니다.") from error
        if format_version < 1 or format_version > BACKUP_FORMAT_VERSION:
            raise UserBackupError("현재 프로그램에서 지원하지 않는 백업 파일 버전입니다.")

        settings = _normalized_settings(
            _validated_json(archive.read("settings.json"), "설정")
        )
        library = _validated_library(
            _validated_json(
                archive.read("user_content/library.json"), "사용자 자료"
            ),
            member_names,
        )
        return manifest, settings, library, validated


def _extract_validated_backup(
    source: Path,
    staging: Path,
    validated: list[tuple[zipfile.ZipInfo, PurePosixPath]],
    settings: dict[str, Any],
    library: dict[str, Any],
) -> None:
    with zipfile.ZipFile(source, "r") as archive:
        for info, member in validated:
            name = member.as_posix()
            if name in {"manifest.json", "settings.json", "user_content/library.json"}:
                continue
            destination = staging.joinpath(*member.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source_file, destination.open("wb") as output:
                shutil.copyfileobj(source_file, output)

    (staging / "user_content").mkdir(parents=True, exist_ok=True)
    (staging / "settings.json").write_bytes(_json_bytes(settings))
    (staging / "user_content" / "library.json").write_bytes(_json_bytes(library))


def _trim_recovery_backups(folder: Path, keep: int = 3) -> None:
    backups = sorted(
        folder.glob(f"*{BACKUP_EXTENSION}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in backups[keep:]:
        path.unlink(missing_ok=True)


def restore_user_backup(
    source: str | os.PathLike[str],
    *,
    app_root: str | os.PathLike[str] | None = None,
    app_version: str = "",
    integration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(app_root) if app_root is not None else app_config.app_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    source_path = Path(source)
    manifest, settings, library, validated = _read_backup(source_path)

    recovery_dir = root / "backup_history"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    recovery_path = recovery_dir / f"복원전_자동백업_{stamp}{BACKUP_EXTENSION}"
    create_user_backup(
        recovery_path,
        app_root=root,
        app_version=app_version,
        integration=integration,
    )
    _trim_recovery_backups(recovery_dir)

    staging = Path(tempfile.mkdtemp(prefix=".restore_staging_", dir=root))
    current_user = root / "user_content"
    previous_user = root / f".user_content_before_restore_{uuid.uuid4().hex}"
    settings_path = root / "settings.json"
    previous_settings = settings_path.read_bytes() if settings_path.is_file() else None
    moved_previous_user = False
    installed_new_user = False

    try:
        _extract_validated_backup(source_path, staging, validated, settings, library)
        if current_user.exists():
            os.replace(current_user, previous_user)
            moved_previous_user = True
        os.replace(staging / "user_content", current_user)
        installed_new_user = True

        settings_temp = root / f".settings_restore_{uuid.uuid4().hex}.tmp"
        try:
            settings_temp.write_bytes((staging / "settings.json").read_bytes())
            os.replace(settings_temp, settings_path)
        finally:
            settings_temp.unlink(missing_ok=True)
    except Exception:
        if installed_new_user and current_user.exists():
            shutil.rmtree(current_user, ignore_errors=True)
        if moved_previous_user and previous_user.exists():
            os.replace(previous_user, current_user)
        if previous_settings is None:
            settings_path.unlink(missing_ok=True)
        else:
            rollback = root / f".settings_rollback_{uuid.uuid4().hex}.tmp"
            rollback.write_bytes(previous_settings)
            os.replace(rollback, settings_path)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if previous_user.exists():
        shutil.rmtree(previous_user, ignore_errors=True)

    return {
        "source_path": str(source_path.resolve()),
        "recovery_path": str(recovery_path.resolve()),
        "backup_version": str(manifest.get("app_version") or ""),
        "created_at": str(manifest.get("created_at") or ""),
        "integration": dict(manifest.get("integration") or {}),
    }
