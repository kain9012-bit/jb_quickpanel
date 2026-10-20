# -*- coding: utf-8 -*-
from __future__ import annotations

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.core.runtime import is_rpc_error, pythoncom
from src.jb_quickpanel.features.object_properties import set_current_object_treat_as_char
from src.jb_quickpanel.features.character_effects import compose_parameters
from src.jb_quickpanel.features.page_layout import PageLayout


class TauriHwpBridge(HwpBridge):
    """Tauri sidecar에서 필요한 한글 버전별 커서 이동 보정."""

    def apply_page_preset(self, margins, orientation="portrait", scope="document", paper_size=None):
        ok, message = self.ensure()
        if not ok:
            return False, message
        try:
            PageLayout(self.hwp).apply(margins, orientation, scope, paper_size=paper_size)
            return True, "현재 페이지 편집용지 적용 완료" if scope == "page" else "문서 전체 편집용지 적용 완료"
        except Exception as error:
            if is_rpc_error(error):
                self.reset()
            return False, f"편집용지 적용 실패: {error}"

    def compose_characters(self, value, shape):
        try:
            values = compose_parameters(value, shape)
        except ValueError as error:
            return False, str(error)
        ok, message = self.ensure()
        if not ok:
            return False, message
        try:
            action = self.hwp.CreateAction("ComposeChars")
            pset = action.CreateSet()
            action.GetDefault(pset)
            for key, item in values.items():
                self._hwp_set_item(pset, key, item)
            if not action.Execute(pset):
                return False, "글자 겹치기를 실행하지 못했습니다."
            return True, "글자 겹치기 삽입 완료"
        except Exception as error:
            if is_rpc_error(error):
                self.reset()
            return False, f"글자 겹치기 실패: {error}"

    def set_object_treat_as_char(self, enabled: bool):
        ok, message = self.ensure()
        if not ok:
            return False, message
        try:
            return set_current_object_treat_as_char(
                self.hwp, enabled, self._hwp_get_item, self._hwp_set_item,
            )
        except Exception as error:
            if is_rpc_error(error):
                self.reset()
            return False, f"개체 설정 실패: {error}"

    def start_table_drawing(self):
        ok, message = self.ensure()
        if not ok:
            return False, message
        try:
            if not self.hwp.HAction.Run("TableDrawPen"):
                return False, "표 그리기를 시작하지 못했습니다. 한글의 편집 상태를 확인하세요."
            return True, "표 그리기 모드를 시작했습니다."
        except Exception as error:
            if is_rpc_error(error):
                self.reset()
            return False, f"표 그리기 시작 실패: {error}"

    def _raw_parameter_set_position(self, parameter_set):
        if pythoncom is None or parameter_set is None:
            return None
        try:
            raw_set = getattr(parameter_set, "_oleobj_", parameter_set)
            item_id = raw_set.GetIDsOfNames("Item")
            flags = pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET
            return tuple(
                int(raw_set.Invoke(item_id, 0, flags, True, name))
                for name in ("List", "Para", "Pos")
            )
        except Exception:
            return None

    def _current_table_anchor(self):
        try:
            ctrl = getattr(self.hwp, "ParentCtrl", None)
            if str(getattr(ctrl, "CtrlID", "") or "").lower() != "tbl":
                return None

            try:
                parameter_set = ctrl.GetAnchorPos(0)
                position = self._parameter_set_position(parameter_set)
                if position is not None:
                    return position
            except Exception:
                pass

            raw_ctrl = getattr(ctrl, "_oleobj_", None)
            if raw_ctrl is None or pythoncom is None:
                return None
            method_id = raw_ctrl.GetIDsOfNames("GetAnchorPos")
            raw_set = raw_ctrl.Invoke(
                method_id,
                0,
                pythoncom.DISPATCH_METHOD,
                True,
                0,
            )
            return self._raw_parameter_set_position(raw_set)
        except Exception:
            return None

    def _place_cursor_after_inserted_table(self, table_is_selected: bool = False):
        anchor = self._current_table_anchor()
        if anchor is None:
            if self._is_caret_in_table():
                return False, "삽입한 표의 본문 위치를 확인하지 못했습니다."
            return super()._place_cursor_after_inserted_table(table_is_selected)

        list_id, para_id, anchor_pos = anchor
        for offset in (1, 2, 3):
            try:
                moved = self.hwp.SetPos(
                    int(list_id),
                    int(para_id),
                    int(anchor_pos) + offset,
                )
            except Exception:
                moved = False
            if moved is not False and not self._is_caret_in_table():
                return self.insert_paragraph_break()

        return False, "삽입한 표의 바로 다음 문단으로 이동하지 못했습니다."
