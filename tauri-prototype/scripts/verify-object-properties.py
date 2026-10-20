"""Exercise the new commands in an isolated, disposable HWP instance."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tauri-prototype")]

import pythoncom
import win32com.client
import win32com.client.dynamic
import win32process

from backend.tauri_hwp_bridge import TauriHwpBridge
from src.jb_quickpanel.core.runtime import get_running_hwp_from_rot


def main():
    pythoncom.CoInitialize()
    hwp = None
    isolated = False
    try:
        existing_pids = set()
        ok, running, _ = get_running_hwp_from_rot()
        if ok:
            for index in range(int(running.XHwpWindows.Count)):
                hwnd = int(running.XHwpWindows.Item(index).WindowHandle)
                existing_pids.add(win32process.GetWindowThreadProcessId(hwnd)[1])

        hwp = win32com.client.dynamic.Dispatch(
            win32com.client.DispatchEx("HWPFrame.HwpObject")._oleobj_,
        )
        hwnd = int(hwp.XHwpWindows.Item(0).WindowHandle)
        if win32process.GetWindowThreadProcessId(hwnd)[1] in existing_pids:
            raise RuntimeError("Test HWP instance is not isolated; no document changes attempted.")
        isolated = True
        bridge = TauriHwpBridge()
        bridge.hwp = hwp
        bridge.ensure = lambda: (True, "isolated test instance")

        action = hwp.CreateAction("TableCreate")
        params = action.CreateSet()
        action.GetDefault(params)
        params.SetItem("Rows", 2)
        params.SetItem("Cols", 2)
        assert action.Execute(params), "Test table creation failed"
        table = hwp.ParentCtrl
        assert table is not None and table.CtrlID == "tbl"

        def check_pair(ctrl, label):
            before = ctrl.Properties
            size = tuple(bridge._hwp_get_item(before, name) for name in ("Width", "Height"))
            for enabled in (False, True, False):
                ok, message = bridge.set_object_treat_as_char(enabled)
                assert ok, message
                assert bool(bridge._hwp_get_item(ctrl.Properties, "TreatAsChar")) == enabled
                assert tuple(bridge._hwp_get_item(ctrl.Properties, name) for name in ("Width", "Height")) == size
                print(f"{label}: enabled={enabled}, readback verified, size unchanged", flush=True)

        check_pair(table, "table caret")
        hwp.SetPosBySet(table.GetAnchorPos(0))
        hwp.FindCtrl()
        assert hwp.CurSelectedCtrl is not None and hwp.CurSelectedCtrl.CtrlID == "tbl"
        check_pair(hwp.CurSelectedCtrl, "selected table")
        hwp.HAction.Run("Cancel")
        hwp.HAction.Run("MoveDocEnd")
        hwp.HAction.Run("BreakPara")

        picture_path = next((ROOT / "page_thumbs").glob("*.png"))
        bridge._insert_picture_compatible(str(picture_path), 0)
        ctrl = hwp.HeadCtrl
        picture = None
        while ctrl is not None:
            if ctrl.CtrlID == "gso":
                picture = ctrl
                break
            ctrl = ctrl.Next
        assert picture is not None, "Test picture creation failed"
        hwp.SetPosBySet(picture.GetAnchorPos(0))
        hwp.FindCtrl()
        assert hwp.CurSelectedCtrl is not None and hwp.CurSelectedCtrl.CtrlID == "gso"
        check_pair(hwp.CurSelectedCtrl, "selected picture")
        hwp.HAction.Run("Cancel")
        hwp.HAction.Run("MoveDocEnd")
        assert not bridge.set_object_treat_as_char(True)[0], "Missing selection should fail"
        print("Missing selection rejected. Existing user documents were not changed.", flush=True)
    finally:
        if isolated and hwp is not None:
            hwp.Clear(1)
            hwp.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
