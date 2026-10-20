"""Keep the selected source in place until the replacement has been written."""
from __future__ import annotations


def _text(value):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


class SelectedTextRewrite:
    def __init__(self, hwp, start, end):
        self.hwp = hwp
        self.start = tuple(start)
        self.end = tuple(end)
        self.started = False
        self.committed = False

    def _position(self):
        return tuple(int(v) for v in self.hwp.GetPos()[:3])

    def _move(self, position):
        result = self.hwp.SetPos(*position)
        if isinstance(result, (bool, int)) and not result:
            raise RuntimeError("선택 영역 위치로 이동하지 못했습니다.")
        actual = self._position()
        if actual[:2] != tuple(position)[:2]:
            raise RuntimeError("선택 영역이 다른 문단으로 이동했습니다.")
        return actual

    def _run(self, action):
        result = self.hwp.HAction.Run(action)
        if isinstance(result, (bool, int)) and not result:
            raise RuntimeError(f"한글에서 {action} 명령을 실행하지 못했습니다.")

    def _select(self, start, end):
        if start[0] != end[0] or start > end:
            raise RuntimeError("선택 영역의 범위를 확인하지 못했습니다.")
        self._move(start)
        if self.hwp.SelectText(start[1], start[2], end[1], end[2]) is False:
            raise RuntimeError("선택 영역을 지정하지 못했습니다.")

    def _read(self, start, end):
        self._select(start, end)
        value = self.hwp.GetTextFile("UNICODE", "saveblock")
        if not isinstance(value, str):
            raise RuntimeError("원본 선택 영역을 확인하지 못했습니다.")
        return _text(value)

    def _last_paragraph(self):
        self._run("Cancel")
        self._move(self.start)
        self._run("MoveListEnd")
        position = self._position()
        if position[0] != self.start[0]:
            raise RuntimeError("본문의 끝 위치를 확인하지 못했습니다.")
        return position[1]

    def _source_range(self):
        added = self._last_paragraph() - self.last_before
        if added < 1:
            raise RuntimeError("새 결과와 원문의 경계를 확인하지 못했습니다.")
        start = (self.start[0], self.start[1] + added, 0)
        end_offset = self.end[2] - self.start[2] if self.end[1] == self.start[1] else self.end[2]
        return start, (self.end[0], self.end[1] + added, end_offset)

    def _check_document(self):
        current = int(self.hwp.XHwpDocuments.Active_XHwpDocument.DocumentID)
        if current != self.document_id:
            raise RuntimeError("작업 중 한글 문서가 바뀌어 원문을 지우지 않았습니다.")

    def begin(self):
        if self.start[0] != 0 or self.end[0] != 0:
            raise RuntimeError("표 밖의 본문을 블록 지정해 주세요.")
        self.document_id = int(self.hwp.XHwpDocuments.Active_XHwpDocument.DocumentID)
        self.start = self._move(self.start)
        self.end = self._move(self.end)
        self.source = self._read(self.start, self.end)
        if not self.source:
            raise RuntimeError("원본 선택 영역이 비어 있습니다.")
        self._run("Cancel")
        self._move(self.start)
        self.paragraph_shape = self.hwp.ParaShape
        self.last_before = self._last_paragraph()
        self._move(self.start)
        self.started = True
        self._run("BreakPara")
        if self._last_paragraph() != self.last_before + 1:
            raise RuntimeError("원문 앞에 새 결과를 쓸 자리를 만들지 못했습니다.")
        self._move(self.start)

    def commit(self):
        self._check_document()
        written_end = self._position()
        source_start, source_end = self._source_range()
        if written_end[0] != self.start[0] or not self.start < written_end < source_start:
            raise RuntimeError("새 결과의 끝을 확인하지 못해 원문을 유지했습니다.")
        if self._read(source_start, source_end) != self.source:
            raise RuntimeError("작업 중 원문이 달라져 원문을 지우지 않았습니다.")
        self._select(written_end, source_end)
        self._run("Delete")
        self.committed = True

    def rollback(self):
        self._check_document()
        if not self.started:
            return
        if self.committed:
            raise RuntimeError("원문 교체가 완료되어 새 결과만 제거할 수 없습니다.")
        if self._last_paragraph() == self.last_before:
            self._select(self.start, self.end)
            return
        source_start, source_end = self._source_range()
        if self._read(source_start, source_end) != self.source:
            raise RuntimeError("원문의 위치가 달라 새 결과를 제거하지 않았습니다.")
        self._select(self.start, source_start)
        self._run("Delete")
        self._move(self.start)
        self.hwp.ParaShape = self.paragraph_shape
        if self._read(self.start, self.end) != self.source:
            raise RuntimeError("원문 보존 결과를 확인하지 못했습니다.")
