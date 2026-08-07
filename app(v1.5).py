# -*- coding: utf-8 -*-
import os, json, io, sys, time, re
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
def resource_base_dir() -> str:
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
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
# 선택 셀 공백 정리 대상: 일반 공백, NBSP, 전각 공백, zero-width space, BOM
CELL_SPACE_RE = re.compile(r"[ \u00A0\u3000\u200B\ufeff]+")
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
class HwpBridge:
    """
    이미 열려 있는 한글 COM 객체를 ROT에서 직접 찾아 연결한다.
    Dispatch("HWPFrame.HwpObject")로 새 한글 인스턴스를 만들지 않는다.
    """
    def __init__(self):
        self.hwp = None
        self._cell_span_prop_action = None
        self._cell_span_prop_available = None
    def reset(self):
        self.hwp = None
        self._cell_span_prop_action = None
        self._cell_span_prop_available = None
    def connect(self):
        try:
            bring_last_hwp_to_front_if_any()
            ok, hwp, msg = get_running_hwp_from_rot()
            if not ok:
                self.hwp = None
                return False, f"실행 중 한글 COM 객체 연결 실패:\n{msg}"
            self.hwp = hwp
            try:
                self.hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
            except Exception:
                pass
            time.sleep(0.05)
            return True, msg
        except Exception as e:
            self.hwp = None
            return False, f"실행 중 한글 COM 연결 실패: {e}"
    def connect_without_focus(self):
        """
        셀 범위 드래그 감시용 연결.
        드래그 중에는 한글 창을 다시 앞으로 가져오면 셀 선택 흐름이 흔들릴 수 있어
        ROT 조회만 수행하고 창 활성화는 하지 않는다.
        """
        try:
            if self.hwp is not None:
                return True, "OK"
            ok, hwp, msg = get_running_hwp_from_rot()
            if not ok:
                self.hwp = None
                return False, f"실행 중 한글 COM 객체 연결 실패:\n{msg}"
            self.hwp = hwp
            try:
                self.hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
            except Exception:
                pass
            return True, msg
        except Exception as e:
            self.hwp = None
            return False, f"실행 중 한글 COM 연결 실패: {e}"

    def ensure(self):
        # 사용자가 다른 한글 문서를 클릭했을 수 있으므로 작업 직전 마지막 한글창을 다시 활성화한다.
        bring_last_hwp_to_front_if_any()
        if self.hwp is None:
            return self.connect()
        return True, "OK"
    def _retry_once_with_reconnect(self, fn):
        try:
            return fn()
        except Exception as e:
            self.reset()
            ok, msg = self.connect()
            if not ok:
                raise e
            time.sleep(0.08)
            return fn()
    def new_doc(self):
        return False, "이 버전은 새 한글 문서를 만들지 않습니다. 열려 있는 한글 문서에만 적용합니다."
    def insert_text(self, text: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            self.hwp.HAction.GetDefault("InsertText", self.hwp.HParameterSet.HInsertText.HSet)
            self.hwp.HParameterSet.HInsertText.Text = text
            self.hwp.HAction.Execute("InsertText", self.hwp.HParameterSet.HInsertText.HSet)
            return True, "문자 삽입 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문자 삽입 실패: {e}"
    def insert_file(self, filepath_abs: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        path = os.path.abspath(filepath_abs)
        if not os.path.exists(path):
            return False, f"파일이 없습니다: {path}"
        try:
            ps = self.hwp.HParameterSet.HInsertFile
            self.hwp.HAction.GetDefault("InsertFile", ps.HSet)
            for key in ["FileName", "filename", "FilePath", "path"]:
                try:
                    setattr(ps, key, path)
                    break
                except Exception:
                    pass
            for k, v in [("KeepCharshape", 1), ("KeepParashape", 1), ("KeepSection", 0), ("KeepNumbering", 1)]:
                try:
                    setattr(ps, k, v)
                except Exception:
                    pass
            self.hwp.HAction.Execute("InsertFile", ps.HSet)
            return True, "삽입 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"삽입 실패: {e}"
    def run_cmd(self, cmd: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            self.hwp.Run(cmd)
            return True, "OK"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"명령 실행 실패({cmd}): {e}"
    def run_first_supported(self, commands):
        last_msg = ""
        for cmd in commands:
            ok, msg = self.run_cmd(cmd)
            if ok:
                return True, cmd
            last_msg = msg
        return False, last_msg or "지원되는 명령이 없습니다."
    def insert_paragraph_break(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            self.hwp.Run("BreakPara")
            return True, "OK"
        except Exception:
            return self.insert_text("\r\n")
    def clear_current_cell_text(self):
        # 표 삽입 직후에는 표 전체가 선택된 상태로 남는 경우가 있어 Delete 실행 시
        # '표를 지울까요?' 확인창이 뜰 수 있음. 1차 버전에서는 셀 비우기를 생략한다.
        # 제목박스/소제목박스 템플릿의 대상 셀은 비어 있다는 전제로 텍스트만 바로 입력한다.
        return True, "SKIP"
    def _enter_recent_table_from_before_insert(self):
        # 현재 환경에서는 InsertFile 후 커서가 표 앞에 놓임.
        # 환경별로 표 안 진입 명령이 달라 여러 조합을 순차 시도한다.
        attempts = [
            ["FindCtrl", "ShapeObjSelect", "TableCellBlock"],
            ["SelectCtrlFront", "TableCellBlock"],
            ["SelectCtrlFront", "FindCtrl", "TableCellBlock"],
            ["MoveRight", "FindCtrl", "TableCellBlock"],
            ["MoveRight", "TableCellBlock"],
            ["MoveRight", "ShapeObjSelect", "TableCellBlock"],
        ]
        for seq in attempts:
            for cmd in seq:
                self.run_first_supported([cmd])
            # 표 안으로 진입했는지 확인용으로 셀 이동을 한 번 시도
            ok, _ = self.run_first_supported(["TableRightCell", "TableLowerCell", "TableDownCell"])
            if ok:
                # 진입 확인용으로 움직였을 수 있으니 가능한 첫 셀로 복귀 시도
                for _i in range(5):
                    self.run_first_supported(["TableLeftCell"])
                for _i in range(5):
                    self.run_first_supported(["TableUpperCell", "TableUpCell"])
                return True, "OK"
            self.run_first_supported(["CloseEx", "Cancel", "ShapeObjSelect"])
        return False, "표 안으로 진입하지 못했습니다."
    def _exit_table_to_next_paragraph(self):
        self.run_first_supported(["CloseEx", "Cancel", "Esc"])
        self.run_first_supported(["MoveParaEnd", "MoveRight"])
        self.insert_paragraph_break()
    def _move_right_n(self, n: int):
        last_msg = ""
        for _ in range(max(0, int(n))):
            ok, msg = self.run_first_supported(["MoveRight"])
            if not ok:
                return False, msg
            last_msg = msg
        return True, last_msg or "OK"
    def _delete_once(self):
        return self.run_first_supported(["Delete", "DeleteBack", "BackSpace"])
    def insert_document_title_box(self, filepath_abs: str, title_text: str):
        ok, msg = self.insert_file(filepath_abs)
        if not ok:
            return False, msg
        time.sleep(0.08)
        ok, msg = self._move_right_n(2)
        if not ok:
            return False, f"제목박스 진입 실패: {msg}"
        ok, msg = self.set_current_charshape("HY헤드라인M", 23, bold=True)
        if not ok:
            return False, msg
        ok, msg = self.insert_text(title_text)
        if not ok:
            return False, msg
        self._move_right_n(2)
        self.insert_paragraph_break()
        return True, "문서제목 박스 삽입 완료"
    def insert_section_title_box(self, filepath_abs: str, number_text: str, title_text: str):
        ok, msg = self.insert_file(filepath_abs)
        if not ok:
            return False, msg
        time.sleep(0.08)
        ok, msg = self._move_right_n(1)
        if not ok:
            return False, f"소제목박스 첫 칸 진입 실패: {msg}"
        self._delete_once()
        ok, msg = self.set_current_charshape("HY헤드라인M", 16, bold=False)
        if not ok:
            return False, msg
        ok, msg = self.insert_text(number_text)
        if not ok:
            return False, msg
        ok, msg = self._move_right_n(3)
        if not ok:
            return False, f"소제목박스 제목 칸 이동 실패: {msg}"
        ok, msg = self.set_current_charshape("HY헤드라인M", 16, bold=False)
        if not ok:
            return False, msg
        ok, msg = self.insert_text(title_text)
        if not ok:
            return False, msg
        self._move_right_n(1)
        self.insert_paragraph_break()
        return True, "제목 박스 삽입 완료"
    def insert_picture_clipboard(self, filepath_abs: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        path = os.path.abspath(filepath_abs)
        if not os.path.exists(path):
            return False, f"이미지 파일이 없습니다: {path}"
        if Image is None or win32clipboard is None:
            return False, "심볼 삽입을 위해 pillow + pywin32 필요\n설치: python -m pip install pillow pywin32"
        try:
            im = Image.open(path)
            if im.mode == "RGBA":
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[3])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            output = io.BytesIO()
            im.save(output, "BMP")
            data = output.getvalue()[14:]
            output.close()
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
            for cmd in ["Paste", "ClipboardPaste", "PasteClipboard", "EditPaste"]:
                try:
                    self.hwp.Run(cmd)
                    return True, "심볼 삽입 완료"
                except Exception:
                    pass
            return True, "클립보드 복사 완료. 한글에서 Ctrl+V로 붙여넣으세요."
        except Exception as e:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            if is_rpc_error(e):
                self.reset()
            return False, f"심볼 삽입 실패: {e}"
    def _mili_to_unit(self, mm: float) -> int:
        try:
            fn = getattr(self.hwp, "MiliToHwpUnit", None)
            if callable(fn):
                return int(fn(float(mm)))
        except Exception:
            pass
        return int(float(mm) * 100)
    def apply_basic_report_page_setup(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ps = self.hwp.HParameterSet.HSecDef
            self.hwp.HAction.GetDefault("PageSetup", ps.HSet)
            ps.PageDef.LeftMargin  = self._mili_to_unit(20.0)
            ps.PageDef.RightMargin = self._mili_to_unit(20.0)
            ps.PageDef.TopMargin   = self._mili_to_unit(10.0)
            ps.PageDef.BottomMargin= self._mili_to_unit(15.0)
            ps.PageDef.HeaderLen   = self._mili_to_unit(10.0)
            ps.PageDef.FooterLen   = self._mili_to_unit(10.0)
            self.hwp.HAction.Execute("PageSetup", ps.HSet)
            return True, "편집용지 적용 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"편집용지 적용 실패: {e}"
    def _hwp_line_width(self, mm_str: str):
        try:
            fn = getattr(self.hwp, "HwpLineWidth", None)
            if callable(fn):
                return fn(mm_str)
        except Exception:
            pass
        try:
            mm = float(mm_str.replace("mm", "").strip())
        except Exception:
            mm = 0.1
        return self._mili_to_unit(mm)
    def _hwp_line_type(self, name: str):
        try:
            fn = getattr(self.hwp, "HwpLineType", None)
            if callable(fn):
                return fn(name)
        except Exception:
            pass
        return 0 if name == "None" else 7
    def _brush_type(self, name: str):
        try:
            fn = getattr(self.hwp, "BrushType", None)
            if callable(fn):
                return fn(name)
        except Exception:
            pass
        return name
    def _hatch_style(self, name: str):
        try:
            fn = getattr(self.hwp, "HatchStyle", None)
            if callable(fn):
                return fn(name)
        except Exception:
            pass
        return name
    def _rgb_color(self, r: int, g: int, b: int):
        try:
            fn = getattr(self.hwp, "RGBColor", None)
            if callable(fn):
                return int(fn(int(r), int(g), int(b)))
        except Exception:
            pass
        return int(r) | (int(g) << 8) | (int(b) << 16)

    def _set_fill_attr_color(self, fill_attr, r: int, g: int, b: int):
        """HCellBorderFill.FillAttr 계열에 셀 배경색 값을 안정적으로 넣는다."""
        color = self._rgb_color(r, g, b)
        hatch = self._rgb_color(153, 153, 153)
        brush = self._brush_type("NullBrush|WinBrush")
        hatch_style = self._hatch_style("None")

        # 한글/pywin32 환경에 따라 Type/type 대소문자 동작이 달라 둘 다 시도한다.
        for attr in ["Type", "type"]:
            try:
                setattr(fill_attr, attr, brush)
            except Exception:
                pass
        for attr in ["WinBrushFaceColor", "FaceColor"]:
            try:
                setattr(fill_attr, attr, color)
            except Exception:
                pass
        for attr in ["WinBrushHatchColor", "HatchColor"]:
            try:
                setattr(fill_attr, attr, hatch)
            except Exception:
                pass
        for attr in ["WinBrushFaceStyle", "WinBrushHatchStyle", "HatchStyle"]:
            try:
                setattr(fill_attr, attr, hatch_style)
            except Exception:
                pass
        try:
            fill_attr.WindowsBrush = 1
        except Exception:
            pass

    def _apply_cell_fill_color(self, r: int, g: int, b: int):
        """
        선택된 표 셀 배경색 적용.
        핵심: 배경색은 CellBorder/CellBorderFill이 아니라 CellFill 액션이 가장 안정적이다.
        """
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ps = self.hwp.HParameterSet.HCellBorderFill
            last_error = None
            loaded_action = None
            for action_name in ["CellFill", "CellBorderFill", "BorderFill"]:
                try:
                    self.hwp.HAction.GetDefault(action_name, ps.HSet)
                    loaded_action = action_name
                    break
                except Exception as e:
                    last_error = e
            if not loaded_action:
                raise last_error or RuntimeError("셀 배경색 액션을 불러오지 못했습니다.")

            self._set_fill_attr_color(ps.FillAttr, r, g, b)

            # 일부 환경에서는 선택 셀 값이 SelCellsBorderFill 쪽에 따로 들어가야 반영된다.
            try:
                self._set_fill_attr_color(ps.SelCellsBorderFill.FillAttr, r, g, b)
            except Exception:
                pass

            last_error = None
            for action_name in ["CellFill", loaded_action, "CellBorderFill", "BorderFill"]:
                try:
                    self.hwp.HAction.Execute(action_name, ps.HSet)
                    return True, "셀 배경색 적용 완료"
                except Exception as e:
                    last_error = e
            raise last_error or RuntimeError("셀 배경색 적용에 실패했습니다.")
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"셀 배경색 적용 실패: {e}"

    def apply_table_tool(self, action_id: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ps = self.hwp.HParameterSet.HCellBorderFill
            execute_action = "CellBorder"

            def _load_cell_action(preferred_action: str = "CellBorder"):
                """
                표 선 작업은 CellBorder로도 적용되지만, 배경 채우기는 한글 버전에 따라
                CellBorderFill 액션으로 실행해야 정상 반영된다.
                """
                last_error = None
                for action_name in [preferred_action, "CellBorder", "CellBorderFill"]:
                    try:
                        self.hwp.HAction.GetDefault(action_name, ps.HSet)
                        return action_name
                    except Exception as e:
                        last_error = e
                raise last_error

            _load_cell_action("CellBorder")
            if action_id == "기본선변경하기":
                w = self._hwp_line_width("0.1mm")
                for attr in ["WidthVert","WidthHorz","BorderWidthBottom","BorderWidthTop","BorderWidthRight","BorderWidthLeft"]:
                    try: setattr(ps, attr, w)
                    except Exception: pass
            elif action_id == "전체바깥선굵게변경하기":
                w = self._hwp_line_width("0.5mm")
                for attr in ["BorderWidthBottom","BorderWidthTop","BorderWidthRight","BorderWidthLeft"]:
                    try: setattr(ps, attr, w)
                    except Exception: pass
            elif action_id == "위쪽바깥선굵게변경하기":
                w = self._hwp_line_width("0.5mm")
                try: ps.BorderWidthTop = w
                except Exception: pass
            elif action_id == "아래쪽바깥선굵게변경하기":
                w = self._hwp_line_width("0.5mm")
                try: ps.BorderWidthBottom = w
                except Exception: pass
            elif action_id == "아래쪽바깥선이중선변경하기":
                w = self._hwp_line_width("0.5mm")
                try: ps.BorderWidthBottom = w
                except Exception: pass
                t = self._hwp_line_type("DoubleSlim")
                try: ps.BorderTypeBottom = t
                except Exception: pass
            elif action_id == "왼쪽바깥선없애기":
                t = self._hwp_line_type("None")
                try: ps.BorderTypeLeft = t
                except Exception: pass
            elif action_id == "오른쪽바깥선없애기":
                t = self._hwp_line_type("None")
                try: ps.BorderTypeRight = t
                except Exception: pass
            elif action_id == "표전체선없애기":
                t = self._hwp_line_type("None")
                for attr in ["TypeHorz","BorderTypeBottom","BorderTypeTop","BorderTypeRight","BorderTypeLeft"]:
                    try: setattr(ps, attr, t)
                    except Exception: pass
            elif action_id == "하늘색배경채우기":
                return self._apply_cell_fill_color(223, 230, 247)
            elif action_id == "연한노랑색배경채우기":
                return self._apply_cell_fill_color(250, 243, 219)
            elif action_id == "빨간색강조선넣기":
                # 표 바깥 4면(상/하/좌/우) 빨간색 0.5mm 실선
                w = self._hwp_line_width("0.5mm")
                t = self._hwp_line_type("Solid")
                red = self._rgb_color(255, 0, 0)
                # 색상
                for attr in ["BorderColorBottom", "ColorBottom"]:
                    try: setattr(ps, attr, red)
                    except Exception: pass
                for attr in ["BorderColorTop", "ColorTop"]:
                    try: setattr(ps, attr, red)
                    except Exception: pass
                for attr in ["BorderColorRight", "ColorRight"]:
                    try: setattr(ps, attr, red)
                    except Exception: pass
                # ※ 일부 한글/매크로 환경에서 Left 색 속성명이 오타( BorderCorlorLeft )로 노출되는 경우가 있어 둘 다 시도
                for attr in ["BorderColorLeft", "ColorLeft", "BorderCorlorLeft", "CorlorLeft"]:
                    try: setattr(ps, attr, red)
                    except Exception: pass
                # 굵기
                for attr in ["BorderWidthBottom", "WidthBottom"]:
                    try: setattr(ps, attr, w)
                    except Exception: pass
                for attr in ["BorderWidthTop", "WidthTop"]:
                    try: setattr(ps, attr, w)
                    except Exception: pass
                for attr in ["BorderWidthRight", "WidthRight"]:
                    try: setattr(ps, attr, w)
                    except Exception: pass
                for attr in ["BorderWidthLeft", "WidthLeft"]:
                    try: setattr(ps, attr, w)
                    except Exception: pass
                # 선 종류(실선)
                for attr in ["BorderTypeBottom", "TypeBottom"]:
                    try: setattr(ps, attr, t)
                    except Exception: pass
                for attr in ["BorderTypeTop", "TypeTop"]:
                    try: setattr(ps, attr, t)
                    except Exception: pass
                for attr in ["BorderTypeRight", "TypeRight"]:
                    try: setattr(ps, attr, t)
                    except Exception: pass
                for attr in ["BorderTypeLeft", "TypeLeft"]:
                    try: setattr(ps, attr, t)
                    except Exception: pass
            else:
                return False, f"알 수 없는 표 작업 action_id: {action_id}"
            try:
                self.hwp.HAction.Execute(execute_action, ps.HSet)
            except Exception:
                if execute_action != "CellBorder":
                    self.hwp.HAction.Execute("CellBorder", ps.HSet)
                else:
                    raise
            return True, "표 작업 적용 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"표 작업 실패: {e}"
    def _point_to_hwp_unit(self, pt: float) -> int:
        """한글 내부 단위로 변환(가능하면 PointToHwpUnit 사용)."""
        ok, msg = self.ensure()
        if not ok:
            return int(pt * 100)
        try:
            fn = getattr(self.hwp, "PointToHwpUnit", None)
            if callable(fn):
                return int(fn(float(pt)))
        except Exception:
            pass
        # fallback: 많은 환경에서 1pt = 100 단위로 동작
        return int(float(pt) * 100)
    def apply_charshape(self, font_name: str | None = None, font_size_pt: int | None = None, font_color_rgb: tuple[int,int,int] | None = None, bold: bool | None = None):
        """
        선택 영역 또는 이후 입력될 글자에 글꼴/글자크기/색상/굵게 적용.
        """
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ps = self.hwp.HParameterSet.HCharShape
            self.hwp.HAction.GetDefault("CharShape", ps.HSet)
            if font_name:
                for attr in [
                    "FaceNameHangul", "FaceNameHanja", "FaceNameLatin", "FaceNameJapanese",
                    "FaceNameOther", "FaceNameSymbol", "FaceNameUser"
                ]:
                    try:
                        setattr(ps, attr, font_name)
                    except Exception:
                        pass
            if font_size_pt is not None:
                try:
                    ps.Height = self._point_to_hwp_unit(float(font_size_pt))
                except Exception:
                    try:
                        ps.Size = self._point_to_hwp_unit(float(font_size_pt))
                    except Exception:
                        pass
            if font_color_rgb is not None:
                r, g, b = font_color_rgb
                col = (int(r) | (int(g) << 8) | (int(b) << 16))
                for attr in ["TextColor", "FontColor", "Color"]:
                    try:
                        setattr(ps, attr, col)
                    except Exception:
                        pass
            if bold is not None:
                for attr in ["Bold", "BoldExp"]:
                    try:
                        setattr(ps, attr, 1 if bold else 0)
                    except Exception:
                        pass
                for attr in ["Weight"]:
                    try:
                        setattr(ps, attr, 700 if bold else 400)
                    except Exception:
                        pass
            self.hwp.HAction.Execute("CharShape", ps.HSet)
            return True, "글자 적용 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"글자 적용 실패: {e}"
    def get_selected_text(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        if win32clipboard is None:
            return False, "pywin32 clipboard 모듈을 사용할 수 없습니다."

        # 중요:
        # 한글에서 블록을 지정하지 않은 상태로 Copy를 실행하면 클립보드가 바뀌지 않는 경우가 있다.
        # 이때 직전에 복사해 둔 프롬프트가 그대로 남아 있으면, 그 프롬프트를 선택 텍스트로 오인하여
        # '서식 자동 지정하기'가 프롬프트 내용을 한글 문서에 삽입하는 문제가 생긴다.
        # 따라서 Copy 전 클립보드에 고유한 임시 표식을 넣고, Copy 후에도 표식이 그대로이면
        # "선택 영역 없음"으로 판단한다.
        backup = get_clipboard_text()
        sentinel = f"__JBE_HWP_FORMAT_HELPER_NO_SELECTION__{time.time_ns()}__"
        try:
            set_clipboard_text(sentinel)
            time.sleep(0.03)

            self.hwp.Run("Copy")
            time.sleep(0.08)

            text = get_clipboard_text()
            set_clipboard_text(backup)

            if text == sentinel or not text:
                return False, "선택한 텍스트를 읽지 못했습니다. 한글에서 서식을 적용할 범위를 먼저 블록 지정하세요."

            return True, text
        except Exception as e:
            try:
                set_clipboard_text(backup)
            except Exception:
                pass
            if is_rpc_error(e):
                self.reset()
            return False, f"선택 텍스트 읽기 실패: {e}"
    def delete_selection(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            try:
                self.hwp.Run("Delete")
            except Exception:
                self.hwp.Run("Cut")
            return True, "선택 영역 삭제 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"선택 영역 삭제 실패: {e}"
    def set_current_charshape(self, font_name: str, font_size_pt: int, bold: bool = False):
        return self.apply_charshape(font_name=font_name, font_size_pt=font_size_pt, bold=bold)
    def insert_report_line(self, text: str, font_name: str, font_size_pt: int, bold: bool = False):
        ok, msg = self.set_current_charshape(font_name, font_size_pt, bold=bold)
        if not ok:
            return False, msg
        return self.insert_text(text)
    def move_para_begin(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            self.hwp.Run("MoveParaBegin")
            return True, "OK"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문단 처음 이동 실패: {e}"
    def move_right(self, count: int):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            for _ in range(max(0, int(count))):
                self.hwp.Run("MoveRight")
            return True, "OK"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"커서 이동 실패: {e}"
    def move_para_end(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            self.hwp.Run("MoveParaEnd")
            return True, "OK"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문단 끝 이동 실패: {e}"
    def paragraph_shape_indent_at_caret(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            fn = getattr(self.hwp, "ParagraphShapeIndentAtCaret", None)
            if callable(fn):
                fn()
            else:
                self.hwp.Run("ParagraphShapeIndentAtCaret")
            return True, "OK"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문단 내어쓰기 적용 실패: {e}"
    def apply_indent_at_caret_for_current_para(self, caret_offset: int):
        ok, msg = self.move_para_begin()
        if not ok:
            return False, msg
        ok, msg = self.move_right(caret_offset)
        if not ok:
            return False, msg
        ok, msg = self.paragraph_shape_indent_at_caret()
        if not ok:
            return False, msg
        return self.move_para_end()

    def reset_selected_parashape(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ps = self.hwp.HParameterSet.HParaShape
            self.hwp.HAction.GetDefault("ParaShape", ps.HSet)
            for attr, value in [
                ("LeftMargin", 0), ("RightMargin", 0), ("Indent", 0),
                ("PrevSpacing", 0), ("NextSpacing", 0),
            ]:
                try:
                    setattr(ps, attr, value)
                except Exception:
                    pass
            try:
                ps.Alignment = 0
            except Exception:
                pass
            self.hwp.HAction.Execute("ParaShape", ps.HSet)
            return True, "문단 모양 초기화 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문단 모양 초기화 실패: {e}"

    def select_recent_paragraphs(self, para_count: int):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            cnt = max(1, int(para_count))
            for _ in range(cnt):
                self.hwp.Run("MoveSelPrevParaBegin")
            return True, "OK"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"최근 문단 선택 실패: {e}"

    def convert_selected_text_to_table(self, rows: int, cols: int):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ps = self.hwp.HParameterSet.HTableStrToTbl
            self.hwp.HAction.GetDefault("TableStringToTable", ps.HSet)
            tc = ps.TableCreation
            tc.Rows = max(1, int(rows))
            tc.Cols = max(1, int(cols))
            tc.WidthType = 1
            tc.HeightType = 0
            try:
                tc.WidthValue = self._mili_to_unit(0.0)
            except Exception:
                pass
            try:
                tc.HeightValue = self._mili_to_unit(0.0)
            except Exception:
                pass
            self.hwp.HAction.Execute("TableStringToTable", ps.HSet)
            return True, "문자열을 표로 변환 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문자열을 표로 변환 실패: {e}"

    def set_selected_table_treat_as_char(self, enabled: bool = True):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ctrl = getattr(self.hwp, "CurSelectedCtrl", None) or getattr(self.hwp, "ParentCtrl", None)
            if not ctrl:
                return True, "SKIP"
            pset = self.hwp.CreateSet("Table")
            pset.SetItem("TreatAsChar", bool(enabled))
            ctrl.Properties = pset
            return True, "OK"
        except Exception:
            return True, "SKIP"



    def _select_current_table_whole(self):
        """사용자 환경 기준: 표 생성 직후 아래 1번 + F5 3번 흐름 재현."""
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        attempts = [
            ["MoveDown", "TableCellBlock", "TableCellBlockExtend", "TableCellBlockExtend"],
            ["MoveDown", "MoveRight", "TableCellBlock", "TableCellBlockExtend", "TableCellBlockExtend"],
            ["MoveDown", "FindCtrl", "TableCellBlock", "TableCellBlockExtend", "TableCellBlockExtend"],
            ["MoveDown", "ShapeObjSelect", "TableCellBlock", "TableCellBlockExtend", "TableCellBlockExtend"],
        ]
        for seq in attempts:
            ok_all = True
            for cmd in seq:
                ok, _ = self.run_first_supported([cmd])
                if not ok:
                    ok_all = False
                    break
            if ok_all:
                return True, "OK"
            self.run_first_supported(["Cancel", "CloseEx", "Esc"])
        return False, "표 전체 선택 실패"

    def insert_pipe_table(self, rows_data, font_name: str = "굴림체", font_size_pt: int = 12):
        if not rows_data:
            return True, "SKIP"
        text_lines = ["\t".join([str(c).strip() for c in row]) for row in rows_data]
        table_text = "\r\n".join(text_lines)
        ok, msg = self.insert_text(table_text)
        if not ok:
            return False, msg

        # 표 문자열 단계에서 먼저 글꼴을 지정해 두면, 문자열을 표로 변환한 뒤에도
        # 셀 안 텍스트에 같은 글꼴이 유지될 가능성이 높다.
        ok, msg = self.select_recent_paragraphs(len(text_lines))
        if not ok:
            return False, msg
        self.apply_charshape(font_name=font_name, font_size_pt=font_size_pt, bold=False)

        ok, msg = self.convert_selected_text_to_table(len(rows_data), max(len(r) for r in rows_data))
        if not ok:
            return False, msg

        ok_sel, _ = self._select_current_table_whole()
        if ok_sel:
            self.set_selected_table_treat_as_char(True)
            self.reset_selected_parashape()
            # 표 전체 선택 상태에서 한 번 더 굴림체 12pt를 보정 적용
            self.apply_charshape(font_name=font_name, font_size_pt=font_size_pt, bold=False)
            for aid in [
                "왼쪽바깥선없애기",
                "오른쪽바깥선없애기",
                "위쪽바깥선굵게변경하기",
                "아래쪽바깥선굵게변경하기",
            ]:
                self.apply_table_tool(aid)

        # 사용자 환경 기준: 표 전체 선택 후 ESC를 누르면 마지막 셀 맨 앞으로 이동하고,
        # 그다음 아래 방향키 1번으로 표 밖으로 빠져나옴.
        self.run_first_supported(["Cancel", "CloseEx", "Esc"])
        self.run_first_supported(["MoveDown"])
        return True, "표 삽입 완료"


    # ------------------------------------------------------------------
    # 선택 셀 범위 텍스트 정리 기능(v1.4)
    # ------------------------------------------------------------------
    def _cell_get_hwp(self, focus: bool = False):
        """셀 정리 작업용 한글 객체 확보.
        처리 중에는 매 명령마다 창을 다시 앞으로 가져오지 않아 속도와 안정성을 높인다.
        """
        if self.hwp is None:
            ok, msg = self.connect() if focus else self.connect_without_focus()
            if not ok:
                raise RuntimeError(msg)
        return self.hwp

    def _cell_run_cmd(self, command: str, delay: float = 0.0):
        hwp = self._cell_get_hwp()
        try:
            hwp.Run(command)
            if delay:
                time.sleep(delay)
            return True
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            raise RuntimeError(f"한글 명령 실행 실패({command}): {e}")

    def _cell_try_cmd(self, command: str, delay: float = 0.0):
        try:
            self._cell_run_cmd(command, delay)
            return True
        except Exception:
            return False

    def _cell_focus_hwp(self):
        hwp = self._cell_get_hwp(focus=True)
        try:
            hwp.XHwpWindows.Item(0).SetFocus()
            time.sleep(0.01)
        except Exception:
            pass

    def _cell_get_pos(self):
        hwp = self._cell_get_hwp()
        try:
            return hwp.GetPos()
        except Exception:
            return None

    def _cell_set_pos(self, pos):
        if pos is None:
            return False
        hwp = self._cell_get_hwp()
        try:
            hwp.SetPos(pos[0], pos[1], pos[2])
            return True
        except Exception:
            return False

    def _cell_col_to_num(self, col_text):
        n = 0
        for ch in str(col_text).upper():
            n = n * 26 + (ord(ch) - ord("A") + 1)
        return n

    def _cell_num_to_col(self, n):
        n = int(n)
        result = ""
        while n:
            n, r = divmod(n - 1, 26)
            result = chr(ord("A") + r) + result
        return result

    def cell_addr_to_text(self, col, row):
        return f"{self._cell_num_to_col(col)}{int(row)}"

    def _cell_parse_addr(self, col_text, row_text):
        col = self._cell_col_to_num(col_text)
        row = int(row_text)
        return col, row, f"{str(col_text).upper()}{row_text}"

    def get_table_cell_addr(self, focus_before: bool = True):
        """현재 커서가 위치한 한글 표 셀 주소를 A1 형식으로 읽는다."""
        if focus_before:
            ok, msg = self.ensure()
        else:
            ok, msg = self.connect_without_focus()
        if not ok:
            raise RuntimeError(msg)
        try:
            indicator = self.hwp.KeyIndicator()
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            raise RuntimeError(f"셀 주소를 읽지 못했습니다. 한글 표 안에 커서를 둔 뒤 다시 시도하세요.\n\n오류: {e}")

        try:
            last = str(indicator[-1])
            addr = last[1:].split(")")[0].strip()
            m = CELL_ADDR_RE.search(addr)
            if m:
                return self._cell_parse_addr(m.group(1), m.group(2))
        except Exception:
            pass

        try:
            last = str(indicator[-1])
            matches = CELL_ADDR_RE.findall(last)
            if matches:
                col_text, row_text = matches[-1]
                return self._cell_parse_addr(col_text, row_text)
        except Exception:
            pass

        joined = " ".join(str(x) for x in indicator)
        matches = CELL_ADDR_RE.findall(joined)
        if matches:
            col_text, row_text = matches[-1]
            return self._cell_parse_addr(col_text, row_text)

        raise RuntimeError(
            "셀 주소를 읽지 못했습니다.\n\n"
            "한글 표 안의 셀을 클릭한 뒤 다시 드래그하세요.\n\n"
            f"KeyIndicator 결과:\n{repr(indicator)}"
        )

    def cell_move_right(self):
        if not self._cell_try_cmd("TableRightCell"):
            raise RuntimeError("오른쪽 셀로 이동하지 못했습니다.")

    def cell_move_left(self):
        if not self._cell_try_cmd("TableLeftCell"):
            raise RuntimeError("왼쪽 셀로 이동하지 못했습니다.")

    def cell_move_down(self):
        if not self._cell_try_cmd("TableLowerCell"):
            raise RuntimeError("아래쪽 셀로 이동하지 못했습니다.")

    def cell_move_up(self):
        if not self._cell_try_cmd("TableUpperCell"):
            raise RuntimeError("위쪽 셀로 이동하지 못했습니다.")

    def cell_move_to_addr(self, target_col, target_row):
        cur_col, cur_row, _ = self.get_table_cell_addr()
        row_diff = int(target_row) - int(cur_row)
        col_diff = int(target_col) - int(cur_col)

        if row_diff > 0:
            for _ in range(row_diff):
                self.cell_move_down()
        elif row_diff < 0:
            for _ in range(-row_diff):
                self.cell_move_up()

        if col_diff > 0:
            for _ in range(col_diff):
                self.cell_move_right()
        elif col_diff < 0:
            for _ in range(-col_diff):
                self.cell_move_left()

        new_col, new_row, new_addr = self.get_table_cell_addr()
        if (new_col, new_row) != (target_col, target_row):
            raise RuntimeError(
                "목표 셀로 이동하지 못했습니다.\n\n"
                f"목표 셀: {self.cell_addr_to_text(target_col, target_row)}\n"
                f"현재 셀: {new_addr}"
            )

    def cell_select_current_text(self):
        if not self._cell_try_cmd("MoveListBegin", 0.005):
            raise RuntimeError("현재 셀 시작 위치로 이동하지 못했습니다.")
        start_pos = self._cell_get_pos()
        if start_pos is None:
            raise RuntimeError("현재 셀 시작 위치를 저장하지 못했습니다.")
        if not self._cell_try_cmd("MoveSelListEnd", 0.005):
            raise RuntimeError("현재 셀 내부 텍스트 선택에 실패했습니다.")
        return start_pos

    def cell_get_selected_text_fast(self):
        hwp = self._cell_get_hwp()
        for fmt in ("TEXT", "UNICODE"):
            try:
                text = hwp.GetTextFile(fmt, "saveblock")
                if text is not None:
                    return cell_normalize_text(text)
            except Exception:
                pass
        return None

    def cell_copy_current_text_clipboard(self):
        if win32clipboard is None:
            raise RuntimeError("pywin32 clipboard 모듈을 사용할 수 없습니다.")
        start_pos = self.cell_select_current_text()
        backup = get_clipboard_text()
        try:
            set_clipboard_text(CELL_CLIPBOARD_SENTINEL)
            time.sleep(0.01)
            self.hwp.Run("Copy")
            time.sleep(0.03)
            copied = get_clipboard_text()
        finally:
            self._cell_try_cmd("Cancel", 0.005)
            self._cell_set_pos(start_pos)
            try:
                set_clipboard_text(backup)
            except Exception:
                pass

        if copied is None or copied == CELL_CLIPBOARD_SENTINEL:
            return ""

        copied = cell_normalize_text(copied)
        if "\t" in copied:
            raise RuntimeError(
                "현재 셀 하나가 아니라 여러 셀이 복사된 것으로 보입니다.\n"
                "작업을 중단합니다."
            )
        return copied

    def cell_insert_text_over_selection(self, text):
        text = cell_normalize_text(text)
        hwp = self._cell_get_hwp()
        try:
            if text == "":
                hwp.Run("Delete")
                return
            hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
            hwp.HParameterSet.HInsertText.Text = text
            hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            raise RuntimeError(
                "현재 셀 텍스트 교체에 실패했습니다.\n\n"
                f"입력값: {repr(text)}\n"
                f"오류: {e}"
            )

    def cell_replace_current_text_clipboard_fallback(self, new_text):
        self.cell_select_current_text()
        self.cell_insert_text_over_selection(new_text)
        self._cell_try_cmd("MoveListBegin", 0.005)

    def cell_transform_current_fast(self, transform_func):
        """현재 셀의 텍스트를 읽고 transform_func 적용 후 셀 안 텍스트만 교체한다."""
        start_pos = self.cell_select_current_text()
        current_text = self.cell_get_selected_text_fast()

        if current_text is None:
            self._cell_try_cmd("Cancel", 0.005)
            self._cell_set_pos(start_pos)
            current_text = self.cell_copy_current_text_clipboard()
            new_text = transform_func(current_text)
            if new_text == current_text:
                return False
            self.cell_replace_current_text_clipboard_fallback(new_text)
            return True

        new_text = transform_func(current_text)
        if new_text == current_text:
            self._cell_try_cmd("Cancel", 0.005)
            self._cell_set_pos(start_pos)
            return False

        self.cell_insert_text_over_selection(new_text)
        self._cell_try_cmd("MoveListBegin", 0.005)
        return True

    def _cell_read_int_attr(self, obj, names):
        for name in names:
            try:
                value = getattr(obj, name)
            except Exception:
                continue
            try:
                if value is None:
                    continue
                if isinstance(value, bool):
                    continue
                return int(value)
            except Exception:
                try:
                    text = str(value).strip()
                    if text.isdigit():
                        return int(text)
                except Exception:
                    pass
        return None

    def _cell_current_span_from_properties(self):
        """현재 셀의 병합 span 속성을 읽어 본다.
        한글 버전별 속성명이 달라 실패할 수 있으므로, 실패 시 None을 반환하고 이동 검사로 보완한다.
        최초 탐색 결과를 캐시해 반복 예외로 인한 속도 저하를 줄인다.
        """
        if self._cell_span_prop_available is False:
            return None

        hwp = self._cell_get_hwp()
        row_names = [
            "RowSpan", "Rowspan", "rowSpan",
            "RowMerge", "MergedRowCount", "MergeRowCount",
        ]
        col_names = [
            "ColSpan", "Colspan", "colSpan", "ColumnSpan",
            "ColMerge", "ColumnMerge", "MergedColCount", "MergedColumnCount", "MergeColCount",
        ]

        def _read_from_action(action, pset_name):
            ps = getattr(hwp.HParameterSet, pset_name)
            hwp.HAction.GetDefault(action, ps.HSet)
            objects = [ps]
            for nested_name in ["CellShape", "TableCell", "Cell", "ShapeCell"]:
                try:
                    nested = getattr(ps, nested_name)
                    if nested is not None:
                        objects.append(nested)
                except Exception:
                    pass
            for obj in objects:
                row_span = self._cell_read_int_attr(obj, row_names)
                col_span = self._cell_read_int_attr(obj, col_names)
                if row_span is not None or col_span is not None:
                    return max(1, int(row_span or 1)), max(1, int(col_span or 1))
            return None

        if self._cell_span_prop_action:
            try:
                action, pset_name = self._cell_span_prop_action
                return _read_from_action(action, pset_name)
            except Exception:
                self._cell_span_prop_action = None
                self._cell_span_prop_available = None

        action_candidates = [
            ("CellProperty", "HCellShape"),
            ("CellShape", "HCellShape"),
            ("TableCellProperty", "HCellShape"),
            ("TablePropertyDialog", "HShapeObject"),
        ]
        for action, pset_name in action_candidates:
            try:
                result = _read_from_action(action, pset_name)
            except Exception:
                continue
            if result is not None:
                self._cell_span_prop_action = (action, pset_name)
                self._cell_span_prop_available = True
                return result

        self._cell_span_prop_available = False
        return None

    def _cell_neighbor_right_skips(self, cur_col, cur_row):
        pos = self._cell_get_pos()
        if pos is None:
            return False, ""
        try:
            if not self._cell_try_cmd("TableRightCell", 0):
                return False, ""
            try:
                n_col, n_row, n_addr = self.get_table_cell_addr(focus_before=False)
            except Exception:
                return False, ""
            if int(n_row) == int(cur_row) and int(n_col) > int(cur_col) + 1:
                return True, n_addr
            return False, n_addr
        finally:
            self._cell_set_pos(pos)

    def _cell_neighbor_down_skips(self, cur_col, cur_row):
        pos = self._cell_get_pos()
        if pos is None:
            return False, ""
        try:
            if not self._cell_try_cmd("TableLowerCell", 0):
                return False, ""
            try:
                n_col, n_row, n_addr = self.get_table_cell_addr(focus_before=False)
            except Exception:
                return False, ""
            if int(n_col) == int(cur_col) and int(n_row) > int(cur_row) + 1:
                return True, n_addr
            return False, n_addr
        finally:
            self._cell_set_pos(pos)

    def _cell_raise_merged_detected(self, addr, detail=""):
        extra = f"\n확인 내용: {detail}" if detail else ""
        raise RuntimeError(
            "병합 셀이 포함되어 작업을 중단했습니다.\n\n"
            f"감지 위치: {addr}{extra}\n\n"
            "셀 병합을 해제하거나, 병합 셀이 포함되지 않은 범위만 선택한 뒤 다시 실행하세요."
        )

    def cell_validate_range_no_merged_cells(self, left_col, top_row, right_col, bottom_row):
        self._cell_focus_hwp()
        self._cell_try_cmd("Cancel", 0)

        row_count = int(bottom_row) - int(top_row) + 1
        col_count = int(right_col) - int(left_col) + 1
        self.cell_move_to_addr(left_col, top_row)

        for r in range(row_count):
            for c in range(col_count):
                expected_col = int(left_col) + c
                expected_row = int(top_row) + r
                expected_addr = self.cell_addr_to_text(expected_col, expected_row)
                cur_col, cur_row, cur_addr = self.get_table_cell_addr(focus_before=False)

                if (cur_col, cur_row) != (expected_col, expected_row):
                    raise RuntimeError(
                        "병합 셀 또는 비정형 표 구조가 감지되어 작업을 중단했습니다.\n\n"
                        f"예상 셀: {expected_addr}\n"
                        f"현재 셀: {cur_addr}\n\n"
                        "병합 셀이 포함되지 않은 일반 셀 범위만 처리합니다."
                    )

                span = self._cell_current_span_from_properties()
                if span is not None:
                    row_span, col_span = span
                    if int(row_span) > 1 or int(col_span) > 1:
                        self._cell_raise_merged_detected(
                            cur_addr,
                            f"행 병합 {row_span}칸 / 열 병합 {col_span}칸"
                        )

                # 세로 병합은 행 단위 이동 검사만으로는 놓칠 수 있어 각 셀에서 아래쪽 이동을 확인한다.
                down_skip, down_addr = self._cell_neighbor_down_skips(cur_col, cur_row)
                if down_skip:
                    self._cell_raise_merged_detected(cur_addr, f"아래쪽 이동 시 {down_addr}로 건너뜀")

                if c < col_count - 1:
                    self.cell_move_right()
                    next_expected = self.cell_addr_to_text(expected_col + 1, expected_row)
                    n_col, n_row, n_addr = self.get_table_cell_addr(focus_before=False)
                    if (n_col, n_row) != (expected_col + 1, expected_row):
                        raise RuntimeError(
                            "병합 셀 또는 비정형 표 구조가 감지되어 작업을 중단했습니다.\n\n"
                            f"예상 셀: {next_expected}\n"
                            f"현재 셀: {n_addr}\n\n"
                            "병합 셀이 포함되지 않은 일반 셀 범위만 처리합니다."
                        )
                else:
                    # 선택 범위의 오른쪽 끝에 있는 병합 셀도 놓치지 않도록 한 번 더 확인한다.
                    right_skip, right_addr = self._cell_neighbor_right_skips(cur_col, cur_row)
                    if right_skip:
                        self._cell_raise_merged_detected(cur_addr, f"오른쪽 이동 시 {right_addr}로 건너뜀")

            if r < row_count - 1:
                self.cell_move_down()
                for _ in range(col_count - 1):
                    self.cell_move_left()

                row_start_expected = self.cell_addr_to_text(int(left_col), int(top_row) + r + 1)
                n_col, n_row, n_addr = self.get_table_cell_addr(focus_before=False)
                if (n_col, n_row) != (int(left_col), int(top_row) + r + 1):
                    raise RuntimeError(
                        "병합 셀 또는 비정형 표 구조가 감지되어 작업을 중단했습니다.\n\n"
                        f"예상 셀: {row_start_expected}\n"
                        f"현재 셀: {n_addr}\n\n"
                        "병합 셀이 포함되지 않은 일반 셀 범위만 처리합니다."
                    )

    def process_recorded_cell_range(self, start_col, start_row, end_col, end_row, transform_func):
        left_col = min(int(start_col), int(end_col))
        right_col = max(int(start_col), int(end_col))
        top_row = min(int(start_row), int(end_row))
        bottom_row = max(int(start_row), int(end_row))

        row_count = bottom_row - top_row + 1
        col_count = right_col - left_col + 1

        self._cell_focus_hwp()
        self.cell_validate_range_no_merged_cells(left_col, top_row, right_col, bottom_row)
        self.cell_move_to_addr(left_col, top_row)

        cur_col, cur_row, cur_addr = self.get_table_cell_addr()
        start_addr = self.cell_addr_to_text(left_col, top_row)
        if (cur_col, cur_row) != (left_col, top_row):
            raise RuntimeError(
                "시작 셀로 이동하지 못했습니다.\n\n"
                f"예상 시작 셀: {start_addr}\n"
                f"현재 셀: {cur_addr}"
            )

        changed = 0
        for r in range(row_count):
            for c in range(col_count):
                if self.cell_transform_current_fast(transform_func):
                    changed += 1
                if c < col_count - 1:
                    self.cell_move_right()

            if r < row_count - 1:
                self.cell_move_down()
                for _ in range(col_count - 1):
                    self.cell_move_left()

        return {
            "left_col": left_col,
            "right_col": right_col,
            "top_row": top_row,
            "bottom_row": bottom_row,
            "start_addr": self.cell_addr_to_text(left_col, top_row),
            "end_addr": self.cell_addr_to_text(right_col, bottom_row),
            "row_count": row_count,
            "col_count": col_count,
            "changed": changed,
        }


def cell_normalize_text(text):
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.rstrip("\n")
    return text


def cell_clean_space_text(text):
    return CELL_SPACE_RE.sub("", cell_normalize_text(text))


def cell_replace_text_plain(text, find_text, replace_text):
    return cell_normalize_text(text).replace(find_text, replace_text)


def cell_add_prefix_text(text, prefix):
    return prefix + cell_normalize_text(text)


def cell_add_suffix_text(text, suffix):
    return cell_normalize_text(text) + suffix


# -----------------------------------------------------------------------------
# K-에듀파인 WXSClient 기안창 연결 보조 클래스(v1.5)
# -----------------------------------------------------------------------------
# 일반 한글은 ROT의 !HwpObject.* 객체를 사용하지만,
# K-에듀파인 기안창은 WXSClient.exe 내부 Internet Explorer_Server의
# frame[0].window.editor1 ActiveX 객체를 직접 잡아 InvokeTypes로 호출한다.
# 현재 v1.6에서는 글자 작업과 표 작업 일부를 지원한다.
class WxsHwpBridge:
    TARGET_EXE = "wxsclient.exe"

    def __init__(self):
        self.editor = None
        self.ie_hwnd = None
        self.main_hwnd = None
        self.edit_hwnd = None
        self.last_msg = ""

    def reset(self):
        self.editor = None
        self.ie_hwnd = None
        self.main_hwnd = None
        self.edit_hwnd = None
        self.last_msg = ""

    def _format_hwnd(self, hwnd: int) -> str:
        try:
            title = win32gui.GetWindowText(hwnd) if win32gui else ""
            cls = win32gui.GetClassName(hwnd) if win32gui else ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd) if win32process else (0, 0)
            exe = os.path.basename(ui_get_process_path(pid)) if pid else ""
            return f"hwnd=0x{int(hwnd):x}, pid={pid}, exe={exe}, class={cls}, title={title}"
        except Exception:
            return f"hwnd=0x{int(hwnd):x}"

    def _enum_top_windows(self):
        if win32gui is None:
            return []
        result = []
        def cb(hwnd, _):
            result.append(hwnd)
            return True
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            pass
        return result

    def _enum_children_recursive(self, hwnd: int, max_depth: int = 12):
        result = []
        if win32gui is None:
            return result
        def walk(parent, depth):
            if depth > max_depth:
                return
            children = []
            def cb(ch, _):
                children.append(ch)
                return True
            try:
                win32gui.EnumChildWindows(parent, cb, None)
            except Exception:
                return
            for ch in children:
                result.append((depth, ch))
                walk(ch, depth + 1)
        walk(hwnd, 1)
        return result

    def _hwnd_process_info(self, hwnd: int):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = 0
        path = ui_get_process_path(pid) if pid else ""
        exe = os.path.basename(path).lower() if path else ""
        try:
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            title = ""
        try:
            cls = win32gui.GetClassName(hwnd) or ""
        except Exception:
            cls = ""
        try:
            visible = bool(win32gui.IsWindowVisible(hwnd))
        except Exception:
            visible = False
        try:
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
        except Exception:
            w = h = 0
        return {
            "hwnd": hwnd,
            "pid": pid,
            "path": path,
            "exe": exe,
            "title": title,
            "class": cls,
            "visible": visible,
            "w": w,
            "h": h,
        }

    def _score_wxs_top(self, hwnd: int) -> int:
        info = self._hwnd_process_info(hwnd)
        score = 0
        if info["exe"] == self.TARGET_EXE:
            score += 20
        if info["visible"]:
            score += 10
        if info["class"] == "#32770":
            score += 8
        if "표준서식" in info["title"] or "결재" in info["title"]:
            score += 8
        if info["w"] > 400 and info["h"] > 400:
            score += 5
        return score

    def _find_wxs_top_windows(self):
        wins = []
        for hwnd in self._enum_top_windows():
            info = self._hwnd_process_info(hwnd)
            if info["exe"] == self.TARGET_EXE:
                wins.append(hwnd)
        wins.sort(key=self._score_wxs_top, reverse=True)
        return wins

    def _find_ie_servers(self):
        ies = []
        seen = set()
        for top in self._find_wxs_top_windows():
            top_score = self._score_wxs_top(top)
            for depth, ch in self._enum_children_recursive(top):
                if ch in seen:
                    continue
                seen.add(ch)
                info = self._hwnd_process_info(ch)
                if (info.get("class") or "").lower() == "internet explorer_server":
                    ies.append((top_score, top, depth, ch))
        ies.sort(key=lambda x: (x[0], -x[2]), reverse=True)
        return ies

    def _get_document_from_ie(self, hwnd: int):
        if pythoncom is None or win32gui is None or win32com is None:
            raise RuntimeError("pywin32 모듈을 사용할 수 없습니다.")
        msg = win32gui.RegisterWindowMessage("WM_HTML_GETOBJECT")
        ret = win32gui.SendMessageTimeout(
            hwnd,
            msg,
            0,
            0,
            win32con.SMTO_ABORTIFHUNG,
            3000,
        )
        if isinstance(ret, tuple):
            lresult = ret[1] if len(ret) >= 2 else (ret[0] if ret else 0)
        else:
            lresult = ret
        if not lresult:
            raise RuntimeError(f"WM_HTML_GETOBJECT 결과가 없습니다: {ret!r}")
        disp = pythoncom.ObjectFromLresult(lresult, pythoncom.IID_IDispatch, 0)
        return win32com.client.Dispatch(disp)

    def _get_frame_document(self, parent_doc, idx: int):
        try:
            return parent_doc.frames.item(idx).document
        except Exception:
            return None

    def _get_root_from_child(self, hwnd: int):
        if win32gui is None or not hwnd:
            return None
        try:
            # GA_ROOT = 2. Some pywin32 builds do not expose the constant.
            root = win32gui.GetAncestor(hwnd, getattr(win32con, "GA_ROOT", 2))
            if root:
                return root
        except Exception:
            pass
        try:
            cur = hwnd
            while True:
                parent = win32gui.GetParent(cur)
                if not parent:
                    return cur
                cur = parent
        except Exception:
            return hwnd

    def _find_hwp_main_edit_hwnd(self, root_hwnd: int | None = None):
        """WXSClient 내부의 실제 본문 편집창(HwpMainEditWnd)을 찾는다."""
        if win32gui is None:
            return None
        candidates = []
        roots = []
        if root_hwnd:
            roots.append(root_hwnd)
        roots.extend([h for h in self._find_wxs_top_windows() if h not in roots])
        seen = set()
        for root in roots:
            if not root or root in seen:
                continue
            seen.add(root)
            for _depth, ch in self._enum_children_recursive(root):
                try:
                    cls = win32gui.GetClassName(ch) or ""
                except Exception:
                    cls = ""
                if cls != "HwpMainEditWnd":
                    continue
                info = self._hwnd_process_info(ch)
                area = int(info.get("w") or 0) * int(info.get("h") or 0)
                if area <= 0:
                    continue
                candidates.append((area, ch))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _refresh_focus_hwnds(self):
        root = None
        if self.ie_hwnd and win32gui is not None:
            try:
                if win32gui.IsWindow(self.ie_hwnd):
                    root = self._get_root_from_child(self.ie_hwnd)
            except Exception:
                root = None
        if not root:
            tops = self._find_wxs_top_windows()
            root = tops[0] if tops else None
        self.main_hwnd = root
        self.edit_hwnd = self._find_hwp_main_edit_hwnd(root)
        return root, self.edit_hwnd

    def restore_focus(self):
        """작업 후 키보드 입력이 바로 이어지도록 기안창 본문으로 포커스를 돌린다."""
        if win32gui is None or win32con is None or win32process is None:
            return False
        try:
            root, edit = self._refresh_focus_hwnds()
            if not root:
                return False

            try:
                if win32gui.IsIconic(root):
                    win32gui.ShowWindow(root, win32con.SW_RESTORE)
                win32gui.ShowWindow(root, win32con.SW_SHOW)
            except Exception:
                pass

            attached = []
            try:
                cur_tid = win32api.GetCurrentThreadId() if win32api is not None else 0
                target_hwnd = edit or root
                target_tid, _ = win32process.GetWindowThreadProcessId(target_hwnd)
                fg = win32gui.GetForegroundWindow()
                fg_tid, _ = win32process.GetWindowThreadProcessId(fg) if fg else (0, 0)
                for tid in {target_tid, fg_tid}:
                    if cur_tid and tid and tid != cur_tid:
                        try:
                            win32process.AttachThreadInput(cur_tid, tid, True)
                            attached.append((cur_tid, tid))
                        except Exception:
                            pass

                try:
                    win32gui.BringWindowToTop(root)
                except Exception:
                    pass
                try:
                    win32gui.SetForegroundWindow(root)
                except Exception:
                    pass
                time.sleep(0.03)

                if edit:
                    try:
                        win32gui.SetFocus(edit)
                    except Exception:
                        try:
                            win32gui.PostMessage(edit, win32con.WM_SETFOCUS, 0, 0)
                        except Exception:
                            pass
            finally:
                for cur_tid, tid in attached:
                    try:
                        win32process.AttachThreadInput(cur_tid, tid, False)
                    except Exception:
                        pass
            return True
        except Exception:
            return False

    def connect(self):
        if pythoncom is None or win32com is None or win32gui is None or win32con is None or win32process is None:
            self.reset()
            return False, "K-에듀파인 기안창 연결에 필요한 pywin32 모듈을 사용할 수 없습니다."

        # WXSClient/HwpODTCtrl은 보통 32비트 프로세스이므로 64비트 Python/EXE에서는 실패할 수 있다.
        if sys.maxsize > 2**32:
            self.reset()
            return False, (
                "K-에듀파인 기안창 모드는 32비트 Python/EXE에서 실행해야 합니다.\n"
                "예: py -V:3.14-32 app(1.13).py"
            )

        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

        errors = []
        for _score, _top, _depth, ie_hwnd in self._find_ie_servers():
            try:
                doc = self._get_document_from_ie(ie_hwnd)
                # 현재 기안 본문은 frame[0].document.parentWindow.editor1에 있다.
                for idx, editor_name in [(0, "editor1"), (1, "editor2")]:
                    fdoc = self._get_frame_document(doc, idx)
                    if fdoc is None:
                        continue
                    try:
                        editor = getattr(fdoc.parentWindow, editor_name)
                    except Exception:
                        continue
                    if editor is None:
                        continue
                    # 기본 속성 접근으로 실제 객체인지 확인
                    try:
                        _ = getattr(editor, "Name")
                    except Exception:
                        pass
                    self.editor = editor
                    self.ie_hwnd = ie_hwnd
                    self._refresh_focus_hwnds()
                    self.last_msg = f"K-에듀파인 기안창 연결 완료: {editor_name}"
                    return True, self.last_msg
            except Exception as e:
                errors.append(f"{self._format_hwnd(ie_hwnd)}: {e}")

        self.reset()
        detail = "\n".join(errors[:5]) if errors else "WXSClient 기안창의 editor1 객체를 찾지 못했습니다."
        return False, "K-에듀파인 기안창 연결 실패:\n" + detail

    def ensure(self):
        if self.editor is not None:
            return True, "OK"
        return self.connect()

    def _dispatch_obj(self, obj):
        try:
            return win32com.client.Dispatch(obj)
        except Exception:
            return obj

    def _ole(self, obj=None):
        target = self.editor if obj is None else obj
        disp = self._dispatch_obj(target)
        ole = getattr(disp, "_oleobj_", None)
        if ole is None:
            raise RuntimeError("COM _oleobj_를 찾지 못했습니다.")
        return ole

    def _dispid(self, obj, name: str) -> int:
        ole = self._ole(obj)
        ids = ole.GetIDsOfNames(name)
        if isinstance(ids, (tuple, list)):
            return int(ids[0])
        return int(ids)

    def _invoke_method(self, obj, name: str, args=(), ret_type=None, arg_types=None):
        if ret_type is None:
            ret_type = (pythoncom.VT_VARIANT, 0)
        if arg_types is None:
            arg_types = tuple((pythoncom.VT_VARIANT, 1) for _ in args)
        ole = self._ole(obj)
        dispid = self._dispid(obj, name)
        return ole.InvokeTypes(
            dispid,
            0,
            pythoncom.DISPATCH_METHOD,
            ret_type,
            arg_types,
            *args,
        )

    def _set_item(self, pset, key: str, value):
        return self._invoke_method(
            pset,
            "SetItem",
            (key, value),
            ret_type=(pythoncom.VT_VARIANT, 0),
            arg_types=((pythoncom.VT_BSTR, 1), (pythoncom.VT_VARIANT, 1)),
        )

    def _item(self, pset, key: str):
        return self._invoke_method(
            pset,
            "Item",
            (key,),
            ret_type=(pythoncom.VT_VARIANT, 0),
            arg_types=((pythoncom.VT_BSTR, 1),),
        )

    def _create_action(self, action_name: str):
        return self._invoke_method(
            self.editor,
            "CreateAction",
            (action_name,),
            ret_type=(pythoncom.VT_DISPATCH, 0),
            arg_types=((pythoncom.VT_BSTR, 1),),
        )

    def _action_create_set(self, action):
        return self._invoke_method(
            action,
            "CreateSet",
            (),
            ret_type=(pythoncom.VT_DISPATCH, 0),
            arg_types=(),
        )

    def _action_get_default(self, action, pset):
        return self._invoke_method(
            action,
            "GetDefault",
            (pset,),
            ret_type=(pythoncom.VT_VARIANT, 0),
            arg_types=((pythoncom.VT_DISPATCH, 1),),
        )

    def _action_execute(self, action, pset):
        return self._invoke_method(
            action,
            "Execute",
            (pset,),
            ret_type=(pythoncom.VT_VARIANT, 0),
            arg_types=((pythoncom.VT_DISPATCH, 1),),
        )

    def run_cmd(self, cmd: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            self._invoke_method(
                self.editor,
                "Run",
                (cmd,),
                ret_type=(pythoncom.VT_VARIANT, 0),
                arg_types=((pythoncom.VT_BSTR, 1),),
            )
            self.restore_focus()
            return True, "OK"
        except Exception as e:
            self.reset()
            return False, f"K-에듀파인 기안창 명령 실행 실패({cmd}): {e}"

    def _rgb_color(self, r: int, g: int, b: int) -> int:
        try:
            return int(self._invoke_method(
                self.editor,
                "RGBColor",
                (int(r), int(g), int(b)),
                ret_type=(pythoncom.VT_VARIANT, 0),
                arg_types=((pythoncom.VT_I4, 1), (pythoncom.VT_I4, 1), (pythoncom.VT_I4, 1)),
            ))
        except Exception:
            return int(r) | (int(g) << 8) | (int(b) << 16)

    def _hwp_line_width(self, mm_str: str):
        """HwpCtrl 선 굵기 값.
        WXSClient editor1에서는 HwpLineWidth 호출이 실패하는 환경이 있어,
        한글 Action API에서 쓰는 선 굵기 enum 값으로 보정한다.
        이전 v1.6의 int(mm*100) fallback은 0.5mm를 50으로 넣어
        선택 셀에 얇은 선이 적용되는 문제가 있었다.
        """
        try:
            v = self._invoke_method(
                self.editor,
                "HwpLineWidth",
                (mm_str,),
                ret_type=(pythoncom.VT_VARIANT, 0),
                arg_types=((pythoncom.VT_BSTR, 1),),
            )
            if v is not None:
                return int(v)
        except Exception:
            pass

        key = str(mm_str or "").lower().replace("mm", "").strip()
        width_map = {
            "0": 0,
            "0.1": 0,
            "0.12": 1,
            "0.15": 2,
            "0.2": 3,
            "0.25": 4,
            "0.3": 5,
            "0.4": 6,
            "0.5": 7,
            "0.6": 8,
            "0.7": 9,
            "1": 10,
            "1.0": 10,
            "1.5": 11,
            "2": 12,
            "2.0": 12,
        }
        return width_map.get(key, 0)

    def _hwp_line_type(self, name: str):
        """HwpCtrl 선 종류 값.
        None=0, Solid=1이 중요하다. v1.6에서는 Solid fallback을 7로 둬서
        빨간색 강조선이 굵은 실선이 아니라 점선 계열로 적용될 수 있었다.
        """
        try:
            v = self._invoke_method(
                self.editor,
                "HwpLineType",
                (name,),
                ret_type=(pythoncom.VT_VARIANT, 0),
                arg_types=((pythoncom.VT_BSTR, 1),),
            )
            if v is not None:
                return int(v)
        except Exception:
            pass

        type_map = {
            "None": 0,
            "Solid": 1,
            "Dash": 2,
            "Dot": 3,
            "DashDot": 4,
            "DashDotDot": 5,
            "LongDash": 6,
            # 환경별 차이가 있을 수 있으나 기존 fallback보다 실제 이중선 계열에 가깝게 둔다.
            "DoubleSlim": 11,
            "Double": 11,
        }
        return type_map.get(str(name), 1)

    def _brush_type(self, name: str):
        try:
            return self._invoke_method(
                self.editor,
                "BrushType",
                (name,),
                ret_type=(pythoncom.VT_VARIANT, 0),
                arg_types=((pythoncom.VT_BSTR, 1),),
            )
        except Exception:
            return name

    def _hatch_style(self, name: str):
        try:
            return self._invoke_method(
                self.editor,
                "HatchStyle",
                (name,),
                ret_type=(pythoncom.VT_VARIANT, 0),
                arg_types=((pythoncom.VT_BSTR, 1),),
            )
        except Exception:
            return name

    def _safe_set_item(self, pset, key: str, value) -> bool:
        try:
            self._set_item(pset, key, value)
            return True
        except Exception:
            return False

    def _safe_set_any(self, pset, keys, value) -> bool:
        ok = False
        for key in keys:
            if self._safe_set_item(pset, key, value):
                ok = True
        return ok

    def _create_item_set(self, pset, item_name: str, set_name: str):
        return self._invoke_method(
            pset,
            "CreateItemSet",
            (item_name, set_name),
            ret_type=(pythoncom.VT_DISPATCH, 0),
            arg_types=((pythoncom.VT_BSTR, 1), (pythoncom.VT_BSTR, 1)),
        )

    def _set_fill_color_params(self, pset, r: int, g: int, b: int):
        """K-에듀파인 기안창 셀 배경색 설정.

        성공 확인된 방식(v1.10):
        - action: CellFill
        - pset: action.CreateSet()
        - FillAttr: pset.CreateItemSet("FillAttr", "DrawFillAttr")
        - Type = 1
        - WinBrushFaceStyle = 0xffffffff
        - WinBrushHatchColor = 0x00000000
        - WinBrushFaceColor = r | (g << 8) | (b << 16)

        WXSClient editor1에서는 RGBColor/BrushType/HatchStyle 함수가 노출되지 않으므로
        문자열 fallback을 쓰지 않고 숫자 상수만 사용한다.
        """
        color = int(r) | (int(g) << 8) | (int(b) << 16)
        fill = self._create_item_set(pset, "FillAttr", "DrawFillAttr")
        self._set_item(fill, "Type", 1)
        self._set_item(fill, "WinBrushFaceStyle", 0xFFFFFFFF)
        self._set_item(fill, "WinBrushHatchColor", 0x00000000)
        self._set_item(fill, "WinBrushFaceColor", color)

    def _execute_table_action(self, action_name: str, configure_func):
        action = self._create_action(action_name)
        pset = self._action_create_set(action)
        try:
            self._action_get_default(action, pset)
        except Exception:
            pass
        configure_func(pset)
        result = self._action_execute(action, pset)
        try:
            if int(result) == 0:
                return False, f"기안창 표 작업이 실행되지 않았습니다({action_name}). 선택 영역을 확인한 뒤 다시 시도하세요."
        except Exception:
            pass
        self.restore_focus()
        return True, "K-에듀파인 기안창 표 작업 적용 완료"

    def _apply_cell_fill_color(self, r: int, g: int, b: int):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            return self._execute_table_action(
                "CellFill",
                lambda pset, rr=r, gg=g, bb=b: self._set_fill_color_params(pset, rr, gg, bb),
            )
        except Exception as e:
            return False, f"K-에듀파인 기안창 셀 배경색 적용 실패: {e}"

    def apply_table_tool(self, action_id: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            if action_id == "하늘색배경채우기":
                return self._apply_cell_fill_color(223, 230, 247)
            if action_id == "연한노랑색배경채우기":
                return self._apply_cell_fill_color(250, 243, 219)

            def config(pset):
                if action_id == "기본선변경하기":
                    w = self._hwp_line_width("0.1mm")
                    t = self._hwp_line_type("Solid")
                    self._safe_set_any(pset, ["WidthVert", "WidthHorz", "BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft"], w)
                    self._safe_set_any(pset, ["TypeVert", "TypeHorz", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"], t)
                elif action_id == "전체바깥선굵게변경하기":
                    w = self._hwp_line_width("0.5mm")
                    t = self._hwp_line_type("Solid")
                    self._safe_set_any(pset, ["BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft", "WidthBottom", "WidthTop", "WidthRight", "WidthLeft"], w)
                    self._safe_set_any(pset, ["BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft", "TypeBottom", "TypeTop", "TypeRight", "TypeLeft"], t)
                elif action_id == "위쪽바깥선굵게변경하기":
                    self._safe_set_any(pset, ["BorderWidthTop", "WidthTop"], self._hwp_line_width("0.5mm"))
                    self._safe_set_any(pset, ["BorderTypeTop", "TypeTop"], self._hwp_line_type("Solid"))
                elif action_id == "아래쪽바깥선굵게변경하기":
                    self._safe_set_any(pset, ["BorderWidthBottom", "WidthBottom"], self._hwp_line_width("0.5mm"))
                    self._safe_set_any(pset, ["BorderTypeBottom", "TypeBottom"], self._hwp_line_type("Solid"))
                elif action_id == "아래쪽바깥선이중선변경하기":
                    self._safe_set_any(pset, ["BorderWidthBottom", "WidthBottom"], self._hwp_line_width("0.5mm"))
                    self._safe_set_any(pset, ["BorderTypeBottom", "TypeBottom"], self._hwp_line_type("DoubleSlim"))
                elif action_id == "왼쪽바깥선없애기":
                    self._safe_set_any(pset, ["BorderTypeLeft", "TypeLeft"], self._hwp_line_type("None"))
                elif action_id == "오른쪽바깥선없애기":
                    self._safe_set_any(pset, ["BorderTypeRight", "TypeRight"], self._hwp_line_type("None"))
                elif action_id == "표전체선없애기":
                    t = self._hwp_line_type("None")
                    self._safe_set_any(pset, ["TypeHorz", "TypeVert", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"], t)
                elif action_id == "빨간색강조선넣기":
                    w = self._hwp_line_width("0.5mm")
                    t = self._hwp_line_type("Solid")
                    red = self._rgb_color(255, 0, 0)
                    self._safe_set_any(pset, ["BorderColorBottom", "ColorBottom"], red)
                    self._safe_set_any(pset, ["BorderColorTop", "ColorTop"], red)
                    self._safe_set_any(pset, ["BorderColorRight", "ColorRight"], red)
                    self._safe_set_any(pset, ["BorderColorLeft", "ColorLeft", "BorderCorlorLeft", "CorlorLeft"], red)
                    self._safe_set_any(pset, ["BorderWidthBottom", "WidthBottom"], w)
                    self._safe_set_any(pset, ["BorderWidthTop", "WidthTop"], w)
                    self._safe_set_any(pset, ["BorderWidthRight", "WidthRight"], w)
                    self._safe_set_any(pset, ["BorderWidthLeft", "WidthLeft"], w)
                    self._safe_set_any(pset, ["BorderTypeBottom", "TypeBottom"], t)
                    self._safe_set_any(pset, ["BorderTypeTop", "TypeTop"], t)
                    self._safe_set_any(pset, ["BorderTypeRight", "TypeRight"], t)
                    self._safe_set_any(pset, ["BorderTypeLeft", "TypeLeft"], t)
                else:
                    raise RuntimeError(f"알 수 없는 표 작업 action_id: {action_id}")

            return self._execute_table_action("CellBorder", config)
        except Exception as e:
            self.reset()
            return False, f"K-에듀파인 기안창 표 작업 실패: {e}"

    def insert_text(self, text: str):
        """K-에듀파인 기안창 현재 커서 위치에 문자 삽입."""
        ok, msg = self.ensure()
        if not ok:
            return False, msg

        text = "" if text is None else str(text)
        last_error = ""

        # 1차: HwpCtrl Action API로 삽입
        try:
            action = self._create_action("InsertText")
            pset = self._action_create_set(action)
            try:
                self._action_get_default(action, pset)
            except Exception:
                pass

            key_ok = False
            for key in ["Text", "TextString", "String"]:
                try:
                    self._set_item(pset, key, text)
                    key_ok = True
                    break
                except Exception as e:
                    last_error = f"{key}: {e}"

            if key_ok:
                result = self._action_execute(action, pset)
                try:
                    if int(result) != 0:
                        self.restore_focus()
                        return True, "K-에듀파인 기안창 문자 삽입 완료"
                    last_error = "InsertText 실행 결과가 0입니다."
                except Exception:
                    self.restore_focus()
                    return True, "K-에듀파인 기안창 문자 삽입 완료"
        except Exception as e:
            last_error = str(e)

        # 2차: 클립보드 붙여넣기 fallback
        if win32clipboard is not None:
            backup = get_clipboard_text()
            try:
                set_clipboard_text(text)
                for cmd in ["Paste", "ClipboardPaste", "PasteClipboard", "EditPaste"]:
                    ok, msg = self.run_cmd(cmd)
                    if ok:
                        self.restore_focus()
                        return True, "K-에듀파인 기안창 문자 삽입 완료"
                    last_error = msg
            finally:
                try:
                    set_clipboard_text(backup)
                except Exception:
                    pass

        return False, f"K-에듀파인 기안창 문자 삽입 실패: {last_error}"

    def apply_charshape(self, font_name: str | None = None, font_size_pt: int | None = None, font_color_rgb: tuple[int,int,int] | None = None, bold: bool | None = None):
        """K-에듀파인 기안창 선택 영역 또는 이후 입력 글자에 글자모양 적용."""
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            action = self._create_action("CharShape")
            pset = self._action_create_set(action)
            self._action_get_default(action, pset)

            if font_name:
                for key in [
                    "FaceNameHangul", "FaceNameLatin", "FaceNameHanja", "FaceNameJapanese",
                    "FaceNameOther", "FaceNameSymbol", "FaceNameUser",
                ]:
                    try:
                        self._set_item(pset, key, font_name)
                    except Exception:
                        pass
            if font_size_pt is not None:
                try:
                    self._set_item(pset, "Height", int(float(font_size_pt) * 100))
                except Exception:
                    self._set_item(pset, "Size", int(float(font_size_pt) * 100))
            if font_color_rgb is not None:
                r, g, b = font_color_rgb
                color = self._rgb_color(r, g, b)
                applied = False
                for key in ["TextColor", "FontColor", "Color"]:
                    try:
                        self._set_item(pset, key, color)
                        applied = True
                    except Exception:
                        pass
                if not applied:
                    return False, "기안창 글자색 항목을 설정하지 못했습니다."
            if bold is not None:
                for key, value in [("Bold", 1 if bold else 0), ("BoldExp", 1 if bold else 0), ("Weight", 700 if bold else 400)]:
                    try:
                        self._set_item(pset, key, value)
                    except Exception:
                        pass

            result = self._action_execute(action, pset)
            try:
                if int(result) == 0:
                    return False, "기안창 글자 적용이 실행되지 않았습니다. 선택 영역을 확인한 뒤 다시 시도하세요."
            except Exception:
                pass
            self.restore_focus()
            return True, "K-에듀파인 기안창 글자 적용 완료"
        except Exception as e:
            self.reset()
            return False, f"K-에듀파인 기안창 글자 적용 실패: {e}"


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
def detect_report_tag(line: str):
    s = (line or "").lstrip("﻿")
    for tag in TAG_ORDER + [TABLE_START_TAG, TABLE_END_TAG]:
        prefix = f"({tag})"
        if s.startswith(prefix):
            rest = s[len(prefix):]
            if rest.startswith(" "):
                rest = rest[1:]
            return tag, rest
    return None, line

def parse_pipe_table_lines(lines):
    rows = []
    max_cols = 0
    for line in lines:
        if line is None:
            continue
        raw = str(line).rstrip("\n").strip()
        if raw == "":
            continue
        # 양끝 파이프는 있으면 제거
        if raw.startswith("|"):
            raw = raw[1:].lstrip()
        if raw.endswith("|"):
            raw = raw[:-1].rstrip()
        # Markdown 구분선은 제외
        compact = raw.replace(" ", "")
        if compact and set(compact) <= set("|-:"):
            continue
        cols = [c.strip() for c in raw.split("|")]
        rows.append(cols)
        if len(cols) > max_cols:
            max_cols = len(cols)
    if max_cols <= 0:
        max_cols = 1
    norm_rows = []
    for cols in rows:
        if len(cols) < max_cols:
            cols = cols + ([""] * (max_cols - len(cols)))
        norm_rows.append(cols)
    return norm_rows, max_cols

def normalize_document_title_text(text: str) -> str:
    s = (text or "")
    if s.startswith("- "):
        return s[2:]
    if s.startswith("-"):
        return s[1:].lstrip()
    return s
def split_section_title_text(text: str):
    s = (text or "").strip()
    m = re.match(r"^(\d+)\.\s*(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(\d+)\s+(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", s
def calc_indent(tag: str, current_level: str | None) -> int:
    if tag == "문서제목":
        return 0
    if tag == "제목":
        return 0
    if tag == "소제목":
        return 2
    if tag == "소소제목":
        return 4
    if tag == "본문":
        if current_level == "소소제목":
            return 6
        if current_level == "소제목":
            return 4
        return 2
    if tag == "참고":
        if current_level == "소소제목":
            return 8
        if current_level == "소제목":
            return 6
        return 4
    return 0
def transform_report_text(raw_text: str):
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    current_level = None
    results = []
    changed_count = 0
    in_table = False
    table_lines = []

    def flush_table():
        nonlocal table_lines, results
        rows, max_cols = parse_pipe_table_lines(table_lines)
        if rows:
            results.append({
                "tag": "표",
                "text": "",
                "style": None,
                "rows": rows,
                "cols": max_cols,
            })
        table_lines = []

    for line in lines:
        tag, content = detect_report_tag(line)

        if in_table:
            if tag == TABLE_END_TAG:
                changed_count += 1
                flush_table()
                in_table = False
            else:
                table_lines.append(line)
            continue

        if line == "":
            results.append({"tag": None, "text": "", "style": None})
            continue

        if tag == TABLE_START_TAG:
            changed_count += 1
            in_table = True
            table_lines = []
            continue

        if tag == TABLE_END_TAG:
            changed_count += 1
            continue

        if tag is None:
            results.append({"tag": None, "text": line, "style": None})
            continue

        changed_count += 1
        if tag == "제목":
            current_level = "제목"
        elif tag == "소제목":
            current_level = "소제목"
        elif tag == "소소제목":
            current_level = "소소제목"

        if tag == "문서제목":
            content = normalize_document_title_text(content)

        indent = calc_indent(tag, current_level)
        final_text = (" " * indent) + content
        style = REPORT_TAG_RULES[tag].copy()
        if tag in ("본문", "참고"):
            style["caret_indent_at"] = indent + 2
        else:
            style["caret_indent_at"] = None
        results.append({"tag": tag, "text": final_text, "style": style})

    if in_table:
        flush_table()

    return results, changed_count

PROMPT_FILENAME = "report_format_prompt.txt"
UI_SETTINGS_FILENAME = "hwp_helper_ui_settings.json"


def external_base_dir() -> str:
    """
    사용자가 수정할 수 있는 외부 파일 기준 경로.
    - .py 실행: 현재 py 파일 폴더
    - PyInstaller EXE 실행: exe 파일이 있는 폴더
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def external_path(rel_path: str) -> str:
    return os.path.abspath(os.path.join(external_base_dir(), rel_path))


def prompt_candidate_paths():
    """
    프롬프트 파일 후보 경로.
    1순위: EXE 옆 외부 txt(나중에 프롬프트만 교체할 때 사용)
    2순위: PyInstaller onefile 내부에 포함된 txt(_MEIPASS)
    3순위: 개발 중 현재 py 파일 폴더의 txt
    """
    paths = []

    # EXE 옆 외부 파일: 있으면 내장 파일보다 우선 사용
    paths.append(external_path(PROMPT_FILENAME))

    # PyInstaller --add-data로 EXE 내부에 포함된 파일
    paths.append(resource_path(PROMPT_FILENAME))

    unique = []
    seen = set()
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen:
            unique.append(ap)
            seen.add(ap)
    return unique


def read_report_prompt():
    """별도 txt 파일에서 프롬프트를 읽는다. 빈 줄은 그대로 유지한다."""
    tried = prompt_candidate_paths()
    found_path = None
    for path in tried:
        if os.path.exists(path):
            found_path = path
            break

    if not found_path:
        return False, (
            "프롬프트 파일을 찾지 못했습니다.\n\n"
            f"EXE 내부 또는 EXE와 같은 폴더에 '{PROMPT_FILENAME}' 파일이 필요합니다.\n"
            "확인한 위치:\n- " + "\n- ".join(tried)
        )

    try:
        # utf-8-sig: 메모장 등에서 BOM이 붙어도 첫 글자가 깨지지 않게 처리
        # newline=None: CRLF/LF 모두 읽되, 아래 복사 단계에서 다시 CRLF로 맞춤
        with open(found_path, "r", encoding="utf-8-sig", newline=None) as f:
            prompt = f.read()
        if not prompt.strip():
            return False, f"프롬프트 파일이 비어 있습니다.\n\n파일 위치: {found_path}"
        return True, prompt
    except Exception as e:
        return False, f"프롬프트 파일 읽기 실패: {e}\n\n파일 위치: {found_path}"



def copy_text_preserve_blank_lines(root: tk.Tk, text: str):
    """빈 줄 유지를 위해 Windows 클립보드용 CRLF 줄바꿈으로 복사한다."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    windows_text = normalized.replace("\n", "\r\n")

    if win32clipboard is not None:
        set_clipboard_text(windows_text)
    else:
        root.clipboard_clear()
        root.clipboard_append(windows_text)
        root.update_idletasks()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        FIX_W, FIX_H = 500, 780
        self._fixed_w = FIX_W
        self._fixed_h = FIX_H
        self.title("전북교육 한글 서식도우미(v1.5)")
        self.configure(bg=WHITE)
        self.geometry(f"{FIX_W}x{FIX_H}")
        self.resizable(False, False)
        self.hwp = HwpBridge()
        self.wxs = WxsHwpBridge()
        self.var_target_mode = tk.StringVar(value="hwp")
        self.data = load_json(CFG_PATH, {})
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
        self.table_tools = self.data.get("table_tools", [])
        self.card_w = int(self.settings.get("card_w", 230))
        self.card_h = int(self.settings.get("card_h", 170))
        self.symbols_root = resource_path(self.settings.get("symbols_root", "symbols"))
        self._thumb_cache = {}
        self.var_top = tk.BooleanVar(value=bool(self.settings.get("always_on_top", False)))
        self.status_var = tk.StringVar(value="준비됨")
        self.cell_range_var = tk.StringVar(value="기록된 범위: 없음")
        self.cell_status_var = tk.StringVar(value="기록 대기")
        self.mouse_down_prev = False
        self.drag_start = None
        self.drag_last = None
        self.recorded_start = None
        self.recorded_end = None
        self.is_cell_processing = False
        self._apply_white_style()
        self._build_ui()
        self._refresh_mode_tabs()
        self.attributes("-topmost", bool(self.var_top.get()))
        self.after(10, self._move_top_right)
        self.after(150, self._poll_last_hwp_window)
        self.after(25, self.poll_cell_mouse_drag)
        self.bind_all("<MouseWheel>", self._on_mousewheel_global)
    def _poll_last_hwp_window(self):
        try:
            ui_remember_foreground_hwp()
        finally:
            self.after(150, self._poll_last_hwp_window)

    def _move_top_right(self):
        sw = self.winfo_screenwidth()
        x = max(0, sw - self._fixed_w - 10)
        y = 10
        self.geometry(f"{self._fixed_w}x{self._fixed_h}+{x}+{y}")
    def _apply_white_style(self):
        style = ttk.Style()
        style.configure(".", background=WHITE)
        style.configure("TFrame", background=WHITE)
        style.configure("TLabel", background=WHITE)
        style.configure("TNotebook", background=WHITE)
        style.configure("TNotebook.Tab", padding=(12, 6))
        style.configure("TLabelframe", background=WHITE)
        style.configure("TLabelframe.Label", background=WHITE)

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

    def _refresh_mode_tabs(self):
        """적용 대상 모드에 따라 사용 가능한 탭만 표시한다."""
        if not hasattr(self, "main_nb"):
            return

        if self.is_kedufine_mode():
            # 기안창 모드: 실제 지원되는 기능만 노출
            self._set_notebook_tabs(
                self.main_nb,
                self._ordered_tab_defs(self.main_tab_defs, self.main_tab_order),
                {"edit", "chars"},
            )
            if hasattr(self, "edit_nb"):
                self._set_notebook_tabs(
                    self.edit_nb,
                    self._ordered_tab_defs(self.edit_tab_defs, self.edit_tab_order),
                    {"table", "text"},
                )
            try:
                self.btn_auto_format.configure(state="disabled")
            except Exception:
                pass
        else:
            # 일반 한글 모드: 전체 기능 복원
            self._set_notebook_tabs(
                self.main_nb,
                self._ordered_tab_defs(self.main_tab_defs, self.main_tab_order),
                {"style", "edit", "chars", "symbol", "forms", "page"},
            )
            if hasattr(self, "edit_nb"):
                self._set_notebook_tabs(
                    self.edit_nb,
                    self._ordered_tab_defs(self.edit_tab_defs, self.edit_tab_order),
                    {"table", "cell", "text"},
                )
            try:
                self.btn_auto_format.configure(state="normal")
            except Exception:
                pass

        self._refresh_text_font_rows()
        self._refresh_symbol_tabs()

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
    def _make_scroll_grid(self, parent):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        self.text_font_rows = {}
        self.text_font_order = []
        canvas = tk.Canvas(wrap, highlightthickness=0, bg=WHITE)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        def refresh_scroll(_evt=None):
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(inner_id, width=canvas.winfo_width())
        inner.bind("<Configure>", refresh_scroll)
        canvas.bind("<Configure>", refresh_scroll)
        self.after(50, refresh_scroll)
        return canvas, inner
    def _load_thumb_any(self, filepath_abs, max_size):
        if not filepath_abs or not os.path.exists(filepath_abs):
            return None
        key = (filepath_abs, max_size)
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        if Image is not None and ImageTk is not None:
            try:
                im = Image.open(filepath_abs).convert("RGBA")
                im.thumbnail(max_size, resample=Image.LANCZOS)
                img = ImageTk.PhotoImage(im)
                self._thumb_cache[key] = img
                return img
            except Exception:
                return None
        return None
    def _build_ui(self):
        opt = ttk.Frame(self, padding=(8, 8, 8, 4))
        opt.pack(fill="x")
        ttk.Checkbutton(opt, text="항상 위로 표시", variable=self.var_top, command=self.on_toggle_top).pack(side="left")
        ttk.Label(opt, text="적용 대상", background=WHITE).pack(side="left", padx=(18, 4))
        ttk.Radiobutton(opt, text="일반 한글", value="hwp", variable=self.var_target_mode, command=self.on_target_mode_changed).pack(side="left", padx=(0, 4))
        ttk.Radiobutton(opt, text="K-에듀파인 기안창", value="kedufine", variable=self.var_target_mode, command=self.on_target_mode_changed).pack(side="left")

        self.auto_row = ttk.Frame(self, padding=(8, 0, 8, 6))
        self.auto_row.pack(fill="x")
        self.btn_auto_format = ttk.Button(self.auto_row, text="서식 자동 지정하기", command=self.on_auto_format_report)
        self.btn_auto_format.pack(side="left")
        self.btn_copy_prompt = ttk.Button(self.auto_row, text="프롬프트 복사", command=self.on_copy_report_prompt)
        self.btn_copy_prompt.pack(side="left", padx=(6, 0))
        self.btn_tab_order = ttk.Button(self.auto_row, text="탭 순서 편집", command=self.on_edit_tab_order)
        self.btn_tab_order.pack(side="left", padx=(6, 0))

        nb = ttk.Notebook(self)
        self.main_nb = nb
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        tab_style = ttk.Frame(nb, padding=8)
        tab_edit  = ttk.Frame(nb, padding=8)
        tab_chars = ttk.Frame(nb, padding=8)
        tab_symbol= ttk.Frame(nb, padding=8)
        tab_forms = ttk.Frame(nb, padding=8)
        tab_page  = ttk.Frame(nb, padding=8)
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
        self._build_cards_grid(tab_style, self.blocks, cols=3, card_w=150, card_h=111)
        self._build_chars_scroll(tab_chars)
        self._build_symbol_tabs(tab_symbol)
        self._build_cards_grid(tab_forms, self.forms, cols=2, card_w=self.card_w, card_h=self.card_h)
        self._build_page_cards(tab_page)
        self._build_edit_tools(tab_edit)
    def _build_cards_grid(self, parent, items, cols=2, card_w=230, card_h=170):
        canvas, inner = self._make_scroll_grid(parent)
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        title_font = tkfont.Font(size=10, weight="bold")
        for idx, it in enumerate(items):
            r, c = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=card_w, height=card_h, highlightthickness=1, highlightbackground="#e5e7eb")
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")
            card.grid_propagate(False)
            title = it.get("title", f"항목{idx+1}")
            file_abs = resource_path(it.get("file", "")) if it.get("file") else ""
            thumb_abs = resource_path(it.get("thumb", "")) if it.get("thumb") else ""
            img = self._load_thumb_any(thumb_abs, (card_w-20, card_h-45))
            img_area = tk.Frame(card, bg=WHITE, width=card_w, height=card_h-45)
            img_area.pack(fill="x", padx=6, pady=(6, 2))
            img_area.pack_propagate(False)
            if img is not None:
                lbl = tk.Label(img_area, image=img, bg=WHITE)
                lbl.image = img
                lbl.pack(expand=True)
            else:
                tk.Label(img_area, text="", bg=WHITE).pack(expand=True)
            tk.Label(card, text=title, bg=WHITE, font=title_font).pack(pady=(0, 0))
            def _do_action(p=file_abs, t=title):
                if self.is_kedufine_mode():
                    self._show_kedufine_unsupported("서식/양식 삽입")
                    return
                ok, msg = self.hwp.insert_file(p)
                if ok:
                    self.status_var.set(f"삽입: {t}")
                else:
                    messagebox.showerror("오류", msg)
            bind_click_recursive(card, _do_action)
    def _build_chars_scroll(self, parent):
        canvas, inner = self._make_scroll_grid(parent)
        if not isinstance(self.symbols_text, dict) or not self.symbols_text:
            ttk.Label(inner, text="(문자표 데이터 없음)", background=WHITE).pack(anchor="w")
            return
        for group_name, chars in self.symbols_text.items():
            box = ttk.LabelFrame(inner, text=str(group_name), padding=6)
            box.pack(fill="x", pady=6)
            grid = ttk.Frame(box)
            grid.pack(fill="x")
            cols = 10
            for i, ch in enumerate(chars or []):
                r, c = divmod(i, cols)
                ttk.Button(grid, text=str(ch), width=3, command=lambda x=str(ch): self.on_insert_text(x)).grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
            for c in range(cols):
                grid.columnconfigure(c, weight=1)
    def _build_symbol_tabs(self, parent):
        self.symbol_nb = None
        self.symbol_tab_defs = []
        if not os.path.isdir(self.symbols_root):
            return
        nb2 = ttk.Notebook(parent)
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
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        title_font = tkfont.Font(size=10, weight="bold")
        files = [fn for fn in sorted(os.listdir(folder)) if is_image_file(fn)]
        for idx, fn in enumerate(files):
            r, c = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=self.card_w, height=self.card_h, highlightthickness=1, highlightbackground="#e5e7eb")
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")
            card.grid_propagate(False)
            f_abs = os.path.join(folder, fn)
            title = os.path.splitext(fn)[0]
            img = self._load_thumb_any(f_abs, (self.card_w-20, self.card_h-55))
            img_area = tk.Frame(card, bg=WHITE, width=self.card_w, height=self.card_h-55)
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
    def _build_page_cards(self, parent):
        canvas, inner = self._make_scroll_grid(parent)
        cols = 3
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        PAGE_CARD_W, PAGE_CARD_H = 150, 170
        PREV_W, PREV_H = PAGE_CARD_W - 20, PAGE_CARD_H - 55
        title_font = tkfont.Font(size=10, weight="bold")
        for idx, it in enumerate(self.page_items):
            r, c = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=PAGE_CARD_W, height=PAGE_CARD_H, highlightthickness=1, highlightbackground="#e5e7eb")
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")
            card.grid_propagate(False)
            title = it.get("title", f"편집용지 {idx+1}")
            thumb_fn = it.get("thumb", "")
            thumb_abs = resource_path(os.path.join(self.page_thumbs_root_rel, thumb_fn)) if thumb_fn else ""
            img = self._load_thumb_any(thumb_abs, (PREV_W, PREV_H)) if thumb_fn else None
            img_area = tk.Frame(card, bg=WHITE, width=PAGE_CARD_W, height=PREV_H)
            img_area.pack(fill="x", padx=6, pady=(6, 2))
            img_area.pack_propagate(False)
            if img is not None:
                lbl = tk.Label(img_area, image=img, bg=WHITE)
                lbl.image = img
                lbl.pack(expand=True)
            else:
                tk.Label(img_area, text="", bg=WHITE).pack(expand=True)
            tk.Label(card, text=title, bg=WHITE, font=title_font).pack(pady=(2, 0))
            def _apply():
                if self.is_kedufine_mode():
                    self._show_kedufine_unsupported("편집용지 적용")
                    return
                ok, msg = self.hwp.apply_basic_report_page_setup()
                if ok:
                    self.status_var.set(msg)
                else:
                    self.status_var.set("편집용지 적용 실패")
                    messagebox.showerror("편집용지 적용 실패", msg)
            bind_click_recursive(card, _apply)
    def _build_edit_tools(self, parent):
        nb2 = ttk.Notebook(parent)
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
    def _build_table_tools_cards(self, parent):
        canvas, inner = self._make_scroll_grid(parent)
        cols = 4
        for i in range(cols):
            inner.columnconfigure(i, weight=1)
        title_font = tkfont.Font(size=9, weight="bold")
        items = self.table_tools or []
        if not items:
            ttk.Label(inner, text="(table_tools가 비어있음)", background=WHITE).grid(row=0, column=0, sticky="w")
            return
        CARD_W, CARD_H = 118, 142
        PREV_H = 92
        TITLE_H = 36
        for idx, it in enumerate(items):
            r, c = divmod(idx, cols)
            card = tk.Frame(inner, bg=WHITE, width=CARD_W, height=CARD_H, highlightthickness=1, highlightbackground="#e5e7eb")
            card.grid(row=r, column=c, padx=6, pady=6, sticky="n")
            card.grid_propagate(False)
            title = force_two_lines(it.get("title", f"표작업{idx+1}"))
            action_id = it.get("action_id", "")
            thumb_abs = resource_path(it.get("thumb", "")) if it.get("thumb") else ""
            img = self._load_thumb_any(thumb_abs, (CARD_W-18, PREV_H))
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
                bridge = self.wxs if self.is_kedufine_mode() else self.hwp
                ok, msg = bridge.apply_table_tool(aid)
                if ok:
                    target = "기안창" if self.is_kedufine_mode() else "한글"
                    self.status_var.set(f"{target} 표 작업: {t}")
                    self._restore_kedufine_focus_later()
                else:
                    messagebox.showerror("표 작업 실패", msg)
            bind_click_recursive(card, _do)
    
    def _make_cell_tool_card(self, parent, title: str, desc: str | None = None):
        card = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground="#e5e7eb")
        card.pack(fill="x", pady=(0, 10))
        tk.Label(
            card,
            text=title,
            bg=WHITE,
            fg="#111827",
            font=tkfont.Font(size=10, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 3))
        if desc:
            tk.Label(
                card,
                text=desc,
                bg=WHITE,
                fg="#6b7280",
                font=tkfont.Font(size=9),
                justify="left",
                anchor="w",
                wraplength=430,
            ).pack(fill="x", padx=12, pady=(0, 8))
        return card

    def _build_cell_cleaner_tools(self, parent):
        wrap_canvas, inner = self._make_scroll_grid(parent)

        range_card = self._make_cell_tool_card(inner, "선택 범위")
        tk.Label(
            range_card,
            textvariable=self.cell_range_var,
            bg=WHITE,
            fg="#1f2937",
            font=tkfont.Font(size=10, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=430,
        ).pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(
            range_card,
            textvariable=self.cell_status_var,
            bg=WHITE,
            fg="#6b7280",
            font=tkfont.Font(size=9),
            anchor="w",
            justify="left",
            wraplength=430,
        ).pack(fill="x", padx=12, pady=(0, 10))

        clean_card = self._make_cell_tool_card(inner, "공백 정리")
        ttk.Button(
            clean_card,
            text="기록된 범위 공백 제거",
            command=self.on_cell_clean_spaces,
        ).pack(fill="x", padx=12, pady=(0, 12))

        replace_card = self._make_cell_tool_card(inner, "찾아바꾸기")
        form = ttk.Frame(replace_card)
        form.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(form, text="찾을 내용", background=WHITE).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.cell_find_var = tk.StringVar()
        self.cell_replace_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.cell_find_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(form, text="바꿀 내용", background=WHITE).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(form, textvariable=self.cell_replace_var).grid(row=1, column=1, sticky="ew", pady=3)
        form.columnconfigure(1, weight=1)
        ttk.Button(
            replace_card,
            text="기록된 범위 찾아바꾸기",
            command=self.on_cell_find_replace,
        ).pack(fill="x", padx=12, pady=(0, 12))

        add_card = self._make_cell_tool_card(inner, "문자 추가")
        add_form = ttk.Frame(add_card)
        add_form.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(add_form, text="추가할 문자", background=WHITE).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.cell_add_text_var = tk.StringVar()
        ttk.Entry(add_form, textvariable=self.cell_add_text_var).grid(row=0, column=1, sticky="ew", pady=3)
        add_form.columnconfigure(1, weight=1)
        add_btns = ttk.Frame(add_card)
        add_btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(add_btns, text="앞에 넣기", command=self.on_cell_add_prefix).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(add_btns, text="뒤에 넣기", command=self.on_cell_add_suffix).pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _foreground_is_hwp_window(self):
        """단독 셀 정리 도구와 유사하게 한글 창 판별 기준을 느슨하게 둔다."""
        if win32gui is None or win32process is None:
            return False
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return False
            try:
                if hwnd == self.winfo_id():
                    return False
            except Exception:
                pass

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

            # 한글 편집 영역의 자식 창처럼 제목이 비어 있는 경우를 대비해
            # 마지막으로 기억한 한글 창과 같은 프로세스면 한글 창으로 인정한다.
            last = ui_get_last_hwp_window()
            if last and int(last.get("pid") or -1) == int(pid):
                return True

            return False
        except Exception:
            return False

    def _update_cell_range_label(self):
        if not self.recorded_start or not self.recorded_end:
            self.cell_range_var.set("기록된 범위: 없음")
            return
        s_col, s_row, _ = self.recorded_start
        e_col, e_row, _ = self.recorded_end
        left_col = min(s_col, e_col)
        right_col = max(s_col, e_col)
        top_row = min(s_row, e_row)
        bottom_row = max(s_row, e_row)
        self.cell_range_var.set(
            f"기록된 범위: {self.hwp.cell_addr_to_text(left_col, top_row)} ~ {self.hwp.cell_addr_to_text(right_col, bottom_row)} "
            f"({bottom_row - top_row + 1}행 × {right_col - left_col + 1}열)"
        )

    def poll_cell_mouse_drag(self):
        try:
            if win32api is None or win32con is None:
                return
            if self.is_cell_processing:
                return

            left_down = bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)

            if left_down:
                # 드래그가 이미 시작된 뒤에는 전경 창 판별이 순간적으로 실패해도 계속 추적한다.
                # 한글 내부 편집 영역/자식 창으로 포커스가 바뀌면서 판별이 끊기면 끝 셀이 틀어질 수 있기 때문이다.
                if self.drag_start is not None or self._foreground_is_hwp_window():
                    try:
                        addr = self.hwp.get_table_cell_addr(focus_before=False)
                        if not self.mouse_down_prev:
                            self.drag_start = addr
                            self.drag_last = addr
                            self.cell_status_var.set(f"시작: {addr[2]}")
                        else:
                            if self.drag_start is None:
                                self.drag_start = addr
                            self.drag_last = addr
                    except Exception:
                        pass

            if self.mouse_down_prev and not left_down:
                if self.drag_start and self.drag_last:
                    self.recorded_start = self.drag_start
                    self.recorded_end = self.drag_last
                    self._update_cell_range_label()
                    self.cell_status_var.set(f"완료: {self.recorded_start[2]} → {self.recorded_end[2]}")
                self.drag_start = None
                self.drag_last = None

            self.mouse_down_prev = left_down
        finally:
            self.after(25, self.poll_cell_mouse_drag)

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

            self.cell_status_var.set("처리 완료")
            self.status_var.set(f"셀 정리 완료: {result['changed']}개 셀 변경")
            messagebox.showinfo(
                "셀 정리 완료",
                (
                    f"{complete_title}\n\n"
                    f"처리 범위: {result['start_addr']} ~ {result['end_addr']}\n"
                    f"선택 범위: {result['row_count']}행 × {result['col_count']}열\n"
                    f"변경 셀 수: {result['changed']}개"
                ),
            )
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

    def _refresh_text_font_rows(self):
        """적용 대상 모드에 따라 글자 작업의 글꼴 행을 표시/숨김 처리한다."""
        if not hasattr(self, "text_font_rows") or not hasattr(self, "text_font_order"):
            return

        hide_fonts = {"휴먼명조"} if self.is_kedufine_mode() else set()

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

    def _build_text_tools_cards(self, parent):
        """
        글자 작업:
        - 글꼴 버튼: 글꼴만 변경
        - 숫자 버튼: 해당 글꼴 + 크기 적용
        - 색상 버튼: 글자색 변경(검정/빨강/파랑/흰색)
        """
        font_map = [
            ("HY헤드라인M", [15, 16, 17, 18, 20, 25, 30]),
            ("휴먼명조",     [11, 12, 13, 14, 15, 17, 20]),
            ("맑은 고딕",    [9, 10, 11, 12, 13, 14, 15]),
            ("굴림체",       [9, 10, 11, 12, 13, 14, 15]),
        ]
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        # --- 색상 버튼 행 ---
        color_row = ttk.Frame(wrap)
        color_row.pack(fill="x", pady=(0, 10))
        ttk.Label(color_row, text="글자색", background=WHITE).pack(side="left", padx=(0, 8))
        def _mk_color_btn(label, rgb, fg, bg):
            b = tk.Button(
                color_row, text=label, fg=fg, bg=bg,
                relief="groove", bd=1, padx=8, pady=2,
                command=lambda c=rgb, t=label: self._apply_font_color(c, t)
            )
            b.pack(side="left", padx=3)
            return b
        _mk_color_btn("검정", (0, 0, 0), "#000000", "#ffffff")
        _mk_color_btn("빨강", (220, 0, 0), "#dc0000", "#ffffff")
        _mk_color_btn("파랑", (0, 70, 200), "#0046c8", "#ffffff")
        # 흰색은 흰 글자가 보이도록 배경을 어둡게
        _mk_color_btn("흰색", (255, 255, 255), "#ffffff", "#444444")
        ttk.Separator(wrap, orient="horizontal").pack(fill="x", pady=(0, 10))
        # --- 글꼴/크기 행들 ---
        for r, (fname, sizes) in enumerate(font_map):
            row = ttk.Frame(wrap)
            row.pack(fill="x", pady=6)
            self.text_font_rows[fname] = row
            self.text_font_order.append(fname)
            # 글꼴 버튼은 "버튼 글꼴 자체"를 해당 글꼴로 표시
            try:
                fnt = tkfont.Font(family=fname, size=10, weight="bold")
            except Exception:
                fnt = tkfont.Font(size=10, weight="bold")
            btn_font = tk.Button(
                row, text=fname, font=fnt, bg="#ffffff",
                relief="groove", bd=1, padx=8, pady=6,
                command=lambda f=fname: self._apply_font_only(f)
            )
            btn_font.pack(side="left")
            btns = ttk.Frame(row)
            btns.pack(side="left", padx=8, fill="x", expand=True)
            for s in sizes:
                ttk.Button(
                    btns, text=str(s), width=4,
                    command=lambda f=fname, sz=s: self._apply_font_size(f, sz)
                ).pack(side="left", padx=2)
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=(10, 0))
        ttk.Label(parent, text="※ 글꼴 버튼: 글꼴만 변경 / 숫자 버튼: 해당 글꼴 + 크기 / 색상 버튼: 글자색 변경",
                  background=WHITE).pack(anchor="w", pady=(6, 0))
        self._refresh_text_font_rows()
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

        lb = tk.Listbox(list_wrap, height=8, exportselection=False)
        lb.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.configure(yscrollcommand=sb.set)

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

        dlg = tk.Toplevel(self)
        dlg.title("탭 순서 편집")
        dlg.configure(bg=WHITE)
        dlg.geometry("560x520")
        dlg.resizable(False, False)
        try:
            dlg.transient(self)
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
        ttk.Button(bottom, text="저장", command=save_and_close).pack(side="right")

        refresh_main(0)

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
        transformed, changed_count = transform_report_text(raw)
        if changed_count == 0:
            messagebox.showinfo("안내", "선택한 영역에서 보고서 태그를 찾지 못했습니다.")
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
        ok, msg = self.hwp.delete_selection()
        if not ok:
            messagebox.showerror("서식 자동 지정 실패", msg)
            return
        total = len(transformed)
        for idx, item in enumerate(transformed):
            line_text = item["text"]
            tag = item.get("tag")
            if tag == "표":
                ok, msg = self.hwp.insert_pipe_table(item.get("rows") or [], font_name="굴림체", font_size_pt=12)
            elif item["style"] is None:
                ok, msg = self.hwp.insert_text(line_text)
            elif tag == "문서제목":
                ok, msg = self.hwp.insert_document_title_box(title_box_file, line_text.strip())
            elif tag == "제목":
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
        self.attributes("-topmost", bool(self.var_top.get()))
        self.settings["always_on_top"] = bool(self.var_top.get())
        self.data["settings"] = self.settings
        try:
            save_json(CFG_PATH, self.data)
        except Exception:
            pass
if __name__ == "__main__":
    App().mainloop()
