# -*- coding: utf-8 -*-
import ctypes
import queue
import sys
import threading
import webbrowser
from tkinter import filedialog

from src.jb_quickpanel.core.runtime import *
from src.jb_quickpanel.core.single_instance import (
    acquire_single_instance,
    activate_existing_window,
    notify_already_running,
)
from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge
from src.jb_quickpanel.features.cell_text import *
from src.jb_quickpanel.features.cell_images import (
    IMAGE_SIZE_FIT_INSIDE,
    IMAGE_SIZE_FIT_WIDTH,
    IMAGE_SIZE_STRETCH_TO_CELL,
    sort_image_paths,
)
from src.jb_quickpanel.features.auto_format import *
from src.jb_quickpanel.features.document_preview import create_document_preview
from src.jb_quickpanel.features import registry as feature_registry
from src.jb_quickpanel.features.global_hotkeys import (
    DIRECT_HOTKEY_FEATURE_ACTIONS,
    WindowsGlobalHotkeyRegistry,
    build_hotkey_actions,
    normalize_bindings,
)
from src.jb_quickpanel.services import app_config, update_checker
from src.jb_quickpanel.ui.hotkey_dialog import HotkeySettingsDialog
from src.jb_quickpanel.services.user_content import (
    DEFAULT_PAGE_MARGINS,
    PAGE_MARGIN_FIELDS,
    UserContentError,
    UserContentStore,
)

APP_TITLE = app_config.APP_TITLE
APP_VERSION = "v3.4"
APP_BG = "#f3f5f7"
SURFACE = "#ffffff"
SURFACE_ALT = "#f8fafc"
TEXT_PRIMARY = "#20262e"
TEXT_MUTED = "#667085"
BORDER = "#d5dae1"
BORDER_STRONG = "#b8c0cc"
ACCENT = "#2257a6"
ACCENT_HOVER = "#194987"
ACCENT_SOFT = "#eaf1fb"
DANGER = "#b42318"
DANGER_HOVER = "#8f1d14"
DANGER_SOFT = "#fff0ee"
SUCCESS = "#237a57"
APP_ICON_FILENAME = os.path.join("assets", "icons", "app_icon.ico")
APP_USER_MODEL_ID = "JeonbukEducation.HwpStyleHelper"

def get_app_icon_path():
    icon_path = resource_path(APP_ICON_FILENAME)
    return icon_path if os.path.exists(icon_path) else None

def set_windows_app_user_model_id():
    # Frozen builds already carry the application icon in the executable.
    if os.name != "nt" or getattr(sys, "frozen", False):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

def close_splash():
    """Close the PyInstaller splash when running from a bundled executable."""
    try:
        import pyi_splash  # type: ignore

        pyi_splash.close()
    except Exception:
        pass

def _reduce_vertical_transparent_margins(image, margin_ratio=0.5):
    """Keep only the requested share of transparent space above and below an icon."""
    try:
        alpha_bbox = image.getchannel("A").getbbox()
    except Exception:
        return image
    if alpha_bbox is None:
        return image

    margin_ratio = max(0.0, min(1.0, float(margin_ratio)))
    top_margin = alpha_bbox[1]
    bottom_margin = image.height - alpha_bbox[3]
    keep_top = int(round(top_margin * margin_ratio))
    keep_bottom = int(round(bottom_margin * margin_ratio))
    crop_top = top_margin - keep_top
    crop_bottom = alpha_bbox[3] + keep_bottom
    return image.crop((0, crop_top, image.width, crop_bottom))

class NativeTrayIcon:
    RESTORE_ID = 1001
    EXIT_ID = 1002

    def __init__(self, app):
        if win32gui is None or win32con is None or win32api is None:
            raise RuntimeError("pywin32 tray API를 사용할 수 없습니다.")
        self.app = app
        self.hwnd = None
        self.nid = None
        self.class_name = f"JbHwpHelperTray{os.getpid()}_{id(self)}"
        self.wm_tray = win32con.WM_USER + 20
        self.hotkeys = WindowsGlobalHotkeyRegistry()
        self.pending_hotkeys = queue.SimpleQueue()

    def ensure_window(self):
        if self.hwnd:
            return
        hinst = win32api.GetModuleHandle(None)
        wndclass = win32gui.WNDCLASS()
        wndclass.hInstance = hinst
        wndclass.lpszClassName = self.class_name
        wndclass.lpfnWndProc = self._wnd_proc
        try:
            win32gui.RegisterClass(wndclass)
        except Exception:
            pass
        self.hwnd = win32gui.CreateWindow(
            self.class_name,
            self.class_name,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            hinst,
            None,
        )

    def show(self):
        self.ensure_window()
        if self.nid is not None:
            return
        hinst = win32api.GetModuleHandle(None)
        icon_path = get_app_icon_path()
        if icon_path:
            icon = win32gui.LoadImage(hinst, icon_path, win32con.IMAGE_ICON, 0, 0, win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        else:
            icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        self.nid = (self.hwnd, 0, flags, self.wm_tray, icon, f"{APP_TITLE} {APP_VERSION}")
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, self.nid)

    def register_hotkeys(self, bindings):
        self.ensure_window()
        return self.hotkeys.replace(self.hwnd, bindings)

    def unregister_hotkeys(self):
        self.hotkeys.clear(self.hwnd)

    def take_pending_hotkey(self):
        try:
            return self.pending_hotkeys.get_nowait()
        except queue.Empty:
            return None

    def destroy(self):
        self.unregister_hotkeys()
        if self.nid is not None:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, self.nid)
            except Exception:
                pass
            self.nid = None
        if self.hwnd:
            try:
                win32gui.DestroyWindow(self.hwnd)
            except Exception:
                pass
            self.hwnd = None

    def _show_menu(self):
        menu = win32gui.CreatePopupMenu()
        try:
            win32gui.AppendMenu(menu, win32con.MF_STRING, self.RESTORE_ID, "열기")
            win32gui.AppendMenu(menu, win32con.MF_STRING, self.EXIT_ID, "종료")
            x, y = win32gui.GetCursorPos()
            win32gui.SetForegroundWindow(self.hwnd)
            win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, x, y, 0, self.hwnd, None)
            win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        finally:
            try:
                win32gui.DestroyMenu(menu)
            except Exception:
                pass

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == getattr(win32con, "WM_HOTKEY", 0x0312):
            action_id = self.hotkeys.action_for_message_id(int(wparam))
            if action_id:
                self.pending_hotkeys.put(action_id)
            return 0
        if msg == self.wm_tray:
            if lparam in (win32con.WM_LBUTTONUP, win32con.WM_LBUTTONDBLCLK):
                self.app.restore_from_tray()
            elif lparam == win32con.WM_RBUTTONUP:
                self._show_menu()
            return 0
        if msg == win32con.WM_COMMAND:
            cmd = int(wparam) & 0xFFFF
            if cmd == self.RESTORE_ID:
                self.app.restore_from_tray()
            elif cmd == self.EXIT_ID:
                self.app.exit_from_tray()
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

