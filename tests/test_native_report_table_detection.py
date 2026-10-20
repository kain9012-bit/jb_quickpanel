import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_checkpoint_reselects_original_range_before_editing(self):
        class FakeHwp:
            XHwpDocuments = SimpleNamespace(Active_XHwpDocument=SimpleNamespace(DocumentID=1))
            HParameterSet = SimpleNamespace(
                HSecDef=SimpleNamespace(
                    HSet=object(),
                    PageDef=SimpleNamespace(
                        LeftMargin=2000, RightMargin=2000,
                        TopMargin=1000, BottomMargin=1500,
                        HeaderLen=1000, FooterLen=1000,
                    ),
                ),
            )
            HAction = SimpleNamespace(GetDefault=lambda *_args: True)
            def GetSelectedPos(self):
                return True, 0, 2, 3, 0, 4, 5

        bridge = HwpBridge()
        bridge.hwp = FakeHwp()
        bridge.ensure = lambda: (True, "ok")
        bridge.save_selected_block = lambda path: (True, path)
        selected = []
        bridge._restore_selected_report_range = lambda value: selected.append(value) or True
        with tempfile.TemporaryDirectory() as folder, patch(
            "src.jb_quickpanel.services.app_config.app_data_dir", return_value=Path(folder)
        ):
            ok, checkpoint = bridge.create_auto_format_checkpoint()
        self.assertTrue(ok)
        self.assertEqual(selected, [((0, 2, 3), (0, 4, 5))])
        self.assertEqual(checkpoint["start"], (0, 2, 3))
        self.assertEqual(checkpoint["end"], (0, 4, 5))
        self.assertEqual(checkpoint["page_setup"]["LeftMargin"], 2000)

    def test_restore_replaces_only_inserted_range(self):
        calls = []
        class FakeHwp:
            def GetPos(self):
                return (0, 4, 5)
            def SetPos(self, *position):
                calls.append(("set_pos", position))
            def SelectText(self, *selection):
                calls.append(("select", selection))
                return True

        bridge = HwpBridge()
        bridge.hwp = FakeHwp()
        bridge.ensure = lambda: (True, "ok")
        bridge.delete_selection = lambda: calls.append(("delete",)) or (True, "ok")
        bridge.insert_file = lambda path, **options: calls.append(("insert", path, options)) or (True, "ok")
        ok, _message = bridge.restore_auto_format_checkpoint({
            "path": "backup.hwp", "start": (0, 2, 3),
        })
        self.assertTrue(ok)
        self.assertEqual(calls, [
            ("set_pos", (0, 2, 3)),
            ("select", (2, 3, 4, 5)),
            ("delete",),
            ("insert", "backup.hwp", {"preserve_document": True}),
        ])

    def test_restore_native_table_uses_original_end_not_current_table_caret(self):
        selections = []
        class FakeHwp:
            def GetPos(self):
                return (1, 99, 2)
            def SetPos(self, *_position):
                return True
            def SelectText(self, *selection):
                selections.append(selection)
                return True

        bridge = HwpBridge()
        bridge.hwp = FakeHwp()
        bridge.ensure = lambda: (True, "ok")
        bridge.delete_selection = lambda: (True, "ok")
        bridge.insert_file = lambda _path, **_options: (True, "ok")
        ok, _message = bridge.restore_auto_format_checkpoint({
            "path": "backup.hwp", "start": (0, 2, 3), "end": (0, 4, 5),
        }, original_range=True)
        self.assertTrue(ok)
        self.assertEqual(selections, [(2, 3, 4, 5)])

    def test_restores_exact_page_margins_from_checkpoint(self):
        page_def = SimpleNamespace(
            LeftMargin=100, RightMargin=100, TopMargin=100, BottomMargin=100,
            HeaderLen=100, FooterLen=100,
        )
        applied = []
        class FakeHwp:
            HParameterSet = SimpleNamespace(
                HSecDef=SimpleNamespace(HSet=object(), PageDef=page_def),
            )
            HAction = SimpleNamespace(
                GetDefault=lambda *_args: True,
                Execute=lambda *_args: applied.append(page_def.LeftMargin) or True,
            )
            def SetPos(self, *_position):
                return True

        bridge = HwpBridge()
        bridge.hwp = FakeHwp()
        bridge.ensure = lambda: (True, "ok")
        margins = {
            "LeftMargin": 2000, "RightMargin": 2100,
            "TopMargin": 1100, "BottomMargin": 1500,
            "HeaderLen": 1000, "FooterLen": 900,
        }
        ok, _message = bridge.restore_page_setup({
            "start": (0, 2, 3), "page_setup": margins,
        })
        self.assertTrue(ok)
        self.assertEqual(applied, [2000])
        self.assertEqual({key: getattr(page_def, key) for key in margins}, margins)


