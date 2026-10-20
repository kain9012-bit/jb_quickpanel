"""Section-scoped page presets without rewriting document contents."""
import math
import xml.etree.ElementTree as ET

from src.jb_quickpanel.services.user_content import DEFAULT_PAGE_MARGINS, PAGE_MARGIN_FIELDS


MARGIN_FIELDS = dict(zip(PAGE_MARGIN_FIELDS, (
    'TopMargin', 'HeaderLen', 'LeftMargin', 'GutterLen',
    'RightMargin', 'FooterLen', 'BottomMargin',
)))
PAGE_FIELDS = ('PaperWidth', 'PaperHeight', 'Landscape', *MARGIN_FIELDS.values(), 'GutterType')


class PageLayout:
    def __init__(self, hwp):
        self.hwp = hwp
        self.edits = 0
        self.page_breaks = set()

    @staticmethod
    def require(result, message):
        if isinstance(result, (bool, int)) and not result:
            raise RuntimeError(message)

    def run(self, action):
        self.require(self.hwp.HAction.Run(action), f'한글에서 {action} 명령을 실행하지 못했습니다.')

    def position(self):
        return tuple(int(value) for value in self.hwp.GetPos()[:3])

    def move(self, position):
        self.hwp.HAction.Run('Cancel')
        self.require(self.hwp.SetPos(*position), '편집용지를 적용할 위치로 이동하지 못했습니다.')
        if self.position() != position:
            raise RuntimeError('편집용지를 적용할 위치가 일치하지 않습니다.')

    def section_count(self):
        indicator = self.hwp.KeyIndicator()
        if len(indicator) < 4 or not indicator[0]:
            raise RuntimeError('현재 구역을 확인하지 못했습니다.')
        return int(indicator[1])

    def sections(self):
        result = []
        ctrl = self.hwp.HeadCtrl
        while ctrl:
            if str(ctrl.CtrlID) == 'secd':
                anchor = ctrl.GetAnchorPos(0)
                result.append(tuple(int(anchor.Item(name)) for name in ('List', 'Para', 'Pos')))
            ctrl = ctrl.Next
        result.sort()
        if not result or len(result) != self.section_count() or any(pos[0] != 0 for pos in result):
            raise RuntimeError('문서의 구역 경계를 확인하지 못했습니다.')
        return result

    def read(self):
        ps = self.hwp.HParameterSet.HSecDef
        self.require(self.hwp.HAction.GetDefault('PageSetup', ps.HSet), '현재 편집용지를 읽지 못했습니다.')
        return {name: int(getattr(ps.PageDef, name)) for name in PAGE_FIELDS}

    def enter_page_body(self, origin):
        if origin[0] == 0:
            return
        indicator = self.hwp.KeyIndicator()
        page_key = tuple(indicator[2:4])
        for outward, inward in (('MovePageDown', 'MovePageUp'), ('MovePageUp', 'MovePageDown')):
            self.move(origin)
            self.hwp.HAction.Run(outward)
            current_key = tuple(self.hwp.KeyIndicator()[2:4])
            if current_key != page_key:
                self.hwp.HAction.Run(inward)
            if self.position()[0] == 0 and tuple(self.hwp.KeyIndicator()[2:4]) == page_key:
                return
        raise RuntimeError('현재 페이지의 본문을 찾지 못했습니다. 표 밖의 본문에 커서를 놓고 적용하세요.')

    def set_page(self, values, scope):
        ps = self.hwp.HParameterSet.HSecDef
        self.require(self.hwp.HAction.GetDefault('PageSetup', ps.HSet), '현재 편집용지를 읽지 못했습니다.')
        for name, value in values.items():
            setattr(ps.PageDef, name, value)
        ps.HSet.SetItem('ApplyTo', scope)
        self.require(self.hwp.HAction.Execute('PageSetup', ps.HSet), '편집용지 변경을 실행하지 못했습니다.')
        self.edits += 1
        actual = self.read()
        if any(actual[name] != value for name, value in values.items()):
            raise RuntimeError('한글에서 편집용지 변경 결과를 확인하지 못했습니다.')

    def section_pages(self, anchors):
        result = {}
        for index, anchor in enumerate(anchors, 1):
            self.hwp.HAction.Run('Cancel')
            self.require(self.hwp.SetPos(*anchor), '구역의 편집용지를 읽지 못했습니다.')
            if int(self.hwp.KeyIndicator()[2]) != index:
                raise RuntimeError('구역의 편집용지 위치가 일치하지 않습니다.')
            result[anchor] = self.read()
        return result

    def boundary_is_section(self, position, anchors):
        # A section starts with non-text controls. Read their text instead of
        # assuming a fixed length for the section/column control headers.
        for anchor in anchors:
            if anchor[:2] != position[:2] or anchor > position:
                continue
            if anchor == position:
                return True
            self.hwp.HAction.Run('Cancel')
            self.require(self.hwp.SetPos(*anchor), '구역 시작 위치로 이동하지 못했습니다.')
            actual = self.position()
            # Hancom clamps an anchor inside section controls to their end.
            if actual == position:
                return True
            if actual[:2] != position[:2] or actual > position:
                continue
            self.require(self.hwp.SelectText(actual[1], actual[2], position[1], position[2]),
                         '구역 시작 위치를 확인하지 못했습니다.')
            text = str(self.hwp.GetTextFile('TEXT', 'saveblock'))
            self.hwp.HAction.Run('Cancel')
            if not text.strip():
                return True
        return False

    def break_section(self, position):
        self.move(position)
        # Replace an existing paragraph page break rather than adding a blank
        # paragraph when BreakSection runs at that same boundary.
        ps = self.hwp.HParameterSet.HParaShape
        self.require(self.hwp.HAction.GetDefault('ParagraphShape', ps.HSet), '쪽 나눔 상태를 확인하지 못했습니다.')
        if position[2] == 0 and position[1] in self.page_breaks:
            before_text = self.hwp.GetTextFile('TEXT', '')
            self.run('DeleteBack')
            self.edits += 1
            if self.position() != position or self.hwp.GetTextFile('TEXT', '') != before_text:
                raise RuntimeError('기존 쪽 나눔을 안전하게 대체하지 못했습니다.')
        if position[2] == 0 and int(ps.PagebreakBefore):
            action = self.hwp.CreateAction('ParagraphShape')
            values = action.CreateSet()
            values.SetItem('PagebreakBefore', 0)
            self.require(action.Execute(values), '기존 쪽 나눔을 정리하지 못했습니다.')
            self.edits += 1
        before = self.section_count()
        self.run('BreakSection')
        self.edits += 1
        if self.section_count() != before + 1:
            raise RuntimeError('새 구역이 만들어지지 않았습니다.')
        return self.position()

    def apply(self, margins, orientation='portrait', scope='document', paper_size=None):
        if orientation not in ('portrait', 'landscape'):
            raise ValueError('용지 방향을 선택하세요.')
        if scope not in ('document', 'page'):
            raise ValueError('편집용지 적용 범위를 선택하세요.')
        requested = {'Landscape': int(orientation == 'landscape')}
        if paper_size is not None:
            for name, field in (('width', 'PaperWidth'), ('height', 'PaperHeight')):
                value = float(paper_size[name])
                if not math.isfinite(value) or not 10 <= value <= 1000:
                    raise ValueError('용지 크기가 올바르지 않습니다.')
                requested[field] = int(self.hwp.MiliToHwpUnit(value))
            requested['GutterType'] = 0
        for name, attr in MARGIN_FIELDS.items():
            value = float(margins.get(name, DEFAULT_PAGE_MARGINS[name]))
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError('용지 여백은 0~100mm 범위로 입력하세요.')
            requested[attr] = int(self.hwp.MiliToHwpUnit(value))
        origin = self.position()
        restore = origin
        original_sections = self.section_count()
        try:
            if scope == 'document':
                self.set_page(requested, 3)
                self.move(restore)
                return
            current = self.read()
            if all(current[name] == value for name, value in requested.items()):
                self.move(restore)
                return
            anchors = self.sections()
            original_pages = self.section_pages(anchors)
            original_text = self.hwp.GetTextFile('TEXT', '')
            # Explicit Ctrl+Enter breaks belong to paragraph instances, not
            # ParaShape.PagebreakBefore. Read their flags without saving a file.
            xml = ET.fromstring(self.hwp.GetTextFile('HWPML2X', ''))
            paragraphs = xml.findall('./BODY/SECTION/P')
            self.page_breaks = {i for i, para in enumerate(paragraphs) if para.get('PageBreak') == 'true'}
            self.move(origin)
            self.enter_page_body(origin)
            self.run('MovePageBegin')
            start = self.position()
            self.run('MovePageEnd')
            last = self.position()
            # Moving past the final document character is a valid no-op.
            self.hwp.HAction.Run('MoveNextChar')
            end = self.position()
            if start[0] != 0 or last[0] != 0 or end[0] != 0:
                raise RuntimeError('여러 쪽에 걸친 표 안에서는 구역을 나눌 수 없습니다. 표 밖의 본문에 커서를 놓고 적용하세요.')
            if start > last or end < last:
                raise RuntimeError('현재 페이지의 범위를 확인하지 못했습니다.')
            split_start = not self.boundary_is_section(start, anchors)
            split_end = end != last and not self.boundary_is_section(end, anchors)
            if (split_start and start[2] != 0) or (split_end and end[2] != 0):
                raise RuntimeError('페이지 경계가 문단 중간에 있습니다. 해당 경계에서 문단을 나눈 뒤 다시 적용하세요.')
            # Split the later boundary first so the earlier coordinates stay valid.
            if split_end:
                self.break_section(end)
            if split_start:
                applied_start = self.break_section(start)
                if origin[:2] == start[:2] and origin >= start:
                    restore = (origin[0], origin[1], origin[2] + applied_start[2] - start[2])
            else:
                self.move(start)
            self.set_page(requested, 2)
            target_section = int(self.hwp.KeyIndicator()[2])
            if self.section_count() != original_sections + int(split_start) + int(split_end):
                raise RuntimeError('편집용지 적용 후 구역 구성이 일치하지 않습니다.')
            if self.hwp.GetTextFile('TEXT', '') != original_text:
                raise RuntimeError('구역 나누기 후 문서 내용이 달라져 변경을 취소했습니다.')
            for index, (anchor, actual) in enumerate(self.section_pages(self.sections()).items(), 1):
                source = max(old for old in anchors if old <= anchor)
                expected = dict(original_pages[source])
                if index == target_section:
                    expected.update(requested)
                if actual != expected:
                    raise RuntimeError('앞뒤 구역의 편집용지가 유지되지 않아 변경을 취소했습니다.')
            self.move(restore)
        except Exception:
            if self.edits:
                try:
                    for _ in range(self.edits):
                        self.run('Undo')
                    if self.section_count() != original_sections:
                        raise RuntimeError('구역 복원 결과가 일치하지 않습니다.')
                    restore = origin
                except Exception as error:
                    raise RuntimeError('변경 복원을 완료하지 못했습니다. 한글에서 실행 취소로 확인하세요.') from error
            self.move(origin)
            raise
