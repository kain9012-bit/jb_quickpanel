# -*- coding: utf-8 -*-
from src.jb_quickpanel_v24.core.runtime import CELL_SPACE_CHARS

def cell_normalize_text(text):
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.rstrip("\n")
    return text


def cell_clean_space_text(text):
    return cell_normalize_text(text).strip(CELL_SPACE_CHARS)


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