class SelectedReportInspectionTests(unittest.TestCase):
    def test_objects_and_incomplete_inspection_are_reported_without_editing(self):
        class Ctrl:
            CtrlID = "gso"
            Next = None

            def __init__(self, position):
                self.position = position

            def GetAnchorPos(self, _mode):
                if self.position is None:
                    raise RuntimeError("unreadable anchor")
                return SimpleNamespace(Item=lambda name: dict(
                    zip(("List", "Para", "Pos"), self.position)
                )[name])

        class BrokenNext(Ctrl):
            @property
            def Next(self):
                raise RuntimeError("unreadable control chain")

        for control, positions, complete in (
            (Ctrl((0, 1, 2)), [(0, 1, 2)], True),
            (Ctrl((0, 3, 0)), [], True),
            (Ctrl(None), [], False),
            (BrokenNext((0, 1, 2)), [(0, 1, 2)], False),
        ):
            with self.subTest(control=type(control).__name__, complete=complete):
                hwp = SimpleNamespace(
                    HeadCtrl=control,
                    GetSelectedPos=lambda: (True, 0, 0, 0, 0, 3, 0),
                    InitScan=lambda *args: len(args) == 6,
                    GetText=lambda: (0, ""),
                    ReleaseScan=lambda: True,
                    SetPos=lambda *_args: True,
                    SelectText=lambda *_args: True,
                )
                bridge = HwpBridge()
                bridge.hwp = hwp
                bridge.ensure = lambda: (True, "ok")
                ok, data = bridge.inspect_selected_report_content()
                self.assertTrue(ok)
                self.assertEqual(data["native_object_positions"], positions)
                self.assertEqual(data["controls_complete"], complete)
                bridge._restore_selected_report_range = lambda _range: False
                self.assertFalse(bridge.inspect_selected_report_content()[0])

    def test_checkpoint_cannot_restore_into_a_different_document(self):
        bridge = HwpBridge()
        bridge.hwp = SimpleNamespace(
            XHwpDocuments=SimpleNamespace(Active_XHwpDocument=SimpleNamespace(DocumentID=2)),
        )
        bridge.ensure = lambda: (True, "ok")
        checkpoint = {
            "_hwp": bridge.hwp, "document_id": 1,
            "path": "backup.hwp", "start": (0, 0, 0),
            "page_setup": {"LeftMargin": 2000},
        }
        self.assertFalse(bridge.restore_auto_format_checkpoint(checkpoint)[0])
        self.assertFalse(bridge.restore_page_setup(checkpoint)[0])

    def test_active_rewrite_never_reconnects_to_a_different_window(self):
        bridge = HwpBridge()
        bridge.hwp = object()
        bridge._auto_format_transaction = SimpleNamespace(
            hwp=bridge.hwp, _check_document=lambda: None,
        )
        with patch(
            "src.jb_quickpanel.bridges.hwp_bridge.hwp_connection_matches_visible_target",
            return_value=False,
        ), patch.object(bridge, "connect_without_focus") as connect:
            self.assertFalse(bridge.ensure()[0])
            connect.assert_not_called()

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

            def InitScan(self, _option, _range, *_positions):
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
