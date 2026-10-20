"""Verify only disposable HWP documents; never modify an existing process."""
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pythoncom
import win32com.client
import win32com.client.dynamic
import win32process
from src.jb_quickpanel.features.line_spacing import LineSpacingCleanup, SPACING_FIELDS
from src.jb_quickpanel.bridges.hwp_bridge import HwpBridge


def insert(hwp, text):
    ps = hwp.HParameterSet.HInsertText
    hwp.HAction.GetDefault('InsertText', ps.HSet)
    ps.Text = text
    assert hwp.HAction.Execute('InsertText', ps.HSet)


def shape(hwp, position):
    hwp.Run('Cancel')
    hwp.SetPos(*position)
    hwp.Run('MoveNextChar')
    end = hwp.GetPos()
    hwp.SetPos(*position)
    assert hwp.SelectText(position[1], position[2], end[1], end[2])
    ps = hwp.HParameterSet.HCharShape
    assert hwp.HAction.GetDefault('CharShape', ps.HSet)
    fields = SPACING_FIELDS + ('Height', 'Bold', 'TextColor') + tuple('Ratio' + x for x in (
        'Hangul', 'Latin', 'Hanja', 'Japanese', 'Other', 'Symbol', 'User',
    )) + ('FaceNameHangul', 'FaceNameLatin')
    return tuple(getattr(ps, field) for field in fields)


