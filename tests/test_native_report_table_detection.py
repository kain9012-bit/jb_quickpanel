import unittest

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge


class SelectedReportPositionTests(unittest.TestCase):
    def test_normalizes_selected_position_tuple(self):
        class FakeHwp:
            def GetSelectedPos(self):
                return True, 0, 41, 46, 0, 35, 0

        bridge = HwpBridge()
        bridge.hwp = FakeHwp()
        self.assertEqual(
            bridge._selected_report_position_range(),
            ((0, 35, 0), (0, 41, 46)),
        )


class SelectedReportInspectionTests(unittest.TestCase):
    def test_collects_following_paragraph_status_and_native_table_anchor(self):
        class PosSet:
            def Item(self, name):
                return {"List": 0, "Para": 2, "Pos": 0}[name]

        class Ctrl:
            CtrlID = "tbl"
            Next = None

            def GetAnchorPos(self, _mode):
                return PosSet()

        class FakeHwp:
            SelectionMode = 1
            ParentCtrl = None

            def __init__(self):
                self.HeadCtrl = Ctrl()
                self.events = [
                    ((2, "첫 문단\r\n"), (0, 0, 0)),
                    ((3, "둘째 문단"), (0, 1, 0)),
                    ((0, ""), (0, 1, 0)),
                ]
                self.event_index = 0
                self.current_pos = (0, 0, 0)
                self.restored = False

            def GetSelectedPos(self):
                return True, 0, 0, 0, 0, 3, 0

            def InitScan(self, _option, _range):
                return True

            def GetText(self):
                event, pos = self.events[self.event_index]
                self.current_pos = pos
                self.event_index += 1
                return event

            def MovePos(self, *_args):
                return True

            def GetPos(self):
                return self.current_pos

            def ReleaseScan(self):
                return True

            def SetPos(self, *_args):
                return True

            def SelectText(self, *_args):
                self.restored = True
                return True

        fake = FakeHwp()
        bridge = HwpBridge()
        bridge.hwp = fake
        ok, data = bridge.inspect_selected_report_content()
        self.assertTrue(ok)
        self.assertEqual([item["text"] for item in data["paragraphs"]], ["첫 문단", "둘째 문단"])
        self.assertEqual(data["native_table_positions"], [(0, 2, 0)])
        self.assertTrue(fake.restored)


if __name__ == "__main__":
    unittest.main()
