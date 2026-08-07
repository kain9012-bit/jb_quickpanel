# -*- coding: utf-8 -*-
"""
중복 실행 방지.

`C:\\work\\pdf_doc_tools_tk\\main.py`에서 실제로 잘 동작하는 방식을 그대로 가져왔다.

동작:
1. ctypes로 이름 있는 뮤텍스를 만들고, 바로 다음 줄에서 GetLastError를 읽어
   ERROR_ALREADY_EXISTS 인지 본다. (중간에 다른 Win32 호출이 끼지 않는 것이 핵심)
2. 이미 실행 중이면, 창 제목으로 기존 창을 찾아 ShowWindow + SetForegroundWindow 로
   앞으로 가져온다. 트레이로 숨겨져 있거나 최소화된 경우도 복원된다.
3. 어느 단계든 실패하면 실행을 막지 않는다.

숨은 메시지 창이나 브로드캐스트 메시지는 쓰지 않는다.
창을 직접 찾아 띄우는 편이 단순하고 확실하다.
"""

import os
import sys


_SINGLE_INSTANCE_HANDLE = None

MUTEX_NAME = "JbHwpHelper_SingleInstance"
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance() -> bool:
    """False 를 돌려주면 이미 실행 중이라는 뜻이다."""
    global _SINGLE_INSTANCE_HANDLE
    if os.name != "nt":
        return True
    try:
        import ctypes

        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        _SINGLE_INSTANCE_HANDLE = handle
        return True
    except Exception:
        return True


def activate_existing_window(window_title: str) -> bool:
    """이미 실행 중인 창을 찾아 앞으로 가져온다. 성공하면 True.

    중복 실행 시 안내창을 띄우는 대신, 사용자가 쓰려던 그 창을 바로 보여준다.
    트레이로 숨겨져 있거나 최소화된 경우에도 복원한다.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes

        u = ctypes.windll.user32
        u.FindWindowW.restype = ctypes.c_void_p
        u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        u.IsIconic.argtypes = [ctypes.c_void_p]

        hwnd = u.FindWindowW(None, window_title)
        if not hwnd:
            return False
        SW_SHOW, SW_RESTORE = 5, 9
        u.ShowWindow(hwnd, SW_SHOW)          # 트레이로 숨겨져 있던 경우
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, SW_RESTORE)   # 최소화되어 있던 경우
        u.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def notify_already_running(app_title: str, message: str) -> None:
    """창을 못 찾은 경우에만 쓰는 마지막 안내."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, app_title, 0x40)
    except Exception:
        pass
