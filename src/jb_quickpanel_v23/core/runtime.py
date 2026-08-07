# -*- coding: utf-8 -*-
import os, json, io, sys, time, re


def _early_project_base_dir() -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    cur = here
    for _ in range(8):
        if os.path.isdir(os.path.join(cur, "config")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.getcwd()


def _add_vendor_pywin32_paths():
    if getattr(sys, "frozen", False):
        return

    vendor_root = os.path.join(_early_project_base_dir(), "vendor", "pywin32")
    if not os.path.isdir(vendor_root):
        return

    pywin32_paths = [
        vendor_root,
        os.path.join(vendor_root, "win32"),
        os.path.join(vendor_root, "win32", "lib"),
        os.path.join(vendor_root, "pywin32_system32"),
    ]
    for path in reversed(pywin32_paths):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    dll_dir = os.path.join(vendor_root, "pywin32_system32")
    if os.path.isdir(dll_dir):
        try:
            os.add_dll_directory(dll_dir)
        except Exception:
            pass
        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")


_add_vendor_pywin32_paths()

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
try:
    import pythoncom
    import win32com.client
    import win32clipboard
except Exception:
    pythoncom = None
    win32com = None
    win32clipboard = None

try:
    import win32gui
    import win32process
    import win32con
    import win32api
except Exception:
    win32gui = None
    win32process = None
    win32con = None
    win32api = None
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None
WHITE = "#ffffff"
RPC_ERR_HINT = "RPC 서버를 사용할 수 없습니다"


def _project_base_dir() -> str:
    """개발 실행 시 실제 프로젝트 루트를 찾는다."""
    return _early_project_base_dir()


def resource_base_dir() -> str:
    return getattr(sys, "_MEIPASS", _project_base_dir())


def resource_path(rel_path: str) -> str:
    return os.path.abspath(os.path.join(resource_base_dir(), rel_path))
CFG_PATH = resource_path(os.path.join("config", "config.json"))
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default
def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
def get_clipboard_text() -> str:
    if win32clipboard is None:
        return ""
    text = ""
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    except Exception:
        text = ""
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
    return text or ""
def set_clipboard_text(text: str):
    if win32clipboard is None:
        return
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text or "")
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
def is_rpc_error(e: Exception) -> bool:
    s = str(e)
    return ("-2147023174" in s) or (RPC_ERR_HINT in s)
def is_image_file(fn: str) -> bool:
    fn = fn.lower()
    return fn.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp"))
def bind_click_recursive(widget: tk.Widget, handler):
    try:
        widget.bind("<Button-1>", lambda _e: handler())
    except Exception:
        pass
    for child in widget.winfo_children():
        bind_click_recursive(child, handler)
def force_two_lines(s: str) -> str:
    s = (s or "").strip()
    if "\n" in s:
        return s
    parts = s.split()
    if len(parts) <= 1:
        return s
    # 예외: "연한 노랑 ..."은 "연한 노랑"을 첫 줄로 묶기
    if len(parts) >= 3 and parts[0] == "연한" and parts[1] == "노랑":
        return "연한 노랑\n" + " ".join(parts[2:])
    return parts[0] + "\n" + " ".join(parts[1:])

# -----------------------------------------------------------------------------
# 실행 중 한글 COM 객체 연결 보조 함수
# -----------------------------------------------------------------------------
# 일반적인 GetActiveObject("HWPFrame.HwpObject")가 실패하는 환경이 있어,
# ROT(Running Object Table)에 등록된 !HwpObject.버전.번호 객체를 직접 찾는다.
# 이 방식은 Dispatch("HWPFrame.HwpObject")처럼 새 한글 인스턴스를 만들지 않는다.
HWP_ROT_RE = re.compile(r"^!HwpObject\.(\d+)\.(\d+)$", re.IGNORECASE)
CELL_CLIPBOARD_SENTINEL = "__JBE_HWP_CELL_CLEANER_SENTINEL__"
# 선택 셀 공백 정리 대상: 일반 공백, 탭, NBSP, 전각 공백, zero-width space, BOM
CELL_SPACE_CHARS = " \t\u00A0\u3000\u200B\ufeff"
CELL_SPACE_RE = re.compile(rf"[{re.escape(CELL_SPACE_CHARS)}]+")
CELL_ADDR_RE = re.compile(r"\b([A-Z]{1,4})([0-9]{1,5})\b", re.IGNORECASE)
LAST_HWP_HWND = None
LAST_HWP_TITLE = ""


def ui_get_process_path(pid: int) -> str:
    if win32api is None or win32process is None or win32con is None:
        return ""
    try:
        access = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
        hproc = win32api.OpenProcess(access, False, pid)
        try:
            return win32process.GetModuleFileNameEx(hproc, 0)
        finally:
            try:
                win32api.CloseHandle(hproc)
            except Exception:
                pass
    except Exception:
        return ""


