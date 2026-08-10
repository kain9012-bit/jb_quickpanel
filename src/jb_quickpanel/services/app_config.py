# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


APP_DIR_NAME = "JbHwpHelper"
SETTINGS_VERSION = 5

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": SETTINGS_VERSION,
    "start_mode": "hwp",
    "start_position": "top_right",
    "remember_window_position": False,
    "last_geometry": "",
    "close_to_tray": False,
    "start_minimized": False,
    "tutorial_completed": False,
    "check_updates_on_startup": True,
    "toggle_hotkey": "Ctrl+Alt+H",
    "global_hotkeys_enabled": True,
    "global_hotkeys": {},
    "start_menu_auto_done": False,
    "start_menu_signature": "",
}


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def crash_log_path() -> Path:
    return app_data_dir() / "crash.log"


def _merged_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)
    settings["version"] = SETTINGS_VERSION
    return settings


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with path.open("r", encoding="utf-8") as file:
            return _merged_settings(json.load(file))
    except Exception:
        try:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = path.with_name(f"settings.broken_{stamp}.json")
            path.replace(backup)
        except Exception:
            pass
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    try:
        with temp.open("w", encoding="utf-8") as file:
            json.dump(_merged_settings(settings), file, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except Exception:
            pass


def log_crash(exc_type, exc_value, exc_traceback) -> Path:
    path = crash_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write("\n" + "=" * 80 + "\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=file)
    return path


def install_excepthook(on_crash: Callable[[Path, BaseException], None] | None = None) -> None:
    def _hook(exc_type, exc_value, exc_traceback):
        path = log_crash(exc_type, exc_value, exc_traceback)
        if on_crash is not None:
            try:
                on_crash(path, exc_value)
            except Exception:
                pass
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = _hook


def open_path(path: str | os.PathLike[str]) -> None:
    target = str(path)
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


RUN_VALUE_NAME = "JbHwpHelper"
APP_TITLE = "전북교육 한글 서식도우미"
LEGACY_SHORTCUT_NAME = f"{APP_TITLE}.lnk"


def _quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def launch_parts() -> tuple[str, str, str]:
    if getattr(sys, "frozen", False):
        target = str(Path(sys.executable).resolve())
        args = ""
        workdir = str(Path(target).parent)
    else:
        launcher = Path(sys.executable).resolve()
        pythonw = launcher.with_name("pythonw.exe")
        if pythonw.exists():
            launcher = pythonw
        target = str(launcher)
        script = str(Path(sys.argv[0]).resolve())
        args = _quote(script)
        workdir = str(Path(script).parent)
    return target, args, workdir


def launch_icon_path() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    script_dir = Path(sys.argv[0]).resolve().parent
    icon = script_dir / "assets" / "icons" / "app_icon.ico"
    return str(icon if icon.exists() else Path(sys.executable).resolve())


def launch_command(start_minimized: bool = False) -> str:
    target, args, _workdir = launch_parts()
    parts = [_quote(target)]
    if args:
        parts.append(args)
    if start_minimized:
        parts.append("--tray")
    return " ".join(parts)


def is_windows_startup_enabled() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE_NAME)
        return bool(value)
    except (FileNotFoundError, OSError):
        return False


def set_windows_startup_enabled(enabled: bool, start_minimized: bool = False) -> None:
    if os.name != "nt":
        return
    import winreg
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                RUN_VALUE_NAME,
                0,
                winreg.REG_SZ,
                launch_command(start_minimized=start_minimized),
            )
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass


def _start_menu_folder() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def start_menu_shortcut_name(app_version: str) -> str:
    version = str(app_version or "").strip()
    return f"{APP_TITLE} ({version}).lnk" if version else LEGACY_SHORTCUT_NAME


def start_menu_shortcut_path(app_version: str) -> Path:
    return _start_menu_folder() / start_menu_shortcut_name(app_version)


def _is_own_shortcut_name(name: str) -> bool:
    value = str(name or "").casefold()
    if value == LEGACY_SHORTCUT_NAME.casefold():
        return True
    prefix = f"{APP_TITLE} (v".casefold()
    return value.startswith(prefix) and value.endswith(").lnk")


def start_menu_shortcut_paths() -> list[Path]:
    folder = _start_menu_folder()
    return sorted(
        (path for path in folder.glob("*.lnk") if _is_own_shortcut_name(path.name)),
        key=lambda path: path.name.casefold(),
    )


def has_any_start_menu_shortcut() -> bool:
    if os.name != "nt":
        return False
    return bool(start_menu_shortcut_paths())


def has_obsolete_start_menu_shortcuts(app_version: str) -> bool:
    if os.name != "nt":
        return False
    desired = start_menu_shortcut_path(app_version)
    return any(path != desired for path in start_menu_shortcut_paths())


def is_start_menu_registered(app_version: str) -> bool:
    if os.name != "nt":
        return False
    return start_menu_shortcut_path(app_version).exists()


def start_menu_signature(app_version: str) -> str:
    target, args, workdir = launch_parts()
    return "|".join((str(Path(target).resolve()), args, str(Path(workdir).resolve()), str(app_version or "")))


def _remove_start_menu_shortcuts(keep: Path | None = None) -> None:
    keep_resolved = keep.resolve() if keep is not None else None
    for path in start_menu_shortcut_paths():
        try:
            if keep_resolved is not None and path.resolve() == keep_resolved:
                continue
            path.unlink()
        except FileNotFoundError:
            pass


def set_start_menu_registered(enabled: bool, app_version: str) -> None:
    if os.name != "nt":
        return
    if not enabled:
        _remove_start_menu_shortcuts()
        return

    import win32com.client

    path = start_menu_shortcut_path(app_version)
    target, args, workdir = launch_parts()
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(path))
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = workdir
    shortcut.Description = f"{APP_TITLE} {app_version}".strip()
    shortcut.IconLocation = launch_icon_path()
    shortcut.Save()

    # 새 바로가기를 정상적으로 만든 뒤에만 같은 앱의 구버전 항목을 지운다.
    _remove_start_menu_shortcuts(keep=path)
