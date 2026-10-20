"""Edit only the whitespace or insertion point at a table cell's edges."""
from src.jb_quickpanel.core.runtime import CELL_SPACE_CHARS


class CellEdgeEditor:
    def __init__(self, hwp):
        self.hwp = hwp

    @staticmethod
    def require(result):
        if isinstance(result, (bool, int)) and not result:
            raise RuntimeError("셀 편집 명령을 실행하지 못했습니다.")

    def run(self, action):
        self.require(self.hwp.Run(action))

    def position(self):
        return tuple(int(value) for value in self.hwp.GetPos()[:3])

    def move(self, position):
        self.require(self.hwp.SetPos(*position))
        if self.position() != position:
            raise RuntimeError("셀 안의 정확한 위치로 이동하지 못했습니다.")

    def bounds(self):
        self.run("Cancel")
        if str(self.hwp.ParentCtrl.CtrlID).lower() != "tbl":
            raise RuntimeError("표의 셀 안에서 실행해 주세요.")
        self.run("MoveListBegin")
        start = self.position()
        self.run("MoveListEnd")
        end = self.position()
        if start[0] <= 0 or start[0] != end[0] or start > end:
            raise RuntimeError("현재 셀의 범위를 확인하지 못했습니다.")
        return start, end

    def select(self, start, end):
        self.move(start)
        self.require(self.hwp.SelectText(start[1], start[2], end[1], end[2]))

    def read(self):
        text = self.hwp.GetTextFile("UNICODE", "saveblock")
        if not isinstance(text, str):
            raise RuntimeError("셀의 글자를 정확히 읽지 못해 변경하지 않았습니다.")
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def edge_range(self, expected, start, end, *, at_end):
        anchor = end if at_end else start
        offset = -len(expected) if at_end else len(expected)
        candidate = (anchor[0], anchor[1], anchor[2] + offset)
        first, last = (candidate, end) if at_end else (start, candidate)
        if "\t" not in expected and start <= first <= last <= end:
            self.select(first, last)
            if self.read() == expected:
                return first, last
        # Tabs and other HWP controls need actual caret movement, not text offsets.
        self.run("Cancel")
        self.move(anchor)
        for _ in expected:
            previous = self.position()
            self.run("MoveSelLeft" if at_end else "MoveSelRight")
            current = self.position()
            if not start <= current <= end or current == previous:
                raise RuntimeError("삭제할 공백의 범위를 확인하지 못했습니다.")
        first, last = (self.position(), end) if at_end else (start, self.position())
        if self.read() != expected:
            raise RuntimeError("선택한 글자가 공백과 달라 삭제하지 않았습니다.")
        return first, last

    def trim(self):
        start, end = self.bounds()
        try:
            if start == end:
                return False
            self.select(start, end)
            text = self.read()
            leading = len(text) - len(text.lstrip(CELL_SPACE_CHARS))
            trailing = len(text) - len(text.rstrip(CELL_SPACE_CHARS))
            if not leading and not trailing:
                return False
            if leading == len(text):
                first, last = self.edge_range(text, start, end, at_end=False)
                if last != end:
                    raise RuntimeError("셀 전체가 공백인지 확인하지 못해 삭제하지 않았습니다.")
                edits = [(first, last, text)]
            else:
                edits = []
                if trailing:
                    first, last = self.edge_range(text[-trailing:], start, end, at_end=True)
                    edits.append((first, last, text[-trailing:]))
                if leading:
                    first, last = self.edge_range(text[:leading], start, end, at_end=False)
                    edits.append((first, last, text[:leading]))
            for first, last, expected in edits:
                self.select(first, last)
                if self.read() != expected:
                    raise RuntimeError("셀 내용이 달라져 공백 삭제를 중단했습니다.")
                self.run("Delete")
            return True
        finally:
            self.run("Cancel")
            self.move(start)

    def affix(self, value, *, at_end=False):
        if not value:
            return False
        start, end = self.bounds()
        try:
            self.move(end if at_end else start)
            ps = self.hwp.HParameterSet.HInsertText
            self.require(self.hwp.HAction.GetDefault("InsertText", ps.HSet))
            ps.Text = str(value)
            self.require(self.hwp.HAction.Execute("InsertText", ps.HSet))
            return True
        finally:
            self.run("Cancel")
            self.move(start)
