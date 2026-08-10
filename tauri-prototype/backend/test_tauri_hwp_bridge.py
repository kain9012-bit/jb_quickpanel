import unittest

from backend.server import TauriHwpBridge


class FakePositionSet:
    def __init__(self, values):
        self.values = values

    def Item(self, name):
        return self.values[name]


class FakeTableCtrl:
    CtrlID = "tbl"

    def __init__(self, anchor=None):
        self.anchor = anchor

    def GetAnchorPos(self, index):
        if self.anchor is None:
            raise RuntimeError("missing anchor")
        return FakePositionSet(
            {
                "List": self.anchor[0],
                "Para": self.anchor[1],
                "Pos": self.anchor[2],
            }
        )


class FakeHwp:
    def __init__(self, anchor):
        self.ParentCtrl = FakeTableCtrl(anchor)
        self.set_positions = []

    def SetPos(self, list_id, para_id, pos):
        self.set_positions.append((list_id, para_id, pos))
        self.ParentCtrl = None
        return True


class TauriHwpBridgeTests(unittest.TestCase):
    def test_inserted_table_exit_uses_main_document_anchor(self):
        bridge = TauriHwpBridge()
        bridge.hwp = FakeHwp((0, 4, 12))
        paragraph_breaks = []
        bridge.insert_paragraph_break = lambda: (
            paragraph_breaks.append(True) or True,
            "OK",
        )

        ok, message = bridge._place_cursor_after_inserted_table(True)

        self.assertTrue(ok, message)
        self.assertEqual(bridge.hwp.set_positions, [(0, 4, 13)])
        self.assertEqual(paragraph_breaks, [True])

    def test_inserted_table_exit_fails_instead_of_writing_into_last_cell(self):
        bridge = TauriHwpBridge()
        bridge.hwp = FakeHwp(None)

        ok, message = bridge._place_cursor_after_inserted_table(True)

        self.assertFalse(ok)
        self.assertIn("본문 위치", message)
        self.assertEqual(bridge.hwp.set_positions, [])


if __name__ == "__main__":
    unittest.main()