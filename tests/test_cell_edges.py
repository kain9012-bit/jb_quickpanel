import unittest
from types import SimpleNamespace

from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge
from src.jb_quickpanel.features.cell_edges import CellEdgeEditor


class StyledCell:
    def __init__(self, text):
        self.characters = [(char, index) for index, char in enumerate(text)]
        self.cursor = 0
        self.anchor = None
        self.actions = []
        self.ParentCtrl = SimpleNamespace(CtrlID="tbl")
        self.HParameterSet = SimpleNamespace(HInsertText=SimpleNamespace(HSet=object(), Text=""))
        self.HAction = SimpleNamespace(GetDefault=lambda *_: True, Execute=self.execute)
        self.fail_action = None

    def text(self):
        return "".join(char for char, _style in self.characters)

    @staticmethod
    def width(char):
        return 8 if char == "\t" else len(char.encode("utf-16-le")) // 2

    def GetPos(self):
        before = self.text()[:self.cursor]
        return 2, before.count("\n"), sum(self.width(char) for char in before.split("\n")[-1])

    def SetPos(self, list_id, para, pos):
        if list_id != 2:
            return False
        previous = self.cursor
        for index in range(len(self.characters) + 1):
            self.cursor = index
            if self.GetPos() == (list_id, para, pos):
                self.anchor = None
                return True
        self.cursor = previous
        return False

    def SelectText(self, first_para, first_pos, last_para, last_pos):
        if not self.SetPos(2, first_para, first_pos):
            return False
        first = self.cursor
        if not self.SetPos(2, last_para, last_pos):
            return False
        self.anchor = first
        return True

    def GetTextFile(self, fmt, option):
        assert (fmt, option) == ("UNICODE", "saveblock")
        if self.anchor is None:
            return None
        first, last = sorted((self.anchor, self.cursor))
        return self.text()[first:last].replace("\n", "\r\n")

    def Run(self, action):
        self.actions.append(action)
        if action == self.fail_action:
            return False
        if action == "Cancel":
            self.anchor = None
        elif action == "MoveListBegin":
            self.cursor, self.anchor = 0, None
        elif action == "MoveListEnd":
            self.cursor, self.anchor = len(self.characters), None
        elif action in {"MoveSelRight", "MoveSelLeft"}:
            if self.anchor is None:
                self.anchor = self.cursor
            self.cursor = min(len(self.characters), max(0, self.cursor + (1 if action == "MoveSelRight" else -1)))
        elif action == "Delete":
            assert self.anchor is not None
            first, last = sorted((self.anchor, self.cursor))
            del self.characters[first:last]
            self.cursor, self.anchor = first, None
        else:
            raise AssertionError(action)
        return True

    def execute(self, action, _parameters):
        self.actions.append(action)
        if action == self.fail_action:
            return False
        assert action == "InsertText"
        assert self.anchor is None, "Affix must not replace a text selection"
        value = self.HParameterSet.HInsertText.Text.replace("\r\n", "\n")
        self.characters[self.cursor:self.cursor] = [(char, "added") for char in value]
        self.cursor += len(value)
        return True


