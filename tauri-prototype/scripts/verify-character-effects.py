"""Verify character effects in a disposable HWP process, never a user's document."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

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
        existing = set()
        ok, running, _ = get_running_hwp_from_rot()
        if ok:
            for index in range(int(running.XHwpWindows.Count)):
                existing.add(win32process.GetWindowThreadProcessId(
                    int(running.XHwpWindows.Item(index).WindowHandle))[1])
        hwp = win32com.client.dynamic.Dispatch(
            win32com.client.DispatchEx("HWPFrame.HwpObject")._oleobj_)
        pid = win32process.GetWindowThreadProcessId(int(hwp.XHwpWindows.Item(0).WindowHandle))[1]
        assert pid not in existing, "Instance is not isolated; no edits attempted"
        isolated = True
        bridge = TauriHwpBridge()
        bridge.hwp = hwp
        bridge.ensure = lambda: (True, "isolated")
        assert bridge.insert_text("example")[0]
        hwp.HAction.Run("SelectAll")
        assert bridge.apply_charshape(bold=True)[0]
        for mode, expected in (("super", (1, 0)), ("super", (1, 0)),
                               ("sub", (0, 1)), ("normal", (0, 0))):
            ok, message = bridge.apply_charshape(script_mode=mode)
            assert ok, message
            action = hwp.CreateAction("CharShape")
            pset = action.CreateSet()
            action.GetDefault(pset)
            actual = tuple(int(pset.Item(key) or 0) for key in ("SuperScript", "SubScript"))
            assert actual == expected, (mode, actual)
            assert int(pset.Item("Bold")) == 1, "Other formatting changed"
            print(f"{mode}: readback={actual}, bold preserved", flush=True)
        hwp.HAction.Run("Cancel")
        hwp.HAction.Run("MoveDocEnd")
        for value, shape in (("30", "circle"), ("1", "square"),
                             ("가", "square"), ("A", "square")):
            assert bridge.insert_text(" ")[0]
            ok, message = bridge.compose_characters(value, shape)
            assert ok, message
            print(f"compose {shape} {value}: executed", flush=True)
        xml = hwp.GetTextFile("HWPML2X", "")
        root = ET.fromstring(xml)
        composed = [element for element in root.iter() if "COMPOSE" in element.tag.upper()]
        assert len(composed) >= 4, [(el.tag, el.attrib) for el in composed]
        print("Composed controls:", [(el.tag, el.attrib) for el in composed], flush=True)
        print("Existing user documents untouched.", flush=True)
    finally:
        if isolated and hwp is not None:
            hwp.Clear(1)
            hwp.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