class App(tk.Tk):
    def __init__(self):
        set_windows_app_user_model_id()
        super().__init__()
        self.withdraw()
        app_config.install_excepthook()
        self.app_settings = app_config.load_settings()
        FIX_W, FIX_H = 500, 780
        self._fixed_w = FIX_W
        self._fixed_h = FIX_H
        _dock_x, _dock_y, self._fixed_h = self._docked_window_geometry()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self._apply_app_icon()
        self.configure(bg=APP_BG)
        self.geometry(f"{FIX_W}x{self._fixed_h}")
        self.minsize(FIX_W, 520)
        self.resizable(False, True)
        self.hwp = HwpBridge()
        self.wxs = WxsHwpBridge()
        self._auto_format_running = False
        self._auto_format_stop_requested = False
        self.tray_icon = None
        self.hotkey_settings_window = None
        self._hotkey_action_running = False
        self._last_hotkey_failures = {}
        self._force_exit = False
        start_mode = self.app_settings.get("start_mode", "hwp")
        if start_mode not in ("hwp", "kedufine"):
            start_mode = "hwp"
        self.var_target_mode = tk.StringVar(value=start_mode)
        self.data = load_json(CFG_PATH, {})
        self.update_app_id = str(self.data.get("update_app_id") or "").strip()
        self.settings = self.data.get("settings", {"always_on_top": False, "symbols_root": "symbols", "card_w": 230, "card_h": 170})
        self.ui_settings = load_json(external_path(UI_SETTINGS_FILENAME), {})
        self.main_tab_order = list(self.ui_settings.get("main_tab_order", []))
        self.edit_tab_order = list(self.ui_settings.get("edit_tab_order", []))
        self.symbol_tab_order = list(self.ui_settings.get("symbol_tab_order", []))
        self.blocks = self.data.get("blocks", [])
        self.forms = self.data.get("forms", [])
        self.symbols_text = self.data.get("symbols", {})
        self.page_thumbs_root_rel = self.data.get("page_thumbs_root", "page_thumbs")
        self.page_items = self.data.get("page_items", [{"id":"basic_report","title":"기본 보고서 편집용지","thumb":"기본_보고서.png"}])
        self.user_content_store = UserContentStore()
        self.table_tools = feature_registry.with_current_table_tools(self.data.get("table_tools", []))
        self.global_hotkey_actions = ()
        self._hotkey_action_by_id = {}
        self._hotkey_feature_by_id = {}
        self._rebuild_global_hotkey_catalog()
        self.card_w = int(self.settings.get("card_w", 230))
        self.card_h = int(self.settings.get("card_h", 170))
        self.symbols_root = resource_path(self.settings.get("symbols_root", "symbols"))
        self._thumb_cache = {}
        self.text_spacing_box = None
        self.style_card_items = []
        self.var_top = tk.BooleanVar(value=bool(self.settings.get("always_on_top", False)))
        self.var_start_position = tk.StringVar(value=self._start_position_label(self.app_settings.get("start_position", "top_right")))
        self.var_default_mode = tk.StringVar(value=self._mode_label(start_mode))
        self.var_remember_window_position = tk.BooleanVar(value=bool(self.app_settings.get("remember_window_position", False)))
        self.var_close_to_tray = tk.BooleanVar(value=bool(self.app_settings.get("close_to_tray", False)))
        self.var_windows_startup = tk.BooleanVar(value=app_config.is_windows_startup_enabled())
        self.var_start_minimized = tk.BooleanVar(value=bool(self.app_settings.get("start_minimized", False)))
        self.var_check_updates = tk.BooleanVar(value=bool(self.app_settings.get("check_updates_on_startup", True)))
        self.var_global_hotkeys_enabled = tk.BooleanVar(value=bool(self.app_settings.get("global_hotkeys_enabled", True)))
        self.var_hotkey_status = tk.StringVar(value="지정된 단축키 없음")
        self.var_start_menu_status = tk.StringVar(value=f"등록됨 ({APP_VERSION})" if app_config.is_start_menu_registered(APP_VERSION) else "등록 안 됨")
        update_status = f"현재 버전 {APP_VERSION}"
        if not self.update_app_id:
            update_status += " · 업데이트 정보 미설정"
        self.var_update_status = tk.StringVar(value=update_status)
        self.status_var = tk.StringVar(value="준비됨")
        self.cell_range_var = tk.StringVar(value="선택된 범위 없음")
        self.cell_status_var = tk.StringVar(value="한글 표에서 셀을 드래그하세요.")
        self.cell_image_size_mode = tk.StringVar(value=IMAGE_SIZE_FIT_INSIDE)
        self.mouse_down_prev = False
        self.drag_start = None
        self.drag_last = None
        self.recorded_start = None
        self.recorded_end = None
        self.is_cell_processing = False
        self.table_image_section = None
        self.cell_image_button = None
        self.cell_image_refit_button = None
        self._apply_white_style()
        self._build_ui()
        self._refresh_mode_tabs()
        self._bind_palette_keyboard_widgets()
        self.after(300, self._apply_app_icon)
        self.attributes("-topmost", bool(self.var_top.get()))
        self.update_idletasks()
        self._set_palette_noactivate(bool(self.var_top.get()))
        self.after(10, self._apply_initial_window_position)
        self.after(150, self._poll_last_hwp_window)
        self.after(25, self.poll_cell_mouse_drag)
        self.bind_all("<MouseWheel>", self._on_mousewheel_global)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(250, self._ensure_first_run_start_menu_registration)
        self.after(300, self._sync_windows_startup_registration)
        self.after(325, self._reload_global_hotkeys)
        self.after(40, self._poll_global_hotkeys)
        start_in_tray = "--tray" in sys.argv and bool(self.var_close_to_tray.get())
        if start_in_tray:
            self.after(350, self._hide_to_tray)
        else:
            self.deiconify()
            if not bool(self.app_settings.get("tutorial_completed", False)):
                self.after(500, self._show_tutorial)
            elif bool(self.var_check_updates.get()):
                self.after(1500, lambda: self._run_update_check(manual=False))
        self.after(80, close_splash)

    def _apply_app_icon(self):
        icon_path = get_app_icon_path()
        if not icon_path:
            return
        try:
            self.iconbitmap(default=icon_path)
        except Exception:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            user32.LoadImageW.restype = ctypes.c_void_p
            user32.LoadImageW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_uint,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.GetParent.restype = ctypes.c_void_p
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.SendMessageW.restype = ctypes.c_void_p
            user32.SendMessageW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            window_id = self.winfo_id()
            hwnd = user32.GetParent(window_id) or window_id
            handles = []
            for size, icon_kind in ((16, 0), (32, 1)):
                icon = user32.LoadImageW(None, icon_path, 1, size, size, 0x0010)
                if icon:
                    user32.SendMessageW(hwnd, 0x0080, icon_kind, icon)
                    handles.append(icon)
            self._native_icon_handles = handles
        except Exception:
            pass

    def _native_window_handle(self):
        if os.name != "nt":
            return None
        try:
            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.GetParent.restype = ctypes.c_void_p
            inner = self.winfo_id()
            return int(user32.GetParent(inner) or inner)
        except Exception:
            return None

    def _set_palette_noactivate(self, enabled: bool):
        hwnd = self._native_window_handle()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint,
            ]
            user32.SetWindowPos.restype = ctypes.c_bool

            gwl_exstyle = -20
            ws_ex_appwindow = 0x00040000
            ws_ex_noactivate = 0x08000000
            style = int(user32.GetWindowLongPtrW(hwnd, gwl_exstyle))
            palette_style = style | ws_ex_appwindow
            next_style = palette_style | ws_ex_noactivate if enabled else palette_style & ~ws_ex_noactivate
            if next_style == style:
                return
            user32.SetWindowLongPtrW(hwnd, gwl_exstyle, next_style)
            flags = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, flags)
        except Exception:
            pass

    def _bind_palette_keyboard_widgets(self):
        keyboard_types = [tk.Entry, tk.Text, tk.Listbox, ttk.Entry, ttk.Combobox]
        for optional_type in (getattr(tk, "Spinbox", None), getattr(ttk, "Spinbox", None)):
            if optional_type is not None:
                keyboard_types.append(optional_type)
        keyboard_types = tuple(keyboard_types)

        stack = [self]
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
            except Exception:
                pass
            if isinstance(widget, keyboard_types):
                widget.bind("<Button-1>", self._activate_palette_for_keyboard, add="+")

    def _activate_palette_for_keyboard(self, event):
        if not bool(self.var_top.get()):
            return
        self._set_palette_noactivate(False)
        hwnd = self._native_window_handle()
        if hwnd and win32gui is not None:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
        widget = event.widget

        def finish_activation():
            try:
                widget.focus_set()
            except Exception:
                pass
            self.after(80, lambda: self._set_palette_noactivate(bool(self.var_top.get())))

        self.after_idle(finish_activation)

    def _poll_last_hwp_window(self):
        try:
            ui_remember_foreground_hwp()
        finally:
            self.after(150, self._poll_last_hwp_window)

    def _primary_work_area(self):
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _window_chrome_metrics(self):
        try:
            user32 = ctypes.windll.user32
            caption = max(0, int(user32.GetSystemMetrics(4)))
            frame = max(0, int(user32.GetSystemMetrics(33)))
            padded = max(0, int(user32.GetSystemMetrics(92)))
            side = frame + padded
            top = caption + side
            return side, top, top + side
        except Exception:
            return 8, 31, 39

    def _docked_window_geometry(self):
        left, top, right, bottom = self._primary_work_area()
        side, titlebar_height, outer_height = self._window_chrome_metrics()
        x = max(left, right - self._fixed_w - (side * 2) - 10)
        y = top + titlebar_height + 10
        height = max(520, bottom - y - outer_height)
        return x, y, height

    def _move_top_right(self):
        x, y, self._fixed_h = self._docked_window_geometry()
        self.geometry(f"{self._fixed_w}x{self._fixed_h}+{x}+{y}")

    def _center_toplevel(self, win, width, height):
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")

    def _place_left_of(self, win, anchor, width, height, gap=8):
        anchor.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, anchor.winfo_x() - width - gap)
        y = max(0, min(anchor.winfo_y(), sh - height))
        x = min(x, max(0, sw - width))
        win.geometry(f"{width}x{height}+{x}+{y}")

    def _start_position_label(self, code):
        return {
            "top_right": "오른쪽 위",
            "center": "가운데",
            "last": "마지막 위치",
        }.get(code, "오른쪽 위")

    def _start_position_code(self):
        return {
            "오른쪽 위": "top_right",
            "가운데": "center",
            "마지막 위치": "last",
        }.get(self.var_start_position.get(), "top_right")

    def _mode_label(self, code):
        return {
            "hwp": "일반 한글",
            "kedufine": "K-에듀파인 기안창",
        }.get(code, "일반 한글")

    def _mode_code(self, label):
        return {
            "일반 한글": "hwp",
            "K-에듀파인 기안창": "kedufine",
        }.get(label, "hwp")

    def _apply_initial_window_position(self):
        _dock_x, _dock_y, self._fixed_h = self._docked_window_geometry()
        position = self.app_settings.get("start_position", "top_right")
        if position == "last" and self.app_settings.get("remember_window_position"):
            last_geometry = str(self.app_settings.get("last_geometry") or "")
            if last_geometry:
                try:
                    self.geometry(last_geometry)
                    return
                except Exception:
                    pass
        if position == "center":
            left, top, right, bottom = self._primary_work_area()
            side, _titlebar_height, outer_height = self._window_chrome_metrics()
            outer_width = self._fixed_w + (side * 2)
            x = left + max(0, ((right - left) - outer_width) // 2)
            y = top + max(0, ((bottom - top) - (self._fixed_h + outer_height)) // 2)
            self.geometry(f"{self._fixed_w}x{self._fixed_h}+{x}+{y}")
            return
        self._move_top_right()

    def _save_app_settings(self):
        self.app_settings["start_position"] = self._start_position_code()
        self.app_settings["start_mode"] = self._mode_code(self.var_default_mode.get())
        self.app_settings["remember_window_position"] = bool(self.var_remember_window_position.get())
        self.app_settings["close_to_tray"] = bool(self.var_close_to_tray.get())
        self.app_settings["start_minimized"] = bool(self.var_start_minimized.get())
        self.app_settings["check_updates_on_startup"] = bool(self.var_check_updates.get())
        self.app_settings["global_hotkeys_enabled"] = bool(self.var_global_hotkeys_enabled.get())
        if self.app_settings["remember_window_position"]:
            self.app_settings["last_geometry"] = self.geometry()
        try:
            app_config.save_settings(self.app_settings)
        except Exception as e:
            messagebox.showwarning("설정 저장 실패", f"설정을 저장하지 못했습니다.\n\n{e}")

    def _on_app_setting_changed(self):
        self._save_app_settings()

    def _open_path_safely(self, path, missing_message=None):
        try:
            app_config.open_path(path)
        except Exception as e:
            messagebox.showwarning("열기 실패", missing_message or f"대상을 열지 못했습니다.\n\n{e}")

    def _open_settings_folder(self):
        self._open_path_safely(app_config.app_data_dir())

    def _open_crash_log(self):
        path = app_config.crash_log_path()
        if not path.exists():
            messagebox.showinfo("오류 기록", "아직 저장된 오류 기록이 없습니다.")
            return
        self._open_path_safely(path)

    def _open_readme(self):
        path = os.path.join(os.path.dirname(os.path.dirname(CFG_PATH)), "README.md")
        if not os.path.exists(path):
            messagebox.showinfo("README", "README.md 파일을 찾지 못했습니다.")
            return
        self._open_path_safely(path)

    def _open_changelog(self):
        path = os.path.join(os.path.dirname(os.path.dirname(CFG_PATH)), "CHANGELOG.md")
        if not os.path.exists(path):
            messagebox.showinfo("변경 기록", "CHANGELOG.md 파일을 찾지 못했습니다.")
            return
        self._open_path_safely(path)

    def _reset_app_settings(self):
        if not messagebox.askyesno("설정 초기화", "화면/시작 설정을 기본값으로 되돌릴까요?"):
            return
        self.app_settings = dict(app_config.DEFAULT_SETTINGS)
        self.var_start_position.set(self._start_position_label(self.app_settings["start_position"]))
        self.var_default_mode.set(self._mode_label(self.app_settings["start_mode"]))
        self.var_remember_window_position.set(bool(self.app_settings["remember_window_position"]))
        self.var_close_to_tray.set(bool(self.app_settings["close_to_tray"]))
        self.var_windows_startup.set(app_config.is_windows_startup_enabled())
        self.var_start_minimized.set(bool(self.app_settings["start_minimized"]))
        self.var_check_updates.set(bool(self.app_settings["check_updates_on_startup"]))
        self.var_global_hotkeys_enabled.set(bool(self.app_settings["global_hotkeys_enabled"]))
        self.app_settings["global_hotkeys"] = {}
        self._refresh_start_minimized_state()
        self._refresh_start_menu_status()
        self._save_app_settings()
        self._reload_global_hotkeys()

    def _show_tutorial(self):
        win = getattr(self, "tutorial_window", None)
        try:
            if win is not None and win.winfo_exists():
                win.lift()
                win.focus_force()
                return
        except Exception:
            pass

        steps = [
            (
                "전북교육 한글 서식도우미에 오신 것을 환영합니다",
                "한글 문서와 K-에듀파인 기안창에서 자주 쓰는 서식을 빠르게 적용하는 도구입니다.\n\n"
                "약 1분이면 기본 사용법을 확인할 수 있습니다. 이 안내는 설정에서 언제든 다시 볼 수 있습니다.",
            ),
            (
                "1. 적용 대상을 먼저 선택하세요",
                "화면 위쪽의 적용 대상에서 현재 작업 중인 곳을 선택합니다.\n\n"
                "일반 한글: 한글 프로그램에서 문서를 편집할 때 사용합니다.\n"
                "K-에듀파인 기안창: 기안창에서 지원되는 기능만 자동으로 표시합니다.",
            ),
            (
                "2. 한글에서 적용할 부분을 선택하세요",
                "글자 모양이나 자간을 바꿀 때는 한글 문서에서 텍스트를 먼저 블록 지정합니다. "
                "텍스트는 왼쪽 위에서 오른쪽 아래 방향으로 드래그하는 것이 가장 안정적입니다.\n\n"
                "표 안에서는 글자 블록뿐 아니라 셀을 선택한 상태에서도 자간 정리를 사용할 수 있습니다.",
            ),
            (
                "3. 필요한 기능 탭을 고르세요",
                "서식: 보고서용 박스 서식 삽입\n"
                "편집도구: 표 작업, 셀 정리, 글자 작업\n"
                "문자표·심볼: 특수문자와 교육청 상징 삽입\n"
                "양식·편집용지: 자주 쓰는 문서 양식과 용지 설정 적용\n\n"
                "설정의 탭 순서 편집에서 자주 쓰는 탭을 앞으로 옮길 수 있습니다.",
            ),
            (
                "4. 자간 정리와 셀 정리",
                "자간 정리 1단계·2단계는 선택 영역 안에서 줄 끝의 짧은 줄넘김을 줄이도록 줄 단위로 조정합니다. "
                "자간 초기화는 선택 영역의 자간을 0으로 되돌립니다.\n\n"
                "셀 정리는 엑셀에서 붙여 넣은 표의 앞뒤 공백과 문단 배경·글자 음영을 없애고 글자색을 검정으로 정리합니다.",
            ),
            (
                "5. 내 서식과 편집용지를 등록할 수 있습니다",
                "서식과 양식 탭 아래의 추가 버튼에서 한글의 현재 블록이나 HWP·HWPX 파일을 내 항목으로 등록할 수 있습니다.\n\n"
                "편집용지 탭에서는 위·아래·왼쪽·오른쪽·머리말·꼬리말·제본 여백을 입력해 자주 쓰는 설정을 저장할 수 있습니다.",
            ),
            (
                "6. 준비가 끝났습니다",
                "창을 오른쪽에 두고 한글 문서를 편집하면 바로 사용할 수 있습니다.\n\n"
                "오른쪽 위 설정 버튼에서 항상 위 표시, 트레이 최소화, Windows 자동 실행, 시작 메뉴 등록, "
                "업데이트 확인과 튜토리얼 다시 보기를 관리할 수 있습니다.",
            ),
        ]

        win = tk.Toplevel(self)
        self.tutorial_window = win
        win.title("처음 사용 안내")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(self)
        except Exception:
            pass

        step_var = tk.StringVar()
        title_var = tk.StringVar()
        body_var = tk.StringVar()

        header = ttk.Frame(win, padding=(18, 16, 18, 10))
        header.pack(fill="x")
        ttk.Label(header, textvariable=step_var, foreground=ACCENT).pack(anchor="w")
        ttk.Label(
            header,
            textvariable=title_var,
            font=tkfont.Font(size=12, weight="bold"),
            wraplength=424,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=18)
        content = ttk.Frame(win, padding=(18, 18, 18, 12))
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            textvariable=body_var,
            justify="left",
            wraplength=424,
        ).pack(anchor="nw", fill="x")

        progress = ttk.Progressbar(content, mode="determinate", maximum=len(steps))
        progress.pack(side="bottom", fill="x", pady=(18, 0))

        footer = ttk.Frame(win, padding=(18, 10, 18, 16))
        footer.pack(fill="x")
        ttk.Button(footer, text="건너뛰기", command=lambda: close_tutorial()).pack(side="left")
        btn_next = ttk.Button(footer, style="Primary.TButton")
        btn_next.pack(side="right")
        btn_prev = ttk.Button(footer, text="이전")
        btn_prev.pack(side="right", padx=(0, 6))

        index = {"value": 0}

        def render_step():
            current = index["value"]
            title, body = steps[current]
            step_var.set(f"{current + 1} / {len(steps)}")
            title_var.set(title)
            body_var.set(body)
            progress.configure(value=current + 1)
            btn_prev.configure(state="normal" if current > 0 else "disabled")
            btn_next.configure(text="시작하기" if current == len(steps) - 1 else "다음")

        def close_tutorial():
            self.app_settings["tutorial_completed"] = True
            self._save_app_settings()
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        def previous_step():
            if index["value"] > 0:
                index["value"] -= 1
                render_step()

        def next_step():
            if index["value"] >= len(steps) - 1:
                close_tutorial()
                return
            index["value"] += 1
            render_step()

        btn_prev.configure(command=previous_step)
        btn_next.configure(command=next_step)
        win.protocol("WM_DELETE_WINDOW", close_tutorial)
        win.bind("<Escape>", lambda _event: close_tutorial())

        def clear_tutorial_window(event):
            if event.widget is win:
                self.tutorial_window = None

        win.bind("<Destroy>", clear_tutorial_window, add="+")
        render_step()
        self._center_toplevel(win, 460, 430)
        win.after(50, win.grab_set)

    def _finish_update_check_ui(self):
        button = getattr(self, "btn_check_update", None)
        try:
            if button is not None and button.winfo_exists():
                button.configure(state="normal", text="지금 확인")
        except Exception:
            pass

    def _run_update_check(self, manual=False):
        if not self.update_app_id:
            self.var_update_status.set(f"현재 버전 {APP_VERSION} · 업데이트 정보 미설정")
            if manual:
                messagebox.showinfo(
                    "업데이트 확인",
                    "최신 버전 확인 기능은 준비되어 있지만 업데이트 고유번호는 아직 설정되지 않았습니다.",
                )
            self._finish_update_check_ui()
            return

        if manual:
            button = getattr(self, "btn_check_update", None)
            try:
                if button is not None and button.winfo_exists():
                    button.configure(state="disabled", text="확인 중...")
            except Exception:
                pass
        self.var_update_status.set(f"현재 버전 {APP_VERSION} · 확인 중...")

        def worker():
            result = update_checker.check_update(
                self.update_app_id,
                APP_VERSION.lstrip("vV"),
            )
            try:
                self.after(0, lambda: self._handle_update_result(result, manual))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _handle_update_result(self, result, manual):
        self._finish_update_check_ui()
        if not result.get("ok"):
            reason = result.get("reason")
            if reason == "not_registered":
                self.var_update_status.set(f"현재 버전 {APP_VERSION} · 업데이트 정보 미등록")
                if manual:
                    messagebox.showinfo(
                        "업데이트 확인",
                        "교육청 업데이트 안내에 이 프로그램의 정보가 아직 등록되지 않았습니다.",
                    )
            else:
                self.var_update_status.set(f"현재 버전 {APP_VERSION} · 확인할 수 없음")
                if manual:
                    messagebox.showinfo(
                        "업데이트 확인",
                        "업데이트 정보를 확인하지 못했습니다.\n네트워크가 차단되었거나 안내 페이지에 연결할 수 없습니다.",
                    )
            return

        latest = str(result.get("version") or "")
        if result.get("is_newer"):
            self.var_update_status.set(f"새 버전 {latest} 사용 가능")
            if messagebox.askyesno(
                "업데이트 안내",
                f"새 버전 {latest}이(가) 있습니다. (현재 {APP_VERSION})\n\n다운로드 안내 페이지를 여시겠습니까?",
            ):
                try:
                    webbrowser.open(str(result.get("download") or ""))
                except Exception as exc:
                    messagebox.showwarning("페이지 열기 실패", f"다운로드 안내 페이지를 열지 못했습니다.\n\n{exc}")
            return

        self.var_update_status.set(f"최신 버전 사용 중 ({APP_VERSION})")
        if manual:
            messagebox.showinfo("업데이트 확인", f"최신 버전을 사용 중입니다. ({APP_VERSION})")

    def _on_check_updates_changed(self):
        self._save_app_settings()

    def _refresh_start_minimized_state(self):
        checkbox = getattr(self, "chk_start_minimized", None)
        enabled = (
            os.name == "nt"
            and bool(self.var_close_to_tray.get())
            and bool(self.var_windows_startup.get())
        )
        try:
            if checkbox is not None and checkbox.winfo_exists():
                checkbox.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _on_close_to_tray_changed(self):
        if not self.var_close_to_tray.get():
            self.var_start_minimized.set(False)
        if self.var_windows_startup.get():
            try:
                app_config.set_windows_startup_enabled(
                    True,
                    start_minimized=bool(self.var_start_minimized.get()),
                )
            except Exception as exc:
                messagebox.showerror("Windows 시작 설정 실패", f"자동 실행 설정을 갱신하지 못했습니다.\n\n{exc}")
        self._refresh_start_minimized_state()
        self._save_app_settings()

    def _on_windows_startup_changed(self):
        enabled = bool(self.var_windows_startup.get())
        old_start_minimized = bool(self.var_start_minimized.get())
        if not enabled:
            self.var_start_minimized.set(False)
        try:
            app_config.set_windows_startup_enabled(
                enabled,
                start_minimized=bool(self.var_start_minimized.get()),
            )
        except Exception as exc:
            self.var_windows_startup.set(not enabled)
            self.var_start_minimized.set(old_start_minimized)
            messagebox.showerror(
                "Windows 시작 설정 실패",
                f"Windows 시작 시 자동 실행 설정을 바꾸지 못했습니다.\n\n{exc}",
            )
        self._refresh_start_minimized_state()
        self._save_app_settings()

    def _on_start_minimized_changed(self):
        try:
            if self.var_windows_startup.get():
                app_config.set_windows_startup_enabled(
                    True,
                    start_minimized=bool(self.var_start_minimized.get()),
                )
            self._save_app_settings()
        except Exception as exc:
            self.var_start_minimized.set(not self.var_start_minimized.get())
            messagebox.showerror("Windows 시작 설정 실패", f"트레이 시작 설정을 바꾸지 못했습니다.\n\n{exc}")

    def _refresh_start_menu_status(self):
        registered = app_config.is_start_menu_registered(APP_VERSION)
        self.var_start_menu_status.set(f"등록됨 ({APP_VERSION})" if registered else "등록 안 됨")

    def _register_start_menu(self, show_result=True):
        try:
            app_config.set_start_menu_registered(True, APP_VERSION)
            self.app_settings["start_menu_auto_done"] = True
            self.app_settings["start_menu_signature"] = app_config.start_menu_signature(APP_VERSION)
            self._save_app_settings()
            self._refresh_start_menu_status()
            if show_result:
                messagebox.showinfo(
                    "시작 메뉴 등록",
                    f"시작 메뉴에 등록했습니다.\nWindows 검색에서 '{APP_TITLE}'로 찾을 수 있습니다.",
                )
        except Exception as exc:
            self._refresh_start_menu_status()
            if show_result:
                messagebox.showerror("시작 메뉴 등록 실패", f"시작 메뉴에 등록하지 못했습니다.\n\n{exc}")

    def _unregister_start_menu(self):
        try:
            app_config.set_start_menu_registered(False, APP_VERSION)
            self.app_settings["start_menu_auto_done"] = True
            self.app_settings["start_menu_signature"] = app_config.start_menu_signature(APP_VERSION)
            self._save_app_settings()
            self._refresh_start_menu_status()
            messagebox.showinfo("시작 메뉴 등록", "시작 메뉴 등록을 해제했습니다.")
        except Exception as exc:
            self._refresh_start_menu_status()
            messagebox.showerror("시작 메뉴 등록 실패", f"시작 메뉴 등록을 해제하지 못했습니다.\n\n{exc}")

    def _ensure_first_run_start_menu_registration(self):
        if os.name != "nt":
            self._refresh_start_menu_status()
            return

        signature = app_config.start_menu_signature(APP_VERSION)
        previous_signature = str(self.app_settings.get("start_menu_signature") or "")
        current_registered = app_config.is_start_menu_registered(APP_VERSION)
        any_registered = app_config.has_any_start_menu_shortcut()
        obsolete_registered = app_config.has_obsolete_start_menu_shortcuts(APP_VERSION)
        auto_done = bool(self.app_settings.get("start_menu_auto_done", False))

        should_register = False
        if previous_signature != signature:
            # 기존 바로가기가 있거나 최초 실행이면 현재 파일·버전으로 교체한다.
            # 사용자가 등록을 해제해 바로가기가 전혀 없으면 해제 상태를 존중한다.
            should_register = any_registered or not auto_done
        elif current_registered and obsolete_registered:
            should_register = True
        elif not current_registered and any_registered:
            should_register = True
        elif not auto_done:
            should_register = True

        if should_register:
            self._register_start_menu(show_result=False)
            return

        if previous_signature != signature:
            self.app_settings["start_menu_signature"] = signature
            self._save_app_settings()
        self._refresh_start_menu_status()

    def _sync_windows_startup_registration(self):
        if os.name != "nt" or not bool(self.var_windows_startup.get()):
            return
        try:
            app_config.set_windows_startup_enabled(
                True,
                start_minimized=bool(self.var_start_minimized.get()),
            )
        except Exception:
            pass

    def _poll_global_hotkeys(self):
        try:
            host = self.tray_icon
            if host is not None:
                while True:
                    action_id = host.take_pending_hotkey()
                    if action_id is None:
                        break
                    self._execute_global_hotkey(action_id)
        finally:
            try:
                self.after(40, self._poll_global_hotkeys)
            except Exception:
                pass

    def _rebuild_global_hotkey_catalog(self):
        self.global_hotkey_actions = build_hotkey_actions(self.table_tools, self.symbols_text)
        self._hotkey_action_by_id = {action.id: action for action in self.global_hotkey_actions}
        self._hotkey_feature_by_id = {action.id: action for action in DIRECT_HOTKEY_FEATURE_ACTIONS}
        return self.global_hotkey_actions

    def _ensure_hotkey_host(self):
        if self.tray_icon is None:
            self.tray_icon = NativeTrayIcon(self)
        self.tray_icon.ensure_window()
        return self.tray_icon

    def _suspend_global_hotkeys(self):
        if self.tray_icon is not None:
            self.tray_icon.unregister_hotkeys()

    def _reload_global_hotkeys(self, show_errors=False):
        self._rebuild_global_hotkey_catalog()
        valid_ids = self._hotkey_action_by_id.keys()
        normalized, invalid = normalize_bindings(self.app_settings.get("global_hotkeys", {}), valid_ids)
        self.app_settings["global_hotkeys"] = normalized
        if not bool(self.var_global_hotkeys_enabled.get()):
            self._suspend_global_hotkeys()
            self._last_hotkey_failures = invalid
            self.var_hotkey_status.set("사용 안 함")
            return invalid
        if not normalized:
            self._suspend_global_hotkeys()
            self._last_hotkey_failures = invalid
            self.var_hotkey_status.set("지정된 단축키 없음")
            return invalid
        try:
            host = self._ensure_hotkey_host()
            registered, failures = host.register_hotkeys(normalized)
        except Exception as exc:
            registered = {}
            failures = {action_id: str(exc) for action_id in normalized}
        failures.update(invalid)
        self._last_hotkey_failures = failures
        status = f"{len(registered)}개 등록"
        if failures:
            status += f" · {len(failures)}개 충돌"
        self.var_hotkey_status.set(status)
        if show_errors and failures:
            lines = []
            for action_id, reason in list(failures.items())[:8]:
                action = self._hotkey_action_by_id.get(action_id)
                label = action.label if action is not None else action_id
                shortcut = normalized.get(action_id, "")
                lines.append(f"• {label} ({shortcut}): {reason}")
            if len(failures) > 8:
                lines.append(f"• 그 외 {len(failures) - 8}개")
            messagebox.showwarning("전역 단축키 등록", "일부 단축키를 등록하지 못했습니다.\n\n" + "\n".join(lines))
        return failures

    def _on_global_hotkeys_enabled_changed(self):
        self._save_app_settings()
        self._reload_global_hotkeys(show_errors=True)

    def _foreground_matches_hotkey_target(self):
        if win32gui is None or win32process is None:
            return True
        try:
            hwnd = win32gui.GetForegroundWindow()
            if self.is_kedufine_mode():
                _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
                exe = os.path.basename(ui_get_process_path(pid) or "").casefold()
                return exe == WxsHwpBridge.TARGET_EXE
            return self._is_hwp_window_handle(hwnd)
        except Exception:
            return False

    def _toggle_window_from_hotkey(self):
        if self.state() in ("withdrawn", "iconic"):
            self.restore_from_tray()
        else:
            self._hide_to_tray()

    def _execute_global_hotkey(self, action_id):
        if self._hotkey_action_running:
            return
        action = self._hotkey_action_by_id.get(action_id)
        if action is None:
            self._rebuild_global_hotkey_catalog()
            action = self._hotkey_action_by_id.get(action_id)
        if action is None:
            return
        mode = self.var_target_mode.get()
        if mode not in action.modes:
            self.status_var.set(f"현재 적용 대상에서는 사용할 수 없음: {action.label}")
            if win32api is not None:
                try:
                    win32api.MessageBeep()
                except Exception:
                    pass
            return
        if action.requires_target and not self._foreground_matches_hotkey_target():
            target = "K-에듀파인 기안창" if self.is_kedufine_mode() else "한글 문서"
            self.status_var.set(f"{target}이 활성화된 상태에서 단축키를 누르세요.")
            if win32api is not None:
                try:
                    win32api.MessageBeep()
                except Exception:
                    pass
            return
        self._hotkey_action_running = True
        try:
            if action.kind == "app":
                self._toggle_window_from_hotkey()
            elif action.kind == "feature":
                feature = self._hotkey_feature_by_id.get(str(action.payload))
                if feature is not None:
                    self._run_registered_action(feature)
            elif action.kind == "table":
                self._run_table_tool_action(str(action.payload), action.label)
            elif action.kind == "font_color":
                self._apply_font_color(action.payload.rgb, action.payload.label)
            elif action.kind == "font":
                self._apply_font_only(str(action.payload))
            elif action.kind == "font_size":
                font_name, size = action.payload
                self._apply_font_size(font_name, int(size))
            elif action.kind == "insert_text":
                self.on_insert_text(str(action.payload))
        finally:
            self._hotkey_action_running = False

    def _ensure_tray_icon(self):
        if self.tray_icon is None:
            self.tray_icon = NativeTrayIcon(self)
        self.tray_icon.show()

    def _hide_to_tray(self):
        try:
            self._ensure_tray_icon()
            self.withdraw()
            return True
        except Exception as e:
            messagebox.showerror("트레이 최소화 실패", f"트레이 아이콘을 만들지 못했습니다.\n\n{e}")
            return False

    def restore_from_tray(self):
        try:
            self.deiconify()
            self.lift()
            topmost = bool(self.var_top.get())
            self.attributes("-topmost", topmost)
            self._set_palette_noactivate(topmost)
            if not topmost:
                self.focus_force()
        except Exception:
            pass

    def exit_from_tray(self):
        self._force_exit = True
        self._save_app_settings()
        if self.tray_icon is not None:
            self.tray_icon.destroy()
            self.tray_icon = None
        self.destroy()

    def on_close(self):
        self._save_app_settings()
        if not self._force_exit and bool(self.var_close_to_tray.get()):
            if self._hide_to_tray():
                return
        if self.tray_icon is not None:
            self.tray_icon.destroy()
            self.tray_icon = None
        self.destroy()
    def _apply_white_style(self):
        self.option_add("*Font", ("맑은 고딕", 9))
        self.option_add("*Listbox.Font", ("맑은 고딕", 9))
        self.option_add("*Listbox.Background", SURFACE)
        self.option_add("*Listbox.Foreground", TEXT_PRIMARY)
        self.option_add("*Listbox.SelectBackground", ACCENT)
        self.option_add("*Listbox.SelectForeground", "#ffffff")
        self.option_add("*Listbox.BorderWidth", 1)
        self.option_add("*Listbox.Relief", "solid")

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            default_font.configure(family="맑은 고딕", size=9)
            text_font = tkfont.nametofont("TkTextFont")
            text_font.configure(family="맑은 고딕", size=9)
        except Exception:
            pass

        body_font = ("맑은 고딕", 9)
        bold_font = ("맑은 고딕", 9, "bold")
        section_font = ("맑은 고딕", 10, "bold")

        style.configure(".", background=SURFACE, foreground=TEXT_PRIMARY, font=body_font)
        style.configure("TFrame", background=SURFACE)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("App.TFrame", background=APP_BG)
        style.configure("Toolbar.TFrame", background=SURFACE)
        style.configure("ActionBar.TFrame", background=SURFACE_ALT, borderwidth=1, relief="solid")
        style.configure("Status.TFrame", background=SURFACE_ALT)
        style.configure("TLabel", background=SURFACE, foreground=TEXT_PRIMARY, font=body_font)
        style.configure("Toolbar.TLabel", background=SURFACE, foreground=TEXT_PRIMARY, font=bold_font)
        style.configure("Muted.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=body_font)
        style.configure("Status.TLabel", background=SURFACE_ALT, foreground=TEXT_MUTED, font=body_font)
        style.configure("SectionTitle.TLabel", background=SURFACE, foreground=TEXT_PRIMARY, font=section_font)

        button_layout = [
            (
                "Button.border",
                {
                    "sticky": "nswe",
                    "border": "1",
                    "children": [
                        (
                            "Button.padding",
                            {
                                "sticky": "nswe",
                                "children": [("Button.label", {"sticky": "nswe"})],
                            },
                        )
                    ],
                },
            )
        ]
        for button_style in ("TButton", "Primary.TButton", "Danger.TButton", "Tool.TButton", "Compact.TButton", "Symbol.TButton"):
            style.layout(button_style, button_layout)

        style.configure(
            "TButton",
            padding=(9, 5),
            background=SURFACE,
            foreground=TEXT_PRIMARY,
            borderwidth=1,
            relief="solid",
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            font=body_font,
        )
        style.map(
            "TButton",
            background=[("disabled", "#f2f4f7"), ("pressed", "#e9edf2"), ("active", SURFACE_ALT)],
            foreground=[("disabled", "#98a2b3"), ("active", TEXT_PRIMARY)],
            bordercolor=[("active", BORDER_STRONG), ("focus", ACCENT)],
        )
        style.configure(
            "Primary.TButton",
            padding=(12, 7),
            background=ACCENT,
            foreground="#ffffff",
            bordercolor=ACCENT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            font=bold_font,
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", "#a9b8d1"), ("pressed", ACCENT_HOVER), ("active", ACCENT_HOVER)],
            foreground=[("disabled", "#edf1f7"), ("active", "#ffffff")],
            bordercolor=[("disabled", "#a9b8d1"), ("active", ACCENT_HOVER)],
        )
        style.configure(
            "Danger.TButton",
            padding=(9, 6),
            background=DANGER_SOFT,
            foreground=DANGER,
            bordercolor="#efb7b1",
            lightcolor="#efb7b1",
            darkcolor="#efb7b1",
            font=bold_font,
        )
        style.map(
            "Danger.TButton",
            background=[("disabled", "#f7f7f8"), ("pressed", "#fbd9d5"), ("active", "#fde4e1")],
            foreground=[("disabled", "#a8adb5"), ("active", DANGER_HOVER)],
        )
        style.configure("Tool.TButton", padding=(8, 4))
        style.configure("Compact.TButton", padding=(5, 3))
        style.configure("Symbol.TButton", padding=(5, 5), font=("맑은 고딕", 10))

        style.configure("TEntry", padding=(6, 5), fieldbackground=SURFACE, foreground=TEXT_PRIMARY, bordercolor=BORDER)
        style.configure("TCombobox", padding=(6, 4), fieldbackground=SURFACE, foreground=TEXT_PRIMARY, bordercolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", TEXT_PRIMARY)])

        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT_PRIMARY, font=body_font)
        style.configure("TRadiobutton", background=SURFACE, foreground=TEXT_PRIMARY, font=body_font)
        style.map("TCheckbutton", background=[("active", SURFACE)], foreground=[("disabled", "#98a2b3")])
        style.map("TRadiobutton", background=[("active", SURFACE)], foreground=[("disabled", "#98a2b3")])
        style.layout(
            "TRadiobutton",
            [
                (
                    "Radiobutton.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            ("Radiobutton.indicator", {"side": "left", "sticky": ""}),
                            ("Radiobutton.label", {"side": "left", "sticky": "nswe"}),
                        ],
                    },
                )
            ],
        )
        style.layout(
            "TCheckbutton",
            [
                (
                    "Checkbutton.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            ("Checkbutton.indicator", {"side": "left", "sticky": ""}),
                            ("Checkbutton.label", {"side": "left", "sticky": "nswe"}),
                        ],
                    },
                )
            ],
        )

        tab_layout = [
            (
                "Notebook.tab",
                {
                    "sticky": "nswe",
                    "children": [
                        (
                            "Notebook.padding",
                            {
                                "side": "top",
                                "sticky": "nswe",
                                "children": [("Notebook.label", {"side": "top", "sticky": ""})],
                            },
                        )
                    ],
                },
            )
        ]
        for tab_style in ("TNotebook.Tab", "Main.TNotebook.Tab", "Sub.TNotebook.Tab"):
            style.layout(tab_style, tab_layout)

        style.configure("TNotebook", background=APP_BG, borderwidth=0, tabmargins=(0, 3, 0, 0))
        style.configure("Main.TNotebook", background=APP_BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure(
            "Main.TNotebook.Tab",
            padding=(9, 5),
            background="#e9edf2",
            foreground=TEXT_MUTED,
            borderwidth=1,
            bordercolor=BORDER,
            font=body_font,
        )
        style.map(
            "Main.TNotebook.Tab",
            padding=[("selected", (12, 7))],
            background=[("selected", SURFACE), ("active", "#f4f6f8")],
            foreground=[("selected", ACCENT), ("active", TEXT_PRIMARY)],
            bordercolor=[("selected", ACCENT), ("active", BORDER_STRONG)],
        )
        style.configure("Sub.TNotebook", background=SURFACE, borderwidth=0, tabmargins=(0, 3, 0, 0))
        style.configure(
            "Sub.TNotebook.Tab",
            padding=(8, 4),
            background="#eef1f4",
            foreground=TEXT_MUTED,
            borderwidth=1,
            bordercolor=BORDER,
        )
        style.map(
            "Sub.TNotebook.Tab",
            padding=[("selected", (10, 6))],
            background=[("selected", SURFACE), ("active", SURFACE_ALT)],
            foreground=[("selected", TEXT_PRIMARY), ("active", TEXT_PRIMARY)],
            bordercolor=[("selected", BORDER_STRONG)],
        )
        style.configure("TNotebook.Tab", padding=(8, 4), background="#eef1f4", foreground=TEXT_MUTED)
        style.map(
            "TNotebook.Tab",
            padding=[("selected", (10, 6))],
            background=[("selected", SURFACE), ("active", SURFACE_ALT)],
            foreground=[("selected", TEXT_PRIMARY), ("active", TEXT_PRIMARY)],
        )

        style.configure("TLabelframe", background=SURFACE, bordercolor=BORDER, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=SURFACE, foreground=TEXT_PRIMARY, font=bold_font)
        style.configure("Section.TLabelframe", background=SURFACE, bordercolor=BORDER, borderwidth=1, relief="solid")
        style.configure("Section.TLabelframe.Label", background=SURFACE, foreground=TEXT_PRIMARY, font=section_font)
        style.configure("TSeparator", background=BORDER)
        style.configure("TScrollbar", troughcolor=SURFACE_ALT, background=BORDER_STRONG, bordercolor=SURFACE, arrowcolor=TEXT_MUTED)
        style.configure("Horizontal.TProgressbar", troughcolor="#e7ebf0", background=ACCENT, bordercolor="#e7ebf0")
    def is_kedufine_mode(self):
        return self.var_target_mode.get() == "kedufine"

    def on_target_mode_changed(self):
        if self.is_kedufine_mode():
            self.status_var.set("적용 대상: K-에듀파인 기안창")
            self.wxs.reset()
        else:
            self.status_var.set("적용 대상: 일반 한글")
        self._refresh_mode_tabs()

    def _show_kedufine_unsupported(self, feature_name: str):
        messagebox.showinfo(
            "K-에듀파인 기안창 모드",
            f"현재 K-에듀파인 기안창 모드에서 아직 지원하지 않는 기능입니다.\n\n지원 예정 기능: {feature_name}",
        )

    def _restore_kedufine_focus_later(self):
        if self.is_kedufine_mode():
            try:
                self.after(80, self.wxs.restore_focus)
            except Exception:
                pass

    def _normalize_tab_order(self, order, tab_defs):
        default_keys = [key for key, _child, _label in tab_defs]
        normalized = []
        for key in order or []:
            if key in default_keys and key not in normalized:
                normalized.append(key)
        for key in default_keys:
            if key not in normalized:
                normalized.append(key)
        return normalized

    def _ordered_tab_defs(self, tab_defs, order):
        order = self._normalize_tab_order(order, tab_defs)
        by_key = {key: (key, child, label) for key, child, label in tab_defs}
        result = []
        for key in order:
            if key in by_key:
                result.append(by_key[key])
        return result

    def _save_ui_settings(self):
        self.ui_settings["main_tab_order"] = self._normalize_tab_order(
            self.main_tab_order,
            getattr(self, "main_tab_defs", []),
        )
        self.ui_settings["edit_tab_order"] = self._normalize_tab_order(
            self.edit_tab_order,
            getattr(self, "edit_tab_defs", []),
        )
        self.ui_settings["symbol_tab_order"] = self._normalize_tab_order(
            self.symbol_tab_order,
            getattr(self, "symbol_tab_defs", []),
        )
        try:
            path = external_path(UI_SETTINGS_FILENAME)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.ui_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showwarning("저장 실패", f"탭 순서 설정 저장에 실패했습니다.\n\n{e}")

    def _set_notebook_tabs(self, notebook: ttk.Notebook, tab_defs, visible_keys):
        """모드에 따라 Notebook 탭을 재구성한다.

        ttk.Notebook.hide() 대신 forget/add 방식으로 순서를 확실히 유지한다.
        child frame은 삭제하지 않으므로 탭을 다시 추가해도 기존 내용은 그대로 유지된다.
        """
        if notebook is None:
            return
        visible_keys = set(visible_keys)
        try:
            current = notebook.select()
        except Exception:
            current = ""

        try:
            for child in list(notebook.tabs()):
                notebook.forget(child)
        except Exception:
            pass

        visible_children = []
        for key, child, label in tab_defs:
            if key in visible_keys:
                try:
                    notebook.add(child, text=label)
                    visible_children.append(str(child))
                except Exception:
                    pass

        try:
            tabs = list(notebook.tabs())
            if not tabs:
                return
            if current and str(current) in tabs:
                notebook.select(current)
            else:
                notebook.select(tabs[0])
        except Exception:
            pass

    def _refresh_symbol_tabs(self):
        """심볼 탭 내부의 그룹 탭 순서를 적용한다."""
        if not hasattr(self, "symbol_nb") or not hasattr(self, "symbol_tab_defs"):
            return
        if not self.symbol_tab_defs:
            return
        self.symbol_tab_order = self._normalize_tab_order(self.symbol_tab_order, self.symbol_tab_defs)
        self._set_notebook_tabs(
            self.symbol_nb,
            self._ordered_tab_defs(self.symbol_tab_defs, self.symbol_tab_order),
            {key for key, _child, _label in self.symbol_tab_defs},
        )

    def _refresh_style_cards(self):
        """기안창 모드에서는 사용 가능한 서식 카드만 표시한다."""
        if not getattr(self, "style_card_items", None):
            return

        if self.is_kedufine_mode():
            visible_titles = KEDUFIN_SUPPORTED_BLOCK_TITLES
        else:
            visible_titles = None

        visible_cards = []
        for item in self.style_card_items:
            card = item.get("card")
            try:
                card.grid_forget()
            except Exception:
                pass
            title = item.get("title", "")
            if visible_titles is None or title in visible_titles:
                visible_cards.append(item)

        cols = 3
        for new_idx, item in enumerate(visible_cards):
            r, c = divmod(new_idx, cols)
            try:
                item["card"].grid(row=r, column=c, padx=5, pady=6, sticky="n")
            except Exception:
                pass
        action_bar = getattr(self, "style_user_actions_bar", None)
        if action_bar is not None:
            try:
                action_bar.grid(row=max(1, (len(visible_cards) + cols - 1) // cols), column=0, columnspan=cols, sticky="ew", padx=2, pady=(4, 8))
            except Exception:
                pass


    def _refresh_mode_tabs(self):
        """적용 대상 모드에 따라 사용 가능한 탭만 표시한다."""
        if not hasattr(self, "main_nb"):
            return

        if self.is_kedufine_mode():
            self._set_notebook_tabs(
                self.main_nb,
                self._ordered_tab_defs(self.main_tab_defs, self.main_tab_order),
                feature_registry.VISIBLE_MAIN_TABS[feature_registry.MODE_KEDUFINE],
            )
            if hasattr(self, "edit_nb"):
                self._set_notebook_tabs(
                    self.edit_nb,
                    self._ordered_tab_defs(self.edit_tab_defs, self.edit_tab_order),
                    feature_registry.VISIBLE_EDIT_TABS[feature_registry.MODE_KEDUFINE],
                )
        else:
            self._set_notebook_tabs(
                self.main_nb,
                self._ordered_tab_defs(self.main_tab_defs, self.main_tab_order),
                feature_registry.VISIBLE_MAIN_TABS[feature_registry.MODE_HWP],
            )
            if hasattr(self, "edit_nb"):
                self._set_notebook_tabs(
                    self.edit_nb,
                    self._ordered_tab_defs(self.edit_tab_defs, self.edit_tab_order),
                    feature_registry.VISIBLE_EDIT_TABS[feature_registry.MODE_HWP],
                )

        self._refresh_registered_feature_buttons()
        self._refresh_text_font_rows()
        self._refresh_symbol_tabs()
        self._refresh_style_cards()

    def _run_registered_action(self, action):
        handler = getattr(self, action.handler)
        return handler(*action.args)

    def _feature_button_command(self, action):
        return lambda action=action: self._run_registered_action(action)

    def _refresh_registered_feature_buttons(self):
        mode = self.var_target_mode.get()
        for action in feature_registry.TOP_ROW_ACTIONS:
            if not action.widget_attr:
                continue
            widget = getattr(self, action.widget_attr, None)
            if widget is None:
                continue
            state = "normal" if mode in action.modes else "disabled"
            try:
                widget.configure(state=state)
            except Exception:
                pass

        image_action = feature_registry.TABLE_INSERT_IMAGES_ACTION
        image_section = getattr(self, "table_image_section", None)
        if image_section is not None:
            try:
                if mode in image_action.modes:
                    image_section.grid()
                else:
                    image_section.grid_remove()
            except Exception:
                pass
        self._set_cell_actions_enabled(bool(self.recorded_start and self.recorded_end))

    def _find_canvas_ancestor(self, w):
        while w is not None:
            if isinstance(w, tk.Canvas):
                return w
            w = getattr(w, "master", None)
        return None
    def _find_template_file_by_title(self, wanted_title: str):
        wanted = (wanted_title or "").strip().replace(" ", "")
        for source in (self.blocks or []) + (self.forms or []):
            title = str(source.get("title", "")).strip().replace(" ", "")
            rel = source.get("file", "")
            if title == wanted and rel:
                abs_path = resource_path(rel)
                if os.path.exists(abs_path):
                    return abs_path
        return None
    def _canvas_can_scroll(self, canvas: tk.Canvas) -> bool:
        try:
            y0, y1 = canvas.yview()
            if y0 <= 0.0 and y1 >= 1.0:
                return False
        except Exception:
            pass
        return True
    def _on_mousewheel_global(self, event):
        w = self.winfo_containing(event.x_root, event.y_root)
        canvas = self._find_canvas_ancestor(w)
        if canvas is None:
            return
        if not self._canvas_can_scroll(canvas):
            return
        delta_units = int(-1 * (event.delta / 120))
        if delta_units == 0:
            return
        try:
            canvas.yview_scroll(delta_units, "units")
        except Exception:
            pass
    def _set_scrollbar_needed(self, scrollbar, needed):
        try:
            managed = scrollbar.winfo_manager() == "grid"
            if needed and not managed:
                scrollbar.grid()
            elif not needed and managed:
                scrollbar.grid_remove()
        except Exception:
            pass
    def _make_scroll_grid(self, parent):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.text_font_rows = {}
        self.text_font_order = []
        canvas = tk.Canvas(wrap, highlightthickness=0, bg=SURFACE)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        def refresh_scroll(_evt=None):
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            canvas.configure(scrollregion=bbox)
            canvas.itemconfigure(inner_id, width=canvas.winfo_width())
            content_height = 0 if bbox is None else bbox[3] - bbox[1]
            self._set_scrollbar_needed(vsb, content_height > canvas.winfo_height() + 1)
        inner.bind("<Configure>", refresh_scroll)
        canvas.bind("<Configure>", refresh_scroll)
        self.after(50, refresh_scroll)
        return canvas, inner
    def _load_thumb_any(
        self,
        filepath_abs,
        max_size,
        vertical_margin_ratio=1.0,
        zoom=1.0,
        anchor_y=0.5,
    ):
        if not filepath_abs or not os.path.exists(filepath_abs):
            return None
        key = (filepath_abs, max_size, vertical_margin_ratio, zoom, anchor_y)
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        if Image is not None and ImageTk is not None:
            try:
                im = Image.open(filepath_abs).convert("RGBA")
                if vertical_margin_ratio < 1.0:
                    im = _reduce_vertical_transparent_margins(im, vertical_margin_ratio)
                zoom = max(1.0, float(zoom))
                if zoom > 1.0:
                    max_w, max_h = (max(1, int(value)) for value in max_size)
                    base_scale = min(max_w / im.width, max_h / im.height)
                    scaled_size = (
                        max(1, int(round(im.width * base_scale * zoom))),
                        max(1, int(round(im.height * base_scale * zoom))),
                    )
                    im = im.resize(scaled_size, resample=Image.LANCZOS)
                    viewport = Image.new("RGBA", (max_w, max_h), "white")
                    x = (max_w - im.width) // 2
                    y = int(round((max_h - im.height) * min(1.0, max(0.0, float(anchor_y)))))
                    viewport.paste(im, (x, y), im)
                    im = viewport
                else:
                    im.thumbnail(max_size, resample=Image.LANCZOS)
                img = ImageTk.PhotoImage(im)
                self._thumb_cache[key] = img
                return img
            except Exception:
                pass
        try:
            ext = os.path.splitext(filepath_abs)[1].lower()
            if ext not in (".png", ".gif"):
                return None
            img = tk.PhotoImage(file=filepath_abs)
            max_w, max_h = max_size
            factor = max(1, (img.width() + max_w - 1) // max_w, (img.height() + max_h - 1) // max_h)
            if factor > 1:
                img = img.subsample(factor, factor)
            self._thumb_cache[key] = img
            return img
        except Exception:
            return None
    def _build_style_actions(self, parent):
        bar = ttk.Frame(parent, style="ActionBar.TFrame", padding=(10, 9))
        bar.pack(fill="x", pady=(0, 10))
        bar.columnconfigure(0, weight=2)
        bar.columnconfigure(2, weight=1)

        actions = {action.id: action for action in feature_registry.TOP_ROW_ACTIONS}
        auto_action = actions["auto_format_report"]
        prompt_action = actions["copy_report_prompt"]

        self.btn_auto_format = ttk.Button(
            bar,
            text=auto_action.label,
            style="Primary.TButton",
            command=self._feature_button_command(auto_action),
        )
        self.btn_auto_format.grid(row=0, column=0, sticky="ew")

        self.btn_stop_auto_format = ttk.Button(
            bar,
            text="중지",
            style="Danger.TButton",
            command=self.on_stop_auto_format,
            state="disabled",
        )
        self.btn_stop_auto_format.grid(row=0, column=1, padx=6)

        self.btn_copy_prompt = ttk.Button(
            bar,
            text=prompt_action.label,
            command=self._feature_button_command(prompt_action),
        )
        self.btn_copy_prompt.grid(row=0, column=2, sticky="ew")

    def _build_ui(self):
        top = ttk.Frame(self, style="Toolbar.TFrame", padding=(12, 10, 12, 8))
        top.pack(fill="x")

        meta = ttk.Frame(top, style="Toolbar.TFrame")
        meta.pack(side="right")
        ttk.Button(
            meta,
            text="설정",
            style="Tool.TButton",
            command=self.open_settings_window,
            takefocus=0,
        ).pack(side="left")

        opt = ttk.Frame(top, style="Toolbar.TFrame")
        opt.pack(side="left", fill="x", expand=True)
        ttk.Label(opt, text="적용 대상", style="Toolbar.TLabel").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            opt,
            text="일반 한글",
            value="hwp",
            variable=self.var_target_mode,
            command=self.on_target_mode_changed,
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            opt,
            text="K-에듀파인 기안창",
            value="kedufine",
            variable=self.var_target_mode,
            command=self.on_target_mode_changed,
        ).pack(side="left")

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        status_shell = ttk.Frame(self, style="Status.TFrame")
        status_shell.pack(side="bottom", fill="x")
        ttk.Separator(status_shell, orient="horizontal").pack(fill="x")
        ttk.Label(
            status_shell,
            textvariable=self.status_var,
            style="Status.TLabel",
            anchor="w",
            padding=(12, 7),
        ).pack(fill="x")

        nb = ttk.Notebook(self, style="Main.TNotebook", takefocus=0)
        self.main_nb = nb
        nb.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        tab_style = ttk.Frame(nb, style="Surface.TFrame", padding=(8, 10, 8, 8))
        tab_edit = ttk.Frame(nb, style="Surface.TFrame", padding=(8, 10, 8, 8))
        tab_chars = ttk.Frame(nb, style="Surface.TFrame", padding=(8, 10, 8, 8))
        tab_symbol = ttk.Frame(nb, style="Surface.TFrame", padding=(8, 10, 8, 8))
        tab_forms = ttk.Frame(nb, style="Surface.TFrame", padding=(8, 10, 8, 8))
        tab_page = ttk.Frame(nb, style="Surface.TFrame", padding=(8, 10, 8, 8))
        self.tab_style = tab_style
        self.tab_chars = tab_chars
        self.tab_forms = tab_forms
        self.tab_page = tab_page
        self.main_tab_defs = [
            ("style", tab_style, "서식"),
            ("edit", tab_edit, "편집도구"),
            ("chars", tab_chars, "문자표"),
            ("symbol", tab_symbol, "심볼"),
            ("forms", tab_forms, "양식"),
            ("page", tab_page, "편집용지"),
        ]
        self.main_tab_order = self._normalize_tab_order(self.main_tab_order, self.main_tab_defs)
        for _key, _tab, _label in self._ordered_tab_defs(self.main_tab_defs, self.main_tab_order):
            nb.add(_tab, text=_label)

        self._build_style_actions(tab_style)
        self._build_cards_grid(
            tab_style,
            self._combined_content_items("style"),
            cols=3,
            card_w=142,
            card_h=112,
            card_context="style",
            user_kind="style",
        )
        self._build_chars_scroll(tab_chars)
        self._build_symbol_tabs(tab_symbol)
        self._build_cards_grid(
            tab_forms,
            self._combined_content_items("form"),
            cols=2,
            card_w=min(self.card_w, 218),
            card_h=self.card_h,
            user_kind="form",
            preview_zoom=2.5,
            preview_anchor_y=0.0,
        )
        self._build_page_cards(tab_page)
        self._build_edit_tools(tab_edit)
    def open_settings_window(self):
        win = getattr(self, "settings_window", None)
        try:
            if win is not None and win.winfo_exists():
                win.lift()
                win.focus_force()
                return
        except Exception:
            pass

        win = tk.Toplevel(self)
        self.settings_window = win
        win.title("설정")
        win.configure(bg=APP_BG)

        win.minsize(460, 560)
        win.resizable(False, True)
        try:
            win.transient(self)
        except Exception:
            pass

        body = ttk.Frame(win, padding=(10, 10, 10, 0))
        body.pack(fill="both", expand=True)
        self._build_settings_page(body, show_title=False)

        footer = ttk.Frame(win, padding=(10, 8, 10, 10))
        footer.pack(fill="x")
        ttk.Button(footer, text="닫기", command=win.destroy, takefocus=0).pack(side="right")

        def clear_settings_window(event):
            if event.widget is win:
                self.settings_window = None

        win.bind("<Destroy>", clear_settings_window, add="+")
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.update_idletasks()
        content = getattr(self, "settings_content", None)
        content_height = content.winfo_reqheight() if content is not None else 824
        target_height = max(720, content_height + footer.winfo_reqheight() + 20)

        left, top, right, bottom = self._primary_work_area()
        side, _titlebar_height, outer_height = self._window_chrome_metrics()
        max_height = max(560, (bottom - top) - outer_height - 20)
        height = min(target_height, max_height)
        width = 500
        outer_width = width + (side * 2)
        x = left + max(0, ((right - left) - outer_width) // 2)
        y = top + max(0, ((bottom - top) - (height + outer_height)) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")

    def _settings_card(self, parent, title):
        box = ttk.LabelFrame(parent, text=title, style="Section.TLabelframe", padding=10)
        box.pack(fill="x", pady=(0, 12))
        return box

    def _make_settings_scroll(self, parent):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        canvas = tk.Canvas(wrap, highlightthickness=0, bg=SURFACE)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas)
        self.settings_content = inner
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        def refresh_scroll(_evt=None):
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            canvas.configure(scrollregion=bbox)
            canvas.itemconfigure(inner_id, width=canvas.winfo_width())
            content_height = 0 if bbox is None else bbox[3] - bbox[1]
            self._set_scrollbar_needed(vsb, content_height > canvas.winfo_height() + 1)
        inner.bind("<Configure>", refresh_scroll)
        canvas.bind("<Configure>", refresh_scroll)
        self.after(50, refresh_scroll)
        self.settings_scroll = canvas
        return canvas, inner

    def _build_settings_page(self, parent, show_title=False):
        _canvas, outer = self._make_settings_scroll(parent)

        if show_title:
            title_font = tkfont.Font(size=11, weight="bold")
            ttk.Label(outer, text="설정", font=title_font, background=WHITE).pack(anchor="w", pady=(0, 8))

        screen = self._settings_card(outer, "화면")
        ttk.Checkbutton(
            screen,
            text="항상 위로 표시",
            variable=self.var_top,
            command=self.on_toggle_top,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Checkbutton(
            screen,
            text="마지막 창 위치 기억",
            variable=self.var_remember_window_position,
            command=self._on_app_setting_changed,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(screen, text="시작 위치", background=WHITE).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(2, 0))
        pos = ttk.Combobox(
            screen,
            textvariable=self.var_start_position,
            values=("오른쪽 위", "가운데", "마지막 위치"),
            state="readonly",
            width=16,
        )
        pos.grid(row=2, column=1, sticky="w", pady=(2, 0))
        pos.bind("<<ComboboxSelected>>", lambda _event: self._on_app_setting_changed())

        work = self._settings_card(outer, "시작 동작")
        ttk.Label(work, text="시작 시 적용 대상", background=WHITE).grid(row=0, column=0, sticky="w", padx=(0, 8))
        mode = ttk.Combobox(
            work,
            textvariable=self.var_default_mode,
            values=("일반 한글", "K-에듀파인 기안창"),
            state="readonly",
            width=18,
        )
        mode.grid(row=0, column=1, sticky="w")
        mode.bind("<<ComboboxSelected>>", lambda _event: self._on_app_setting_changed())
        ttk.Label(
            work,
            text="프로그램을 열었을 때 기본으로 표시할 작업 환경입니다.",
            foreground=TEXT_MUTED,
            background=WHITE,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        windows = self._settings_card(outer, "Windows 통합")
        ttk.Checkbutton(
            windows,
            text="닫기 시 종료하지 않고 트레이로 최소화",
            variable=self.var_close_to_tray,
            command=self._on_close_to_tray_changed,
        ).pack(anchor="w")
        ttk.Label(
            windows,
            text="X 버튼을 눌러도 프로그램을 종료하지 않고 작업표시줄 알림 영역에 보관합니다.",
            foreground=TEXT_MUTED,
            background=WHITE,
            wraplength=430,
            justify="left",
        ).pack(anchor="w", padx=(22, 0), pady=(1, 7))

        ttk.Checkbutton(
            windows,
            text="Windows 시작 시 자동 실행",
            variable=self.var_windows_startup,
            command=self._on_windows_startup_changed,
        ).pack(anchor="w")
        ttk.Label(
            windows,
            text="현재 사용자 계정에만 등록되며 관리자 권한은 필요하지 않습니다.",
            foreground=TEXT_MUTED,
            background=WHITE,
        ).pack(anchor="w", padx=(22, 0), pady=(1, 7))

        self.chk_start_minimized = ttk.Checkbutton(
            windows,
            text="Windows 시작 시 트레이로 시작",
            variable=self.var_start_minimized,
            command=self._on_start_minimized_changed,
        )
        self.chk_start_minimized.pack(anchor="w")
        ttk.Label(
            windows,
            text="자동 실행과 트레이 최소화를 모두 켠 경우에만 사용할 수 있습니다.",
            foreground=TEXT_MUTED,
            background=WHITE,
        ).pack(anchor="w", padx=(22, 0), pady=(1, 8))

        ttk.Separator(windows, orient="horizontal").pack(fill="x", pady=(2, 8))
        start_menu_head = ttk.Frame(windows)
        start_menu_head.pack(fill="x")
        ttk.Label(start_menu_head, text="시작 메뉴", background=WHITE).pack(side="left")
        ttk.Label(
            start_menu_head,
            textvariable=self.var_start_menu_status,
            foreground=ACCENT,
            background=WHITE,
        ).pack(side="right")
        ttk.Label(
            windows,
            text=f"Windows 검색에는 {APP_TITLE} ({APP_VERSION})로 표시됩니다. 파일 위치나 버전이 바뀌면 현재 실행 파일로 자동 갱신됩니다.",
            foreground=TEXT_MUTED,
            background=WHITE,
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(2, 6))
        start_menu_buttons = ttk.Frame(windows)
        start_menu_buttons.pack(fill="x")
        ttk.Button(
            start_menu_buttons,
            text="등록 / 경로 갱신",
            command=self._register_start_menu,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            start_menu_buttons,
            text="등록 해제",
            style="Danger.TButton",
            command=self._unregister_start_menu,
        ).pack(side="left")

        hotkeys = self._settings_card(outer, "전역 단축키")
        ttk.Checkbutton(
            hotkeys,
            text="전역 단축키 사용",
            variable=self.var_global_hotkeys_enabled,
            command=self._on_global_hotkeys_enabled_changed,
        ).pack(anchor="w")
        ttk.Label(
            hotkeys,
            text="서식도우미가 트레이에 있어도 작동하며, 상단의 적용 대상 설정을 기준으로 실행합니다.",
            foreground=TEXT_MUTED,
            background=WHITE,
            wraplength=430,
            justify="left",
        ).pack(anchor="w", padx=(22, 0), pady=(1, 8))
        hotkey_row = ttk.Frame(hotkeys)
        hotkey_row.pack(fill="x")
        ttk.Button(
            hotkey_row,
            text="단축키 설정",
            command=self.open_hotkey_settings_window,
            takefocus=0,
        ).pack(side="left")
        ttk.Label(
            hotkey_row,
            textvariable=self.var_hotkey_status,
            foreground=ACCENT,
            background=WHITE,
        ).pack(side="right")

        guide = self._settings_card(outer, "안내")
        for column in range(3):
            guide.columnconfigure(column, weight=1)
        ttk.Button(guide, text="튜토리얼 다시 보기", command=self._show_tutorial).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(guide, text="README", command=self._open_readme).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(guide, text="변경 기록", command=self._open_changelog).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        updates = self._settings_card(outer, "업데이트")
        ttk.Checkbutton(
            updates,
            text="시작할 때 새 버전 확인",
            variable=self.var_check_updates,
            command=self._on_check_updates_changed,
        ).pack(anchor="w")
        ttk.Label(
            updates,
            text="확인에 실패해도 프로그램 실행과 한글 작업에는 영향을 주지 않습니다.",
            foreground=TEXT_MUTED,
            background=WHITE,
        ).pack(anchor="w", padx=(22, 0), pady=(1, 7))
        update_row = ttk.Frame(updates)
        update_row.pack(fill="x")
        ttk.Label(update_row, textvariable=self.var_update_status, background=WHITE).pack(side="left")
        self.btn_check_update = ttk.Button(
            update_row,
            text="지금 확인",
            command=lambda: self._run_update_check(manual=True),
        )
        self.btn_check_update.pack(side="right")

        manage = self._settings_card(outer, "관리")
        for column in range(3):
            manage.columnconfigure(column, weight=1)
        ttk.Button(manage, text="설정 폴더", command=self._open_settings_folder).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(manage, text="오류 기록", command=self._open_crash_log).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(manage, text="설정 초기화", style="Danger.TButton", command=self._reset_app_settings).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        tabs = self._settings_card(outer, "탭")
        ttk.Button(tabs, text="탭 순서 편집", command=self.on_edit_tab_order).pack(anchor="w")

        self._refresh_start_minimized_state()
        self._refresh_start_menu_status()

    def open_hotkey_settings_window(self):
        existing = getattr(self, "hotkey_settings_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        actions = self._rebuild_global_hotkey_catalog()
        bindings, _invalid = normalize_bindings(
            self.app_settings.get("global_hotkeys", {}),
            self._hotkey_action_by_id.keys(),
        )
        self._suspend_global_hotkeys()
        parent = getattr(self, "settings_window", None)
        try:
            if parent is None or not parent.winfo_exists():
                parent = self
        except Exception:
            parent = self

        def save_bindings(updated):
            self.app_settings["global_hotkeys"] = dict(updated)
            self._save_app_settings()

        def finish(saved):
            self.hotkey_settings_window = None
            self.after_idle(lambda: self._reload_global_hotkeys(show_errors=bool(saved)))

        dialog = HotkeySettingsDialog(parent, actions, bindings, save_bindings, finish)
        self.hotkey_settings_window = dialog.window

    def _user_kind_labels(self, kind):
        return {
            "style": ("서식", "내 서식 추가", "사용자 서식 관리"),
            "form": ("양식", "내 양식 추가", "사용자 양식 관리"),
            "page": ("편집용지", "내 편집용지 추가", "사용자 편집용지 관리"),
        }[kind]

    def _combined_content_items(self, kind):
        built_in = {
            "style": self.blocks,
            "form": self.forms,
            "page": self.page_items,
        }[kind]
        return list(built_in or []) + self.user_content_store.list_items(kind)

    def _build_user_action_bar(self, inner, kind, row, cols):
        _name, add_label, manage_label = self._user_kind_labels(kind)
        bar = ttk.Frame(inner, padding=(4, 8, 4, 4))
        bar.grid(row=row, column=0, columnspan=cols, sticky="ew", padx=2, pady=(4, 8))
        ttk.Separator(bar).pack(fill="x", pady=(0, 10))
        buttons = ttk.Frame(bar)
        buttons.pack(fill="x")
        ttk.Button(
            buttons,
            text=add_label,
            style="Primary.TButton",
            command=lambda k=kind: self.on_add_user_content(k),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(
            buttons,
            text=manage_label,
            command=lambda k=kind: self.open_user_content_manager(k),
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))
        return bar

    def _rebuild_user_content_tab(self, kind):
        if kind == "style":
            tab = self.tab_style
            for child in tab.winfo_children():
                child.destroy()
            self.style_card_items = []
            self._build_style_actions(tab)
            self._build_cards_grid(
                tab,
                self._combined_content_items("style"),
                cols=3,
                card_w=142,
                card_h=112,
                card_context="style",
                user_kind="style",
            )
            self._refresh_style_cards()
        elif kind == "form":
            tab = self.tab_forms
            for child in tab.winfo_children():
                child.destroy()
            self._build_cards_grid(
                tab,
                self._combined_content_items("form"),
                cols=2,
                card_w=min(self.card_w, 218),
                card_h=self.card_h,
                user_kind="form",
                preview_zoom=2.5,
                preview_anchor_y=0.0,
            )
        elif kind == "page":
            tab = self.tab_page
            for child in tab.winfo_children():
                child.destroy()
            self._build_page_cards(tab)

    def _ask_user_item_title(self, kind, initial="", owner=None, button_text="등록"):
        owner = owner or self
        item_name = self._user_kind_labels(kind)[0]
        win = tk.Toplevel(owner)
        win.title(f"{item_name} 이름")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(owner)
            win.attributes("-topmost", bool(self.var_top.get()))
            win.grab_set()
        except Exception:
            pass

        result = {"value": None}
        body = ttk.Frame(win, padding=(16, 16, 16, 10))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"{item_name} 이름").pack(anchor="w", pady=(0, 5))
        value_var = tk.StringVar(value=initial)
        entry = ttk.Entry(body, textvariable=value_var)
        entry.pack(fill="x")

        footer = ttk.Frame(win, padding=(16, 6, 16, 14))
        footer.pack(fill="x")

        def close():
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        def accept():
            value = " ".join(value_var.get().strip().split())
            if not value:
                messagebox.showerror("이름 확인", "이름을 입력하세요.", parent=win)
                return
            if len(value) > 40:
                messagebox.showerror("이름 확인", "이름은 40자 이내로 입력하세요.", parent=win)
                return
            result["value"] = value
            close()

        ttk.Button(footer, text="취소", command=close).pack(side="right")
        ttk.Button(footer, text=button_text, style="Primary.TButton", command=accept).pack(side="right", padx=(0, 6))
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda _event: close())
        win.bind("<Return>", lambda _event: accept())
        self._center_toplevel(win, 380, 155)
        win.after(60, entry.focus_set)
        win.wait_window()
        try:
            if owner is not self and owner.winfo_exists():
                owner.grab_set()
        except Exception:
            pass
        return result["value"]

    def on_add_user_content(self, kind):
        if kind == "page":
            self.open_page_preset_dialog()
            return
        self._open_user_content_source_dialog(kind)

    def _open_user_content_source_dialog(self, kind):
        item_name = self._user_kind_labels(kind)[0]
        win = tk.Toplevel(self)
        win.title(f"내 {item_name} 추가")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(self)
            win.attributes("-topmost", bool(self.var_top.get()))
            win.grab_set()
        except Exception:
            pass

        body = ttk.Frame(win, padding=(16, 16, 16, 10))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="추가할 방법을 선택하세요.", font=tkfont.Font(size=10, weight="bold")).pack(anchor="w", pady=(0, 12))
        button_area = ttk.Frame(body)
        button_area.pack(fill="x")

        def choose(mode):
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()
            if mode == "block":
                self.after(20, lambda: self._add_user_content_from_block(kind))
            else:
                self.after(20, lambda: self._add_user_content_from_file(kind))

        choices = [
            ("block", "현재 블록에서 추가"),
            ("file", "한글 파일에서 추가"),
        ]
        preferred = "block" if kind == "style" else "file"
        for mode, label in choices:
            ttk.Button(
                button_area,
                text=label,
                style="Primary.TButton" if mode == preferred else "TButton",
                command=lambda m=mode: choose(m),
            ).pack(fill="x", pady=(0, 7))

        footer = ttk.Frame(win, padding=(16, 0, 16, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="취소", command=win.destroy).pack(side="right")
        win.bind("<Escape>", lambda _event: win.destroy())
        self._center_toplevel(win, 370, 215)

    def _create_pending_user_preview(self, kind, source_path):
        pending = self.user_content_store.pending_preview_path()
        item_name = self._user_kind_labels(kind)[0]
        self.status_var.set(f"내 {item_name} 미리보기 만드는 중...")
        try:
            self.update_idletasks()
        except Exception:
            pass
        ok, message = create_document_preview(
            source_path,
            pending,
            crop_content=(kind == "style"),
        )
        return (pending if ok else None), message, pending

    def _show_preview_generation_warning(self, item_name, message):
        messagebox.showwarning(
            "미리보기 안내",
            f"내 {item_name}은 등록했지만 미리보기를 자동으로 만들지 못했습니다.\n"
            f"사용자 {item_name} 관리에서 이미지로 직접 지정할 수 있습니다.\n\n{message}",
        )

    def _add_user_content_from_file(self, kind):
        restore_noactivate = bool(self.var_top.get())
        if restore_noactivate:
            self._set_palette_noactivate(False)
        try:
            path = filedialog.askopenfilename(
                parent=self,
                title="등록할 한글 파일 선택",
                filetypes=(("한글 문서", "*.hwp *.hwpx"), ("모든 파일", "*.*")),
            )
        finally:
            if restore_noactivate:
                self._set_palette_noactivate(True)
        if not path:
            return
        title = self._ask_user_item_title(kind, initial=os.path.splitext(os.path.basename(path))[0])
        if not title:
            return
        preview = None
        pending_preview = None
        preview_message = ""
        try:
            preview, preview_message, pending_preview = self._create_pending_user_preview(kind, path)
            self.user_content_store.add_file(kind, title, path, preview_path=preview)
            self._thumb_cache.clear()
            self._rebuild_user_content_tab(kind)
            item_name = self._user_kind_labels(kind)[0]
            self.status_var.set(f"내 {item_name} 추가 완료: {title}")
            if preview is None:
                self._show_preview_generation_warning(item_name, preview_message)
        except (UserContentError, OSError) as exc:
            messagebox.showerror("사용자 항목 추가 실패", str(exc))
        finally:
            if pending_preview is not None:
                try:
                    pending_preview.unlink(missing_ok=True)
                except Exception:
                    pass

    def _add_user_content_from_block(self, kind):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("현재 블록에서 사용자 항목 추가")
            return
        title = self._ask_user_item_title(kind)
        if not title:
            return
        pending = self.user_content_store.pending_file_path(".hwpx")
        try:
            ok, msg = self.hwp.save_selected_block(str(pending), format_name="HWPX")
            if not ok:
                messagebox.showerror("현재 블록 저장 실패", msg)
                return
            preview, preview_message, pending_preview = self._create_pending_user_preview(kind, pending)
            self.user_content_store.add_file(kind, title, pending, preview_path=preview)
            self._thumb_cache.clear()
            self._rebuild_user_content_tab(kind)
            item_name = self._user_kind_labels(kind)[0]
            self.status_var.set(f"현재 블록을 내 {item_name}으로 추가: {title}")
            if preview is None:
                self._show_preview_generation_warning(item_name, preview_message)
        except (UserContentError, OSError) as exc:
            messagebox.showerror("사용자 항목 추가 실패", str(exc))
        finally:
            for temporary in (locals().get("pending_preview"), pending):
                if temporary is None:
                    continue
                try:
                    temporary.unlink(missing_ok=True)
                except Exception:
                    pass

    def open_user_content_preview_dialog(self, kind, item, owner=None, on_saved=None):
        if kind not in ("style", "form"):
            return
        owner = owner or self
        item_name = self._user_kind_labels(kind)[0]
        try:
            if owner is not self:
                owner.grab_release()
        except Exception:
            pass

        win = tk.Toplevel(owner)
        win.title(f"{item_name} 미리보기")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(owner)
            win.attributes("-topmost", bool(self.var_top.get()))
            win.grab_set()
        except Exception:
            pass

        body = ttk.Frame(win, padding=(14, 14, 14, 8))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=item.get("title", ""), font=tkfont.Font(size=10, weight="bold")).pack(anchor="w", pady=(0, 8))
        preview_area = tk.Frame(body, bg=WHITE, width=360, height=235, highlightthickness=1, highlightbackground=BORDER)
        preview_area.pack(fill="x")
        preview_area.pack_propagate(False)
        status = tk.StringVar(value="")
        ttk.Label(body, textvariable=status, foreground=TEXT_MUTED, wraplength=360).pack(anchor="w", pady=(8, 0))

        def draw_preview():
            for child in preview_area.winfo_children():
                child.destroy()
            current = next(
                (entry for entry in self.user_content_store.list_items(kind) if entry.get("id") == item.get("id")),
                item,
            )
            image = self._load_thumb_any(current.get("thumb", ""), (340, 215))
            if image is None:
                tk.Label(preview_area, text="등록된 미리보기가 없습니다.", bg=WHITE, fg=TEXT_MUTED).pack(expand=True)
            else:
                label = tk.Label(preview_area, image=image, bg=WHITE)
                label.image = image
                label.pack(expand=True)

        def saved(message):
            self._thumb_cache.clear()
            self._rebuild_user_content_tab(kind)
            draw_preview()
            status.set(message)
            if callable(on_saved):
                on_saved()

        def auto_generate():
            source = item.get("file", "")
            preview, message, pending_preview = self._create_pending_user_preview(kind, source)
            try:
                if preview is None:
                    messagebox.showerror("미리보기 생성 실패", message, parent=win)
                    return
                self.user_content_store.update_preview(kind, item["id"], preview)
                saved("한글 파일에서 미리보기를 다시 만들었습니다.")
            except (UserContentError, OSError) as exc:
                messagebox.showerror("미리보기 저장 실패", str(exc), parent=win)
            finally:
                try:
                    pending_preview.unlink(missing_ok=True)
                except Exception:
                    pass

        def choose_image():
            try:
                win.grab_release()
            except Exception:
                pass
            selected = filedialog.askopenfilename(
                parent=win,
                title="미리보기 이미지 선택",
                filetypes=(("이미지", "*.png *.jpg *.jpeg *.bmp *.gif"), ("모든 파일", "*.*")),
            )
            try:
                win.grab_set()
            except Exception:
                pass
            if not selected:
                return
            try:
                self.user_content_store.update_preview(kind, item["id"], selected)
                saved("선택한 이미지로 미리보기를 변경했습니다.")
            except (UserContentError, OSError) as exc:
                messagebox.showerror("미리보기 변경 실패", str(exc), parent=win)

        def remove_preview():
            if not messagebox.askyesno("미리보기 삭제", "현재 미리보기를 삭제할까요?", parent=win):
                return
            try:
                self.user_content_store.update_preview(kind, item["id"], None)
                saved("미리보기를 삭제했습니다.")
            except UserContentError as exc:
                messagebox.showerror("미리보기 삭제 실패", str(exc), parent=win)

        def close():
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()
            try:
                if owner is not self and owner.winfo_exists():
                    owner.grab_set()
            except Exception:
                pass

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="자동 다시 만들기", style="Primary.TButton", command=auto_generate).pack(fill="x", pady=(0, 6))
        ttk.Button(buttons, text="이미지에서 선택", command=choose_image).pack(fill="x", pady=(0, 6))
        ttk.Button(buttons, text="미리보기 삭제", command=remove_preview).pack(fill="x")
        footer = ttk.Frame(win, padding=(14, 4, 14, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="닫기", command=close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda _event: close())
        draw_preview()
        self._center_toplevel(win, 410, 455)

    def open_user_content_manager(self, kind):
        item_name = self._user_kind_labels(kind)[0]
        win = tk.Toplevel(self)
        win.title(f"사용자 {item_name} 관리")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(self)
            win.attributes("-topmost", bool(self.var_top.get()))
            win.grab_set()
        except Exception:
            pass

        body = ttk.Frame(win, padding=(14, 14, 14, 8))
        body.pack(fill="both", expand=True)
        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(list_frame, exportselection=False, activestyle="none")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(10, 0))
        edit_text = "수정" if kind == "page" else "이름 변경"
        edit_button = ttk.Button(controls, text=edit_text)
        edit_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        preview_button = None
        if kind in ("style", "form"):
            preview_button = ttk.Button(controls, text="미리보기")
            preview_button.pack(side="left", fill="x", expand=True, padx=4)
        delete_button = ttk.Button(controls, text="삭제", style="Danger.TButton")
        delete_button.pack(side="left", fill="x", expand=True, padx=(4, 0))

        current_items = []

        def selected_item():
            selection = listbox.curselection()
            if not selection or not current_items:
                return None
            index = int(selection[0])
            return current_items[index] if 0 <= index < len(current_items) else None

        def refresh(select_index=0):
            nonlocal current_items
            current_items = self.user_content_store.list_items(kind)
            listbox.delete(0, "end")
            if current_items:
                for item in current_items:
                    listbox.insert("end", item.get("title", ""))
                index = max(0, min(select_index, len(current_items) - 1))
                listbox.selection_set(index)
                listbox.activate(index)
                edit_button.configure(state="normal")
                if preview_button is not None:
                    preview_button.configure(state="normal")
                delete_button.configure(state="normal")
            else:
                listbox.insert("end", "등록된 사용자 항목이 없습니다.")
                edit_button.configure(state="disabled")
                if preview_button is not None:
                    preview_button.configure(state="disabled")
                delete_button.configure(state="disabled")
            win.after_idle(
                lambda: self._set_scrollbar_needed(scrollbar, listbox.size() > 10)
            )

        def edit_selected():
            item = selected_item()
            if item is None:
                return
            if kind == "page":
                win.destroy()
                self.open_page_preset_dialog(item)
                return
            new_title = self._ask_user_item_title(
                kind,
                initial=item.get("title", ""),
                owner=win,
                button_text="저장",
            )
            if not new_title:
                return
            try:
                self.user_content_store.update_item(kind, item["id"], title=new_title)
                self._rebuild_user_content_tab(kind)
                refresh(listbox.curselection()[0] if listbox.curselection() else 0)
            except UserContentError as exc:
                messagebox.showerror("이름 변경 실패", str(exc), parent=win)

        def edit_preview():
            item = selected_item()
            if item is None or kind not in ("style", "form"):
                return
            selected_index = int(listbox.curselection()[0]) if listbox.curselection() else 0
            self.open_user_content_preview_dialog(
                kind,
                item,
                owner=win,
                on_saved=lambda: refresh(selected_index),
            )

        def delete_selected():
            item = selected_item()
            if item is None:
                return
            if not messagebox.askyesno(
                f"{item_name} 삭제",
                f"'{item.get('title', '')}' 항목을 삭제할까요?",
                parent=win,
            ):
                return
            try:
                index = int(listbox.curselection()[0]) if listbox.curselection() else 0
                self.user_content_store.delete_item(kind, item["id"])
                self._rebuild_user_content_tab(kind)
                refresh(index)
            except UserContentError as exc:
                messagebox.showerror("삭제 실패", str(exc), parent=win)

        edit_button.configure(command=edit_selected)
        if preview_button is not None:
            preview_button.configure(command=edit_preview)
        delete_button.configure(command=delete_selected)
        listbox.bind("<Double-Button-1>", lambda _event: edit_selected())

        footer = ttk.Frame(win, padding=(14, 4, 14, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="닫기", command=win.destroy).pack(side="right")
        refresh()
        self._center_toplevel(win, 420, 370)


    def _paint_page_margin_preview(self, canvas, margins):
        canvas.delete("all")
        try:
            width = max(100, int(float(canvas.cget("width"))))
            height = max(130, int(float(canvas.cget("height"))))
        except Exception:
            width, height = 140, 175
        page_height = height - 12
        page_width = min(width - 18, int(page_height / 1.414))
        page_height = int(page_width * 1.414)
        x0 = (width - page_width) // 2
        y0 = (height - page_height) // 2
        x1 = x0 + page_width
        y1 = y0 + page_height
        canvas.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#303640", width=1)

        def value(key, default=0.0):
            try:
                raw = margins[key].get() if hasattr(margins[key], "get") else margins[key]
                return max(0.0, float(str(raw).replace(",", ".")))
            except Exception:
                return default

        left_mm = min(100.0, value("left") + value("gutter"))
        right_mm = min(100.0, value("right"))
        top_mm = min(120.0, value("top"))
        bottom_mm = min(120.0, value("bottom"))
        header_mm = min(100.0, value("header"))
        footer_mm = min(100.0, value("footer"))
        inner_left = min(x1 - 12, x0 + max(5, page_width * left_mm / 210.0))
        inner_right = max(inner_left + 8, x1 - max(5, page_width * right_mm / 210.0))
        inner_top = min(y1 - 16, y0 + max(6, page_height * top_mm / 297.0))
        inner_bottom = max(inner_top + 12, y1 - max(6, page_height * bottom_mm / 297.0))
        header_y = min(inner_bottom - 6, y0 + max(4, page_height * header_mm / 297.0))
        footer_y = max(inner_top + 6, y1 - max(4, page_height * footer_mm / 297.0))

        canvas.create_rectangle(inner_left, inner_top, inner_right, inner_bottom, outline="#8b96a5", dash=(2, 2))
        canvas.create_line(inner_left, header_y, inner_right, header_y, fill="#c1c7d0")
        canvas.create_line(inner_left, footer_y, inner_right, footer_y, fill="#c1c7d0")
        text_top = max(inner_top + 8, header_y + 7)
        text_bottom = min(inner_bottom - 7, footer_y - 7)
        y = text_top
        line_index = 0
        while y <= text_bottom:
            shorten = 10 if line_index % 4 == 3 else 0
            canvas.create_line(inner_left + 4, y, max(inner_left + 8, inner_right - 4 - shorten), y, fill="#aab2bd")
            y += 8
            line_index += 1

    def _paint_page_card_preview(self, canvas, margins):
        canvas.delete("all")
        try:
            width = max(100, int(float(canvas.cget("width"))))
            height = max(100, int(float(canvas.cget("height"))))
        except Exception:
            width, height = 118, 111

        def value(key, default=0.0):
            try:
                raw = margins[key].get() if hasattr(margins[key], "get") else margins[key]
                return max(0.0, float(str(raw).replace(",", ".")))
            except Exception:
                return default

        def label(key):
            return f"{value(key):g}"

        page_width = min(54, width - 52)
        page_height = min(70, height - 34)
        x0 = (width - page_width) // 2
        y0 = max(18, (height - page_height) // 2)
        x1 = x0 + page_width
        y1 = y0 + page_height
        value_font = ("맑은 고딕", 8, "bold")
        page_font = ("맑은 고딕", 10, "bold")

        canvas.create_text(width // 2, 7, text=label("top"), font=value_font, fill="#111827")
        canvas.create_text(x0 - 11, (y0 + y1) // 2, text=label("left"), font=value_font, fill="#111827")
        canvas.create_text(x1 + 11, (y0 + y1) // 2, text=label("right"), font=value_font, fill="#111827")
        canvas.create_text(width // 2, height - 7, text=label("bottom"), font=value_font, fill="#111827")
        canvas.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#303640", width=1)
        canvas.create_text(width // 2, y0 + 9, text=label("header"), font=value_font, fill="#111827")
        canvas.create_text(width // 2, (y0 + y1) // 2, text="용지", font=page_font, fill="#111827")
        canvas.create_text(width // 2, y1 - 9, text=label("footer"), font=value_font, fill="#111827")
        if value("gutter") > 0:
            canvas.create_line(x0 + 4, y0 + 4, x0 + 4, y1 - 4, fill="#2b61aa", width=2)

    def open_page_preset_dialog(self, item=None):
        editing = bool(item)
        win = tk.Toplevel(self)
        win.title("사용자 편집용지 수정" if editing else "내 편집용지 추가")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(self)
            win.attributes("-topmost", bool(self.var_top.get()))
            win.grab_set()
        except Exception:
            pass

        outer = ttk.Frame(win, padding=(14, 14, 14, 8))
        outer.pack(fill="both", expand=True)
        name_row = ttk.Frame(outer)
        name_row.pack(fill="x", pady=(0, 10))
        ttk.Label(name_row, text="편집용지 이름").pack(side="left", padx=(0, 8))
        title_var = tk.StringVar(value=(item or {}).get("title", ""))
        title_entry = ttk.Entry(name_row, textvariable=title_var)
        title_entry.pack(side="left", fill="x", expand=True)

        margin_box = ttk.LabelFrame(outer, text="용지 여백", padding=(10, 8))
        margin_box.pack(fill="both", expand=True)
        for column in range(3):
            margin_box.columnconfigure(column, weight=1)

        initial = dict(DEFAULT_PAGE_MARGINS)
        if item and isinstance(item.get("margins"), dict):
            initial.update(item["margins"])
        margin_vars = {
            field: tk.StringVar(value=f"{float(initial[field]):.1f}")
            for field in PAGE_MARGIN_FIELDS
        }

        def make_control(parent, label, key):
            row = ttk.Frame(parent)
            row.pack(anchor="center", pady=2)
            ttk.Label(row, text=label, width=7, anchor="e").pack(side="left", padx=(0, 4))
            spin = ttk.Spinbox(
                row,
                from_=0.0,
                to=100.0,
                increment=0.1,
                format="%.1f",
                width=7,
                textvariable=margin_vars[key],
            )
            spin.pack(side="left")
            ttk.Label(row, text="mm", width=3, anchor="w").pack(side="left", padx=(4, 0))
            return spin

        top_group = ttk.Frame(margin_box)
        top_group.grid(row=0, column=1, sticky="s", pady=(0, 5))
        make_control(top_group, "위쪽", "top")
        make_control(top_group, "머리말", "header")

        left_group = ttk.Frame(margin_box)
        left_group.grid(row=1, column=0, sticky="e", padx=(0, 5))
        make_control(left_group, "왼쪽", "left")
        make_control(left_group, "제본", "gutter")

        preview = tk.Canvas(margin_box, width=140, height=175, bg=SURFACE_ALT, highlightthickness=1, highlightbackground=BORDER)
        preview.grid(row=1, column=1, padx=5, pady=3)

        right_group = ttk.Frame(margin_box)
        right_group.grid(row=1, column=2, sticky="w", padx=(5, 0))
        make_control(right_group, "오른쪽", "right")

        bottom_group = ttk.Frame(margin_box)
        bottom_group.grid(row=2, column=1, sticky="n", pady=(5, 0))
        make_control(bottom_group, "꼬리말", "footer")
        make_control(bottom_group, "아래쪽", "bottom")

        def update_preview(*_args):
            self._paint_page_margin_preview(preview, margin_vars)

        for variable in margin_vars.values():
            variable.trace_add("write", update_preview)
        update_preview()

        footer = ttk.Frame(win, padding=(14, 6, 14, 14))
        footer.pack(fill="x")

        def close():
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        def save():
            title = " ".join(title_var.get().strip().split())
            try:
                margins = {
                    key: float(variable.get().strip().replace(",", "."))
                    for key, variable in margin_vars.items()
                }
                if editing:
                    self.user_content_store.update_item("page", item["id"], title=title, margins=margins)
                    status = f"사용자 편집용지 수정 완료: {title}"
                else:
                    self.user_content_store.add_page(title, margins)
                    status = f"내 편집용지 추가 완료: {title}"
                self._rebuild_user_content_tab("page")
                self.status_var.set(status)
                close()
            except (UserContentError, ValueError) as exc:
                messagebox.showerror("편집용지 저장 실패", str(exc), parent=win)

        ttk.Button(footer, text="취소", command=close).pack(side="right")
        ttk.Button(
            footer,
            text="저장" if editing else "등록",
            style="Primary.TButton",
            command=save,
        ).pack(side="right", padx=(0, 6))
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda _event: close())
        self._center_toplevel(win, 500, 500)
        win.after(60, title_entry.focus_set)

    def _set_clickable_cursor(self, widget, card=None):
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._set_clickable_cursor(child, card)
    def _build_cards_grid(
        self,
        parent,
        items,
        cols=2,
        card_w=230,
        card_h=170,
        card_context: str | None = None,
        user_kind: str | None = None,
        preview_zoom: float = 1.0,
        preview_anchor_y: float = 0.5,
    ):
        _canvas, inner = self._make_scroll_grid(parent)
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        title_font = tkfont.Font(size=10, weight="bold")
        for idx, it in enumerate(items):
            r, c = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=card_w, height=card_h, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=r, column=c, padx=5, pady=6, sticky="n")
            card.grid_propagate(False)
            title = it.get("title", f"항목{idx+1}")
            is_user_item = bool(it.get("user_item"))
            if is_user_item:
                file_abs = os.path.abspath(it.get("file", "")) if it.get("file") else ""
                thumb_abs = os.path.abspath(it.get("thumb", "")) if it.get("thumb") else ""
            else:
                file_abs = resource_path(it.get("file", "")) if it.get("file") else ""
                thumb_abs = resource_path(it.get("thumb", "")) if it.get("thumb") else ""
            img = self._load_thumb_any(
                thumb_abs,
                (card_w-20, card_h-45),
                zoom=preview_zoom if is_user_item else 1.0,
                anchor_y=preview_anchor_y if is_user_item else 0.5,
            )
            img_area = tk.Frame(card, bg=WHITE, width=card_w, height=card_h-45)
            img_area.pack(fill="x", padx=6, pady=(6, 2))
            img_area.pack_propagate(False)
            if img is not None:
                lbl = tk.Label(img_area, image=img, bg=WHITE)
                lbl.image = img
                lbl.pack(expand=True)
            elif is_user_item:
                placeholder = tk.Canvas(img_area, bg=WHITE, highlightthickness=0, width=card_w-18, height=card_h-49)
                placeholder.pack(expand=True, fill="both")
                page_w = min(64, max(42, card_w // 3))
                page_h = min(78, max(52, card_h - 62))
                x0 = (card_w - 18 - page_w) // 2
                y0 = max(4, (card_h - 49 - page_h) // 2)
                placeholder.create_rectangle(x0, y0, x0 + page_w, y0 + page_h, fill="#fbfcfd", outline=BORDER_STRONG)
                for line in range(4):
                    y = y0 + 15 + line * 9
                    placeholder.create_line(x0 + 9, y, x0 + page_w - 9, y, fill="#aab2bd")
            else:
                tk.Label(img_area, text="", bg=WHITE).pack(expand=True)
            tk.Label(
                card,
                text=title,
                bg=WHITE,
                font=title_font,
                justify="center",
                wraplength=card_w - 12,
            ).pack(pady=(0, 0))
            if card_context == "style":
                self.style_card_items.append({"card": card, "title": title, "index": idx})

            def _do_action(p=file_abs, t=title):
                if self.is_kedufine_mode():
                    if card_context == "style" and t in KEDUFIN_SUPPORTED_BLOCK_TITLES:
                        ok, msg = self.wxs.insert_file(p)
                        if ok:
                            self.status_var.set(f"기안창 서식 삽입: {t}")
                        else:
                            messagebox.showerror("서식 삽입 실패", msg)
                        return
                    self._show_kedufine_unsupported("서식/양식 삽입")
                    return
                ok, msg = self.hwp.insert_file(p)
                if ok:
                    self.status_var.set(f"삽입: {t}")
                else:
                    messagebox.showerror("오류", msg)

            bind_click_recursive(card, _do_action)
            self._set_clickable_cursor(card)

        if user_kind:
            action_row = max(1, (len(items) + cols - 1) // cols)
            bar = self._build_user_action_bar(inner, user_kind, action_row, cols)
            if user_kind == "style":
                self.style_user_actions_bar = bar

    def _rebuild_user_character_tab(self):
        tab = getattr(self, "tab_chars", None)
        if tab is None:
            return
        for child in tab.winfo_children():
            child.destroy()
        self._build_chars_scroll(tab)

    def open_user_symbol_editor(self, item=None, owner=None):
        owner = owner or self
        editing = bool(item)
        try:
            if owner is not self:
                owner.grab_release()
        except Exception:
            pass
        win = tk.Toplevel(owner)
        win.title("내 문자표 수정" if editing else "내 문자표 추가")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(owner)
            win.attributes("-topmost", bool(self.var_top.get()))
            win.grab_set()
        except Exception:
            pass

        body = ttk.Frame(win, padding=(14, 14, 14, 8))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="문자표 이름").pack(anchor="w", pady=(0, 5))
        title_var = tk.StringVar(value=(item or {}).get("title", ""))
        title_entry = ttk.Entry(body, textvariable=title_var)
        title_entry.pack(fill="x", pady=(0, 12))
        ttk.Label(body, text="문자·기호", font=tkfont.Font(size=10, weight="bold")).pack(anchor="w")
        ttk.Label(body, text="공백, 쉼표 또는 줄바꿈으로 구분하세요.", foreground=TEXT_MUTED).pack(anchor="w", pady=(2, 6))
        values = tk.Text(body, height=9, wrap="word", relief="solid", borderwidth=1)
        values.pack(fill="both", expand=True)
        values.insert("1.0", "\n".join(str(value) for value in (item or {}).get("chars", [])))

        def close():
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()
            try:
                if owner is not self and owner.winfo_exists():
                    owner.grab_set()
            except Exception:
                pass

        def save():
            try:
                if editing:
                    self.user_content_store.update_symbol_group(
                        item["id"], title_var.get(), values.get("1.0", "end-1c")
                    )
                    message = f"내 문자표 수정 완료: {title_var.get().strip()}"
                else:
                    self.user_content_store.add_symbol_group(
                        title_var.get(), values.get("1.0", "end-1c")
                    )
                    message = f"내 문자표 추가 완료: {title_var.get().strip()}"
                self._rebuild_user_character_tab()
                self.status_var.set(message)
                close()
            except UserContentError as exc:
                messagebox.showerror("문자표 저장 실패", str(exc), parent=win)

        footer = ttk.Frame(win, padding=(14, 6, 14, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="취소", command=close).pack(side="right")
        ttk.Button(footer, text="저장" if editing else "등록", style="Primary.TButton", command=save).pack(side="right", padx=(0, 6))
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda _event: close())
        self._center_toplevel(win, 430, 390)
        win.after(60, title_entry.focus_set)
        win.wait_window()

    def open_user_symbol_manager(self):
        win = tk.Toplevel(self)
        win.title("내 문자표 관리")
        win.configure(bg=APP_BG)
        win.resizable(False, False)
        try:
            win.transient(self)
            win.attributes("-topmost", bool(self.var_top.get()))
            win.grab_set()
        except Exception:
            pass
        body = ttk.Frame(win, padding=(14, 14, 14, 8))
        body.pack(fill="both", expand=True)
        listbox = tk.Listbox(body, exportselection=False, activestyle="none")
        listbox.pack(fill="both", expand=True)
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(10, 0))
        edit_button = ttk.Button(controls, text="수정")
        edit_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        delete_button = ttk.Button(controls, text="삭제", style="Danger.TButton")
        delete_button.pack(side="left", fill="x", expand=True, padx=(4, 0))
        current_items = []

        def selected_item():
            selection = listbox.curselection()
            if not selection or not current_items:
                return None
            index = int(selection[0])
            return current_items[index] if 0 <= index < len(current_items) else None

        def refresh(select_index=0):
            nonlocal current_items
            current_items = self.user_content_store.list_symbol_groups()
            listbox.delete(0, "end")
            if current_items:
                for current in current_items:
                    listbox.insert("end", current.get("title", ""))
                index = max(0, min(select_index, len(current_items) - 1))
                listbox.selection_set(index)
                listbox.activate(index)
                edit_button.configure(state="normal")
                delete_button.configure(state="normal")
            else:
                listbox.insert("end", "등록된 사용자 문자표가 없습니다.")
                edit_button.configure(state="disabled")
                delete_button.configure(state="disabled")

        def edit_selected():
            current = selected_item()
            if current is not None:
                self.open_user_symbol_editor(current, owner=win)
                refresh()

        def delete_selected():
            current = selected_item()
            if current is None:
                return
            if not messagebox.askyesno("문자표 삭제", f"'{current.get('title', '')}' 문자표를 삭제할까요?", parent=win):
                return
            index = int(listbox.curselection()[0]) if listbox.curselection() else 0
            try:
                self.user_content_store.delete_symbol_group(current["id"])
                self._rebuild_user_character_tab()
                refresh(index)
            except UserContentError as exc:
                messagebox.showerror("문자표 삭제 실패", str(exc), parent=win)

        edit_button.configure(command=edit_selected)
        delete_button.configure(command=delete_selected)
        listbox.bind("<Double-Button-1>", lambda _event: edit_selected())
        footer = ttk.Frame(win, padding=(14, 4, 14, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="닫기", command=win.destroy).pack(side="right")
        refresh()
        self._center_toplevel(win, 420, 370)

    def _build_chars_scroll(self, parent):
        _canvas, inner = self._make_scroll_grid(parent)
        actions = ttk.Frame(inner, padding=(4, 4, 4, 8))
        actions.pack(fill="x")
        ttk.Button(actions, text="내 문자표 추가", style="Primary.TButton", command=self.open_user_symbol_editor).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(actions, text="내 문자표 관리", command=self.open_user_symbol_manager).pack(side="left", fill="x", expand=True, padx=(4, 0))

        groups = [
            (f"내 문자표 · {item.get('title', '')}", item.get("chars", []))
            for item in self.user_content_store.list_symbol_groups()
        ]
        if isinstance(self.symbols_text, dict):
            groups.extend(self.symbols_text.items())
        if not groups:
            ttk.Label(inner, text="(문자표 데이터 없음)", background=WHITE).pack(anchor="w")
            return
        for group_name, chars in groups:
            box = ttk.LabelFrame(inner, text=str(group_name), style="Section.TLabelframe", padding=8)
            box.pack(fill="x", pady=6)
            grid = ttk.Frame(box)
            grid.pack(fill="x")
            cols = 10
            for i, ch in enumerate(chars or []):
                r, c = divmod(i, cols)
                ttk.Button(grid, text=str(ch), width=3, style="Symbol.TButton", command=lambda x=str(ch): self.on_insert_text(x)).grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
            for c in range(cols):
                grid.columnconfigure(c, weight=1)
    def _build_symbol_tabs(self, parent):
        self.symbol_nb = None
        self.symbol_tab_defs = []
        if not os.path.isdir(self.symbols_root):
            return
        nb2 = ttk.Notebook(parent, style="Sub.TNotebook", takefocus=0)
        self.symbol_nb = nb2
        nb2.pack(fill="both", expand=True)
        groups = []
        for name in sorted(os.listdir(self.symbols_root)):
            p = os.path.join(self.symbols_root, name)
            if os.path.isdir(p):
                groups.append((name, p))
        for gname, gpath in groups:
            tab = ttk.Frame(nb2, padding=8)
            self.symbol_tab_defs.append((gname, tab, gname))
            self._build_symbol_group(tab, gpath)
        self.symbol_tab_order = self._normalize_tab_order(self.symbol_tab_order, self.symbol_tab_defs)
        for _key, _tab, _label in self._ordered_tab_defs(self.symbol_tab_defs, self.symbol_tab_order):
            nb2.add(_tab, text=_label)
    def _build_symbol_group(self, parent, folder):
        canvas, inner = self._make_scroll_grid(parent)
        cols = 2
        card_w = min(self.card_w, 218)
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        title_font = tkfont.Font(size=10, weight="bold")
        files = [fn for fn in sorted(os.listdir(folder)) if is_image_file(fn)]
        for idx, fn in enumerate(files):
            r, c = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=card_w, height=self.card_h, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=r, column=c, padx=5, pady=6, sticky="n")
            card.grid_propagate(False)
            f_abs = os.path.join(folder, fn)
            title = os.path.splitext(fn)[0]
            img = self._load_thumb_any(f_abs, (card_w-20, self.card_h-55))
            img_area = tk.Frame(card, bg=WHITE, width=card_w, height=self.card_h-55)
            img_area.pack(fill="x", padx=6, pady=(6, 2))
            img_area.pack_propagate(False)
            if img is not None:
                lbl = tk.Label(img_area, image=img, bg=WHITE)
                lbl.image = img
                lbl.pack(expand=True)
            else:
                tk.Label(img_area, text="", bg=WHITE).pack(expand=True)
            tk.Label(card, text=title, bg=WHITE, font=title_font).pack(pady=(2, 0))
            def _do(p=f_abs, t=title):
                if self.is_kedufine_mode():
                    self._show_kedufine_unsupported("심볼 삽입")
                    return
                ok, msg = self.hwp.insert_picture_clipboard(p)
                if ok:
                    self.status_var.set(f"심볼 삽입: {t}")
                else:
                    messagebox.showerror("이미지 삽입 실패", msg)
            bind_click_recursive(card, _do)
            self._set_clickable_cursor(card)

    def _build_page_cards(self, parent):
        _canvas, inner = self._make_scroll_grid(parent)
        cols = 3
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        page_card_w, page_card_h = 142, 170
        preview_w, preview_h = page_card_w - 20, page_card_h - 55
        title_font = tkfont.Font(size=10, weight="bold")
        items = self._combined_content_items("page")
        for idx, item in enumerate(items):
            row, column = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=page_card_w, height=page_card_h, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=row, column=column, padx=5, pady=6, sticky="n")
            card.grid_propagate(False)
            title = item.get("title", f"편집용지 {idx+1}")
            is_user_item = bool(item.get("user_item"))
            thumb_name = item.get("thumb", "")
            thumb_abs = resource_path(os.path.join(self.page_thumbs_root_rel, thumb_name)) if thumb_name else ""
            image = self._load_thumb_any(thumb_abs, (preview_w, preview_h)) if thumb_name else None
            image_area = tk.Frame(card, bg=WHITE, width=page_card_w, height=preview_h)
            image_area.pack(fill="x", padx=6, pady=(6, 2))
            image_area.pack_propagate(False)
            if image is not None:
                label = tk.Label(image_area, image=image, bg=WHITE)
                label.image = image
                label.pack(expand=True)
            elif is_user_item:
                preview = tk.Canvas(image_area, width=preview_w - 4, height=preview_h - 4, bg=WHITE, highlightthickness=0)
                preview.pack(expand=True)
                self._paint_page_card_preview(preview, item.get("margins", DEFAULT_PAGE_MARGINS))
            else:
                tk.Label(image_area, text="", bg=WHITE).pack(expand=True)
            tk.Label(
                card,
                text=title,
                bg=WHITE,
                font=title_font,
                justify="center",
                wraplength=page_card_w - 12,
            ).pack(pady=(2, 0))

            def apply_page(selected=item, selected_title=title):
                if self.is_kedufine_mode():
                    self._show_kedufine_unsupported("편집용지 적용")
                    return
                if selected.get("user_item"):
                    ok, msg = self.hwp.apply_page_margins(selected.get("margins", {}))
                else:
                    ok, msg = self.hwp.apply_basic_report_page_setup()
                if ok:
                    self.status_var.set(f"편집용지 적용: {selected_title}")
                else:
                    self.status_var.set("편집용지 적용 실패")
                    messagebox.showerror("편집용지 적용 실패", msg)

            bind_click_recursive(card, apply_page)
            self._set_clickable_cursor(card)

        action_row = max(1, (len(items) + cols - 1) // cols)
        self._build_user_action_bar(inner, "page", action_row, cols)

    def _build_edit_tools(self, parent):
        nb2 = ttk.Notebook(parent, style="Sub.TNotebook", takefocus=0)
        self.edit_nb = nb2
        nb2.pack(fill="both", expand=True)
        tab_table = ttk.Frame(nb2, padding=8)
        tab_cell  = ttk.Frame(nb2, padding=8)
        tab_text  = ttk.Frame(nb2, padding=8)
        self.edit_tab_defs = [
            ("table", tab_table, "표 작업"),
            ("cell", tab_cell, "셀 정리"),
            ("text", tab_text, "글자 작업"),
        ]
        self.edit_tab_order = self._normalize_tab_order(self.edit_tab_order, self.edit_tab_defs)
        for _key, _tab, _label in self._ordered_tab_defs(self.edit_tab_defs, self.edit_tab_order):
            nb2.add(_tab, text=_label)
        self._build_table_tools_cards(tab_table)
        self._build_cell_cleaner_tools(tab_cell)
        self._build_text_tools_cards(tab_text)
    def _run_table_tool_action(self, action_id, title):
        bridge = self.wxs if self.is_kedufine_mode() else self.hwp
        ok, msg = bridge.apply_table_tool(action_id)
        if ok:
            target = "기안창" if self.is_kedufine_mode() else "한글"
            self.status_var.set(f"{target} 표 작업: {title}")
            self._restore_kedufine_focus_later()
            return True
        messagebox.showerror("표 작업 실패", msg)
        return False

    def _build_table_tools_cards(self, parent):
        canvas, inner = self._make_scroll_grid(parent)
        cols = 4
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        title_font = tkfont.Font(size=9, weight="bold")
        items = self.table_tools or []
        if not items:
            ttk.Label(inner, text="(table_tools가 비어있음)", background=WHITE).grid(row=0, column=0, sticky="w")
        CARD_W, CARD_H = 108, 120
        PREV_H = 70
        TITLE_H = 36
        for idx, it in enumerate(items):
            r, c = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=CARD_W, height=CARD_H, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=r, column=c, padx=4, pady=6, sticky="n")
            card.grid_propagate(False)
            title = force_two_lines(it.get("title", f"표작업{idx+1}"))
            action_id = it.get("action_id", "")
            thumb_abs = resource_path(it.get("thumb", "")) if it.get("thumb") else ""
            img = self._load_thumb_any(
                thumb_abs,
                (CARD_W-18, PREV_H),
                vertical_margin_ratio=0.5,
            )
            img_area = tk.Frame(card, bg=WHITE, width=CARD_W, height=PREV_H)
            img_area.pack(padx=4, pady=(6, 2))
            img_area.pack_propagate(False)
            if img is not None:
                lbl = tk.Label(img_area, image=img, bg=WHITE)
                lbl.image = img
                lbl.pack(expand=True)
            else:
                tk.Label(img_area, text="", bg=WHITE).pack(expand=True)
            title_area = tk.Frame(card, bg=WHITE, width=CARD_W, height=TITLE_H)
            title_area.pack(padx=4, pady=(0, 6))
            title_area.pack_propagate(False)
            lbl_title = tk.Label(title_area, text=title, bg=WHITE, font=title_font, justify="center", anchor="center", wraplength=CARD_W-12)
            lbl_title.pack(expand=True, fill="both", padx=2)
            def _do(aid=action_id, t=title.replace("\n", " ")):
                self._run_table_tool_action(aid, t)
            bind_click_recursive(card, _do)
            self._set_clickable_cursor(card)

        picture_row = max(1, (len(items) + cols - 1) // cols) if not items else (len(items) + cols - 1) // cols
        self.table_image_section = ttk.Frame(inner)
        self.table_image_section.grid(
            row=picture_row,
            column=0,
            columnspan=cols,
            sticky="ew",
            padx=4,
            pady=(10, 4),
        )
        ttk.Separator(self.table_image_section).pack(fill="x", pady=(0, 10))
        picture_card = tk.Frame(
            self.table_image_section,
            bg=WHITE,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        picture_card.pack(fill="x")
        tk.Label(
            picture_card,
            text="그림 넣기",
            bg=WHITE,
            fg=TEXT_PRIMARY,
            font=tkfont.Font(size=10, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(
            picture_card,
            textvariable=self.cell_range_var,
            bg=WHITE,
            fg=TEXT_MUTED,
            font=tkfont.Font(size=9),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 7))
        mode_row = tk.Frame(picture_card, bg=WHITE)
        mode_row.pack(fill="x", padx=8, pady=(0, 8))
        for label, value in (
            ("셀 안에 맞춤", IMAGE_SIZE_FIT_INSIDE),
            ("셀 너비에 맞춤", IMAGE_SIZE_FIT_WIDTH),
            ("셀 크기에 맞춤", IMAGE_SIZE_STRETCH_TO_CELL),
        ):
            ttk.Radiobutton(
                mode_row,
                text=label,
                value=value,
                variable=self.cell_image_size_mode,
                takefocus=0,
            ).pack(side="left", expand=True)
        image_action = feature_registry.TABLE_INSERT_IMAGES_ACTION
        self.cell_image_button = ttk.Button(
            picture_card,
            text=image_action.label,
            command=self._feature_button_command(image_action),
            style="Primary.TButton",
            state="disabled",
        )
        self.cell_image_button.pack(fill="x", padx=12, pady=(0, 6))
        refit_action = feature_registry.TABLE_REFIT_IMAGES_ACTION
        self.cell_image_refit_button = ttk.Button(
            picture_card,
            text=refit_action.label,
            command=self._feature_button_command(refit_action),
            state="disabled",
        )
        self.cell_image_refit_button.pack(fill="x", padx=12, pady=(0, 10))

    def _make_cell_tool_card(self, parent, title: str, desc: str | None = None):
        card = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        card.pack(fill="x", pady=(0, 10))
        tk.Label(
            card,
            text=title,
            bg=WHITE,
            fg=TEXT_PRIMARY,
            font=tkfont.Font(size=10, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 3))
        if desc:
            tk.Label(
                card,
                text=desc,
                bg=WHITE,
                fg=TEXT_MUTED,
                font=tkfont.Font(size=9),
                justify="left",
                anchor="w",
                wraplength=430,
            ).pack(fill="x", padx=12, pady=(0, 8))
        return card

    def _build_cell_cleaner_tools(self, parent):
        _wrap_canvas, inner = self._make_scroll_grid(parent)
        self.cell_action_buttons = []

        range_card = self._make_cell_tool_card(
            inner,
            "1. 적용할 셀 선택",
            "한글 표에서 적용할 셀 범위를 드래그하세요. 선택하면 자동으로 기록됩니다.",
        )
        tk.Label(
            range_card,
            textvariable=self.cell_range_var,
            bg=WHITE,
            fg=TEXT_PRIMARY,
            font=tkfont.Font(size=10, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=430,
        ).pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(
            range_card,
            textvariable=self.cell_status_var,
            bg=WHITE,
            fg=TEXT_MUTED,
            font=tkfont.Font(size=9),
            anchor="w",
            justify="left",
            wraplength=430,
        ).pack(fill="x", padx=12, pady=(0, 10))

        quick_card = self._make_cell_tool_card(
            inner,
            "2. 빠른 정리",
            "선택한 셀에서 자주 생기는 공백과 엑셀 붙여넣기 흔적을 정리합니다.",
        )
        tk.Label(
            quick_card,
            text="엑셀 붙여넣기 흔적 정리",
            bg=WHITE,
            fg=TEXT_PRIMARY,
            font=tkfont.Font(size=9, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 2))
        tk.Label(
            quick_card,
            text="셀 앞뒤 공백과 문단 배경·글자 음영을 없애고 글자색을 검정으로 정리합니다.",
            bg=WHITE,
            fg=TEXT_MUTED,
            font=tkfont.Font(size=9),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 6))
        excel_button = ttk.Button(
            quick_card,
            text=feature_registry.CELL_EXCEL_PASTE_ACTION.label,
            command=self._feature_button_command(feature_registry.CELL_EXCEL_PASTE_ACTION),
            style="Primary.TButton",
        )
        excel_button.pack(fill="x", padx=12, pady=(0, 10))
        self.cell_action_buttons.append(excel_button)
        ttk.Separator(quick_card).pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(
            quick_card,
            text="앞뒤 공백 정리",
            bg=WHITE,
            fg=TEXT_PRIMARY,
            font=tkfont.Font(size=9, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 2))
        tk.Label(
            quick_card,
            text="띄어쓰기는 유지하고 셀 내용 앞뒤의 일반·전각·숨은 공백만 제거합니다.",
            bg=WHITE,
            fg=TEXT_MUTED,
            font=tkfont.Font(size=9),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 6))
        clean_button = ttk.Button(
            quick_card,
            text=feature_registry.CELL_CLEAN_SPACE_ACTION.label,
            command=self._feature_button_command(feature_registry.CELL_CLEAN_SPACE_ACTION),
        )
        clean_button.pack(fill="x", padx=12, pady=(0, 12))
        self.cell_action_buttons.append(clean_button)

        replace_card = self._make_cell_tool_card(
            inner,
            "3. 셀 내용 찾아바꾸기",
            "선택한 모든 셀에서 같은 내용을 찾아 바꿉니다.",
        )
        form = ttk.Frame(replace_card)
        form.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(form, text="찾을 내용", background=WHITE).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.cell_find_var = tk.StringVar()
        self.cell_replace_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.cell_find_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(form, text="바꿀 내용", background=WHITE).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(form, textvariable=self.cell_replace_var).grid(row=1, column=1, sticky="ew", pady=3)
        form.columnconfigure(1, weight=1)
        replace_button = ttk.Button(
            replace_card,
            text=feature_registry.CELL_FIND_REPLACE_ACTION.label,
            command=self._feature_button_command(feature_registry.CELL_FIND_REPLACE_ACTION),
        )
        replace_button.pack(fill="x", padx=12, pady=(0, 12))
        self.cell_action_buttons.append(replace_button)

        add_card = self._make_cell_tool_card(
            inner,
            "4. 셀마다 문자 붙이기",
            "각 셀의 기존 내용 앞이나 뒤에 같은 문자를 추가합니다.",
        )
        add_form = ttk.Frame(add_card)
        add_form.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(add_form, text="추가할 문자", background=WHITE).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.cell_add_text_var = tk.StringVar()
        ttk.Entry(add_form, textvariable=self.cell_add_text_var).grid(row=0, column=1, sticky="ew", pady=3)
        add_form.columnconfigure(1, weight=1)
        add_btns = ttk.Frame(add_card)
        add_btns.pack(fill="x", padx=12, pady=(0, 12))
        prefix_button = ttk.Button(
            add_btns,
            text=feature_registry.CELL_ADD_PREFIX_ACTION.label,
            command=self._feature_button_command(feature_registry.CELL_ADD_PREFIX_ACTION),
        )
        prefix_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        suffix_button = ttk.Button(
            add_btns,
            text=feature_registry.CELL_ADD_SUFFIX_ACTION.label,
            command=self._feature_button_command(feature_registry.CELL_ADD_SUFFIX_ACTION),
        )
        suffix_button.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.cell_action_buttons.extend((prefix_button, suffix_button))
        self._set_cell_actions_enabled(False)

    def _set_cell_actions_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for button in getattr(self, "cell_action_buttons", []):
            try:
                button.configure(state=state)
            except Exception:
                pass
        image_buttons = (
            getattr(self, "cell_image_button", None),
            getattr(self, "cell_image_refit_button", None),
        )
        image_enabled = enabled and not self.is_kedufine_mode()
        for image_button in image_buttons:
            if image_button is None:
                continue
            try:
                image_button.configure(state="normal" if image_enabled else "disabled")
            except Exception:
                pass

    def _is_hwp_window_handle(self, hwnd):
        """한글 편집 영역의 자식 창까지 같은 한글 창으로 판별한다."""
        if win32gui is None or win32process is None:
            return False
        try:
            if not hwnd:
                return False
            title = win32gui.GetWindowText(hwnd) or ""
            cls = win32gui.GetClassName(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = (ui_get_process_path(pid) or "").lower().replace("/", "\\")
            cls_l = cls.lower()
            title_l = title.lower()

            if exe.endswith("\\hwp.exe") or exe.endswith("hwp.exe"):
                return True
            if "hwp" in cls_l:
                return True
            if "- 한글" in title or ".hwp" in title_l or ".hwpx" in title_l:
                return True

            last = ui_get_last_hwp_window()
            if last and int(last.get("pid") or -1) == int(pid):
                return True
            return False
        except Exception:
            return False

    def _foreground_is_hwp_window(self):
        if win32gui is None:
            return False
        try:
            return self._is_hwp_window_handle(win32gui.GetForegroundWindow())
        except Exception:
            return False

    def _pointer_is_over_hwp_window(self):
        if win32gui is None:
            return False
        try:
            point = win32gui.GetCursorPos()
            return self._is_hwp_window_handle(win32gui.WindowFromPoint(point))
        except Exception:
            return False
    def _update_cell_range_label(self):
        if not self.recorded_start or not self.recorded_end:
            self.cell_range_var.set("선택된 범위 없음")
            self.cell_status_var.set("한글 표에서 셀을 드래그하세요.")
            self._set_cell_actions_enabled(False)
            return
        s_col, s_row, _ = self.recorded_start
        e_col, e_row, _ = self.recorded_end
        left_col = min(s_col, e_col)
        right_col = max(s_col, e_col)
        top_row = min(s_row, e_row)
        bottom_row = max(s_row, e_row)
        start_addr = self.hwp.cell_addr_to_text(left_col, top_row)
        end_addr = self.hwp.cell_addr_to_text(right_col, bottom_row)
        row_count = bottom_row - top_row + 1
        col_count = right_col - left_col + 1
        self.cell_range_var.set(f"선택됨: {start_addr} ~ {end_addr}")
        self.cell_status_var.set(
            f"{row_count}행 × {col_count}열 · 다른 범위를 드래그하면 새 범위로 바뀝니다."
        )
        self._set_cell_actions_enabled(True)

    def _cell_drag_watch_enabled(self):
        return not self.is_kedufine_mode()
    def poll_cell_mouse_drag(self):
        next_delay = 25
        try:
            if win32api is None or win32con is None:
                return
            if self.is_cell_processing:
                return
            if not self._cell_drag_watch_enabled():
                self.mouse_down_prev = False
                self.drag_start = None
                self.drag_last = None
                return

            left_down = bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)

            if left_down:
                # 팔레트 창은 한글 포커스를 유지하므로 전경 창이 아니라 실제 마우스 아래 창을 확인한다.
                # 드래그가 시작된 뒤에는 포인터가 표 밖으로 나가도 마지막 셀까지 계속 추적한다.
                if self.drag_start is not None or self._pointer_is_over_hwp_window():
                    try:
                        addr = self.hwp.get_table_cell_addr(focus_before=False)
                        if not self.mouse_down_prev:
                            self.drag_start = addr
                            self.drag_last = addr
                            self.cell_range_var.set(f"선택 중: {addr[2]}")
                            self.cell_status_var.set("마우스를 놓으면 범위가 기록됩니다.")
                            self._set_cell_actions_enabled(False)
                        else:
                            if self.drag_start is None:
                                self.drag_start = addr
                            self.drag_last = addr
                            self.cell_range_var.set(f"선택 중: {self.drag_start[2]} → {addr[2]}")
                    except Exception:
                        pass
                self.mouse_down_prev = self.drag_start is not None
            elif self.mouse_down_prev:
                if self.drag_start and self.drag_last:
                    self.recorded_start = self.drag_start
                    self.recorded_end = self.drag_last
                    self._update_cell_range_label()
                self.drag_start = None
                self.drag_last = None
                self.mouse_down_prev = False
            else:
                self.mouse_down_prev = False
                self.drag_start = None
                self.drag_last = None
        finally:
            self.after(next_delay, self.poll_cell_mouse_drag)
    def _run_cell_range_job(self, transform_func, complete_title: str):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("셀 정리")
            return
        if not self.recorded_start or not self.recorded_end:
            messagebox.showerror(
                "셀 정리 실패",
                "기록된 범위가 없습니다.\n\n한글 표에서 셀 범위를 마우스로 드래그한 뒤 다시 실행하세요.",
            )
            return

        ok, msg = self.hwp.ensure()
        if not ok:
            messagebox.showerror("셀 정리 실패", msg)
            return

        self.is_cell_processing = True
        old_clipboard_text = get_clipboard_text()
        try:
            self.cell_status_var.set("처리 전 병합 셀 검사 중...")
            self.update_idletasks()

            s_col, s_row, _ = self.recorded_start
            e_col, e_row, _ = self.recorded_end
            result = self.hwp.process_recorded_cell_range(
                start_col=s_col,
                start_row=s_row,
                end_col=e_col,
                end_row=e_row,
                transform_func=transform_func,
            )

            changed = int(result["changed"])
            action_title = complete_title.rstrip(".")
            if changed:
                self.cell_status_var.set(f"완료: {changed}개 셀 변경")
                self.status_var.set(f"{action_title}: {changed}개 셀 변경")
            else:
                self.cell_status_var.set("완료: 변경할 내용이 없습니다.")
                self.status_var.set(f"{action_title}: 변경 없음")
        except Exception as e:
            self.cell_status_var.set("오류 발생")
            messagebox.showerror("셀 정리 실패", str(e))
        finally:
            if old_clipboard_text is not None:
                try:
                    set_clipboard_text(old_clipboard_text)
                except Exception:
                    pass
            self.is_cell_processing = False

    def on_insert_images_into_cells(self):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("셀에 그림 넣기")
            return
        if not self.recorded_start or not self.recorded_end:
            messagebox.showerror(
                "그림 넣기 실패",
                "기록된 셀 범위가 없습니다.\n\n한글 표에서 셀 범위를 마우스로 드래그한 뒤 다시 실행하세요.",
            )
            return

        restore_noactivate = bool(self.var_top.get())
        if restore_noactivate:
            self._set_palette_noactivate(False)
            try:
                self.lift()
                self.focus_force()
            except Exception:
                pass
        try:
            paths = filedialog.askopenfilenames(
                parent=self,
                title="셀에 넣을 그림 선택",
                filetypes=(
                    ("그림 파일", "*.png *.jpg *.jpeg *.gif *.bmp"),
                    ("모든 파일", "*.*"),
                ),
            )
        finally:
            if restore_noactivate:
                self._set_palette_noactivate(True)
        if not paths:
            return
        image_paths = sort_image_paths(paths)

        s_col, s_row, _ = self.recorded_start
        e_col, e_row, _ = self.recorded_end
        row_count = abs(int(e_row) - int(s_row)) + 1
        col_count = abs(int(e_col) - int(s_col)) + 1
        cell_count = row_count * col_count
        if len(image_paths) > cell_count:
            messagebox.showerror(
                "그림 넣기 실패",
                f"선택한 셀은 {cell_count}개인데 그림은 {len(image_paths)}개입니다.\n\n"
                "그림 수 이상으로 셀을 선택한 뒤 다시 실행하세요.",
            )
            return

        ok, msg = self.hwp.ensure()
        if not ok:
            messagebox.showerror("그림 넣기 실패", msg)
            return

        self.is_cell_processing = True
        try:
            self.status_var.set(f"셀에 그림 넣는 중: 0/{len(image_paths)}")
            self.update_idletasks()

            def report_progress(done, total):
                self.status_var.set(f"셀에 그림 넣는 중: {done}/{total}")
                self.update_idletasks()

            result = self.hwp.insert_pictures_into_cell_range(
                image_paths=image_paths,
                start_col=s_col,
                start_row=s_row,
                end_col=e_col,
                end_row=e_row,
                size_mode=self.cell_image_size_mode.get(),
                progress_callback=report_progress,
            )
            inserted = int(result["inserted"])
            self.status_var.set(f"셀에 그림 넣기 완료: {inserted}장")
        except Exception as e:
            self.status_var.set("셀에 그림 넣기 실패")
            messagebox.showerror("그림 넣기 실패", str(e))
        finally:
            self.is_cell_processing = False


    def on_refit_images_in_cells(self):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("기존 그림 다시 맞춤")
            return
        if not self.recorded_start or not self.recorded_end:
            messagebox.showerror(
                "그림 다시 맞춤 실패",
                "기록된 셀 범위가 없습니다.\n\n한글 표에서 셀 범위를 마우스로 드래그한 뒤 다시 실행하세요.",
            )
            return

        ok, msg = self.hwp.ensure()
        if not ok:
            messagebox.showerror("그림 다시 맞춤 실패", msg)
            return

        s_col, s_row, _ = self.recorded_start
        e_col, e_row, _ = self.recorded_end
        self.is_cell_processing = True
        try:
            self.status_var.set("기존 그림 확인 중")
            self.update_idletasks()

            def report_progress(done, total):
                self.status_var.set(f"기존 그림 확인 중: {done}/{total}")
                self.update_idletasks()

            result = self.hwp.refit_pictures_in_cell_range(
                start_col=s_col,
                start_row=s_row,
                end_col=e_col,
                end_row=e_row,
                size_mode=self.cell_image_size_mode.get(),
                progress_callback=report_progress,
            )
            parts = [f"기존 그림 다시 맞춤 완료: {int(result['resized'])}장"]
            if int(result["empty"]):
                parts.append(f"그림 없음 {int(result['empty'])}칸")
            if int(result["multiple"]):
                parts.append(f"여러 그림 {int(result['multiple'])}칸 건너뜀")
            if int(result["unreadable"]):
                parts.append(f"정보 확인 불가 {int(result['unreadable'])}칸")
            self.status_var.set(" · ".join(parts))
        except Exception as e:
            self.status_var.set("기존 그림 다시 맞춤 실패")
            messagebox.showerror("그림 다시 맞춤 실패", str(e))
        finally:
            self.is_cell_processing = False

    def on_cell_clean_spaces(self):
        self._run_cell_range_job(
            transform_func=cell_clean_space_text,
            complete_title="선택한 셀의 공백 제거를 완료했습니다.",
        )

    def on_cell_find_replace(self):
        find_text = self.cell_find_var.get()
        replace_text = self.cell_replace_var.get()
        if find_text == "":
            messagebox.showerror("셀 정리 실패", "찾을 내용을 입력하세요.")
            return

        def _replace_func(text):
            return cell_replace_text_plain(text, find_text, replace_text)

        self._run_cell_range_job(
            transform_func=_replace_func,
            complete_title="선택한 셀의 찾아바꾸기를 완료했습니다.",
        )

    def on_cell_add_prefix(self):
        add_text = self.cell_add_text_var.get()
        if add_text == "":
            messagebox.showerror("셀 정리 실패", "추가할 문자를 입력하세요.")
            return

        def _prefix_func(text):
            return cell_add_prefix_text(text, add_text)

        self._run_cell_range_job(
            transform_func=_prefix_func,
            complete_title="선택한 셀 앞에 문자를 추가했습니다.",
        )

    def on_cell_add_suffix(self):
        add_text = self.cell_add_text_var.get()
        if add_text == "":
            messagebox.showerror("셀 정리 실패", "추가할 문자를 입력하세요.")
            return

        def _suffix_func(text):
            return cell_add_suffix_text(text, add_text)

        self._run_cell_range_job(
            transform_func=_suffix_func,
            complete_title="선택한 셀 뒤에 문자를 추가했습니다.",
        )

    def on_cell_cleanup_excel_paste(self):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("셀 정리")
            return
        if not self.recorded_start or not self.recorded_end:
            messagebox.showerror(
                "엑셀 붙여넣기 정리 실패",
                "기록된 범위가 없습니다.\n\n한글 표에서 셀 범위를 마우스로 드래그한 뒤 다시 실행하세요.",
            )
            return

        ok, msg = self.hwp.ensure()
        if not ok:
            messagebox.showerror("엑셀 붙여넣기 정리 실패", msg)
            return

        self.is_cell_processing = True
        old_clipboard_text = get_clipboard_text()
        try:
            self.cell_status_var.set("엑셀 붙여넣기 흔적 정리 중...")
            self.update_idletasks()

            s_col, s_row, _ = self.recorded_start
            e_col, e_row, _ = self.recorded_end
            result = self.hwp.cleanup_excel_pasted_cell_range(
                start_col=s_col,
                start_row=s_row,
                end_col=e_col,
                end_row=e_row,
            )

            text_changed = int(result["text_changed"])
            background_changed = int(result["background_changed"])
            charshape_changed = int(result["charshape_changed"])
            self.cell_status_var.set(
                f"완료: 공백 {text_changed} · 문단 배경 {background_changed} · 글자색/음영 {charshape_changed}개 셀"
            )
            self.status_var.set(
                f"엑셀 붙여넣기 흔적 정리 완료: 공백 {text_changed} · 문단 배경 {background_changed} · 글자색/음영 {charshape_changed}개 셀"
            )
        except Exception as e:
            self.cell_status_var.set("오류 발생")
            messagebox.showerror("엑셀 붙여넣기 정리 실패", str(e))
        finally:
            if old_clipboard_text is not None:
                try:
                    set_clipboard_text(old_clipboard_text)
                except Exception:
                    pass
            self.is_cell_processing = False

    def _refresh_text_font_rows(self):
        """적용 대상 모드에 따라 글자 작업의 글꼴 행을 표시/숨김 처리한다."""
        if not hasattr(self, "text_font_rows") or not hasattr(self, "text_font_order"):
            return

        hide_fonts = feature_registry.HIDDEN_TEXT_FONTS_BY_MODE.get(self.var_target_mode.get(), set())

        for font_name in self.text_font_order:
            row = self.text_font_rows.get(font_name)
            if row is None:
                continue
            try:
                row.pack_forget()
            except Exception:
                pass
            if font_name not in hide_fonts:
                try:
                    row.pack(fill="x", pady=6)
                except Exception:
                    pass

        spacing_box = getattr(self, "text_spacing_box", None)
        if spacing_box is not None:
            try:
                spacing_box.pack_forget()
            except Exception:
                pass
            if not self.is_kedufine_mode():
                try:
                    spacing_box.pack(fill="x", pady=(14, 0))
                except Exception:
                    pass

    def _build_text_tools_cards(self, parent):
        """
        글자 작업:
        - 글꼴 버튼: 글꼴만 변경
        - 숫자 버튼: 해당 글꼴 + 크기 적용
        - 색상 버튼: 글자색 변경(검정/빨강/파랑/흰색)
        """
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        # --- 색상 버튼 행 ---
        color_row = ttk.Frame(wrap)
        color_row.pack(fill="x", pady=(0, 10))
        ttk.Label(color_row, text="글자색", background=WHITE).pack(side="left", padx=(0, 8))
        def _mk_color_btn(label, rgb, fg, bg):
            b = tk.Button(
                color_row, text=label, fg=fg, bg=bg,
                relief="solid", bd=1, padx=8, pady=3,
                takefocus=0, highlightthickness=0, cursor="hand2",
                activebackground=bg, activeforeground=fg,
                command=lambda c=rgb, t=label: self._apply_font_color(c, t)
            )
            b.pack(side="left", padx=3)
            return b
        for action in feature_registry.TEXT_COLOR_ACTIONS:
            _mk_color_btn(action.label, action.rgb, action.fg, action.bg)
        ttk.Separator(wrap, orient="horizontal").pack(fill="x", pady=(0, 10))
        font_wrap = ttk.Frame(wrap)
        font_wrap.pack(fill="x")
        # --- 글꼴/크기 행들 ---
        for r, font_row in enumerate(feature_registry.TEXT_FONT_ROWS):
            fname = font_row.font_name
            sizes = font_row.sizes
            row = ttk.Frame(font_wrap)
            row.pack(fill="x", pady=6)
            self.text_font_rows[fname] = row
            self.text_font_order.append(fname)
            # 글꼴 버튼은 "버튼 글꼴 자체"를 해당 글꼴로 표시
            try:
                fnt = tkfont.Font(family=fname, size=10, weight="bold")
            except Exception:
                fnt = tkfont.Font(size=10, weight="bold")
            btn_font = tk.Button(
                row, text=fname, width=10, font=fnt, bg=SURFACE,
                relief="solid", bd=1, padx=8, pady=6,
                takefocus=0, highlightthickness=0, cursor="hand2",
                activebackground=SURFACE_ALT,
                command=lambda f=fname: self._apply_font_only(f)
            )
            btn_font.pack(side="left")
            btns = ttk.Frame(row)
            btns.pack(side="left", padx=8, fill="x", expand=True)
            for s in sizes:
                ttk.Button(
                    btns, text=str(s), width=3, style="Compact.TButton",
                    command=lambda f=fname, sz=s: self._apply_font_size(f, sz)
                ).pack(side="left", padx=2)
            if fname == feature_registry.TEXT_SPACING_ANCHOR_FONT:
                self.text_spacing_box = ttk.LabelFrame(wrap, text="자간 정리", padding=8)
                spacing_box = self.text_spacing_box
                spacing_box.pack(fill="x", pady=(14, 0))
                for idx, action in enumerate(feature_registry.TEXT_SPACING_ACTIONS):
                    ttk.Button(
                        spacing_box,
                        text=action.label,
                        command=self._feature_button_command(action),
                    ).pack(side="left", padx=(0, 6 if idx < len(feature_registry.TEXT_SPACING_ACTIONS) - 1 else 0))
        self._refresh_text_font_rows()
    def on_cleanup_line_spacing(self, adjust_count: int):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("자간 정리")
            return
        self.status_var.set("자간 정리 중...")
        self.update_idletasks()
        use_recorded_cells = False
        if self.recorded_start and self.recorded_end:
            try:
                self.hwp.get_table_cell_addr(focus_before=False)
                use_recorded_cells = True
            except Exception:
                use_recorded_cells = False
        if use_recorded_cells:
            s_col, s_row, _ = self.recorded_start
            e_col, e_row, _ = self.recorded_end
            ok, msg = self.hwp.cleanup_cell_range_line_spacing(s_col, s_row, e_col, e_row, adjust_count)
        else:
            ok, msg = self.hwp.cleanup_line_spacing(adjust_count)
        if ok:
            self.status_var.set(msg)
        else:
            messagebox.showerror("자간 정리 실패", msg)

    def on_reset_char_spacing(self):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("자간 초기화")
            return
        self.status_var.set("자간 초기화 중...")
        self.update_idletasks()
        ok, msg = self.hwp.reset_selected_char_spacing()
        if ok:
            self.status_var.set(msg)
        else:
            messagebox.showerror("자간 초기화 실패", msg)

    def _apply_font_only(self, font_name: str):
        bridge = self.wxs if self.is_kedufine_mode() else self.hwp
        ok, msg = bridge.apply_charshape(font_name=font_name, font_size_pt=None)
        if ok:
            target = "기안창" if self.is_kedufine_mode() else "한글"
            self.status_var.set(f"{target} 글꼴: {font_name}")
            self._restore_kedufine_focus_later()
        else:
            messagebox.showerror("글자 적용 실패", msg)
    def _apply_font_size(self, font_name: str, size_pt: int):
        bridge = self.wxs if self.is_kedufine_mode() else self.hwp
        ok, msg = bridge.apply_charshape(font_name=font_name, font_size_pt=int(size_pt))
        if ok:
            target = "기안창" if self.is_kedufine_mode() else "한글"
            self.status_var.set(f"{target} 글꼴/크기: {font_name} {size_pt}")
            self._restore_kedufine_focus_later()
        else:
            messagebox.showerror("글자 적용 실패", msg)
    def _apply_font_color(self, rgb: tuple[int,int,int], label: str):
        bridge = self.wxs if self.is_kedufine_mode() else self.hwp
        ok, msg = bridge.apply_charshape(font_name=None, font_size_pt=None, font_color_rgb=rgb)
        if ok:
            target = "기안창" if self.is_kedufine_mode() else "한글"
            self.status_var.set(f"{target} 글자색: {label}")
            self._restore_kedufine_focus_later()
        else:
            messagebox.showerror("글자 적용 실패", msg)
    def _make_tab_order_editor(self, parent, title, tab_defs, current_order):
        box = ttk.LabelFrame(parent, text=title, padding=8)
        box.pack(fill="both", expand=True, padx=8, pady=6)

        ordered_defs = self._ordered_tab_defs(tab_defs, current_order)
        labels = {key: label for key, _child, label in tab_defs}
        keys = [key for key, _child, _label in ordered_defs]

        list_wrap = ttk.Frame(box)
        list_wrap.pack(side="left", fill="both", expand=True)
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)

        lb = tk.Listbox(list_wrap, height=8, exportselection=False)
        lb.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=lb.yview)
        sb.grid(row=0, column=1, sticky="ns")
        lb.configure(yscrollcommand=sb.set)

        def refresh_list_scrollbar(_event=None):
            try:
                first, last = lb.yview()
                needed = lb.size() > 0 and (first > 0.0 or last < 1.0)
            except Exception:
                needed = False
            self._set_scrollbar_needed(sb, needed)

        lb.bind("<Configure>", lambda _event: lb.after_idle(refresh_list_scrollbar), add="+")

        def refresh_list(select_idx=None):
            lb.delete(0, "end")
            for key in keys:
                lb.insert("end", labels.get(key, key))
            if keys:
                if select_idx is None:
                    select_idx = 0
                select_idx = max(0, min(int(select_idx), len(keys) - 1))
                lb.selection_set(select_idx)
                lb.activate(select_idx)
                lb.see(select_idx)
            lb.after_idle(refresh_list_scrollbar)

        def selected_index():
            sel = lb.curselection()
            if not sel:
                return None
            return int(sel[0])

        def move_up():
            idx = selected_index()
            if idx is None or idx <= 0:
                return
            keys[idx - 1], keys[idx] = keys[idx], keys[idx - 1]
            refresh_list(idx - 1)

        def move_down():
            idx = selected_index()
            if idx is None or idx >= len(keys) - 1:
                return
            keys[idx + 1], keys[idx] = keys[idx], keys[idx + 1]
            refresh_list(idx + 1)

        btns = ttk.Frame(box)
        btns.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(btns, text="▲ 위로", command=move_up).pack(fill="x", pady=(0, 4))
        ttk.Button(btns, text="▼ 아래로", command=move_down).pack(fill="x", pady=(0, 4))

        refresh_list(0)
        return keys, refresh_list

    def on_edit_tab_order(self):
        if not hasattr(self, "main_tab_defs") or not hasattr(self, "edit_tab_defs"):
            return

        owner = getattr(self, "settings_window", None)
        try:
            if owner is None or not owner.winfo_exists():
                owner = self
        except Exception:
            owner = self

        dlg = tk.Toplevel(owner)
        dlg.title("탭 순서 편집")
        dlg.configure(bg=APP_BG)
        dlg.resizable(False, False)
        try:
            dlg.transient(owner)
            dlg.grab_set()
        except Exception:
            pass

        main_defs = self.main_tab_defs
        edit_defs = getattr(self, "edit_tab_defs", [])
        symbol_defs = getattr(self, "symbol_tab_defs", [])

        main_keys = self._normalize_tab_order(self.main_tab_order, main_defs)
        edit_keys = self._normalize_tab_order(self.edit_tab_order, edit_defs)
        symbol_keys = self._normalize_tab_order(self.symbol_tab_order, symbol_defs)

        labels = {key: label for key, _child, label in main_defs}
        child_defs = {
            "edit": edit_defs,
            "symbol": symbol_defs,
        }
        child_keys = {
            "edit": edit_keys,
            "symbol": symbol_keys,
        }
        child_titles = {
            "edit": "편집도구 하위 탭",
            "symbol": "심볼 하위 탭",
        }

        ttk.Label(
            dlg,
            text="상위 탭을 선택하면, 하위 탭이 있는 경우 오른쪽에서 순서를 바꿀 수 있습니다.",
            background=WHITE,
        ).pack(anchor="w", padx=14, pady=(12, 6))

        body = ttk.Frame(dlg, padding=(12, 0, 12, 8))
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="상위 탭", padding=8)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ttk.LabelFrame(body, text="하위 탭", padding=8)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        main_lb = tk.Listbox(left, height=14, exportselection=False)
        main_lb.pack(fill="both", expand=True)
        main_btns = ttk.Frame(left)
        main_btns.pack(fill="x", pady=(8, 0))

        sub_title_var = tk.StringVar(value="하위 탭 없음")
        ttk.Label(right, textvariable=sub_title_var, background=WHITE).pack(anchor="w", pady=(0, 4))
        sub_lb = tk.Listbox(right, height=12, exportselection=False)
        sub_lb.pack(fill="both", expand=True)
        sub_btns = ttk.Frame(right)
        sub_btns.pack(fill="x", pady=(8, 0))

        def refresh_main(select_idx=None):
            main_lb.delete(0, "end")
            for key in main_keys:
                main_lb.insert("end", labels.get(key, key))
            if main_keys:
                if select_idx is None:
                    select_idx = main_lb.curselection()[0] if main_lb.curselection() else 0
                select_idx = max(0, min(int(select_idx), len(main_keys) - 1))
                main_lb.selection_clear(0, "end")
                main_lb.selection_set(select_idx)
                main_lb.activate(select_idx)
                main_lb.see(select_idx)
            refresh_sub()

        def selected_main_index():
            sel = main_lb.curselection()
            if not sel:
                return None
            return int(sel[0])

        def selected_main_key():
            idx = selected_main_index()
            if idx is None or idx < 0 or idx >= len(main_keys):
                return None
            return main_keys[idx]

        def refresh_sub(select_idx=None):
            # 중요:
            # Listbox가 disabled 상태이면 delete/insert가 정상 반영되지 않아
            # 이전에 표시했던 "하위 탭 없음" 안내 문구가 실제 하위 탭 목록에 남을 수 있다.
            # 따라서 항상 normal로 돌린 뒤 목록을 완전히 비우고 다시 구성한다.
            sub_lb.configure(state="normal")
            sub_lb.delete(0, "end")

            key = selected_main_key()
            defs = child_defs.get(key) or []
            keys = child_keys.get(key) or []

            if not defs:
                sub_title_var.set("하위 탭 없음")
                btn_sub_up.configure(state="disabled")
                btn_sub_down.configure(state="disabled")
                sub_lb.configure(state="disabled")
                return

            btn_sub_up.configure(state="normal")
            btn_sub_down.configure(state="normal")
            sub_title_var.set(child_titles.get(key, "하위 탭"))
            sub_labels = {k: label for k, _child, label in defs}
            for sub_key in keys:
                sub_lb.insert("end", sub_labels.get(sub_key, sub_key))
            if keys:
                if select_idx is None:
                    select_idx = sub_lb.curselection()[0] if sub_lb.curselection() else 0
                select_idx = max(0, min(int(select_idx), len(keys) - 1))
                sub_lb.selection_clear(0, "end")
                sub_lb.selection_set(select_idx)
                sub_lb.activate(select_idx)
                sub_lb.see(select_idx)

        def move_main(delta):
            idx = selected_main_index()
            if idx is None:
                return
            new_idx = idx + delta
            if new_idx < 0 or new_idx >= len(main_keys):
                return
            main_keys[idx], main_keys[new_idx] = main_keys[new_idx], main_keys[idx]
            refresh_main(new_idx)

        def selected_sub_index():
            if str(sub_lb.cget("state")) == "disabled":
                return None
            sel = sub_lb.curselection()
            if not sel:
                return None
            return int(sel[0])

        def move_sub(delta):
            key = selected_main_key()
            if key not in child_keys:
                return
            keys = child_keys[key]
            idx = selected_sub_index()
            if idx is None:
                return
            new_idx = idx + delta
            if new_idx < 0 or new_idx >= len(keys):
                return
            keys[idx], keys[new_idx] = keys[new_idx], keys[idx]
            refresh_sub(new_idx)

        ttk.Button(main_btns, text="▲ 위로", command=lambda: move_main(-1)).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(main_btns, text="▼ 아래로", command=lambda: move_main(1)).pack(side="left", fill="x", expand=True, padx=(3, 0))
        btn_sub_up = ttk.Button(sub_btns, text="▲ 위로", command=lambda: move_sub(-1))
        btn_sub_up.pack(side="left", fill="x", expand=True, padx=(0, 3))
        btn_sub_down = ttk.Button(sub_btns, text="▼ 아래로", command=lambda: move_sub(1))
        btn_sub_down.pack(side="left", fill="x", expand=True, padx=(3, 0))

        def on_main_select(_event=None):
            refresh_sub(0)
        main_lb.bind("<<ListboxSelect>>", on_main_select)

        def reset_default():
            main_keys[:] = [key for key, _child, _label in main_defs]
            edit_keys[:] = [key for key, _child, _label in edit_defs]
            symbol_keys[:] = [key for key, _child, _label in symbol_defs]
            refresh_main(0)

        def save_and_close():
            self.main_tab_order = self._normalize_tab_order(main_keys, self.main_tab_defs)
            self.edit_tab_order = self._normalize_tab_order(edit_keys, self.edit_tab_defs)
            self.symbol_tab_order = self._normalize_tab_order(symbol_keys, self.symbol_tab_defs)
            self._save_ui_settings()
            self._refresh_mode_tabs()
            self.status_var.set("탭 순서 저장 완료")
            try:
                dlg.destroy()
            except Exception:
                pass

        bottom = ttk.Frame(dlg, padding=(12, 6, 12, 12))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="기본 순서", command=reset_default).pack(side="left")
        ttk.Button(bottom, text="취소", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(bottom, text="저장", style="Primary.TButton", command=save_and_close).pack(side="right")

        refresh_main(0)
        self._place_left_of(dlg, owner, 560, 520)

    def on_copy_report_prompt(self):
        ok, prompt_or_msg = read_report_prompt()
        if not ok:
            messagebox.showerror("복사 실패", prompt_or_msg)
            return
        try:
            copy_text_preserve_blank_lines(self, prompt_or_msg)
            messagebox.showinfo("복사 완료", "공문서 초안 작성 프롬프트를 클립보드에 복사했습니다.")
        except Exception as e:
            messagebox.showerror("복사 실패", f"프롬프트 복사 실패: {e}")

    def on_auto_format_report(self):
        if self._auto_format_running:
            return
        self._auto_format_running = True
        self._auto_format_stop_requested = False
        self._set_auto_format_running_ui(True)
        try:
            self._run_auto_format_report()
        finally:
            self._auto_format_running = False
            self._auto_format_stop_requested = False
            self._set_auto_format_running_ui(False)

    def on_stop_auto_format(self):
        if not self._auto_format_running:
            return
        self._auto_format_stop_requested = True
        self.status_var.set("서식 자동 지정 중지 요청...")

    def _set_auto_format_running_ui(self, running: bool):
        try:
            self.btn_auto_format.configure(state="disabled" if running else "normal")
            self.btn_stop_auto_format.configure(state="normal" if running else "disabled")
        except Exception:
            pass

    def _auto_format_cancelled(self):
        try:
            self.update()
        except Exception:
            pass
        if self._auto_format_stop_requested:
            self.status_var.set("서식 자동 지정 중지됨")
            messagebox.showinfo("중지", "서식 자동 지정을 중지했습니다.")
            return True
        return False

    def _run_inferred_format_with_native_tables(self, transformed, inspection):
        paragraphs = list(inspection.get("paragraphs") or [])
        table_positions = list(inspection.get("native_table_positions") or [])
        paragraph_items = [
            item for item in transformed
            if item.get("style") is not None and item.get("tag") != "표"
        ]

        if len(paragraph_items) != len(paragraphs):
            body_text = "\n".join(str(paragraph.get("text") or "") for paragraph in paragraphs)
            body_transformed, _ = transform_untagged_report_text(
                body_text,
                has_external_table=bool(table_positions),
            )
            paragraph_items = [
                item for item in body_transformed
                if item.get("style") is not None and item.get("tag") != "표"
            ]

        if len(paragraph_items) != len(paragraphs):
            messagebox.showerror(
                "서식 자동 지정 실패",
                "표 밖 문단의 위치를 정확히 연결하지 못했습니다. 원본 표를 보호하기 위해 작업을 중단했습니다.",
            )
            return

        title_box_file = self._find_template_file_by_title("제목박스")
        section_box_file = self._find_template_file_by_title("소제목박스")
        if any(item.get("tag") == "문서제목" for item in paragraph_items) and not title_box_file:
            messagebox.showerror("서식 자동 지정 실패", "서식 탭에서 '제목박스' 파일을 찾지 못했습니다.")
            return
        if any(item.get("tag") == "제목" for item in paragraph_items) and not section_box_file:
            messagebox.showerror("서식 자동 지정 실패", "서식 탭에서 '소제목박스' 파일을 찾지 못했습니다.")
            return
        if self._auto_format_cancelled():
            return

        def table_progress(current, total):
            self.status_var.set(f"한글 표 서식 지정 중... ({current}/{total})")
            try:
                self.update()
            except Exception:
                pass

        # 제목박스 삽입 전에 표를 먼저 정돈해야 저장해 둔 표 위치가 바뀌지 않는다.
        ok, msg = self.hwp.format_native_report_tables(
            table_positions,
            progress=table_progress,
            cancelled=lambda: bool(self._auto_format_stop_requested),
        )
        if not ok:
            if msg == "CANCELLED":
                self._auto_format_cancelled()
            else:
                messagebox.showerror("서식 자동 지정 실패", msg)
            return

        def paragraph_progress(current, total):
            self.status_var.set(f"표 밖 문단 서식 지정 중... ({current}/{total})")
            try:
                self.update()
            except Exception:
                pass

        ok, msg = self.hwp.apply_inferred_report_paragraphs(
            paragraphs,
            paragraph_items,
            title_box_file=title_box_file,
            section_box_file=section_box_file,
            progress=paragraph_progress,
            cancelled=lambda: bool(self._auto_format_stop_requested),
        )
        if not ok:
            if msg == "CANCELLED":
                self._auto_format_cancelled()
            else:
                messagebox.showerror("서식 자동 지정 실패", msg)
            return

        changed_count = len(paragraph_items) + len(table_positions)
        self.status_var.set(f"서식 자동 지정 완료 ({changed_count}개 문단·표)")
        messagebox.showinfo(
            "완료",
            "선택한 영역의 서식을 지정했습니다. 기존 한글 표의 행·열 구조는 유지했습니다.",
        )

    def _run_auto_format_report(self):
        if self.is_kedufine_mode():
            self._show_kedufine_unsupported("서식 자동 지정하기")
            return
        ok, msg = self.hwp.apply_basic_report_page_setup()
        if not ok:
            messagebox.showerror("서식 자동 지정 실패", f"기본 보고서 편집용지 적용 실패: {msg}")
            return
        ok, raw = self.hwp.get_selected_text()
        if not ok:
            messagebox.showerror("서식 자동 지정 실패", raw)
            return
        transformed, changed_count, format_mode = transform_auto_format_text(raw)
        if changed_count == 0:
            messagebox.showinfo("안내", "선택한 영역에서 서식을 적용할 문단을 찾지 못했습니다.")
            return
        if format_mode == "inferred":
            self.status_var.set("태그 없는 문서의 문단 체계와 표 분석 완료")
            inspected, inspection = self.hwp.inspect_selected_report_content()
            if inspected and inspection.get("native_table_positions"):
                self._run_inferred_format_with_native_tables(transformed, inspection)
                return
        title_box_file = self._find_template_file_by_title("제목박스")
        section_box_file = self._find_template_file_by_title("소제목박스")
        need_doc_title = any((it.get("tag") == "문서제목") for it in transformed)
        need_title = any((it.get("tag") == "제목") for it in transformed)
        if need_doc_title and not title_box_file:
            messagebox.showerror("서식 자동 지정 실패", "서식 탭에서 '제목박스' 파일을 찾지 못했습니다.")
            return
        if need_title and not section_box_file:
            messagebox.showerror("서식 자동 지정 실패", "서식 탭에서 '소제목박스' 파일을 찾지 못했습니다.")
            return
        if self._auto_format_cancelled():
            return
        ok, msg = self.hwp.delete_selection()
        if not ok:
            messagebox.showerror("서식 자동 지정 실패", msg)
            return
        total = len(transformed)
        for idx, item in enumerate(transformed):
            if self._auto_format_cancelled():
                return
            self.status_var.set(f"서식 자동 지정 중... ({idx + 1}/{total})")
            if idx > 0:
                ok, msg = self.hwp.ensure_cursor_outside_table()
                if not ok:
                    messagebox.showerror("서식 자동 지정 실패", msg)
                    return
            line_text = item["text"]
            tag = item.get("tag")
            if tag == "표":
                ok, msg = self.hwp.insert_pipe_table(item.get("rows") or [], font_name="굴림체", font_size_pt=12)
            elif item["style"] is None:
                ok, msg = self.hwp.insert_text(line_text)
            elif tag == "문서제목":
                ok, msg = self.hwp.insert_document_title_box(title_box_file, line_text.strip())
            elif tag == "제목":
                num_text = item.get("number_text")
                body_text = item.get("body_text")
                if num_text is None or body_text is None:
                    num_text, body_text = split_section_title_text(line_text.strip())
                ok, msg = self.hwp.insert_section_title_box(section_box_file, num_text, body_text)
            else:
                st = item["style"]
                ok, msg = self.hwp.insert_report_line(
                    line_text,
                    font_name=st["font"],
                    font_size_pt=int(st["size"]),
                    bold=bool(st.get("bold", False)),
                )
                if ok and st.get("caret_indent_at") is not None:
                    ok, msg = self.hwp.apply_indent_at_caret_for_current_para(int(st.get("caret_indent_at") or 0))
            if not ok:
                messagebox.showerror("서식 자동 지정 실패", msg)
                return
            if self._auto_format_cancelled():
                return
            if idx < total - 1 and tag not in ("문서제목", "제목", "표"):
                ok, msg = self.hwp.insert_text("\r\n")
                if not ok:
                    messagebox.showerror("서식 자동 지정 실패", msg)
                    return
        self.status_var.set(f"서식 자동 지정 완료 ({changed_count}개 문단)")
        messagebox.showinfo("완료", "선택한 영역의 서식 자동 지정이 완료되었습니다.")
    def on_insert_text(self, ch):
        if self.is_kedufine_mode():
            ok, msg = self.wxs.insert_text(ch)
            if ok:
                self.status_var.set("기안창 문자 삽입")
                self._restore_kedufine_focus_later()
            else:
                messagebox.showerror("문자 삽입 실패", msg)
            return
        ok, msg = self.hwp.insert_text(ch)
        if ok:
            self.status_var.set("문자 삽입")
        else:
            messagebox.showerror("오류", msg)
    def on_new(self):
        messagebox.showinfo("안내", "이 버전은 별도의 한글 열기 버튼을 사용하지 않습니다. 이미 열려 있는 한글 문서에 바로 적용합니다.")
    def on_toggle_top(self):
        topmost = bool(self.var_top.get())
        self.attributes("-topmost", topmost)
        self._set_palette_noactivate(topmost)
        self.settings["always_on_top"] = topmost
        self.data["settings"] = self.settings
        try:
            save_json(CFG_PATH, self.data)
        except Exception:
            pass

def main():
    if not acquire_single_instance():
        close_splash()
        # 안내창 대신, 이미 열려 있는 창을 앞으로 가져온다.
        if activate_existing_window(f"{APP_TITLE} {APP_VERSION}"):
            return
        notify_already_running(APP_TITLE, f"{APP_TITLE}가 이미 실행 중입니다.")
        return

    try:
        App().mainloop()
    except Exception:
        close_splash()
        raise