def main():
    pythoncom.CoInitialize()
    hwp = None
    isolated = False
    try:
        existing = set(win32process.EnumProcesses())
        hwp = win32com.client.dynamic.Dispatch(win32com.client.DispatchEx('HWPFrame.HwpObject')._oleobj_)
        pid = win32process.GetWindowThreadProcessId(int(hwp.XHwpWindows.Item(0).WindowHandle))[1]
        assert pid not in existing, 'Not an isolated HWP process; no changes attempted'
        isolated = True
        changed = 0
        cases = [('normal', '교육행정 업무 지원 ' * 6 + '서비스입니다.')]
        cases += [(f'close-{count}', '지원 ' * 14 + '끝' * count) for count in range(2, 5)]
        cases += [(f'orphan-{count}', '지원 ' * count + '끝') for count in range(12, 25)]
        cases += [(f'word-{count}', '학교와 교육청이 협력하여 교육행정지원서비스를 개선합니다. ' * count) for count in (2, 3, 4)]
        for count, body in cases:
            hwp.Clear(1)
            text = '1. (업무 개선) ' + body
            insert(hwp, text)
            para_action = hwp.CreateAction('ParagraphShape')
            para_set = para_action.CreateSet()
            para_set.SetItem('BreakNonLatinWord', 0)
            assert para_action.Execute(para_set)
            end = tuple(hwp.GetPos()[:3])
            hwp.SetPos(0, 0, 0)
            hwp.Run('MoveParaBegin')
            start = tuple(hwp.GetPos()[:3])
            if count == 'close-2':
                hwp.SetPos(0, 0, start[2] + 14)
                assert hwp.SelectText(0, start[2] + 14, 0, start[2] + 15)
                mixed_action = hwp.CreateAction('CharShape')
                mixed_set = mixed_action.CreateSet()
                mixed_set.SetItem('SpacingLatin', 2)
                assert mixed_action.Execute(mixed_set)
                hwp.Run('Cancel')
            before_text = hwp.GetTextFile('TEXT', '')
            limit = 5 if count == 'close-4' else 3
            engine = LineSpacingCleanup(hwp, limit)
            ends = []
            cursor = start[2]
            while cursor < end[2]:
                stop = engine.line_end((0, 0, cursor))
                assert stop > cursor
                ends.append(stop)
                cursor = stop
            print(f'case {count}: positions {start}..{end}, lines {ends}', flush=True)
            broken = any(not text[b - start[2] - 1].isspace() and not text[b - start[2]].isspace() for b in ends[:-1])
            orphan = len(ends) > 1 and 0 < len(text[ends[-2] - start[2]:].strip()) <= 4
            if not broken and not orphan and count != 'normal':
                continue
            before_shapes = [shape(hwp, (0, 0, p)) for p in range(start[2], end[2])]
            began = time.monotonic()
            try:
                engine.process_range(start, end)
            except Exception:
                engine.rollback()
                raise
            after_shapes = [shape(hwp, (0, 0, p)) for p in range(start[2], end[2])]
            assert hwp.GetTextFile('TEXT', '') == before_text, 'Text changed'
            assert all(a[7:] == b[7:] for a, b in zip(before_shapes, after_shapes)), 'Non-spacing font properties changed'
            assert before_shapes[:11] == after_shapes[:11], 'Leading marker or label changed'
            assert all(-limit <= value <= limit for item in after_shapes for value in item[:7])
            saved = list(after_shapes)
            again = LineSpacingCleanup(hwp, limit)
            again.process_range(start, end)
            repeated = [shape(hwp, (0, 0, p)) for p in range(start[2], end[2])]
            assert saved == repeated, 'Repeated operation changed already resolved spacing'
            engine.rollback()
            restored = [shape(hwp, (0, 0, p)) for p in range(start[2], end[2])]
            assert restored == before_shapes, 'Rollback did not restore original fonts/spacing'
            changed += engine.decreased + engine.increased
            print(f'case {count}: {engine.message()} ({time.monotonic() - began:.2f}s), text/fonts/prefix/repeat/rollback OK', flush=True)
            if changed >= 2:
                break
        assert changed > 0, 'No real layout corrections observed'
        hwp.Clear(1)
        ps = hwp.HParameterSet.HTableCreation
        assert hwp.HAction.GetDefault('TableCreate', ps.HSet)
        ps.Rows = 1
        ps.Cols = 2
        assert hwp.HAction.Execute('TableCreate', ps.HSet)
        insert(hwp, '1. (업무 개선) ' + '지원 ' * 7 + '끝끝')
        hwp.Run('MoveListBegin')
        cell_start = tuple(hwp.GetPos()[:3])
        hwp.Run('MoveListEnd')
        cell_end = tuple(hwp.GetPos()[:3])
        assert cell_start[0] != 0 and cell_start[0] == cell_end[0]
        before_text = hwp.GetTextFile('TEXT', '')
        original = [shape(hwp, (cell_start[0], 0, p)) for p in range(cell_end[2])]
        bridge = HwpBridge()
        bridge.hwp = hwp
        bridge.ensure = lambda: (True, 'private test only')
        assert hwp.SelectText(0, 15, 0, cell_end[2])
        ok, message = bridge.cleanup_line_spacing(5)
        assert ok, message
        assert hwp.GetTextFile('TEXT', '') == before_text
        after = [shape(hwp, (cell_start[0], 0, p)) for p in range(cell_end[2])]
        assert original[:15] == after[:15], 'Cell prefix/outside selection changed'
        assert all(a[7:] == b[7:] for a, b in zip(original, after)), 'Cell fonts or ratio changed'
        print(f'Cell partial selection: {message}, text/fonts/outside selection OK', flush=True)
        hwp.Run('Cancel')
        cursor = (cell_start[0], 0, 15)
        assert hwp.SetPos(*cursor)
        ok, message = bridge.cleanup_current_cell_line_spacing(5)
        assert ok, message
        assert tuple(hwp.GetPos()[:3]) == cursor and not (int(hwp.SelectionMode) & 0xF)
        assert hwp.GetTextFile('TEXT', '') == before_text
        print(f'Cell full cleanup: {message}, original cursor restored, no internal text block left', flush=True)
        print('PASS: disposable HWP layout verified; existing documents untouched.', flush=True)
    finally:
        if isolated and hwp is not None:
            hwp.Clear(1)
            hwp.Quit()
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
