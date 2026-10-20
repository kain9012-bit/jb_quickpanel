"""Exercise Win32 placement only on a newly created, disposable HWP process."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pythoncom
import win32com.client
import win32com.client.dynamic
import win32process
from src.jb_quickpanel.core.runtime import get_running_hwp_from_rot


def main():
    pythoncom.CoInitialize()
    hwp = None
    isolated = False
    try:
        existing = set()
        ok, running, _ = get_running_hwp_from_rot()
        if ok:
            for index in range(int(running.XHwpWindows.Count)):
                existing.add(win32process.GetWindowThreadProcessId(int(running.XHwpWindows.Item(index).WindowHandle))[1])
        hwp = win32com.client.dynamic.Dispatch(win32com.client.DispatchEx("HWPFrame.HwpObject")._oleobj_)
        hwnd = int(hwp.XHwpWindows.Item(0).WindowHandle)
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        assert pid not in existing, "Test process is not isolated; no layout changes attempted"
        isolated = True
        before = hwp.GetTextFile("HWPML2X", "")
        env = os.environ.copy()
        env["JB_LAYOUT_TEST_HWP_HWND"] = str(hwnd)
        env["JB_LAYOUT_TEST_HWP_PID"] = str(pid)
        subprocess.run(["cargo", "test", "--lib", "live_private_hwp_layout_and_restore", "--", "--ignored", "--nocapture"],
                       cwd=ROOT / "tauri-prototype/src-tauri", env=env, check=True)
        assert hwp.GetTextFile("HWPML2X", "") == before, "Test document contents changed"
        print("Document XML unchanged. Existing user documents/windows were not touched.", flush=True)
    finally:
        if isolated and hwp is not None:
            hwp.Clear(1)
            hwp.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
