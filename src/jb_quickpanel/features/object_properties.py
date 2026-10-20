"""Change a current object's inline layout without rebuilding its selection."""


def set_current_object_treat_as_char(editor, enabled, read_item, write_item):
    ctrl = editor.CurSelectedCtrl
    if ctrl is None:
        ctrl = editor.ParentCtrl
        if ctrl is None or str(ctrl.CtrlID or "").strip().lower() != "tbl":
            raise RuntimeError("표나 그림을 선택하거나 표 안에 커서를 놓은 뒤 실행하세요.")
    elif str(ctrl.CtrlID or "").strip().lower() not in {"tbl", "gso"}:
        raise RuntimeError("선택한 개체는 표나 그림이 아닙니다.")

    props = ctrl.Properties
    current = read_item(props, "TreatAsChar")
    if current not in (False, True, 0, 1):
        raise RuntimeError("선택한 개체의 글자처럼 취급 속성을 읽지 못했습니다.")
    label = "글자처럼 취급" if enabled else "글자처럼 취급 해제"
    if bool(current) == enabled:
        return True, f"이미 {label} 상태입니다."

    if write_item(props, "TreatAsChar", int(enabled)) is False:
        raise RuntimeError("글자처럼 취급 속성을 설정하지 못했습니다.")
    ctrl.Properties = props
    applied = read_item(ctrl.Properties, "TreatAsChar")
    if applied not in (False, True, 0, 1) or bool(applied) != enabled:
        raise RuntimeError("한글에 글자처럼 취급 설정이 반영되지 않았습니다.")
    return True, f"{label} 완료"