class CellEdgeTests(unittest.TestCase):
    def test_trim_preserves_original_characters_and_styles(self):
        for text in ("  A😀\nB  ", "\t \u00a0A\tB\u3000\t", "\u200b\ufeff한글\ufeff", " \nA\n "):
            with self.subTest(text=text):
                hwp = StyledCell(text)
                before = hwp.characters.copy()
                spaces = " \t\u00a0\u3000\u200b\ufeff"
                left = len(text) - len(text.lstrip(spaces))
                right = len(text.rstrip(spaces))
                self.assertTrue(CellEdgeEditor(hwp).trim())
                self.assertEqual(hwp.characters, before[left:right])
                self.assertNotIn("InsertText", hwp.actions)
                self.assertIsNone(hwp.anchor)

    def test_empty_whitespace_only_and_unchanged_cells(self):
        for text, expected, changed in (("", "", False), (" \t\u3000", "", True), ("A\n", "A\n", False), ("\nA\n", "\nA\n", False)):
            with self.subTest(text=text):
                hwp = StyledCell(text)
                self.assertEqual(CellEdgeEditor(hwp).trim(), changed)
                self.assertEqual(hwp.text(), expected)

    def test_affix_never_replaces_original_text_or_styles(self):
        for text in ("", "A😀\nB\n", " \tA  "):
            for at_end in (False, True):
                with self.subTest(text=text, at_end=at_end):
                    hwp = StyledCell(text)
                    before = hwp.characters.copy()
                    self.assertTrue(CellEdgeEditor(hwp).affix("※", at_end=at_end))
                    self.assertEqual(hwp.text(), text + "※" if at_end else "※" + text)
                    self.assertEqual(hwp.characters[:-1] if at_end else hwp.characters[1:], before)
                    self.assertNotIn("Delete", hwp.actions)
                    self.assertIsNone(hwp.anchor)

    def test_failed_selection_or_read_never_deletes_content(self):
        for failure in ("select", "read", "movement"):
            hwp = StyledCell("\tA ")
            before = hwp.characters.copy()
            if failure == "select":
                hwp.SelectText = lambda *_: False
            elif failure == "read":
                hwp.GetTextFile = lambda *_: None
            else:
                hwp.fail_action = "MoveSelRight"
            with self.assertRaises(RuntimeError):
                CellEdgeEditor(hwp).trim()
            self.assertEqual(hwp.characters, before)
            self.assertNotIn("Delete", hwp.actions)

    def test_read_mismatch_is_checked_before_any_deletion(self):
        hwp = StyledCell(" A ")
        read = hwp.GetTextFile
        hwp.GetTextFile = lambda *args: read(*args) if read(*args) == " A " else "wrong"
        with self.assertRaises(RuntimeError):
            CellEdgeEditor(hwp).trim()
        self.assertEqual(hwp.text(), " A ")
        self.assertNotIn("Delete", hwp.actions)

    def test_whitespace_with_an_unrepresented_object_is_not_deleted(self):
        hwp = StyledCell(" \ufffc ")
        read = hwp.GetTextFile
        hwp.GetTextFile = lambda *args: read(*args).replace("\ufffc", "")
        with self.assertRaises(RuntimeError):
            CellEdgeEditor(hwp).trim()
        self.assertEqual(hwp.text(), " \ufffc ")
        self.assertNotIn("Delete", hwp.actions)

    def test_failed_delete_or_insert_reports_failure(self):
        for action in ("Delete", "InsertText"):
            hwp = StyledCell(" A ")
            hwp.fail_action = action
            with self.assertRaises(RuntimeError):
                editor = CellEdgeEditor(hwp)
                editor.trim() if action == "Delete" else editor.affix("x")
            self.assertEqual(hwp.text(), " A ")

    def test_root_document_is_not_treated_as_a_cell(self):
        hwp = StyledCell(" A ")
        hwp.ParentCtrl.CtrlID = "gso"
        with self.assertRaises(RuntimeError):
            CellEdgeEditor(hwp).trim()
        self.assertNotIn("Delete", hwp.actions)

    def test_range_iteration_and_generic_replacement_stay_separate(self):
        bridge = HwpBridge()
        bridge._cell_focus_hwp = lambda: None
        bridge.cell_validate_range_no_merged_cells = lambda *_: None
        bridge.cell_move_to_addr = lambda *_: None
        bridge.get_table_cell_addr = lambda: (1, 1, "A1")
        bridge.cell_move_right = lambda: None
        calls = []
        bridge.cell_transform_current_fast = lambda transform: calls.append(transform("old")) or True
        result = bridge.process_recorded_cell_range(1, 1, 2, 1, cell_operation=lambda: calls.append("edge") or True)
        self.assertEqual((calls, result["changed"]), (["edge", "edge"], 2))
        calls.clear()
        result = bridge.process_recorded_cell_range(1, 1, 2, 1, lambda text: text.replace("old", "new"))
        self.assertEqual((calls, result["changed"]), (["new", "new"], 2))


if __name__ == "__main__":
    unittest.main()
