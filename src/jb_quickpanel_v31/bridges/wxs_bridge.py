# -*- coding: utf-8 -*-
from src.jb_quickpanel_v31.core.runtime import *

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

    def _set_fill_none_params(self, pset):
        """K-에듀파인 기안창 셀 배경을 실제 '색 없음'으로 설정한다."""
        fill = self._create_item_set(pset, "FillAttr", "DrawFillAttr")
        self._set_item(fill, "Type", 1)
        self._set_item(fill, "WinBrushFaceStyle", 0xFFFFFFFF)
        self._set_item(fill, "WinBrushHatchColor", 0x00000000)
        self._set_item(fill, "WinBrushFaceColor", 0xFFFFFFFF)
        self._set_item(fill, "WindowsBrush", 0)
        self._set_item(fill, "GradationBrush", 0)
        self._set_item(fill, "ImageBrush", 0)

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

    def _apply_cell_fill_none(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            return self._execute_table_action("CellFill", self._set_fill_none_params)
        except Exception as e:
            return False, f"K-에듀파인 기안창 셀 배경색 제거 실패: {e}"

    def apply_table_tool(self, action_id: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            distribute_commands = {
                "행높이같게": "TableDistributeCellHeight",
                "열너비같게": "TableDistributeCellWidth",
            }
            if action_id in distribute_commands:
                return self.run_cmd(distribute_commands[action_id])

            cell_property_actions = {
                "한줄로입력설정": ("LineWrap", 1),
                "한줄로입력해제": ("LineWrap", 0),
                "제목셀설정": ("Header", 1),
                "제목셀해제": ("Header", 0),
            }
            if action_id in cell_property_actions:
                property_name, value = cell_property_actions[action_id]

                def configure_cell_property(pset):
                    try:
                        cell = self._item(pset, "ShapeTableCell")
                    except Exception:
                        cell = None
                    if cell is None:
                        cell = self._create_item_set(pset, "ShapeTableCell", "Cell")
                    self._set_item(cell, property_name, value)

                return self._execute_table_action("TablePropertyDialog", configure_cell_property)

            if action_id == "하늘색배경채우기":
                return self._apply_cell_fill_color(223, 230, 247)
            if action_id == "연한노랑색배경채우기":
                return self._apply_cell_fill_color(250, 243, 219)
            if action_id == "배경색없애기":
                return self._apply_cell_fill_none()

            def config(pset):
                if action_id == "기본선변경하기":
                    w = self._hwp_line_width("0.1mm")
                    t = self._hwp_line_type("Solid")
                    black = self._rgb_color(0, 0, 0)
                    self._safe_set_any(pset, ["WidthVert", "WidthHorz", "BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft"], w)
                    self._safe_set_any(pset, ["TypeVert", "TypeHorz", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"], t)
                    self._safe_set_any(pset, ["ColorVert", "ColorHorz", "BorderColorBottom", "BorderColorTop", "BorderColorRight", "BorderColorLeft", "BorderCorlorLeft"], black)
                elif action_id == "전체바깥선굵게변경하기":
                    w = self._hwp_line_width("0.5mm")
                    t = self._hwp_line_type("Solid")
                    black = self._rgb_color(0, 0, 0)
                    self._safe_set_any(pset, ["BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft", "WidthBottom", "WidthTop", "WidthRight", "WidthLeft"], w)
                    self._safe_set_any(pset, ["BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft", "TypeBottom", "TypeTop", "TypeRight", "TypeLeft"], t)
                    self._safe_set_any(pset, ["BorderColorBottom", "BorderColorTop", "BorderColorRight", "BorderColorLeft", "BorderCorlorLeft"], black)
                elif action_id == "위쪽바깥선굵게변경하기":
                    self._safe_set_any(pset, ["BorderWidthTop", "WidthTop"], self._hwp_line_width("0.5mm"))
                    self._safe_set_any(pset, ["BorderTypeTop", "TypeTop"], self._hwp_line_type("Solid"))
                    self._safe_set_any(pset, ["BorderColorTop", "ColorTop"], self._rgb_color(0, 0, 0))
                elif action_id == "아래쪽바깥선굵게변경하기":
                    self._safe_set_any(pset, ["BorderWidthBottom", "WidthBottom"], self._hwp_line_width("0.5mm"))
                    self._safe_set_any(pset, ["BorderTypeBottom", "TypeBottom"], self._hwp_line_type("Solid"))
                    self._safe_set_any(pset, ["BorderColorBottom", "ColorBottom"], self._rgb_color(0, 0, 0))
                elif action_id == "아래쪽바깥선이중선변경하기":
                    self._safe_set_any(pset, ["BorderWidthBottom", "WidthBottom"], self._hwp_line_width("0.5mm"))
                    self._safe_set_any(pset, ["BorderTypeBottom", "TypeBottom"], self._hwp_line_type("DoubleSlim"))
                    self._safe_set_any(pset, ["BorderColorBottom", "ColorBottom"], self._rgb_color(0, 0, 0))
                elif action_id == "왼쪽바깥선없애기":
                    self._safe_set_any(pset, ["BorderTypeLeft", "TypeLeft"], self._hwp_line_type("None"))
                elif action_id == "오른쪽바깥선없애기":
                    self._safe_set_any(pset, ["BorderTypeRight", "TypeRight"], self._hwp_line_type("None"))
                elif action_id == "내부세로선없애기":
                    self._safe_set_any(pset, ["TypeVert"], self._hwp_line_type("None"))
                elif action_id == "내부가로선없애기":
                    self._safe_set_any(pset, ["TypeHorz"], self._hwp_line_type("None"))
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

    def insert_file(self, filepath_abs: str):
        """K-에듀파인 기안창 현재 커서 위치에 HWP 조각 파일 삽입."""
        ok, msg = self.ensure()
        if not ok:
            return False, msg

        path = os.path.abspath(filepath_abs)
        if not os.path.exists(path):
            return False, f"파일이 없습니다: {path}"

        try:
            action = self._create_action("InsertFile")
            pset = self._action_create_set(action)
            try:
                self._action_get_default(action, pset)
            except Exception:
                pass

            self._set_item(pset, "FileName", path)

            # 기존 일반 한글 InsertFile에서 쓰던 유지 옵션.
            # 일부 항목은 기안창 HwpCtrl에서 무시될 수 있지만, 삽입 자체에는 영향을 주지 않음.
            for key, value in [
                ("KeepCharshape", 1),
                ("KeepParashape", 1),
                ("KeepSection", 0),
                ("KeepNumbering", 1),
            ]:
                try:
                    self._set_item(pset, key, value)
                except Exception:
                    pass

            result = self._action_execute(action, pset)
            try:
                if int(result) == 0:
                    return False, "기안창 서식 삽입이 실행되지 않았습니다. 커서 위치를 확인한 뒤 다시 시도하세요."
            except Exception:
                pass
            self.restore_focus()
            return True, "K-에듀파인 기안창 서식 삽입 완료"
        except Exception as e:
            self.reset()
            return False, f"K-에듀파인 기안창 서식 삽입 실패: {e}"

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

# 보고서 태그 규칙은 core/runtime.py 로 이동했다. (import * 로 그대로 사용 가능)
