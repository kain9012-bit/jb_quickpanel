import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.server import _set_target_mode, dispatch
from backend.full_features import FullFeatureService
from backend.tauri_hwp_bridge import TauriHwpBridge
from src.jb_quickpanel.features.page_layout import PAGE_FIELDS, MARGIN_FIELDS, PageLayout
from src.jb_quickpanel.services.user_content import DEFAULT_PAGE_MARGINS, UserContentStore, UserContentError
from src.jb_quickpanel.services.user_backup import create_user_backup, restore_user_backup


class Set:
    def __init__(self):
        self.values = {}

    def SetItem(self, name, value):
        self.values[name] = value


class Document:
    def __init__(self, anchors=(0,), origin=50, pages=3):
        self.pos = (0, origin, 0)
        self.pages = pages
        self.anchors = list(anchors)
        self.values = {para: {field: 0 for field in PAGE_FIELDS} for para in anchors}
        for values in self.values.values():
            values.update(PaperWidth=59528, PaperHeight=84186, LeftMargin=5000)
        self.HParameterSet = SimpleNamespace(
            HSecDef=SimpleNamespace(HSet=Set(), PageDef=SimpleNamespace()),
            HParaShape=SimpleNamespace(HSet=Set(), PagebreakBefore=0),
        )
        self.HAction = SimpleNamespace(Run=self.run, GetDefault=self.default, Execute=self.execute)
        self.undo = []
        self.calls = []
        self.ignore_setup = False
        self.wrong_global_scope = False
        self.hard_breaks = set()
        self.fail_break_at = None
        self.nested_boundary = False

    @property
    def HeadCtrl(self):
        following = None
        for para in reversed(self.anchors):
            following = SimpleNamespace(CtrlID='secd', Next=following,
                GetAnchorPos=lambda _, para=para: SimpleNamespace(Item=lambda name: {'List': 0, 'Para': para, 'Pos': 0}[name]))
        return following

    def current(self):
        return max(anchor for anchor in self.anchors if anchor <= self.pos[1])

    def GetPos(self):
        return self.pos

    def SetPos(self, *position):
        self.pos = tuple(position)
        return True

    def SelectText(self, *args):
        return True

    def KeyIndicator(self):
        return True, len(self.anchors), self.anchors.index(self.current()) + 1, 1

    def GetTextFile(self, kind, attributes):
        if kind == 'HWPML2X':
            return '<HWPML><BODY><SECTION>' + ''.join('<P PageBreak="true"/>' if para in self.hard_breaks else '<P/>' for para in range(self.pages * 45)) + '</SECTION></BODY></HWPML>'
        return '' if attributes == 'saveblock' else 'original document'

    def MiliToHwpUnit(self, value):
        return int(value * 100)

    def snapshot(self):
        self.undo.append((list(self.anchors), copy.deepcopy(self.values), self.pos, set(self.hard_breaks)))

    def run(self, action):
        self.calls.append(action)
        if action == 'MovePageBegin':
            self.pos = (int(self.nested_boundary), self.pos[1] // 45 * 45, 0)
        elif action == 'MovePageEnd':
            self.pos = (int(self.nested_boundary), min(self.pages * 45 - 1, self.pos[1] // 45 * 45 + 44), 10)
        elif action == 'MoveNextChar' and self.pos[1] < self.pages * 45 - 1:
            self.pos = (self.pos[0], self.pos[1] + 1, 0)
        elif action == 'BreakSection':
            if self.pos[1] == self.fail_break_at:
                return False
            self.snapshot()
            values = dict(self.values[self.current()])
            self.anchors.append(self.pos[1])
            self.anchors.sort()
            self.values[self.pos[1]] = values
            self.pos = (0, self.pos[1], self.pos[2] + 16)
        elif action == 'Undo':
            self.anchors, self.values, self.pos, self.hard_breaks = self.undo.pop()
        elif action == 'DeleteBack':
            self.snapshot()
            self.hard_breaks.remove(self.pos[1])
        return True

    def default(self, action, _):
        if action == 'PageSetup':
            for name, value in self.values[self.current()].items():
                setattr(self.HParameterSet.HSecDef.PageDef, name, value)
        return True

    def execute(self, action, _):
        self.calls.append(action)
        self.snapshot()
        if not self.ignore_setup:
            ps = self.HParameterSet.HSecDef
            targets = self.anchors if ps.HSet.values['ApplyTo'] == 3 or self.wrong_global_scope else [self.current()]
            for para in targets:
                self.values[para] = {name: getattr(ps.PageDef, name) for name in PAGE_FIELDS}
        return True


class PageLayoutTests(unittest.TestCase):
    def test_middle_page_keeps_front_and_back_settings_and_cursor(self):
        doc = Document()
        original = copy.deepcopy(doc.values[0])
        PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertEqual(doc.anchors, [0, 45, 90])
        self.assertEqual(doc.values[0], original)
        self.assertEqual(doc.values[90], original)
        self.assertEqual(doc.values[45]['Landscape'], 1)
        self.assertEqual(doc.pos, (0, 50, 0))

    def test_existing_boundaries_are_reused(self):
        doc = Document(anchors=(0, 45, 90))
        PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertNotIn('BreakSection', doc.calls)
        self.assertEqual([doc.values[p]['Landscape'] for p in doc.anchors], [0, 1, 0])

    def test_document_scope_changes_all_sections_without_breaks(self):
        doc = Document(anchors=(0, 45, 90))
        PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'document')
        self.assertEqual([doc.values[p]['Landscape'] for p in doc.anchors], [1, 1, 1])
        self.assertNotIn('BreakSection', doc.calls)

    def test_first_last_and_only_page_add_only_needed_boundaries(self):
        for origin, pages, expected in ((10, 3, [0, 45]), (100, 3, [0, 90]), (10, 1, [0])):
            with self.subTest(origin=origin, pages=pages):
                doc = Document(origin=origin, pages=pages)
                PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
                self.assertEqual(doc.anchors, expected)

    def test_repeat_does_not_add_another_section(self):
        doc = Document()
        PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        before = len(doc.calls)
        PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertEqual(doc.calls[before:], ['Cancel'])

    def test_ignored_setup_rolls_back_only_this_operation(self):
        doc = Document()
        original = copy.deepcopy(doc.values)
        doc.ignore_setup = True
        with self.assertRaisesRegex(RuntimeError, '변경 결과'):
            PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertEqual(doc.values, original)
        self.assertEqual(doc.anchors, [0])
        self.assertEqual(doc.calls.count('Undo'), 3)
        self.assertEqual(doc.pos, (0, 50, 0))

    def test_failed_second_break_restores_the_first_break(self):
        doc = Document()
        doc.fail_break_at = 45
        with self.assertRaisesRegex(RuntimeError, 'BreakSection'):
            PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertEqual(doc.anchors, [0])
        self.assertEqual(doc.calls.count('Undo'), 1)

    def test_existing_explicit_page_breaks_are_replaced_and_restore_on_failure(self):
        for failure in (False, True):
            doc = Document()
            doc.hard_breaks = {45, 90}
            doc.ignore_setup = failure
            if failure:
                with self.assertRaises(RuntimeError):
                    PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
                self.assertEqual(doc.hard_breaks, {45, 90})
                self.assertEqual(doc.anchors, [0])
            else:
                PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
                self.assertEqual(doc.hard_breaks, set())
            self.assertEqual(doc.calls.count('DeleteBack'), 2)

    def test_wrong_global_scope_cannot_report_success(self):
        doc = Document()
        original = copy.deepcopy(doc.values)
        doc.wrong_global_scope = True
        with self.assertRaisesRegex(RuntimeError, '앞뒤 구역'):
            PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertEqual(doc.values, original)

    def test_builtin_a4_size_is_explicit_but_custom_size_is_kept(self):
        doc = Document()
        doc.values[0]['PaperWidth'] = 90000
        PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page', paper_size={'width': 210, 'height': 297})
        self.assertEqual(doc.values[45]['PaperWidth'], 21000)
        self.assertEqual(doc.values[0]['PaperWidth'], 90000)
        doc = Document()
        doc.values[0]['PaperWidth'] = 90000
        PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertEqual(doc.values[45]['PaperWidth'], 90000)

    def test_boundary_inside_table_is_rejected_before_any_edits(self):
        doc = Document()
        doc.nested_boundary = True
        with self.assertRaisesRegex(RuntimeError, '표 안'):
            PageLayout(doc).apply(DEFAULT_PAGE_MARGINS, 'landscape', 'page')
        self.assertEqual(doc.undo, [])
        self.assertEqual(doc.pos, (0, 50, 0))

    def test_invalid_values_do_not_modify_document(self):
        for orientation, scope, margins in [('invalid', 'page', {}), ('portrait', 'invalid', {}), ('portrait', 'page', {'left': float('nan')})]:
            doc = Document()
            with self.assertRaises(ValueError):
                PageLayout(doc).apply(margins, orientation, scope)
            self.assertEqual(doc.calls, [])


class PageSettingsTests(unittest.TestCase):
    def tearDown(self):
        _set_target_mode('hwp')

    def test_orientation_persists_and_invalid_update_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            store = UserContentStore(folder)
            item = store.add_page('가로', DEFAULT_PAGE_MARGINS, 'landscape')
            restored = UserContentStore(folder)
            self.assertEqual(restored.list_items('page')[0]['orientation'], 'landscape')
            with self.assertRaises(UserContentError):
                restored.update_item('page', item['id'], title='잘못된 수정', orientation='invalid')
            self.assertEqual(restored.list_items('page')[0]['title'], '가로')
            restored.update_item('page', item['id'], orientation='portrait')
            self.assertEqual(UserContentStore(folder).list_items('page')[0]['orientation'], 'portrait')

    def test_backup_restore_keeps_orientation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            UserContentStore(root / 'source/user_content').add_page('가로', {}, 'landscape')
            create_user_backup(root / 'transfer.jbhbackup', app_root=root / 'source')
            restore_user_backup(root / 'transfer.jbhbackup', app_root=root / 'target')
            self.assertEqual(UserContentStore(root / 'target/user_content').list_items('page')[0]['orientation'], 'landscape')

    def test_builtin_portrait_and_landscape_presets_use_a4_and_same_margins(self):
        from backend.server import REPOSITORY_ROOT
        service = FullFeatureService(REPOSITORY_ROOT)
        records = [record for record in service.content_records('page') if record['source'] == 'builtin']
        self.assertEqual(len(records), 2)
        self.assertEqual([record['orientation'] for record in records], ['portrait', 'landscape'])
        self.assertEqual(records[0]['margins'], records[1]['margins'])
        self.assertEqual(records[1]['paper_size'], {'width': 210, 'height': 297})

    def test_dispatch_passes_explicit_scope_and_saved_orientation(self):
        _set_target_mode('hwp')
        bridge = Mock()
        bridge.apply_page_preset.return_value = True, '현재 페이지 편집용지 적용 완료'
        with patch('backend.server.FEATURES.find_content', return_value={'title': '가로', 'margins': {}, 'orientation': 'landscape'}):
            result = dispatch('apply_page', {'item_key': 'user:1', 'scope': 'page'}, bridge, Mock())
        self.assertTrue(result[0])
        bridge.apply_page_preset.assert_called_once_with({}, 'landscape', 'page')

    def test_draft_mode_does_not_apply_page_settings(self):
        _set_target_mode('kedufine')
        bridge = Mock()
        self.assertFalse(dispatch('apply_page', {'scope': 'page'}, bridge, Mock())[0])
        bridge.apply_page_preset.assert_not_called()

    def test_bridge_reports_failure_instead_of_false_success(self):
        bridge = TauriHwpBridge()
        bridge.ensure = Mock(return_value=(True, 'OK'))
        with patch('backend.tauri_hwp_bridge.PageLayout') as layout:
            layout.return_value.apply.side_effect = RuntimeError('검증 실패')
            ok, message = bridge.apply_page_preset({}, 'landscape', 'page')
        self.assertFalse(ok)
        self.assertIn('검증 실패', message)


if __name__ == '__main__':
    unittest.main()
