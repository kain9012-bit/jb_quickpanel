# -*- coding: utf-8 -*-
from src.jb_quickpanel_v32.core.runtime import *
from src.jb_quickpanel_v32.features.cell_text import *
from src.jb_quickpanel_v32.features.cell_images import (
    IMAGE_SIZE_FIT_INSIDE,
    IMAGE_SIZE_FIT_WIDTH,
    IMAGE_SIZE_STRETCH_TO_CELL,
    calculate_picture_size,
    normalize_image_size_mode,
)

# 일반 편집 연결에서 등록되지 않은 FilePathCheckDLL을 호출하면 정책이 엄격한 PC에서
# 보안 경고가 뜬다. 셀 정리를 포함한 현재 기능에는 이 외부 모듈이 필요하지 않다.
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
            time.sleep(0.05)
            return True, msg
        except Exception as e:
            self.hwp = None
            return False, f"실행 중 한글 COM 연결 실패: {e}"
    def connect_without_focus(self):
        """
        일반 삽입과 셀 범위 감시에 쓰는 무포커스 연결.
        ROT 조회만 수행하고 한글 창을 강제로 활성화하지 않아 선택 상태와
        서식도우미 화면이 불필요하게 다시 그려지는 것을 막는다.
        """
        try:
            if self.hwp is not None:
                return True, "OK"
            ok, hwp, msg = get_running_hwp_from_rot()
            if not ok:
                self.hwp = None
                return False, f"실행 중 한글 COM 객체 연결 실패:\n{msg}"
            self.hwp = hwp
            return True, msg
        except Exception as e:
            self.hwp = None
            return False, f"실행 중 한글 COM 연결 실패: {e}"

    def ensure(self):
        if self.hwp is None:
            return self.connect_without_focus()
        return True, "OK"
    def _retry_once_with_reconnect(self, fn):
        try:
            return fn()
        except Exception as e:
            self.reset()
            ok, msg = self.connect_without_focus()
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

    def save_selected_block(self, filepath_abs: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        path = os.path.abspath(filepath_abs)
        try:
            selection_mode = int(getattr(self.hwp, "SelectionMode", 0) or 0)
        except Exception:
            selection_mode = 0
        if (selection_mode & 0xF) == 0:
            return False, "서식이나 양식으로 등록할 한글 문서 영역을 먼저 블록 지정하세요."

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            ps = self.hwp.HParameterSet.HFileOpenSave
            self.hwp.HAction.GetDefault("FileSaveBlock_S", ps.HSet)
            file_name_set = False
            for attr in ("FileName", "filename"):
                try:
                    setattr(ps, attr, path)
                    file_name_set = True
                    break
                except Exception:
                    pass
            if not file_name_set:
                return False, "블록 저장 경로를 한글에 전달하지 못했습니다."
            ps.Format = "HWP"
            try:
                ps.Attributes = 1
            except Exception:
                pass
            executed = self.hwp.HAction.Execute("FileSaveBlock_S", ps.HSet)
            time.sleep(0.05)
            if executed is False or not os.path.isfile(path) or os.path.getsize(path) <= 0:
                return False, "선택 영역을 한글 파일로 저장하지 못했습니다. 블록 범위를 다시 확인하세요."
            return True, path
        except Exception as exc:
            if is_rpc_error(exc):
                self.reset()
            return False, f"선택 영역 저장 실패: {exc}"

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
    def cleanup_line_spacing(self, adjust_count: int = 3):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        if win32clipboard is None:
            return False, "pywin32 clipboard 모듈을 사용할 수 없습니다."

        try:
            ok, selected_text = self.get_selected_text()
            if not ok:
                return False, "자간 정리를 적용할 한글 문서 영역을 먼저 블록 지정하세요."

            selected_len = len((selected_text or "").strip())
            if selected_len <= 0:
                return False, "자간 정리를 적용할 한글 문서 영역을 먼저 블록 지정하세요."

            end_pos = self.hwp.GetPos()
            self.hwp.HAction.Run("MoveLeft")
            start_pos = self.hwp.GetPos()

            if self._pos_at_or_after(start_pos, end_pos):
                return False, "선택 영역의 범위를 확인하지 못했습니다. 위에서 아래 방향으로 블록 지정한 뒤 다시 실행하세요."

            return self._cleanup_line_spacing_between_positions(adjust_count, end_pos, selected_len)
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"자간 정리 실패: {e}"

    def cleanup_current_cell_line_spacing(self, adjust_count: int = 3):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            self.run_first_supported(["Cancel", "CloseEx", "Esc"])
            self.hwp.HAction.Run("MoveListBegin")
            start_pos = self.hwp.GetPos()
            try:
                self.hwp.HAction.Run("MoveListEnd")
            except Exception:
                self.hwp.HAction.Run("MoveSelListEnd")
                self.hwp.HAction.Run("Cancel")
            end_pos = self.hwp.GetPos()
            self.hwp.SetPos(start_pos[0], start_pos[1], start_pos[2])
        except Exception as e:
            return False, f"현재 셀 범위를 확인하지 못했습니다: {e}"

        return self._cleanup_line_spacing_between_positions(adjust_count, end_pos, 80)

    def cleanup_cell_range_line_spacing(self, start_col, start_row, end_col, end_row, adjust_count: int = 3):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            left_col = min(int(start_col), int(end_col))
            right_col = max(int(start_col), int(end_col))
            top_row = min(int(start_row), int(end_row))
            bottom_row = max(int(start_row), int(end_row))
            self.cell_validate_range_no_merged_cells(left_col, top_row, right_col, bottom_row)

            total_decreased = 0
            total_increased = 0
            cell_count = 0

            for r in range(top_row, bottom_row + 1):
                for c in range(left_col, right_col + 1):
                    self.cell_move_to_addr(c, r)
                    ok_cell, msg_cell = self.cleanup_current_cell_line_spacing(adjust_count)
                    if not ok_cell:
                        return False, msg_cell
                    m = re.search(r"줄임\s+(\d+)곳,\s+늘림\s+(\d+)곳", msg_cell)
                    if m:
                        total_decreased += int(m.group(1))
                        total_increased += int(m.group(2))
                    cell_count += 1

            return True, f"표 셀 자간 정리 완료: {cell_count}개 셀, 줄임 {total_decreased}곳, 늘림 {total_increased}곳"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"표 셀 자간 정리 실패: {e}"

    def _pos_key(self, pos):
        try:
            return tuple(int(v) for v in pos[:3])
        except Exception:
            return None

    def _pos_at_or_after(self, pos, target_pos):
        a = self._pos_key(pos)
        b = self._pos_key(target_pos)
        if a is None or b is None:
            return False
        return a >= b

    def _cleanup_line_spacing_between_positions(self, adjust_count: int, end_pos, selected_len: int):
        adjust_count = max(1, int(adjust_count))
        decreased = 0
        increased = 0
        x = 0
        old_clipboard_text = get_clipboard_text()

        def run(action_id: str):
            self.hwp.HAction.Run(action_id)

        def copy_selected_text() -> str:
            run("Copy")
            return get_clipboard_text()

        try:
            max_iterations = max(50, int(selected_len) * 4)
            for _ in range(max_iterations):
                try:
                    if self._pos_at_or_after(self.hwp.GetPos(), end_pos):
                        break
                except Exception:
                    pass

                run("MoveLineEnd")
                run("MoveSelLeft")
                a = copy_selected_text()

                if a == " " or a == ".":
                    run("MoveRight")
                    x += 1
                else:
                    run("MoveSelNextWord")
                    b = copy_selected_text()
                    if a == b:
                        run("MoveRight")
                        x += 1
                    else:
                        if 2 <= len(b) <= 3:
                            x = 0
                            run("MoveUp")
                            run("MoveSelLineEnd")
                            for _ in range(adjust_count):
                                run("CharShapeSpacingDecrease")
                            run("MoveLineBegin")
                            decreased += 1
                        else:
                            run("MoveLineBegin")
                            run("MoveSelPrevWord")
                            c = copy_selected_text()
                            if len(c) == 1:
                                x = 0
                                run("MoveSelLineBegin")
                                for _ in range(adjust_count):
                                    run("CharShapeSpacingIncrease")
                                run("MoveRight")
                                increased += 1

                if x > 15:
                    before = self.hwp.KeyIndicator()
                    run("MoveDown")
                    after = self.hwp.KeyIndicator()
                    if before == after or self._pos_at_or_after(self.hwp.GetPos(), end_pos):
                        break
            else:
                return False, "선택 영역 처리 횟수가 너무 많아 자간 정리를 중단했습니다. 영역을 나누어 다시 실행하세요."

            return True, f"자간 정리 완료: 줄임 {decreased}곳, 늘림 {increased}곳"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"자간 정리 실패: {e}"
        finally:
            try:
                set_clipboard_text(old_clipboard_text)
            except Exception:
                pass
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
    def _is_caret_in_table(self):
        try:
            ctrl = getattr(self.hwp, "ParentCtrl", None)
            ctrl_id = str(getattr(ctrl, "CtrlID", "") or "").lower()
            return ctrl_id == "tbl"
        except Exception:
            return False
    def _move_right_of_current_cell(self):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            result = self.hwp.MovePos(101)
            if result is False:
                return False, "MovePos(101) 실패"
            return True, "OK"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"표 오른쪽 이동 실패: {e}"
    def ensure_cursor_outside_table(self):
        if not self._is_caret_in_table():
            return True, "OK"
        ok, _ = self._move_right_of_current_cell()
        if not ok:
            self.run_first_supported(["MoveParaEnd"])
            ok, _ = self.run_first_supported(["MoveRight"])
        if not ok:
            return False, "표 밖으로 커서를 이동하지 못했습니다."
        return self.insert_paragraph_break()
    def _place_cursor_after_inserted_table(self, table_is_selected: bool = False):
        if table_is_selected:
            self.run_first_supported(["Cancel", "CloseEx", "Esc"])
            if self._is_caret_in_table():
                return self.ensure_cursor_outside_table()
            ok, _ = self.run_first_supported(["MoveRight"])
            if ok and self._is_caret_in_table():
                return self.ensure_cursor_outside_table()
            if ok:
                return self.insert_paragraph_break()

        self.run_first_supported(["CloseEx", "Cancel", "Esc"])
        if self._is_caret_in_table():
            return self.ensure_cursor_outside_table()
        for _i in range(3):
            self.run_first_supported(["MoveParaEnd"])
            ok, _ = self.run_first_supported(["MoveRight"])
            if ok:
                if self._is_caret_in_table():
                    return self.ensure_cursor_outside_table()
                ok_break, msg_break = self.insert_paragraph_break()
                if ok_break:
                    return True, "OK"
                return False, msg_break
            self.run_first_supported(["MoveDown"])

        self.run_first_supported(["MoveDown"])
        return True, "OK"
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

    def apply_page_margins(self, margins):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        fields = {
            "left": "LeftMargin",
            "right": "RightMargin",
            "top": "TopMargin",
            "bottom": "BottomMargin",
            "header": "HeaderLen",
            "footer": "FooterLen",
            "gutter": "GutterLen",
        }
        try:
            values = {}
            for key in fields:
                value = float(margins[key])
                if value < 0 or value > 100:
                    return False, "용지 여백은 0~100mm 범위로 입력하세요."
                values[key] = value

            ps = self.hwp.HParameterSet.HSecDef
            self.hwp.HAction.GetDefault("PageSetup", ps.HSet)
            page_def = ps.PageDef
            for key, attr in fields.items():
                setattr(page_def, attr, self._mili_to_unit(values[key]))
            self.hwp.HAction.Execute("PageSetup", ps.HSet)
            return True, "사용자 편집용지 여백 적용 완료"
        except KeyError:
            return False, "저장된 편집용지 여백 정보가 올바르지 않습니다."
        except Exception as exc:
            if is_rpc_error(exc):
                self.reset()
            return False, f"사용자 편집용지 적용 실패: {exc}"

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

    def _apply_cell_fill_none(self):
        """선택된 표 셀의 배경을 흰색이 아닌 실제 '색 없음'으로 설정한다."""
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
                raise last_error or RuntimeError("셀 배경색 제거 액션을 불러오지 못했습니다.")

            self._clear_fill_attr(ps.FillAttr)
            try:
                self._clear_fill_attr(ps.SelCellsBorderFill.FillAttr)
            except Exception:
                pass

            last_error = None
            for action_name in ["CellFill", loaded_action, "CellBorderFill", "BorderFill"]:
                try:
                    self.hwp.HAction.Execute(action_name, ps.HSet)
                    return True, "셀 배경색 제거 완료"
                except Exception as e:
                    last_error = e
            raise last_error or RuntimeError("셀 배경색 제거에 실패했습니다.")
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"셀 배경색 제거 실패: {e}"

    def _clear_fill_attr(self, fill_attr):
        """채우기 대상을 흰색으로 덮지 않고 한글의 실제 '색 없음' 값으로 만든다."""
        brush_type = self._brush_type("NullBrush|WinBrush")
        type_set = False
        last_type_error = None
        for attr in ("Type", "type"):
            try:
                setattr(fill_attr, attr, brush_type)
                type_set = True
                break
            except Exception as e:
                last_type_error = e
        if not type_set:
            try:
                fill_attr.HSet.SetItem("Type", brush_type)
            except Exception as e:
                raise RuntimeError("배경 채우기 유형을 설정하지 못했습니다.") from (last_type_error or e)
        fill_attr.WinBrushFaceColor = 0xFFFFFFFF
        fill_attr.WinBrushFaceStyle = self._hatch_style("None")
        fill_attr.WindowsBrush = 0
        for attr in ("GradationBrush", "ImageBrush"):
            try:
                setattr(fill_attr, attr, 0)
            except Exception:
                pass

    def normalize_current_cell_pasted_format(self):
        """현재 셀 전체를 선택해 모든 문단 배경과 글자 색상 흔적을 함께 정리한다."""
        start_pos = None
        try:
            start_pos = self.cell_select_current_text()

            para_shape = self.hwp.HParameterSet.HParaShape
            self.hwp.HAction.GetDefault("ParagraphShape", para_shape.HSet)
            self._clear_fill_attr(para_shape.BorderFill.FillAttr)
            self.hwp.HAction.Execute("ParagraphShape", para_shape.HSet)

            char_shape = self.hwp.HParameterSet.HCharShape
            self.hwp.HAction.GetDefault("CharShape", char_shape.HSet)
            char_shape.TextColor = self._rgb_color(0, 0, 0)
            char_shape.ShadeColor = 0xFFFFFFFF
            self.hwp.HAction.Execute("CharShape", char_shape.HSet)
            return True, "문단 배경·글자색·음영색 정리 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문단 배경·글자색·음영색 정리 실패: {e}"
        finally:
            self._cell_try_cmd("Cancel", 0.005)
            if start_pos is not None:
                try:
                    self._cell_set_pos(start_pos)
                except Exception:
                    pass

    def clear_selected_paragraph_background(self, ensure_before: bool = True):
        """문단 모양 > 테두리/배경 > 배경 면색을 없음으로 설정한다."""
        if ensure_before:
            ok, msg = self.ensure()
            if not ok:
                return False, msg
        try:
            ps = self.hwp.HParameterSet.HParaShape
            self.hwp.HAction.GetDefault("ParagraphShape", ps.HSet)
            self._clear_fill_attr(ps.BorderFill.FillAttr)
            self.hwp.HAction.Execute("ParagraphShape", ps.HSet)
            return True, "문단 배경 면색 제거 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문단 배경 면색 제거 실패: {e}"

    def clear_current_paragraph_background_at_caret(self):
        """현재 커서가 있는 문단의 배경 면색을 없음으로 설정한다."""
        try:
            ps = self.hwp.HParameterSet.HParaShape
            self.hwp.HAction.GetDefault("ParagraphShape", ps.HSet)
            self._clear_fill_attr(ps.BorderFill.FillAttr)
            self.hwp.HAction.Execute("ParagraphShape", ps.HSet)
            return True, "문단 배경 면색 제거 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"문단 배경 면색 제거 실패: {e}"

    def apply_table_tool(self, action_id: str):
        ok, msg = self.ensure()
        if not ok:
            return False, msg
        try:
            distribute_commands = {
                "행높이같게": ("TableDistributeCellHeight", "행 높이 같게"),
                "열너비같게": ("TableDistributeCellWidth", "열 너비 같게"),
            }
            if action_id in distribute_commands:
                command, label = distribute_commands[action_id]
                result = self.hwp.HAction.Run(command)
                if isinstance(result, (bool, int)) and int(result) == 0:
                    return False, f"{label}를 실행하지 못했습니다. 직사각형 셀 범위를 선택한 뒤 다시 시도하세요."
                return True, f"{label} 완료"

            cell_property_actions = {
                "한줄로입력설정": ("LineWrap", 1, "한 줄로 입력 설정"),
                "한줄로입력해제": ("LineWrap", 0, "한 줄로 입력 해제"),
                "제목셀설정": ("Header", 1, "제목 셀 설정"),
                "제목셀해제": ("Header", 0, "제목 셀 해제"),
            }
            if action_id in cell_property_actions:
                property_name, value, label = cell_property_actions[action_id]
                shape = self.hwp.HParameterSet.HShapeObject
                self.hwp.HAction.GetDefault("TablePropertyDialog", shape.HSet)
                cell = shape.ShapeTableCell
                if not self._hwp_set_item(cell, property_name, value):
                    return False, f"{label} 속성을 설정하지 못했습니다. 셀 범위를 다시 선택하세요."
                result = self.hwp.HAction.Execute("TablePropertyDialog", shape.HSet)
                if isinstance(result, (bool, int)) and int(result) == 0:
                    return False, f"{label}를 실행하지 못했습니다. 셀 범위를 다시 선택하세요."
                return True, f"{label} 완료"

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

            def _set_line_attrs(attrs, value):
                for attr in attrs:
                    try:
                        setattr(ps, attr, value)
                    except Exception:
                        pass

            execute_action = _load_cell_action("CellBorder")
            if action_id == "기본선변경하기":
                w = self._hwp_line_width("0.1mm")
                t = self._hwp_line_type("Solid")
                black = self._rgb_color(0, 0, 0)
                _set_line_attrs(["WidthVert", "WidthHorz", "BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft"], w)
                _set_line_attrs(["TypeVert", "TypeHorz", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"], t)
                _set_line_attrs(["ColorVert", "ColorHorz", "BorderColorBottom", "BorderColorTop", "BorderColorRight", "BorderColorLeft", "BorderCorlorLeft"], black)
            elif action_id == "전체바깥선굵게변경하기":
                w = self._hwp_line_width("0.5mm")
                t = self._hwp_line_type("Solid")
                black = self._rgb_color(0, 0, 0)
                _set_line_attrs(["BorderWidthBottom", "BorderWidthTop", "BorderWidthRight", "BorderWidthLeft"], w)
                _set_line_attrs(["BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"], t)
                _set_line_attrs(["BorderColorBottom", "BorderColorTop", "BorderColorRight", "BorderColorLeft", "BorderCorlorLeft"], black)
            elif action_id == "위쪽바깥선굵게변경하기":
                _set_line_attrs(["BorderWidthTop"], self._hwp_line_width("0.5mm"))
                _set_line_attrs(["BorderTypeTop"], self._hwp_line_type("Solid"))
                _set_line_attrs(["BorderColorTop"], self._rgb_color(0, 0, 0))
            elif action_id == "아래쪽바깥선굵게변경하기":
                _set_line_attrs(["BorderWidthBottom"], self._hwp_line_width("0.5mm"))
                _set_line_attrs(["BorderTypeBottom"], self._hwp_line_type("Solid"))
                _set_line_attrs(["BorderColorBottom"], self._rgb_color(0, 0, 0))
            elif action_id == "아래쪽바깥선이중선변경하기":
                _set_line_attrs(["BorderWidthBottom"], self._hwp_line_width("0.5mm"))
                _set_line_attrs(["BorderTypeBottom"], self._hwp_line_type("DoubleSlim"))
                _set_line_attrs(["BorderColorBottom"], self._rgb_color(0, 0, 0))
            elif action_id == "왼쪽바깥선없애기":
                t = self._hwp_line_type("None")
                try: ps.BorderTypeLeft = t
                except Exception: pass
            elif action_id == "오른쪽바깥선없애기":
                t = self._hwp_line_type("None")
                try: ps.BorderTypeRight = t
                except Exception: pass
            elif action_id == "내부세로선없애기":
                _set_line_attrs(["TypeVert"], self._hwp_line_type("None"))
            elif action_id == "내부가로선없애기":
                _set_line_attrs(["TypeHorz"], self._hwp_line_type("None"))
            elif action_id == "표전체선없애기":
                t = self._hwp_line_type("None")
                _set_line_attrs(["TypeHorz", "TypeVert", "BorderTypeBottom", "BorderTypeTop", "BorderTypeRight", "BorderTypeLeft"], t)
            elif action_id == "하늘색배경채우기":
                return self._apply_cell_fill_color(223, 230, 247)
            elif action_id == "연한노랑색배경채우기":
                return self._apply_cell_fill_color(250, 243, 219)
            elif action_id == "배경색없애기":
                return self._apply_cell_fill_none()
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

    def reset_selected_char_spacing(self):
        """블록 지정된 영역의 글자 자간을 0으로 초기화한다."""
        ok, msg = self.ensure()
        if not ok:
            return False, msg

        ok, selected_text = self.get_selected_text()
        if not ok or len((selected_text or "").strip()) <= 0:
            return False, "자간을 초기화할 한글 문서 영역을 먼저 블록 지정하세요."

        try:
            ps = self.hwp.HParameterSet.HCharShape
            self.hwp.HAction.GetDefault("CharShape", ps.HSet)
            spacing_attrs = [
                "SpacingHangul", "SpacingLatin", "SpacingHanja", "SpacingJapanese",
                "SpacingOther", "SpacingSymbol", "SpacingUser",
            ]
            for attr in spacing_attrs:
                try:
                    setattr(ps, attr, 0)
                except Exception:
                    pass
                try:
                    ps.HSet.SetItem(attr, 0)
                except Exception:
                    pass
            self.hwp.HAction.Execute("CharShape", ps.HSet)
            return True, "자간 초기화 완료"
        except Exception as e:
            if is_rpc_error(e):
                self.reset()
            return False, f"자간 초기화 실패: {e}"

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

        # 표 전체 선택이 유지된 경우에는 선택 해제 대신 오른쪽으로 이동해야
        # 다음 문장이 마지막 셀 안에 이어 붙는 일을 피할 수 있다.
        ok_exit, msg_exit = self._place_cursor_after_inserted_table(ok_sel)
        if not ok_exit:
            return False, msg_exit
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

    def cell_get_current_text(self):
        start_pos = self.cell_select_current_text()
        current_text = self.cell_get_selected_text_fast()
        self._cell_try_cmd("Cancel", 0.005)
        self._cell_set_pos(start_pos)
        if current_text is None:
            return self.cell_copy_current_text_clipboard()
        return cell_normalize_text(current_text)

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

    def insert_pictures_into_cell_range(
        self,
        image_paths,
        start_col,
        start_row,
        end_col,
        end_row,
        size_mode=IMAGE_SIZE_FIT_INSIDE,
        progress_callback=None,
    ):
        size_mode = normalize_image_size_mode(size_mode)
        paths = [os.path.abspath(os.fspath(path)) for path in image_paths]
        if not paths:
            raise RuntimeError("선택한 그림이 없습니다.")
        for path in paths:
            if not os.path.isfile(path):
                raise RuntimeError(f"그림 파일을 찾지 못했습니다.\n\n{path}")
            if not is_image_file(path):
                raise RuntimeError(f"지원하지 않는 그림 형식입니다.\n\n{path}")

        left_col = min(int(start_col), int(end_col))
        right_col = max(int(start_col), int(end_col))
        top_row = min(int(start_row), int(end_row))
        bottom_row = max(int(start_row), int(end_row))
        row_count = bottom_row - top_row + 1
        col_count = right_col - left_col + 1
        cell_count = row_count * col_count
        if len(paths) > cell_count:
            raise RuntimeError(f"선택한 셀 {cell_count}개보다 그림 {len(paths)}개가 더 많습니다.")

        self._cell_focus_hwp()
        self.cell_validate_range_no_merged_cells(left_col, top_row, right_col, bottom_row)

        # 문서 내용을 지우지 않도록 실제로 그림을 넣을 셀만 먼저 확인한다.
        self.cell_move_to_addr(left_col, top_row)
        checked = 0
        for r in range(row_count):
            for c in range(col_count):
                if checked >= len(paths):
                    break
                _col, _row, addr = self.get_table_cell_addr(focus_before=False)
                if self.cell_get_current_text().strip():
                    raise RuntimeError(
                        f"{addr} 셀에 내용이 있어 그림을 넣지 않았습니다.\n\n"
                        "내용이 없는 셀 범위를 선택한 뒤 다시 실행하세요."
                    )
                checked += 1
                if checked < len(paths) and c < col_count - 1:
                    self.cell_move_right()
            if checked >= len(paths):
                break
            if r < row_count - 1:
                self.cell_move_down()
                for _ in range(col_count - 1):
                    self.cell_move_left()

        self.cell_move_to_addr(left_col, top_row)
        inserted_ctrls = []
        inserted = 0
        try:
            for r in range(row_count):
                for c in range(col_count):
                    if inserted >= len(paths):
                        break

                    path = paths[inserted]
                    if not self._cell_try_cmd("MoveListBegin", 0.005):
                        raise RuntimeError("그림을 넣을 셀의 시작 위치로 이동하지 못했습니다.")
                    cell_pos = self._cell_get_pos()
                    cell_size = None
                    if size_mode == IMAGE_SIZE_FIT_WIDTH:
                        cell_size = self.cell_get_current_inner_size()
                    try:
                        size_option = 2 if size_mode == IMAGE_SIZE_STRETCH_TO_CELL else 3
                        ctrl = self.hwp.InsertPicture(path, True, size_option, False, False, 0)
                    except Exception as exc:
                        raise RuntimeError(
                            f"그림 삽입에 실패했습니다.\n\n파일: {os.path.basename(path)}\n오류: {exc}"
                        ) from exc
                    if ctrl is None:
                        raise RuntimeError(f"한글이 그림을 삽입하지 못했습니다.\n\n파일: {os.path.basename(path)}")

                    inserted_ctrls.append(ctrl)
                    if size_mode == IMAGE_SIZE_FIT_WIDTH:
                        self._resize_picture_control(ctrl, size_mode, cell_size)
                    inserted += 1
                    self._cell_set_pos(cell_pos)
                    if progress_callback is not None:
                        progress_callback(inserted, len(paths))

                    if inserted < len(paths) and c < col_count - 1:
                        self.cell_move_right()

                if inserted >= len(paths):
                    break
                if r < row_count - 1:
                    self.cell_move_down()
                    for _ in range(col_count - 1):
                        self.cell_move_left()
        except Exception:
            for ctrl in reversed(inserted_ctrls):
                try:
                    self.hwp.DeleteCtrl(ctrl)
                except Exception:
                    pass
            raise

        return {
            "start_addr": self.cell_addr_to_text(left_col, top_row),
            "end_addr": self.cell_addr_to_text(right_col, bottom_row),
            "row_count": row_count,
            "col_count": col_count,
            "inserted": inserted,
            "size_mode": size_mode,
        }


    def _hwp_set_item(self, parameter_set, name, value):
        try:
            parameter_set.SetItem(name, value)
            return True
        except Exception:
            try:
                setattr(parameter_set, name, value)
                return True
            except Exception:
                return False

    def _hwp_get_item(self, parameter_set, name, default=None):
        try:
            return parameter_set.Item(name)
        except Exception:
            try:
                return getattr(parameter_set, name)
            except Exception:
                return default

    def cell_get_current_inner_size(self):
        """현재 셀의 실제 크기에서 셀 안쪽 여백을 뺀 HWPUNIT 크기를 반환한다."""
        hwp = self._cell_get_hwp()
        try:
            action = hwp.CreateAction("TablePropertyDialog")
            pset = action.CreateSet()
            action.GetDefault(pset)
            cell_set = self._hwp_get_item(pset, "ShapeTableCell")
            if cell_set is None:
                raise RuntimeError("ShapeTableCell 속성이 없습니다.")

            width = int(self._hwp_get_item(cell_set, "Width", 0) or 0)
            height = int(self._hwp_get_item(cell_set, "Height", 0) or 0)
            if width <= 0 or height <= 0:
                raise RuntimeError("셀 너비 또는 높이가 0입니다.")

            margin_left = max(0, int(self._hwp_get_item(cell_set, "MarginLeft", 0) or 0))
            margin_right = max(0, int(self._hwp_get_item(cell_set, "MarginRight", 0) or 0))
            margin_top = max(0, int(self._hwp_get_item(cell_set, "MarginTop", 0) or 0))
            margin_bottom = max(0, int(self._hwp_get_item(cell_set, "MarginBottom", 0) or 0))
            return {
                "width": width,
                "height": height,
                "inner_width": max(1, width - margin_left - margin_right),
                "inner_height": max(1, height - margin_top - margin_bottom),
            }
        except Exception as exc:
            raise RuntimeError(f"현재 셀의 크기를 읽지 못했습니다.\n\n오류: {exc}") from exc

    def _picture_control_info(self, ctrl):
        try:
            props = ctrl.Properties
        except Exception:
            return None
        image_attr = self._hwp_get_item(props, "ShapeDrawImageAttr")
        if image_attr is None:
            return None

        width = int(self._hwp_get_item(props, "Width", 0) or 0)
        height = int(self._hwp_get_item(props, "Height", 0) or 0)
        original_width = int(self._hwp_get_item(image_attr, "OriginalSizeX", 0) or 0)
        original_height = int(self._hwp_get_item(image_attr, "OriginalSizeY", 0) or 0)
        if original_width <= 0 or original_height <= 0:
            original_width, original_height = width, height
        if width <= 0 or height <= 0 or original_width <= 0 or original_height <= 0:
            return None
        return {
            "props": props,
            "width": width,
            "height": height,
            "original_width": original_width,
            "original_height": original_height,
            "treat_as_char": self._hwp_get_item(props, "TreatAsChar", None),
        }

    def _picture_control_anchor_lists(self, ctrl):
        list_ids = set()
        for anchor_type in (0, 1, 2):
            try:
                anchor = ctrl.GetAnchorPos(anchor_type)
                list_id = self._hwp_get_item(anchor, "List", None)
                if list_id is not None:
                    list_ids.add(int(list_id))
            except Exception:
                pass
        return list_ids

    def _picture_controls_by_anchor_list(self):
        controls_by_list = {}
        ctrl = getattr(self.hwp, "HeadCtrl", None)
        visited = set()
        visited_refs = []
        while ctrl is not None:
            marker = id(ctrl)
            if marker in visited:
                break
            visited.add(marker)
            visited_refs.append(ctrl)
            try:
                ctrl_id = str(ctrl.CtrlID or "").lower()
            except Exception:
                ctrl_id = ""
            if ctrl_id == "gso" and self._picture_control_info(ctrl) is not None:
                for list_id in self._picture_control_anchor_lists(ctrl):
                    controls_by_list.setdefault(list_id, []).append(ctrl)
            try:
                ctrl = ctrl.Next
            except Exception:
                break
        return controls_by_list

    def _resize_picture_control(self, ctrl, size_mode, cell_size, picture_info=None):
        size_mode = normalize_image_size_mode(size_mode)
        info = picture_info or self._picture_control_info(ctrl)
        if info is None:
            raise RuntimeError("그림의 원본 크기 정보를 읽지 못했습니다.")
        target_width, target_height = calculate_picture_size(
            size_mode,
            cell_size["inner_width"],
            cell_size["inner_height"],
            info["original_width"],
            info["original_height"],
        )
        props = info["props"]
        self._hwp_set_item(props, "KeepRatio", 0 if size_mode == IMAGE_SIZE_STRETCH_TO_CELL else 1)
        if size_mode == IMAGE_SIZE_FIT_WIDTH:
            self._hwp_set_item(props, "TreatAsChar", True)
        if not self._hwp_set_item(props, "Width", int(target_width)):
            raise RuntimeError("그림 너비를 설정하지 못했습니다.")
        if not self._hwp_set_item(props, "Height", int(target_height)):
            raise RuntimeError("그림 높이를 설정하지 못했습니다.")
        ctrl.Properties = props
        return target_width, target_height

    def refit_pictures_in_cell_range(
        self,
        start_col,
        start_row,
        end_col,
        end_row,
        size_mode=IMAGE_SIZE_FIT_INSIDE,
        progress_callback=None,
    ):
        size_mode = normalize_image_size_mode(size_mode)
        left_col = min(int(start_col), int(end_col))
        right_col = max(int(start_col), int(end_col))
        top_row = min(int(start_row), int(end_row))
        bottom_row = max(int(start_row), int(end_row))
        row_count = bottom_row - top_row + 1
        col_count = right_col - left_col + 1
        total_cells = row_count * col_count

        self._cell_focus_hwp()
        self.cell_validate_range_no_merged_cells(left_col, top_row, right_col, bottom_row)
        controls_by_list = self._picture_controls_by_anchor_list()

        jobs = []
        empty_cells = []
        multiple_cells = []
        unreadable_cells = []
        self.cell_move_to_addr(left_col, top_row)
        visited_cells = 0
        for r in range(row_count):
            for c in range(col_count):
                _col, _row, addr = self.get_table_cell_addr(focus_before=False)
                cell_pos = self._cell_get_pos()
                list_id = int(cell_pos[0]) if cell_pos is not None else None
                pictures = controls_by_list.get(list_id, []) if list_id is not None else []
                if not pictures:
                    empty_cells.append(addr)
                elif len(pictures) > 1:
                    multiple_cells.append(addr)
                else:
                    picture_info = self._picture_control_info(pictures[0])
                    if picture_info is None:
                        unreadable_cells.append(addr)
                    else:
                        jobs.append((addr, pictures[0], self.cell_get_current_inner_size(), picture_info))

                visited_cells += 1
                if progress_callback is not None:
                    progress_callback(visited_cells, total_cells)
                if c < col_count - 1:
                    self.cell_move_right()
            if r < row_count - 1:
                self.cell_move_down()
                for _ in range(col_count - 1):
                    self.cell_move_left()

        changed = []
        try:
            for addr, ctrl, cell_size, picture_info in jobs:
                self._resize_picture_control(ctrl, size_mode, cell_size, picture_info)
                changed.append((addr, ctrl, picture_info))
        except Exception as exc:
            for _addr, ctrl, old_info in reversed(changed):
                try:
                    props = ctrl.Properties
                    self._hwp_set_item(props, "Width", old_info["width"])
                    self._hwp_set_item(props, "Height", old_info["height"])
                    if old_info["treat_as_char"] is not None:
                        self._hwp_set_item(props, "TreatAsChar", old_info["treat_as_char"])
                    ctrl.Properties = props
                except Exception:
                    pass
            raise RuntimeError(f"기존 그림 다시 맞춤에 실패해 변경한 크기를 되돌렸습니다.\n\n오류: {exc}") from exc

        return {
            "start_addr": self.cell_addr_to_text(left_col, top_row),
            "end_addr": self.cell_addr_to_text(right_col, bottom_row),
            "resized": len(changed),
            "empty": len(empty_cells),
            "multiple": len(multiple_cells),
            "unreadable": len(unreadable_cells),
            "size_mode": size_mode,
        }

    def cleanup_excel_pasted_cell_range(self, start_col, start_row, end_col, end_row):
        left_col = min(int(start_col), int(end_col))
        right_col = max(int(start_col), int(end_col))
        top_row = min(int(start_row), int(end_row))
        bottom_row = max(int(start_row), int(end_row))

        row_count = bottom_row - top_row + 1
        col_count = right_col - left_col + 1

        self._cell_focus_hwp()
        self.cell_validate_range_no_merged_cells(left_col, top_row, right_col, bottom_row)
        self.cell_move_to_addr(left_col, top_row)

        text_changed = 0
        background_changed = 0
        charshape_changed = 0
        for r in range(row_count):
            for c in range(col_count):
                if self.cell_transform_current_fast(cell_clean_space_text):
                    text_changed += 1
                ok_format, format_message = self.normalize_current_cell_pasted_format()
                if not ok_format:
                    raise RuntimeError(format_message)
                background_changed += 1
                charshape_changed += 1
                if c < col_count - 1:
                    self.cell_move_right()

            if r < row_count - 1:
                self.cell_move_down()
                for _ in range(col_count - 1):
                    self.cell_move_left()

        return {
            "start_addr": self.cell_addr_to_text(left_col, top_row),
            "end_addr": self.cell_addr_to_text(right_col, bottom_row),
            "row_count": row_count,
            "col_count": col_count,
            "text_changed": text_changed,
            "background_changed": background_changed,
            "charshape_changed": charshape_changed,
        }
