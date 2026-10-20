import unittest
from types import SimpleNamespace

from src.jb_quickpanel.features.line_spacing import (
    LineSpacingCleanup, SpacingCancelled, SPACING_FIELDS, body_offset,
    bounded_values, text_offsets,
)
from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge


class FakeHwp:
    def __init__(self, text, capacity):
        self.text = text
        self.capacity = capacity
        self.position = (0, 0, 0)
        self.selection = (0, 0)
        self.values = [(0,) * 7 for _ in text]
        self.writes = []
        self.fail_once = False
        self.HParameterSet = SimpleNamespace(HCharShape=SimpleNamespace(HSet=object()))
        self.HAction = SimpleNamespace(GetDefault=self.get_default)

    def SetPos(self, *position):
        self.position = tuple(position)
        return True

    def GetPos(self):
        return self.position

    def GetSelectedPos(self):
        return (bool(self.selection[0] != self.selection[1]), 0, 0, self.selection[0], 0, 0, self.selection[1])

    @property
    def SelectionMode(self):
        return int(self.selection[0] != self.selection[1])

    def SelectText(self, p1, a, p2, b):
        assert p1 == p2 == 0
        self.selection = (a, b)
        return True

    def GetTextFile(self, format_name, attributes):
        assert (format_name, attributes) == ('TEXT', 'saveblock')
        return self.text[self.selection[0]:self.selection[1]]

    def ends(self):
        ends = []
        width = 0
        for index, values in enumerate(self.values):
            advance = 1 + values[0] / 100
            if width + advance > self.capacity + 1e-8:
                ends.append(index)
                width = 0
            width += advance
        ends.append(len(self.text))
        return ends

    def Run(self, action):
        pos = self.position[2]
        if action == 'Cancel':
            self.selection = (0, 0)
            return True
        elif action == 'MoveLineBegin':
            pos = max([0] + [end for end in self.ends() if end <= pos and end < len(self.text)])
        elif action in ('MoveParaBegin', 'MoveListBegin'):
            pos = 0
        elif action in ('MoveParaEnd', 'MoveListEnd'):
            pos = len(self.text)
        elif action == 'MoveNextChar':
            pos = min(pos + 1, len(self.text))
        elif action == 'MoveLineEnd':
            pos = next((end for end in self.ends() if end > pos), len(self.text))
        else:
            raise AssertionError(action)
        self.position = (0, 0, pos)
        return True

    def get_default(self, action, parameter_set):
        assert action == 'CharShape'
        for field, value in zip(SPACING_FIELDS, self.values[self.selection[0]]):
            setattr(self.HParameterSet.HCharShape, field, value)
        return True

    def CreateAction(self, action):
        assert action == 'CharShape'
        def execute(ps):
            assert set(ps) == set(SPACING_FIELDS)
            self.writes.append(dict(ps))
            for index in range(*self.selection):
                self.values[index] = tuple(ps[field] for field in SPACING_FIELDS)
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError('COM failed after mutation')
            return True
        class Params(dict):
            def SetItem(self, key, value):
                self[key] = value
        return SimpleNamespace(CreateSet=Params, Execute=execute)


