import unittest
from types import SimpleNamespace

from src.jb_quickpanel.features.auto_format_transaction import SelectedTextRewrite


class MemoryHwp:
    def __init__(self, text):
        self.paragraphs = text.split("\n")
        self.position = (0, 0, 0)
        self.selection = None
        self.commands = []
        self.ParaShape = {"indent": 17}
        self.XHwpDocuments = SimpleNamespace(Active_XHwpDocument=SimpleNamespace(DocumentID=1))
        self.HAction = SimpleNamespace(Run=self.run)

    def GetPos(self):
        return self.position

    def SetPos(self, list_id, para, pos):
        if list_id != 0 or not 0 <= para < len(self.paragraphs) or not 0 <= pos <= len(self.paragraphs[para]):
            return False
        self.position = (list_id, para, pos)
        self.selection = None
        return True

    def SelectText(self, first, begin, last, end):
        self.selection = (first, begin, last, end)
        return True

    def GetTextFile(self, _format, _option):
        if self.selection is None:
            return "\n".join(self.paragraphs)
        first, begin, last, end = self.selection
        lines = self.paragraphs[first:last + 1].copy()
        lines[-1] = lines[-1][:end]
        lines[0] = lines[0][begin:]
        return "\r\n".join(lines)

    def insert(self, text):
        _, para, pos = self.position
        lines = text.split("\n")
        lines[0] = self.paragraphs[para][:pos] + lines[0]
        final_pos = len(lines[-1])
        lines[-1] += self.paragraphs[para][pos:]
        self.paragraphs[para:para + 1] = lines
        self.position = (0, para + len(lines) - 1, final_pos)

    def run(self, action):
        self.commands.append(action)
        if action == "Cancel":
            self.selection = None
        elif action == "MoveListEnd":
            self.position = (0, len(self.paragraphs) - 1, len(self.paragraphs[-1]))
        elif action == "BreakPara":
            self.insert("\n")
        elif action == "Delete":
            first, begin, last, end = self.selection
            self.paragraphs[first:last + 1] = [self.paragraphs[first][:begin] + self.paragraphs[last][end:]]
            self.position = (0, first, begin)
            self.selection = None
        return True


class SelectedTextRewriteTests(unittest.TestCase):
    def test_original_is_not_deleted_until_commit(self):
        hwp = MemoryHwp("before\nSOURCE\nafter")
        transaction = SelectedTextRewrite(hwp, (0, 1, 0), (0, 1, 6))
        transaction.begin()
        hwp.insert("result\nbody")
        self.assertIn("SOURCE", hwp.GetTextFile("", ""))
        self.assertNotIn("Delete", hwp.commands)
        transaction.commit()
        self.assertEqual(hwp.GetTextFile("", ""), "before\nresult\nbody\nafter")

    def test_rollback_preserves_partial_selection_and_paragraph_shape(self):
        hwp = MemoryHwp("before SOURCE after\nlast")
        transaction = SelectedTextRewrite(hwp, (0, 0, 7), (0, 0, 13))
        transaction.begin()
        hwp.insert("result\nbody")
        hwp.ParaShape = {"indent": 99}
        transaction.rollback()
        self.assertEqual(hwp.GetTextFile("", ""), "SOURCE")
        self.assertEqual("\n".join(hwp.paragraphs), "before SOURCE after\nlast")
        self.assertEqual(hwp.ParaShape, {"indent": 17})

    def test_partial_commit_keeps_unselected_prefix_and_suffix(self):
        hwp = MemoryHwp("before SOURCE after\nlast")
        transaction = SelectedTextRewrite(hwp, (0, 0, 7), (0, 0, 13))
        transaction.begin()
        hwp.insert("result")
        transaction.commit()
        self.assertEqual(hwp.GetTextFile("", ""), "before result after\nlast")

    def test_changed_source_or_document_is_never_deleted(self):
        for change in ("source", "document"):
            hwp = MemoryHwp("SOURCE\nafter")
            transaction = SelectedTextRewrite(hwp, (0, 0, 0), (0, 0, 6))
            transaction.begin()
            hwp.insert("result")
            if change == "source":
                hwp.paragraphs[1] = "EDITED"
            else:
                hwp.XHwpDocuments.Active_XHwpDocument.DocumentID = 2
            with self.assertRaises(RuntimeError):
                transaction.commit()
            with self.assertRaises(RuntimeError):
                transaction.rollback()
            self.assertNotIn("Delete", hwp.commands)

    def test_table_cell_selection_is_rejected_before_changes(self):
        hwp = MemoryHwp("SOURCE")
        with self.assertRaises(RuntimeError):
            SelectedTextRewrite(hwp, (1, 0, 0), (1, 0, 6)).begin()
        self.assertEqual(hwp.commands, [])

    def test_empty_result_cannot_delete_original(self):
        hwp = MemoryHwp("SOURCE")
        transaction = SelectedTextRewrite(hwp, (0, 0, 0), (0, 0, 6))
        transaction.begin()
        with self.assertRaises(RuntimeError):
            transaction.commit()
        transaction.rollback()
        self.assertEqual(hwp.paragraphs, ["SOURCE"])


if __name__ == "__main__":
    unittest.main()
