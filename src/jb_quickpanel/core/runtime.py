# -*- coding: utf-8 -*-
import importlib, io, json, os, re, shutil, sys, time


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

    dll_dir = os.path.join(vendor_root, "pywin32_system32")
    version = f"{sys.version_info.major}{sys.version_info.minor}"
    if not all(os.path.isfile(os.path.join(dll_dir, f"{name}{version}.dll"))
               for name in ("pythoncom", "pywintypes")):
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
    # 두 단어가 하나의 의미 단위인 버튼은 첫 줄에 함께 표시한다.
    grouped_prefixes = {("연한", "노랑"), ("한", "줄로")}
    if len(parts) >= 3 and tuple(parts[:2]) in grouped_prefixes:
        return " ".join(parts[:2]) + "\n" + " ".join(parts[2:])
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
        if visible and ui_score_hwp_window(w) >= 12:
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
        if visible and ui_score_hwp_window(w) >= 12:
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


def inspect_hwp_windows(hwp):
    """Return live window handles exposed by one HWP COM object."""
    state = {
        "inspected": False,
        "visible": False,
        "handles": (),
        "visible_handles": (),
        "pids": (),
    }
    try:
        windows = hwp.XHwpWindows
        count = int(windows.Count)
    except Exception:
        return state

    state["inspected"] = count == 0
    handles = []
    visible_handles = []
    pids = []
    for index in range(max(0, count)):
        try:
            window = windows.Item(index)
        except Exception:
            continue

        hwnd = 0
        try:
            hwnd = int(window.WindowHandle or 0)
            state["inspected"] = True
        except Exception:
            pass

        com_visible = False
        try:
            com_visible = bool(window.Visible)
            state["inspected"] = True
        except Exception:
            pass

        live_handle = hwnd
        os_visible = None
        if hwnd and win32gui is not None:
            try:
                if not win32gui.IsWindow(hwnd):
                    live_handle = 0
                else:
                    os_visible = bool(win32gui.IsWindowVisible(hwnd))
            except Exception:
                pass

        if live_handle:
            handles.append(live_handle)
            if win32process is not None:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(live_handle)
                    if pid:
                        pids.append(int(pid))
                except Exception:
                    pass

        is_visible = com_visible if os_visible is None else os_visible
        if is_visible:
            state["visible"] = True
            if live_handle:
                visible_handles.append(live_handle)

    state["handles"] = tuple(dict.fromkeys(handles))
    state["visible_handles"] = tuple(dict.fromkeys(visible_handles))
    state["pids"] = tuple(dict.fromkeys(pids))
    return state


def _select_running_hwp_candidate(candidates, preferred_hwnd=0, preferred_pid=0):
    """Choose the visible HWP object that owns the user's last active window."""
    if not candidates:
        return None

    visible = [item for item in candidates if item["window_state"].get("visible")]
    if visible:
        pool = visible
    else:
        uninspected = [
            item for item in candidates if not item["window_state"].get("inspected")
        ]
        if not uninspected:
            return None
        pool = uninspected

    preferred_hwnd = int(preferred_hwnd or 0)
    preferred_pid = int(preferred_pid or 0)

    def score(item):
        state = item["window_state"]
        handles = state.get("handles") or ()
        pids = state.get("pids") or ()
        return (
            int(bool(preferred_hwnd and preferred_hwnd in handles)),
            int(bool(preferred_pid and preferred_pid in pids)),
            int(bool(state.get("visible"))),
            int(item["version"]),
            int(item["index"]),
        )

    return max(pool, key=score)


def hwp_connection_matches_visible_target(hwp):
    """Check that a cached COM object still owns the HWP window the user is editing."""
    if hwp is None:
        return False
    key_indicator = getattr(hwp, "KeyIndicator", None)
    if callable(key_indicator):
        try:
            key_indicator()
        except Exception:
            return False

    ui_remember_foreground_hwp()
    target = ui_get_last_hwp_window()
    state = inspect_hwp_windows(hwp)
    if not state.get("inspected"):
        return True
    if not state.get("visible"):
        return False
    if not target:
        return True

    target_hwnd = int(target.get("hwnd") or 0)
    target_pid = int(target.get("pid") or 0)
    return bool(
        (target_hwnd and target_hwnd in (state.get("handles") or ()))
        or (target_pid and target_pid in (state.get("pids") or ()))
    )


_WIN32COM_GEN_CACHE_ERROR_MARKERS = (
    "win32com.gen_py",
    "CLSIDToPackageMap",
    "CLSIDToClassMap",
    "VTablesToClassMap",
    "VTablesToPackageMap",
)


def is_win32com_gen_cache_error(error: Exception) -> bool:
    """pywin32 makepy 캐시가 깨졌을 때 나타나는 대표 오류인지 판별한다."""
    message = f"{type(error).__name__}: {error}"
    return any(marker in message for marker in _WIN32COM_GEN_CACHE_ERROR_MARKERS)


_HWP_TYPELIB_CACHE_PREFIX = "7D2B6F3C-1D95-4E0C-BF5A-5EE564186FBC"


