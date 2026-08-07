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
    def reset(self):
        self.hwp = None
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
        return int(r) | (int(g) << 8) | (int(b) << 16)
    def apply_table_tool(self, action_id: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            ps = self.hwp.HParameterSet.HCellBorderFill
            self.hwp.HAction.GetDefault("CellBorder", ps.HSet)
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
                fa = ps.FillAttr
                try: fa.Type = self._brush_type("NullBrush|WinBrush")
                except Exception: pass
                try: fa.WinBrushFaceColor = self._rgb_color(223,230,247)
                except Exception: pass
                try: fa.WinBrushHatchColor = self._rgb_color(153,153,153)
                except Exception: pass
                try: fa.WinBrushFaceStyle = self._hatch_style("None")
                except Exception: pass
                try: fa.WindowsBrush = 1
                except Exception: pass
            elif action_id == "연한노랑색배경채우기":
                fa = ps.FillAttr
                try: fa.Type = self._brush_type("NullBrush|WinBrush")
                except Exception: pass
                try: fa.WinBrushFaceColor = self._rgb_color(250,243,219)
                except Exception: pass
                try: fa.WinBrushHatchColor = self._rgb_color(153,153,153)
                except Exception: pass
                try: fa.WinBrushFaceStyle = self._hatch_style("None")
                except Exception: pass
                try: fa.WindowsBrush = 1
                except Exception: pass
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
            self.hwp.HAction.Execute("CellBorder", ps.HSet)
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
        self.title("전북교육 한글 서식도우미(v1.3.1)")
        self.configure(bg=WHITE)
        self.geometry(f"{FIX_W}x{FIX_H}")
        self.resizable(False, False)
        self.hwp = HwpBridge()
        self.data = load_json(CFG_PATH, {})
        self.settings = self.data.get("settings", {"always_on_top": False, "symbols_root": "symbols", "card_w": 230, "card_h": 170})
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
        self._apply_white_style()
        self._build_ui()
        self.attributes("-topmost", bool(self.var_top.get()))
        self.after(10, self._move_top_right)
        self.after(150, self._poll_last_hwp_window)
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

        auto_row = ttk.Frame(self, padding=(8, 0, 8, 6))
        auto_row.pack(fill="x")
        ttk.Button(auto_row, text="서식 자동 지정하기", command=self.on_auto_format_report).pack(side="left")
        ttk.Button(auto_row, text="프롬프트 복사", command=self.on_copy_report_prompt).pack(side="left", padx=(6, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        tab_style = ttk.Frame(nb, padding=8)
        tab_edit  = ttk.Frame(nb, padding=8)
        tab_chars = ttk.Frame(nb, padding=8)
        tab_symbol= ttk.Frame(nb, padding=8)
        tab_forms = ttk.Frame(nb, padding=8)
        tab_page  = ttk.Frame(nb, padding=8)
        nb.add(tab_style, text="서식")
        nb.add(tab_edit,  text="편집도구")
        nb.add(tab_chars, text="문자표")
        nb.add(tab_symbol,text="심볼")
        nb.add(tab_forms, text="양식")
        nb.add(tab_page,  text="편집용지")
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
        if not os.path.isdir(self.symbols_root):
            return
        nb2 = ttk.Notebook(parent)
        nb2.pack(fill="both", expand=True)
        groups = []
        for name in sorted(os.listdir(self.symbols_root)):
            p = os.path.join(self.symbols_root, name)
            if os.path.isdir(p):
                groups.append((name, p))
        for gname, gpath in groups:
            tab = ttk.Frame(nb2, padding=8)
            nb2.add(tab, text=gname)
            self._build_symbol_group(tab, gpath)
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
                ok, msg = self.hwp.apply_basic_report_page_setup()
                if ok:
                    self.status_var.set(msg)
                else:
                    self.status_var.set("편집용지 적용 실패")
                    messagebox.showerror("편집용지 적용 실패", msg)
            bind_click_recursive(card, _apply)
    def _build_edit_tools(self, parent):
        nb2 = ttk.Notebook(parent)
        nb2.pack(fill="both", expand=True)
        tab_table = ttk.Frame(nb2, padding=8)
        tab_text  = ttk.Frame(nb2, padding=8)
        nb2.add(tab_table, text="표 작업")
        nb2.add(tab_text,  text="글자 작업")
        self._build_table_tools_cards(tab_table)
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
                ok, msg = self.hwp.apply_table_tool(aid)
                if ok:
                    self.status_var.set(f"표 작업: {t}")
                else:
                    messagebox.showerror("표 작업 실패", msg)
            bind_click_recursive(card, _do)
    
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
    def _apply_font_only(self, font_name: str):
        ok, msg = self.hwp.apply_charshape(font_name=font_name, font_size_pt=None)
        if ok:
            self.status_var.set(f"글꼴: {font_name}")
        else:
            messagebox.showerror("글자 적용 실패", msg)
    def _apply_font_size(self, font_name: str, size_pt: int):
        ok, msg = self.hwp.apply_charshape(font_name=font_name, font_size_pt=int(size_pt))
        if ok:
            self.status_var.set(f"글꼴/크기: {font_name} {size_pt}")
        else:
            messagebox.showerror("글자 적용 실패", msg)
    def _apply_font_color(self, rgb: tuple[int,int,int], label: str):
        ok, msg = self.hwp.apply_charshape(font_name=None, font_size_pt=None, font_color_rgb=rgb)
        if ok:
            self.status_var.set(f"글자색: {label}")
        else:
            messagebox.showerror("글자 적용 실패", msg)
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