def ui_score_hwp_window(w) -> int:
    score = 0
    exe = (w.get("exe") or "").lower().replace("/", "\\")
    title = (w.get("title") or "")
    cls = (w.get("class") or "")
    if exe.endswith("\\hwp.exe"):
        score += 10
    if w.get("visible"):
        score += 5
    if title:
        score += 2
    if "- 한글" in title:
        score += 5
    if ".hwp" in title.lower() or ".hwpx" in title.lower():
        score += 4
    if "빈 문서" in title or "제목 없음" in title or "새 문서" in title:
        score += 2
    if "hwp" in cls.lower():
        score += 2
    if w.get("parent", 0) == 0:
        score += 1
    return score


def ui_remember_foreground_hwp():
    """사용자가 마지막으로 클릭한 한글 창을 기억한다."""
    global LAST_HWP_HWND, LAST_HWP_TITLE
    if win32gui is None or win32process is None:
        return
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        visible = bool(win32gui.IsWindowVisible(hwnd))
        parent = win32gui.GetParent(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = ui_get_process_path(pid)
        w = {
            "hwnd": hwnd,
            "pid": pid,
            "title": title,
            "class": cls,
            "visible": visible,
            "parent": parent,
            "exe": exe,
        }
        if ui_score_hwp_window(w) >= 12:
            LAST_HWP_HWND = hwnd
            LAST_HWP_TITLE = title
    except Exception:
        pass


def ui_get_last_hwp_window():
    global LAST_HWP_HWND
    if win32gui is None or win32process is None or not LAST_HWP_HWND:
        return None
    try:
        if not win32gui.IsWindow(LAST_HWP_HWND):
            LAST_HWP_HWND = None
            return None
        title = win32gui.GetWindowText(LAST_HWP_HWND)
        cls = win32gui.GetClassName(LAST_HWP_HWND)
        visible = bool(win32gui.IsWindowVisible(LAST_HWP_HWND))
        parent = win32gui.GetParent(LAST_HWP_HWND)
        _, pid = win32process.GetWindowThreadProcessId(LAST_HWP_HWND)
        exe = ui_get_process_path(pid)
        w = {
            "hwnd": LAST_HWP_HWND,
            "pid": pid,
            "title": title,
            "class": cls,
            "visible": visible,
            "parent": parent,
            "exe": exe,
        }
        if ui_score_hwp_window(w) >= 12:
            return w
    except Exception:
        return None
    return None


def ui_bring_to_front(hwnd: int):
    if win32gui is None or win32con is None:
        return False, "win32gui를 사용할 수 없습니다."
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.05)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        time.sleep(0.02)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.06)
        return True, "OK"
    except Exception as e:
        return False, f"한글 창 활성화 실패: {e}"


def bring_last_hwp_to_front_if_any():
    target = ui_get_last_hwp_window()
    if not target:
        return True, "SKIP"
    ok, msg = ui_bring_to_front(target["hwnd"])
    if not ok:
        # 창 활성화 실패가 COM 연결 자체를 반드시 막는 것은 아니므로 경고만 반환 가능하게 둔다.
        return True, msg
    return True, f"대상 한글창: {target.get('title', '')}"


def get_running_hwp_from_rot():
    """
    ROT에서 이미 실행 중인 한글 COM 객체(!HwpObject.x.y)를 직접 찾는다.
    새 한글 인스턴스를 만들 수 있는 Dispatch("HWPFrame.HwpObject")는 사용하지 않는다.
    """
    if pythoncom is None or win32com is None:
        return False, None, "pywin32 미설치: python -m pip install pywin32"

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    found = []
    errors = []
    try:
        rot = pythoncom.GetRunningObjectTable()
        enum = rot.EnumRunning()
        bind_ctx = pythoncom.CreateBindCtx(0)

        while True:
            monikers = enum.Next(1)
            if not monikers:
                break

            moniker = monikers[0]
            try:
                name = moniker.GetDisplayName(bind_ctx, None)
            except Exception:
                continue

            m = HWP_ROT_RE.match(str(name).strip())
            if not m:
                continue

            try:
                obj = rot.GetObject(moniker)
                try:
                    disp = obj.QueryInterface(pythoncom.IID_IDispatch)
                except Exception:
                    disp = obj
                hwp = win32com.client.Dispatch(disp)
                version = int(m.group(1))
                index = int(m.group(2))
                found.append((version, index, name, hwp))
            except Exception as e:
                errors.append(f"{name}: {e}")
    except Exception as e:
        return False, None, f"ROT 조회 실패: {e}"

    if not found:
        detail = "\n".join(errors) if errors else "ROT에서 !HwpObject.* 형식의 실행 중 한글 객체를 찾지 못했습니다."
        return False, None, detail

    # 같은 PC에 여러 한글 버전/인스턴스가 있을 수 있어 최신 버전, 높은 인스턴스 번호를 우선한다.
    # 대상 창은 작업 직전 bring_last_hwp_to_front_if_any()로 활성화한다.
    found.sort(key=lambda x: (x[0], x[1]), reverse=True)
    version, index, name, hwp = found[0]
    return True, hwp, f"실행 중 한글 연결 완료: {name}"
