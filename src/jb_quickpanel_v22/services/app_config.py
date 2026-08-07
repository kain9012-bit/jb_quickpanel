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
SETTINGS_VERSION = 2

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
    "start_menu_auto_done": False,
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
SHORTCUT_NAME = "전북교육 한글 서식도우미.lnk"


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


def start_menu_shortcut_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / SHORTCUT_NAME


def is_start_menu_registered() -> bool:
    if os.name != "nt":
        return False
    return start_menu_shortcut_path().exists()


def set_start_menu_registered(enabled: bool) -> None:
    if os.name != "nt":
        return
    path = start_menu_shortcut_path()
    if not enabled:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    import win32com.client
    target, args, workdir = launch_parts()
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(path))
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = workdir
    shortcut.Description = "전북교육 한글 서식도우미"
    shortcut.IconLocation = launch_icon_path()
    shortcut.Save()