class LineSpacingTests(unittest.TestCase):
    TEXT = '가나다 ' * 4 + '교육행정'

    def test_smallest_success_not_maximum(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        self.assertEqual(engine.decreased, 1)
        self.assertEqual(hwp.ends(), [20])
        self.assertEqual(set(hwp.values), {(-1,) * 7})
        self.assertEqual(hwp.text, self.TEXT)

    def test_failed_trials_restore_mixed_spacing(self):
        hwp = FakeHwp(self.TEXT, 10)
        hwp.values[2] = (1, 2, -1, 0, 0, 0, 0)
        original = list(hwp.values)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        self.assertEqual(hwp.values, original)
        self.assertGreater(engine.unresolved, 0)

    def test_repeating_does_not_overcompress(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        original = list(hwp.values)
        again = LineSpacingCleanup(hwp, 3)
        again.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        self.assertEqual(hwp.values, original)
        self.assertEqual(again.decreased + again.increased, 0)

    def test_marker_and_label_unchanged(self):
        prefix = '1. (업무 개선) '
        hwp = FakeHwp(prefix + self.TEXT, len(prefix + self.TEXT) - .1)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, len(hwp.text)))
        self.assertEqual(hwp.values[:len(prefix)], [(0,) * 7] * len(prefix))
        self.assertEqual(engine.decreased, 1)

    def test_partial_selection_does_not_touch_outside(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 7), (0, 0, len(self.TEXT)))
        self.assertEqual(hwp.values[:7], [(0,) * 7] * 7)

    def test_reverse_selection_supported(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, len(self.TEXT)), (0, 0, 0))
        self.assertEqual(engine.decreased, 1)

    def test_cancellation_after_apply_rolls_back(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        engine = LineSpacingCleanup(hwp, 3, lambda: bool(hwp.writes))
        with self.assertRaises(SpacingCancelled):
            engine.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        engine.rollback()
        self.assertEqual(hwp.values, [(0,) * 7] * len(self.TEXT))

    def test_com_failure_after_write_can_be_rolled_back(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        hwp.fail_once = True
        engine = LineSpacingCleanup(hwp, 3)
        with self.assertRaisesRegex(RuntimeError, 'COM failed'):
            engine.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        engine.rollback()
        self.assertEqual(hwp.values, [(0,) * 7] * len(self.TEXT))

    def test_rollback_across_previously_successful_ranges(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        engine.cancelled = lambda: True
        with self.assertRaises(SpacingCancelled):
            engine.process_range((0, 0, 0), (0, 0, len(self.TEXT)))
        engine.rollback()
        self.assertEqual(hwp.values, [(0,) * 7] * len(self.TEXT))

    def test_short_last_line_without_split(self):
        hwp = FakeHwp('가나다 ' * 4 + '끝', 16.9)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, len(hwp.text)))
        self.assertEqual(hwp.ends(), [17])
        self.assertEqual(engine.decreased, 1)

    def test_expansion_can_move_whole_word_down(self):
        hwp = FakeHwp('가나다 ' * 4 + '교육행정지원서비스', 17.1)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, len(hwp.text)))
        self.assertEqual(engine.increased, 1)
        self.assertEqual(hwp.ends()[0], 16)

    def test_controls_and_cross_list_ranges_are_not_processed(self):
        hwp = FakeHwp('abc\tdef', 4)
        engine = LineSpacingCleanup(hwp, 3)
        engine.process_range((0, 0, 0), (0, 0, 7))
        self.assertEqual(hwp.writes, [])
        with self.assertRaises(RuntimeError):
            engine.process_range((0, 0, 0), (1, 0, 7))

    def test_absolute_budget_and_existing_custom_values(self):
        self.assertEqual(bounded_values((-3, -10, 0, 2), -1, 3, 3), (-3, -10, -3, -1))
        self.assertEqual(bounded_values((3, 10, 0, -2), 1, 3, 3), (3, 10, 3, 1))

    def test_unicode_offsets_and_prefixes(self):
        self.assertEqual(text_offsets('A😀나', 16), [16, 17, 19, 20])
        for prefix in ('1. ', '가. ', 'IV. ', '- ', '○ ', '① ', '  (설명) '):
            self.assertEqual(body_offset(prefix + '본문'), len(prefix))

    def test_soft_wrap_caret_on_previous_line_is_advanced(self):
        hwp = FakeHwp(self.TEXT, 10)
        original_run = hwp.Run
        previous_line = [False]
        original_move = hwp.SetPos
        def move(*position):
            previous_line[0] = position[2] in hwp.ends()[:-1]
            return original_move(*position)
        def run(action):
            if action == 'MoveLineEnd' and previous_line[0]:
                return True
            if action == 'MoveNextChar':
                previous_line[0] = False
            return original_run(action)
        hwp.SetPos = move
        hwp.Run = run
        self.assertEqual(LineSpacingCleanup(hwp).line_end((0, 0, 10)), 20)

    def test_bridge_restores_text_selection(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        hwp.SelectText(0, 0, 0, len(self.TEXT))
        bridge = HwpBridge()
        bridge.hwp = hwp
        bridge.ensure = lambda: (True, 'test')
        ok, message = bridge.cleanup_line_spacing()
        self.assertTrue(ok, message)
        self.assertEqual(hwp.selection, (0, len(self.TEXT)))

    def test_cell_cleanup_clears_internal_text_selection(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        hwp.SetPos(0, 0, 12)
        bridge = HwpBridge()
        bridge.hwp = hwp
        bridge.ensure = lambda: (True, 'test')
        ok, message = bridge.cleanup_current_cell_line_spacing()
        self.assertTrue(ok, message)
        self.assertEqual(hwp.GetPos(), (0, 0, 12))
        self.assertEqual(hwp.SelectionMode, 0)

    def test_bridge_failure_rolls_back_and_restores_selection(self):
        hwp = FakeHwp(self.TEXT, 19.8)
        hwp.SelectText(0, 0, 0, len(self.TEXT))
        hwp.fail_once = True
        bridge = HwpBridge()
        bridge.hwp = hwp
        bridge.ensure = lambda: (True, 'test')
        ok, message = bridge.cleanup_line_spacing()
        self.assertFalse(ok, message)
        self.assertEqual(hwp.values, [(0,) * 7] * len(self.TEXT))
        self.assertEqual(hwp.selection, (0, len(self.TEXT)))


if __name__ == '__main__':
    unittest.main()