def repair_hwp_win32com_gen_cache(error: Exception) -> bool:
    """손상된 HWP makepy 모듈과 색인만 제거하고 pywin32 캐시를 재구성한다."""
    if win32com is None or not is_win32com_gen_cache_error(error):
        return False

    try:
        from win32com.client import gencache

        gen_root = os.path.realpath(str(win32com.__gen_path__))
        if not os.path.isdir(gen_root):
            return False

        removed = False
        for name in os.listdir(gen_root):
            if not name.upper().startswith(_HWP_TYPELIB_CACHE_PREFIX):
                continue
            target = os.path.realpath(os.path.join(gen_root, name))
            if os.path.commonpath((gen_root, target)) != gen_root:
                continue
            if os.path.isdir(target):
                shutil.rmtree(target)
            elif os.path.isfile(target):
                os.remove(target)
            removed = True

        dict_path = os.path.join(gen_root, "dicts.dat")
        if os.path.isfile(dict_path):
            os.remove(dict_path)

        module_prefix = f"win32com.gen_py.{_HWP_TYPELIB_CACHE_PREFIX}"
        for module_name in tuple(sys.modules):
            if module_name.upper().startswith(module_prefix.upper()):
                sys.modules.pop(module_name, None)

        importlib.invalidate_caches()
        gencache.Rebuild(verbose=0)
        return removed
    except Exception:
        return False


def redispatch_com_object_dynamically(dispatch):
    """이미 연결된 COM 객체를 손상된 makepy 캐시를 쓰지 않는 래퍼로 바꾼다."""
    raw_dispatch = getattr(dispatch, "__dict__", {}).get("_oleobj_", dispatch)
    return win32com.client.dynamic.Dispatch(raw_dispatch)


def dispatch_com_object_safely(dispatch):
    """생성 캐시가 손상된 경우 makepy를 쓰지 않는 동적 COM으로 자동 우회한다."""
    try:
        return win32com.client.Dispatch(dispatch), False
    except Exception as error:
        if not is_win32com_gen_cache_error(error):
            raise
        repair_hwp_win32com_gen_cache(error)
        try:
            return redispatch_com_object_dynamically(dispatch), True
        except Exception as fallback_error:
            raise RuntimeError(
                f"pywin32 COM 캐시 손상 자동 우회 실패: {fallback_error}"
            ) from error


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
                hwp, used_dynamic_dispatch = dispatch_com_object_safely(disp)
                version = int(m.group(1))
                index = int(m.group(2))
                found.append(
                    {
                        "version": version,
                        "index": index,
                        "name": name,
                        "hwp": hwp,
                        "used_dynamic_dispatch": used_dynamic_dispatch,
                        "window_state": inspect_hwp_windows(hwp),
                    }
                )
            except Exception as e:
                errors.append(f"{name}: {e}")
    except Exception as e:
        return False, None, f"ROT 조회 실패: {e}"

    if not found:
        detail = "\n".join(errors) if errors else "ROT에서 !HwpObject.* 형식의 실행 중 한글 객체를 찾지 못했습니다."
        return False, None, detail

    ui_remember_foreground_hwp()
    target = ui_get_last_hwp_window() or {}
    selected = _select_running_hwp_candidate(
        found,
        preferred_hwnd=target.get("hwnd"),
        preferred_pid=target.get("pid"),
    )
    if selected is None:
        return (
            False,
            None,
            "화면에 표시된 한글 문서를 찾지 못했습니다. 숨겨진 한글 프로세스에는 작업하지 않습니다.",
        )

    cache_note = " (COM 캐시 자동 우회)" if selected["used_dynamic_dispatch"] else ""
    target_note = f" / 대상: {target.get('title', '')}" if target.get("title") else ""
    return (
        True,
        selected["hwp"],
        f"실행 중 한글 연결 완료: {selected['name']}{target_note}{cache_note}",
    )


# ---------------------------------------------------------------------------
# 보고서 태그 규칙 (서식 자동 지정하기)
# v2.1까지는 단일 파일 app.py 안에 있었으나, v2.2 모듈 분리 과정에서
# wxs_bridge.py 로 잘못 옮겨지고 TABLE_END_TAG 는 누락되어
# features/auto_format.py 에서 NameError 가 발생했다.
# auto_format 이 import 하는 이 모듈이 올바른 위치이므로 여기에 둔다.
# ---------------------------------------------------------------------------
REPORT_TAG_RULES = {
    "문서제목": {"font": "HY헤드라인M", "size": 23, "bold": True,  "indent": 0},
    "제목":     {"font": "HY헤드라인M", "size": 16, "bold": False, "indent": 0},
    "소제목":   {"font": "휴먼명조",   "size": 14, "bold": True,  "indent": 2},
    "소소제목": {"font": "휴먼명조",   "size": 13, "bold": True,  "indent": 4},
    "본문":     {"font": "휴먼명조",   "size": 13, "bold": False},
    "참고":     {"font": "맑은 고딕", "size": 11, "bold": False},
}
TAG_ORDER = ["문서제목", "제목", "소제목", "소소제목", "본문", "참고"]
TABLE_START_TAG = "표시작"
TABLE_END_TAG = "표끝"
