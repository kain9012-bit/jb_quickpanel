# -*- coding: utf-8 -*-
from __future__ import annotations

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.core.runtime import pythoncom


class TauriHwpBridge(HwpBridge):
    """Tauri sidecar에서 필요한 한글 버전별 커서 이동 보정."""

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