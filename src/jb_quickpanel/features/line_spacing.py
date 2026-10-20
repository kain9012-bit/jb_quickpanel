"""Bounded, layout-verified spacing changes on an existing HWP selection."""
from dataclasses import dataclass
import re


SPACING_FIELDS = tuple('Spacing' + language for language in (
    'Hangul', 'Latin', 'Hanja', 'Japanese', 'Other', 'Symbol', 'User',
))
_MARKER = re.compile(
    r'^\s*(?:(?:\d+|[IVXLCDMivxlcdm]+|[가-하])\s*[.)]|'
    r'[①-⑳㉠-㉻]|[-*·○◦●□■※▶▷])\s*'
)
_LABEL = re.compile(r'[（(][^\r\n()（）]{1,50}[)）]\s*[:：]?\s*')


def body_offset(text):
    marker = _MARKER.match(text)
    offset = marker.end() if marker else len(text) - len(text.lstrip())
    label = _LABEL.match(text, offset)
    return label.end() if label else offset


def text_offsets(text, origin):
    result = [origin]
    for char in text:
        result.append(result[-1] + len(char.encode('utf-16-le')) // 2)
    return result


def bounded_values(values, direction, step, limit):
    # Existing custom spacing outside our budget is never reset or compressed further.
    if direction < 0:
        return tuple(max(-limit, value - step) if value > -limit else value for value in values)
    return tuple(min(limit, value + step) if value < limit else value for value in values)


@dataclass(frozen=True)
class SpacingRun:
    start: tuple
    end: tuple
    values: tuple


class SpacingCancelled(RuntimeError):
    pass


class LineSpacingCleanup:
    def __init__(self, hwp, limit=3, cancelled=None):
        self.hwp = hwp
        self.limit = max(1, min(10, int(limit)))
        self.cancelled = cancelled or (lambda: False)
        self.journal = []
        self.decreased = 0
        self.increased = 0
        self.unresolved = 0

    def check_cancel(self):
        if self.cancelled():
            raise SpacingCancelled('자간 정리를 중단하고 원래 자간으로 복원했습니다.')

    @staticmethod
    def require(result, message):
        if isinstance(result, (bool, int)) and not result:
            raise RuntimeError(message)

    def move(self, position):
        self.hwp.Run('Cancel')
        self.require(self.hwp.SetPos(*position), '자간 정리 위치로 이동하지 못했습니다.')
        if tuple(self.hwp.GetPos()[:3]) != tuple(position):
            raise RuntimeError('자간 정리 위치가 일치하지 않습니다.')

    def run(self, action):
        self.require(self.hwp.Run(action), f'한글에서 {action} 명령을 실행하지 못했습니다.')

    def select(self, start, end):
        if start[:2] != end[:2] or start >= end:
            raise RuntimeError('자간 정리 범위를 확인하지 못했습니다.')
        self.move(start)
        self.require(self.hwp.SelectText(start[1], start[2], end[1], end[2]),
                     '자간 정리 범위를 선택하지 못했습니다.')

    def selected_text(self, start, end):
        self.select(start, end)
        return str(self.hwp.GetTextFile('TEXT', 'saveblock'))

    def line_end(self, position):
        self.move(position)
        self.run('MoveLineEnd')
        end = tuple(self.hwp.GetPos()[:3])
        # A caret exactly at a soft wrap can still belong to the preceding line.
        if end == position:
            self.hwp.Run('MoveNextChar')
            probe = tuple(self.hwp.GetPos()[:3])
            if probe[:2] == position[:2] and probe > position:
                self.run('MoveLineEnd')
                end = tuple(self.hwp.GetPos()[:3])
        if end[:2] != position[:2] or end < position:
            raise RuntimeError('현재 줄의 위치를 확인하지 못했습니다.')
        return end[2]

    def snapshot(self, start, end):
        runs = []
        position = start
        while position < end:
            self.check_cancel()
            self.move(position)
            self.run('MoveNextChar')
            next_position = tuple(self.hwp.GetPos()[:3])
            if next_position[:2] != start[:2] or not position < next_position <= end:
                raise RuntimeError('원래 자간을 읽을 문자 위치를 확인하지 못했습니다.')
            self.select(position, next_position)
            ps = self.hwp.HParameterSet.HCharShape
            self.require(self.hwp.HAction.GetDefault('CharShape', ps.HSet), '원래 자간을 읽지 못했습니다.')
            values = tuple(int(getattr(ps, field)) for field in SPACING_FIELDS)
            if any(not -50 <= value <= 50 for value in values):
                raise RuntimeError('원래 자간 값을 확인하지 못했습니다.')
            if runs and runs[-1].values == values:
                runs[-1] = SpacingRun(runs[-1].start, next_position, values)
            else:
                runs.append(SpacingRun(position, next_position, values))
            position = next_position
        return runs

    def apply(self, runs, direction=0, step=0):
        for saved in runs:
            values = saved.values if direction == 0 else bounded_values(saved.values, direction, step, self.limit)
            self.select(saved.start, saved.end)
            action = self.hwp.CreateAction('CharShape')
            ps = action.CreateSet()
            for field, value in zip(SPACING_FIELDS, values):
                ps.SetItem(field, value)
            self.require(action.Execute(ps), '한글에서 자간을 적용하지 못했습니다.')

    def rollback(self):
        errors = []
        for saved in reversed(self.journal):
            try:
                self.apply(saved)
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise RuntimeError('원래 자간 복원 실패: ' + errors[0])
        self.journal.clear()

    def trial(self, start, end, direction, resolved):
        if start >= end:
            return False
        saved = self.snapshot(start, end)
        if not saved:
            return False
        if not any(bounded_values(run.values, direction, self.limit, self.limit) != run.values for run in saved):
            return False
        self.journal.append(saved)
        for step in range(1, self.limit + 1):
            self.check_cancel()
            if not any(bounded_values(run.values, direction, step, self.limit) != run.values for run in saved):
                continue
            self.apply(saved, direction, step)
            self.check_cancel()
            if resolved():
                if direction < 0:
                    self.decreased += 1
                else:
                    self.increased += 1
                return True
        self.apply(saved)
        self.journal.pop()
        return False

    def process_range(self, start, end):
        start, end = sorted((tuple(start), tuple(end)))
        if start[0] != end[0]:
            raise RuntimeError('같은 본문 또는 셀 안의 텍스트를 블록 지정하세요.')
        if start == end:
            return
        for paragraph in range(start[1], end[1] + 1):
            self.check_cancel()
            self.hwp.Run('Cancel')
            self.require(self.hwp.SetPos(start[0], paragraph, 0), '문단으로 이동하지 못했습니다.')
            self.run('MoveParaBegin')
            first = tuple(self.hwp.GetPos()[:3])
            self.run('MoveParaEnd')
            last = tuple(self.hwp.GetPos()[:3])
            if first[:2] != (start[0], paragraph) or last[:2] != first[:2]:
                raise RuntimeError('문단 위치를 확인하지 못했습니다.')
            if first >= last:
                continue
            text = self.selected_text(first, last)
            offsets = text_offsets(text, first[2])
            # Embedded controls cannot safely be mapped from plain text; leave them intact.
            if offsets[-1] != last[2] or any(ord(char) < 32 for char in text):
                self.unresolved += 1
                continue
            left = max(first[2], start[2] if paragraph == start[1] else first[2], offsets[body_offset(text)])
            right = min(last[2], end[2] if paragraph == end[1] else last[2])
            if left >= right:
                continue
            self.process_paragraph(first, last, text, offsets, left, right)
            if self.selected_text(first, last) != text:
                raise RuntimeError('문장 내용이 달라져 자간 정리를 취소했습니다.')

    def process_paragraph(self, first, last, text, offsets, left, right):
        indices = {position: index for index, position in enumerate(offsets)}
        prefix = offsets[body_offset(text)]
        def score():
            broken = 0
            line_start = first[2]
            tail = 0
            while line_start < last[2]:
                line_stop = self.line_end((*first[:2], line_start))
                if line_stop <= line_start or line_stop not in indices:
                    raise RuntimeError('줄 배치를 확인하지 못했습니다.')
                index = indices[line_stop]
                if line_stop < last[2]:
                    if line_stop >= prefix and not text[index - 1].isspace() and not text[index].isspace():
                        broken += 1
                elif line_start > first[2] and 0 < len(text[indices[line_start]:].strip()) <= 4:
                    tail = 1
                line_start = line_stop
            return broken, tail

        cursor = first[2]
        visited = set()
        while cursor < last[2]:
            self.check_cancel()
            position = (*first[:2], cursor)
            boundary = self.line_end(position)
            if boundary <= cursor or boundary >= last[2]:
                break
            cut = indices.get(boundary)
            if cut is None:
                break
            word_start = word_end = cut
            split = not text[cut - 1].isspace() and not text[cut].isspace()
            if split:
                while word_start > 0 and not text[word_start - 1].isspace():
                    word_start -= 1
                while word_end < len(text) and not text[word_end].isspace():
                    word_end += 1
            elif len(text[cut:].strip()) <= 4 and text[cut:].strip():
                word_end = len(text.rstrip())
            else:
                cursor = boundary
                continue
            a, b = offsets[word_start], offsets[word_end]
            key = (a, b)
            if key in visited or a < left or b > right or a < prefix:
                cursor = boundary
                continue
            visited.add(key)
            anchor = position
            adjust_start = (*first[:2], max(cursor, left))
            before_score = score()
            pull = lambda: self.line_end(anchor) >= b and score() < before_score
            push = lambda: self.line_end(anchor) <= a and self.line_end((*first[:2], a)) >= b and score() < before_score
            directions = (-1, 1) if not split or cut - word_start >= word_end - cut else (1, -1)
            success = False
            for direction in directions:
                if not split and direction > 0:
                    continue
                stop = b if direction < 0 else a
                if self.trial(adjust_start, (*first[:2], stop), direction, pull if direction < 0 else push):
                    success = True
                    break
            if success:
                cursor = first[2]
            else:
                self.unresolved += 1
                cursor = boundary

    def message(self):
        return f'자간 정리 완료: 줄임 {self.decreased}곳, 늘림 {self.increased}곳, 유지 {self.unresolved}곳'
