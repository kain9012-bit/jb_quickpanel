(() => {
  const modal = document.querySelector('#practice-dialog');
  const launch = document.querySelector('#reader-practice');
  const close = document.querySelector('#practice-close');
  const reset = document.querySelector('#practice-reset');
  const guide = document.querySelector('#practice-guide');
  const documentWindow = document.querySelector('#practice-document');
  const mount = document.querySelector('#practice-app-mount');
  const catalogs = JSON.parse(document.querySelector('#practice-catalogs').textContent);
  const appSource = new TextDecoder().decode(Uint8Array.from(
    atob(JSON.parse(document.querySelector('#practice-app-html').textContent)), (char) => char.charCodeAt(0),
  ));
  const scenarios = {
    auto: ['전체 서식 자동 지정하기', '한글에서 초안 전체를 블록 지정하세요.', '서식 탭에서 ‘전체 서식 자동 지정하기’를 누르세요.'],
    direct: ['선택한 부분에 자동 서식 적용', '한글에서 서식을 바꿀 글을 선택하세요.', '문서제목·1단계 제목·2단계 제목·3단계 제목·본문·참고 중 하나를 누르세요.'],
    arrange: ['한글과 나란히 배치', 'JB에듀 폼 상단의 ‘한글과 나란히 배치’ 버튼을 누르세요.'],
    profile: ['자동 서식 설정 선택', '한글에서 초안 전체를 블록 지정하세요.', '서식 탭의 ‘사용할 설정’을 바꾼 다음 ‘전체 서식 자동 지정하기’를 누르세요.'],
    title: ['기존 제목 양식 추가', '한글에서 제목 양식 전체를 블록 지정하세요.', '‘서식 설정’을 열고 문서제목의 ‘기존 제목 양식 추가’를 누르세요.'],
    type: ['본문 글자 크기 바꾸기', '한글에서 본문을 블록 지정하세요.', '‘서식 설정’에서 본문 크기를 바꾸고 저장한 다음 ‘본문’을 누르세요.'],
    'insert-style': ['서식 수동 지정', '한글 문서의 삽입 위치를 클릭하세요.', '서식 탭의 ‘서식 수동 지정’에서 카드를 누르세요.'],
    table: ['표의 선·배경 정리', '한글 표 안에서 셀 범위를 드래그하세요.', '‘편집도구 → 표 작업’에서 선이나 배경 카드를 누르세요.'],
    images: ['여러 셀에 그림 넣기', '그림을 넣을 셀 두 개를 드래그하세요.', '그림 맞춤 방식을 고르고 ‘셀에 그림 넣기’를 누르세요.'],
    cell: ['셀마다 문자 붙이기', '한글 표의 숫자 셀을 드래그하세요.', '‘편집도구 → 셀 정리’에서 추가할 문자에 %를 입력하고 ‘내용 뒤에 추가’를 누르세요.'],
    'cell-clean': ['공백·배경 정리', '한글 표에서 정리할 셀을 드래그하세요.', '앞뒤 공백만 지울지, 배경까지 정리할지 골라 버튼을 누르세요.'],
    'cell-replace': ['셀 내용 찾아바꾸기', '한글 표에서 바꿀 셀을 드래그하세요.', '찾을 내용에 ‘연수’, 바꿀 내용에 ‘교육’을 입력하고 실행하세요.'],
    font: ['글자색·글꼴·크기', '한글에서 바꿀 글을 선택하세요.', '글자색이나 글꼴·크기 버튼을 눌러 선택한 글의 변화를 확인하세요.'],
    spacing: ['자간 정리', '한글에서 끝 글자가 다음 줄로 넘어간 문장을 블록 지정하세요.', '‘편집도구 → 글자 작업’에서 ‘자간 정리 1단계’를 누르세요.'],
    script: ['위첨자·아래첨자', '한글에서 숫자 2만 블록 지정하세요.', '‘편집도구 → 글자 작업’에서 ‘위첨자’를 누르세요.'],
    character: ['문자표에서 삽입', '한글에서 문자를 넣을 위치를 클릭하세요.', 'JB에듀 폼의 ‘문자표’ 탭에서 원하는 문자를 누르세요.'],
    compose: ['글자 겹치기', '한글에서 문자를 넣을 위치를 클릭하세요.', '‘문자표 → 글자 겹치기’에서 30을 입력하고 원 모양을 골라 ‘삽입’을 누르세요.'],
    favorite: ['즐겨찾기', '‘심볼’ 탭에서 자주 쓸 이미지 카드의 빈 별을 누르세요.'],
    'hwp-form': ['일반 한글 양식', '한글에서 양식을 넣을 위치를 클릭하세요.', '‘양식’ 탭에서 삽입 방식과 양식 카드를 고르세요.'],
    draft: ['K-에듀파인 기안문 양식', '기안창의 제목 칸이 아닌 본문을 클릭하세요.', '내부결재 또는 발송용에서 양식 카드를 누르세요.'],
    'user-character': ['내 문자표 추가', '‘내 문자표 추가’를 누르고 이름과 문자 목록을 입력하세요.'],
    symbol: ['심볼 넣기', '한글 문서에서 그림을 넣을 위치를 클릭하세요.', '원하는 심볼 카드를 눌러 삽입하세요.'],
    paper: ['편집용지 바꾸기', '한글에서 바꿀 페이지를 클릭하세요.', '‘편집용지’ 탭에서 적용 범위를 고르고 세로·가로 카드를 누르세요.'],
  };
  let state;
  let appFrame;
  let opener;
  let pendingFiles;
  const coach = createPracticeCoach(modal, documentWindow);
  const walkthroughs = {
    auto: ['초안 전체 선택', '전체 서식 자동 지정하기', '완성된 보고서 확인'],
    direct: ['바꿀 글 선택', '적용할 서식 버튼', '선택한 글의 변화 확인'],
    arrange: ['나란히 배치 버튼', '두 창의 배치 확인'],
    profile: ['초안 전체 선택', '사용할 설정 선택', '전체 서식 자동 지정하기', '결과 확인'],
    title: ['제목 양식 선택', '서식 설정 열기', '기존 제목 양식 추가', '이름 입력 후 저장', '설정 저장', '등록 결과 확인'],
    type: ['본문 선택', '서식 설정 열기', '본문 크기 입력', '설정 저장', '본문 버튼', '글자 크기 확인'],
    'insert-style': ['삽입 위치 클릭', '서식 카드 선택', '빈 칸에 내용 입력', '입력 결과 확인'],
    table: ['셀 범위 선택', '표 작업 카드', '선·배경 변화 확인'],
    images: ['그림을 넣을 셀 선택', '그림 맞춤 방식 선택', '셀에 그림 넣기', '그림 선택 후 열기', '각 셀의 그림 확인'],
    cell: ['셀 범위 선택', '추가할 문자 입력', '내용 뒤에 추가', '셀별 결과 확인'],
    'cell-clean': ['셀 범위 선택', '정리 버튼 선택', '공백·배경 확인'],
    'cell-replace': ['셀 범위 선택', '찾을 내용·바꿀 내용', '찾아바꾸기 실행', '바뀐 셀 확인'],
    font: ['바꿀 글 선택', '색상·글꼴·크기 버튼', '선택한 글 확인'],
    spacing: ['문장 전체 선택', '자간 정리 1단계', '줄바꿈 변화 확인'],
    script: ['숫자 2 선택', '위첨자 버튼', '숫자 위치 확인'],
    character: ['삽입 위치 클릭', '특수문자 클릭', '입력된 문자 확인'],
    compose: ['삽입 위치 클릭', '글자 겹치기 열기', '30 입력·모양 선택', '삽입 버튼', '겹친 글자 확인'],
    favorite: ['카드의 빈 별 클릭', '별과 카드 순서 확인'],
    'hwp-form': ['삽입 위치 클릭', '양식 카드 선택', '삽입 결과 확인'],
    draft: ['기안창 본문 클릭', '기안문 양식 카드', '본문 삽입 결과 확인'],
    'user-character': ['내 문자표 추가', '이름·문자 입력', '저장 버튼', '추가된 문자표 확인'],
    symbol: ['삽입 위치 클릭', '심볼 카드 선택', '삽입된 심볼 확인'],
    paper: ['적용할 페이지 클릭', '적용 범위·용지 카드', '방향과 범위 확인'],
  };
  const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const ok = (data = {}, message = '적용했습니다.') => ({ ok: true, message, data });
  const failure = (message) => ({ ok: false, message, data: { reason: 'selection_required' } });
  function say(text, completed = false) {
    guide.querySelector('#practice-instruction').textContent = text;
    guide.dataset.complete = String(completed);
  }
  function step(index, instruction) {
    state.step = Math.min(index, walkthroughs[state.kind].length - 1);
    const labels = walkthroughs[state.kind];
    guide.querySelector('#practice-steps').innerHTML = labels.map((label, i) =>
      '<li' + (i === state.step ? ' aria-current="step"' : '') + ' data-done="' + (i < state.step) + '"><span>' + (i + 1) + '</span>' + escape(label) + '</li>').join('');
    if (instruction) say(instruction);
    appFrame?.contentWindow?.postMessage({ source: 'jbe-practice-host', tutorialStep: state.step }, '*');
    documentWindow.querySelectorAll('.practice-target').forEach((node) => node.classList.remove('practice-target'));
    const target = state.step === 0 ? documentWindow.querySelector('#hwp-select') || documentWindow.querySelector('.hwp-editable,.hwp-draft,.hwp-demo-table,.hwp-paper')
      : state.kind === 'insert-style' && state.step === 2 ? documentWindow.querySelector('[data-style-slot]') : null;
    target?.classList.add('practice-target');
    const picker = state.kind === 'images' && state.step === 3 ? documentWindow.querySelector('.practice-file-picker') : null;
    if (picker) {
      const checked = picker.querySelectorAll('input:checked').length;
      coach.set([picker.querySelector(checked ? '[data-file-open]' : '.practice-file-options')], checked ? '‘열기’를 클릭하세요' : '그림 두 개를 체크하세요', state.step + 1);
    } else if (target) {
      const caption = target.id === 'hwp-select' ? '‘' + target.textContent + '’을 클릭하세요'
        : state.kind === 'insert-style' && state.step === 2 ? '이 칸을 클릭하고 내용을 입력하세요'
        : target.matches('table') ? '셀을 드래그해 선택하세요' : '이곳을 클릭해 커서를 놓으세요';
      coach.set([target], caption, state.step + 1);
    } else coach.clear();
  }
  function inputProgress() {
    if (state.kind === 'insert-style' && state.step === 2 && [...documentWindow.querySelectorAll('[data-style-slot]')].some((node) => node.textContent.trim())) {
      state.complete = true;
      step(3);
      say('서식 안에 내용을 입력했습니다. 다른 카드도 같은 방식으로 넣고 편집할 수 있습니다.', true);
    }
  }
  function setView(view) {
    modal.dataset.view = view;
    for (const button of modal.querySelectorAll('[data-practice-view]')) {
      button.setAttribute('aria-pressed', String(button.dataset.practiceView === view));
    }
    if (view === 'app') requestAnimationFrame(() => appFrame?.contentWindow?.postMessage({ source: 'jbe-practice-host', refreshHints: true }, '*'));
    coach.refresh();
  }
  function syncSelection() {
    const cells = [...documentWindow.querySelectorAll('[data-cell]')].filter((cell) => state.cells.has(cell.dataset.cell));
    const selection = {
      active: !!cells.length, dragging: false,
      label: cells.length ? '선택한 셀 범위' : '선택된 셀 없음',
      rows: new Set(cells.map((cell) => cell.dataset.row)).size,
      columns: new Set(cells.map((cell) => cell.dataset.column)).size,
    };
    appFrame?.contentWindow?.postMessage({ source: 'jbe-practice-host', selection }, '*');
    documentWindow.querySelectorAll('[data-cell]').forEach((cell) => cell.classList.toggle('hwp-cell-selected', state.cells.has(cell.dataset.cell)));
    const needsText = ['auto', 'direct', 'profile', 'title', 'type', 'font', 'spacing', 'script'].includes(state.kind);
    if (!state.complete && state.step === 0 && (needsText ? state.selected : state.cursor || state.cells.size)) {
      step(1, scenarios[state.kind][2] || scenarios[state.kind][1]);
    }
  }
  function selectedText() {
    const textarea = documentWindow.querySelector('textarea.hwp-draft');
    if (textarea) return textarea.selectionStart === 0 && textarea.selectionEnd === textarea.value.length;
    return state.selected;
  }
  function selectDocument() {
    const textarea = documentWindow.querySelector('textarea.hwp-draft');
    const target = documentWindow.querySelector(state.kind === 'script' ? '[data-script-digit]' : '.hwp-editable');
    if (textarea) { textarea.focus(); textarea.select(); }
    if (target) {
      const range = document.createRange();
      range.selectNodeContents(target);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      state.range = range.cloneRange();
    }
    state.selected = true;
    syncSelection();
  }
  function makeDocument() {
    const kind = state.kind;
    const draft = '2026년 교직원 연수 운영 계획\n\n1. 추진 목적\n교직원의 업무 역량 강화\n\n2. 연수 개요\n가. 대상\n소속 교직원\n\n※ 세부 일정은 추후 안내';
    let body = '';
    if (['auto', 'profile'].includes(kind)) {
      body = '<textarea class="hwp-draft" readonly aria-label="연수 운영 계획 초안">' + draft + '</textarea>';
    } else if (['cell', 'cell-clean', 'cell-replace', 'table', 'images'].includes(kind)) {
      const rows = kind === 'images' ? [['', '']] : kind === 'cell' ? [['34.5', '56.0'], ['62.5', '81.2']]
        : kind === 'cell-clean' ? [['　 연수 자료　', '  참석 명단  '], [' 교육 일정 ', '  운영 결과 ']]
        : kind === 'cell-replace' ? [['연수 계획', '연수 자료'], ['연수 일정', '연수 결과']] : [['교육', '교직원 연수'], ['실습', '자료 작성']];
      body = '<table class="hwp-demo-table"><thead><tr><th>' + (kind === 'images' ? '자료 1' : kind === 'cell' ? '신청률' : '구분') + '</th><th>' + (kind === 'images' ? '자료 2' : kind === 'cell' ? '참여율' : '내용') + '</th></tr></thead><tbody>' + rows.map((row, r) =>
        '<tr>' + row.map((value, c) => '<td data-cell="' + r + ':' + c + '" data-row="' + r + '" data-column="' + c + '" tabindex="0">' + value + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
    } else if (kind === 'draft') {
      body = '<div class="kedufine-subject"><label>제목<input aria-label="기안문 제목" value="2026년 교직원 연수 운영 계획" readonly></label></div><label class="kedufine-body-label">본문</label><div class="hwp-editable kedufine-body" contenteditable="true" role="textbox" aria-label="기안문 본문"></div>';
    } else {
      const text = kind === 'script' ? 'm<span data-script-digit>2</span>' : kind === 'direct'
        ? '교직원 연수 운영 계획' : kind === 'font' ? '교직원 업무 역량 강화' : kind === 'spacing'
        ? '<p class="spacing-paragraph"><span class="spacing-bullet">-</span><span class="spacing-text"></span></p>'
        : kind === 'title' ? '<div class="registered-title">교직원 연수 운영 계획</div>' : kind === 'type'
        ? '소속 교직원을 대상으로 연수를 운영함' : kind === 'character' ? '유의 사항 ' : kind === 'hwp-form' ? '업무 메모' : '';
      body = '<div class="hwp-editable" contenteditable="true" role="textbox" aria-label="연습 문서">' + text + '</div>';
    }
    const canSelect = ['auto', 'direct', 'profile', 'title', 'type', 'font', 'spacing', 'script'].includes(kind);
    documentWindow.innerHTML = '<div class="hwp-native-title">' + (kind === 'draft' ? 'K-에듀파인 · 기안문 작성' : '연습 문서 - 한글') + '</div>'
      + '<div class="hwp-native-tabs"><span>파일</span><b>편집</b><span>보기</span><span>입력</span><span>서식</span><span>쪽</span></div>'
      + '<div class="hwp-native-ribbon"><span>글자 모양</span><span>문단 모양</span><span>표</span><span>그림</span>'
      + (canSelect ? '<button type="button" id="hwp-select">' + (kind === 'script' ? '숫자 2 선택' : '전체 선택') + '</button>' : '') + '</div>'
      + '<div class="hwp-native-workspace"><div class="hwp-paper ' + (kind === 'paper' ? 'hwp-portrait' : '') + '">' + body + '</div></div>'
      + '<div class="hwp-native-status">1 / 1쪽　　문자 입력</div>';
    documentWindow.querySelector('#hwp-select')?.addEventListener('click', selectDocument);
    const textarea = documentWindow.querySelector('textarea');
    textarea?.addEventListener('select', () => { state.selected = selectedText(); syncSelection(); });
    const editable = documentWindow.querySelector('.hwp-editable');
    editable?.addEventListener('focus', () => { state.cursor = true; syncSelection(); });
    editable?.addEventListener('keyup', saveRange);
    editable?.addEventListener('pointerup', saveRange);
    editable?.addEventListener('input', inputProgress);
    if (kind === 'spacing') {
      const observer = new ResizeObserver(() => fitSpacingExample());
      observer.observe(editable);
      state.resizeObserver = observer;
      document.fonts.ready.then(() => {
        if (state.kind === 'spacing' && editable.isConnected) { state.spacingWidth = 0; fitSpacingExample(); }
      });
    }
    const table = documentWindow.querySelector('table');
    if (kind === 'cell-clean') table.querySelectorAll('td').forEach((cell) => {
      cell.style.whiteSpace = 'pre-wrap'; cell.style.backgroundColor = '#fff2cc'; cell.style.color = '#bb3030';
    });
    let anchor;
    function selectCells(first, last) {
      const r1 = Math.min(+first.dataset.row, +last.dataset.row);
      const r2 = Math.max(+first.dataset.row, +last.dataset.row);
      const c1 = Math.min(+first.dataset.column, +last.dataset.column);
      const c2 = Math.max(+first.dataset.column, +last.dataset.column);
      state.cells = new Set([...table.querySelectorAll('td')].filter((cell) => +cell.dataset.row >= r1 && +cell.dataset.row <= r2
        && +cell.dataset.column >= c1 && +cell.dataset.column <= c2).map((cell) => cell.dataset.cell));
      syncSelection();
    }
    table?.addEventListener('pointerdown', (event) => {
      const cell = event.target.closest('td');
      if (!cell || event.button !== 0) return;
      anchor = cell;
      table.setPointerCapture(event.pointerId);
      selectCells(cell, cell);
    });
    table?.addEventListener('pointermove', (event) => {
      const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest('td');
      if (anchor && cell && table.contains(cell)) selectCells(anchor, cell);
    });
    table?.addEventListener('lostpointercapture', () => { anchor = null; });
    table?.addEventListener('keydown', (event) => {
      if (event.key === 'F5' || (event.ctrlKey && event.key.toLowerCase() === 'a')) {
        event.preventDefault();
        const cells = table.querySelectorAll('td');
        selectCells(cells[0], cells[cells.length - 1]);
      }
    });
    function saveRange() {
      const selection = window.getSelection();
      if (selection.rangeCount && editable.contains(selection.anchorNode)) {
        state.range = selection.getRangeAt(0).cloneRange();
        state.selected = !selection.isCollapsed;
        syncSelection();
      }
    }
  }
  function fitSpacingExample() {
    const text = documentWindow.querySelector('.spacing-text');
    if (!text || Math.abs((state.spacingWidth || 0) - text.clientWidth) < 1) return;
    const width = text.clientWidth;
    if (!width) return;
    state.spacingWidth = width;
    const context = document.createElement('canvas').getContext('2d');
    const style = getComputedStyle(text);
    context.font = style.fontSize + ' ' + style.fontFamily;
    const samples = [];
    for (const source of ['의견을 모아', '현장 의견을 모아', '부서 협의를 거쳐', '현장 의견을 수렴하여', '학교별 개선 요구를 조사하여', '교직원의 의견을 모아', '담당 부서와 협의하여',
      '학교별 현장 의견을 수렴하고 관계 부서의 검토를 거쳐', '학교별 현장 의견을 수렴하고 관계 부서의 검토 결과를 종합하여']) {
      for (const details of ['', '개선 사항을 ', '업무 특성과 개선 사항을 ', '실제 운영상의 개선 사항을 ', '업무 절차와 현장 요구를 ', '제출된 의견과 개선 요구를 ', '학교별 업무 특성과 현장 개선 요구를 ',
        '현장에 공통으로 적용할 개선 사항과 지원 방안을 ', '학교별 업무 특성과 현장의 개선 요구를 종합한 지원 방안을 ']) {
        for (const target of ['계획에', '추진 계획에', '운영 계획에', '다음 연도 운영 계획에', '학교 지원 계획에', '세부 추진 계획에', '업무 개선 계획에']) {
          const sentence = source + ' ' + details + target + ' 반영함';
          const size = context.measureText(sentence).width;
          if (size > width + 2 && size < width + 27) samples.push({ sentence, size });
        }
      }
    }
    const sample = samples.sort((a, b) => a.size - b.size)[0];
    text.textContent = sample?.sentence || '현장 의견을 수렴하여 학교별 업무 특성과 개선 사항을 다음 연도 운영 계획에 반영함';
    const size = sample?.size || context.measureText(text.textContent).width;
    text.style.setProperty('--spacing-adjustment', -Math.min(1.2, (size - width + 5) / (text.textContent.length - 1)) + 'px');
  }
  function nativeStyle(item) {
    const node = document.createElement('div');
    node.className = 'native-style';
    node.dataset.style = item.id;
    const slot = '<p data-style-slot contenteditable="true" tabindex="0" role="textbox" aria-label="서식 내용"><br></p>';
    const cell = (body = slot, attributes = '') => '<td ' + attributes + '>' + body + '</td>';
    const grid = (rows, attributes = '') => '<table class="native-style-table" ' + attributes + '><tbody>' + rows.map((row) => '<tr>' + row + '</tr>').join('') + '</tbody></table>';
    if (item.title === '제목박스') node.innerHTML = grid([cell('<br>'), cell(slot), cell('<br>')], 'data-layout="title" aria-label="제목 양식"');
    else if (item.title === '붙임박스') node.innerHTML = grid([cell('붙임') + cell('<br>') + cell(slot)], 'data-layout="attachment" aria-label="붙임 양식"');
    else if (item.title === '소제목박스') node.innerHTML = grid([cell('1') + cell('<br>') + cell(slot)], 'data-layout="section" aria-label="소제목 양식"');
    else if (item.title === '표박스') node.innerHTML = grid(Array.from({ length: 3 }, () => Array.from({ length: 4 }, () => cell()).join('')), 'data-layout="grid" aria-label="표 양식"');
    else if (item.title === '참고박스') node.innerHTML = '<fieldset class="native-reference"><legend>&lt; 참고 &gt;</legend>' + slot + '</fieldset>';
    else if (/^[34]단계절차박스$/.test(item.title)) {
      const count = +item.title[0];
      node.innerHTML = grid([
        Array.from({ length: count }, (_, i) => cell((i + 1) + '단계') + (i < count - 1 ? cell('▶', 'rowspan="2" class="native-process-arrow"') : '')).join(''),
        Array.from({ length: count }, () => cell('<p data-style-slot contenteditable="true" tabindex="0" role="textbox" aria-label="단계 내용">· </p><p>· </p><p>· </p>')).join(''),
      ], 'data-layout="process" aria-label="' + count + '단계 절차 양식"');
    } else return null;
    return node;
  }
  function insertContent(node) {
    const editable = documentWindow.querySelector('.hwp-editable');
    if (state.range && editable.contains(state.range.commonAncestorContainer)) {
      state.range.deleteContents();
      state.range.insertNode(node);
      state.range.setStartAfter(node);
      state.range.collapse(true);
    } else editable.append(node);
  }
  function report(settings) {
    const paper = documentWindow.querySelector('.hwp-paper');
    paper.innerHTML = '<h3 class="report-native-title">2026년 교직원 연수 운영 계획</h3>'
      + '<h4 class="report-native-section"><b>1</b>추진 목적</h4><p class="native-body">- 교직원의 업무 역량 강화</p>'
      + '<h4 class="report-native-section"><b>2</b>연수 개요</h4><p>가. 대상</p><p class="native-body">- 소속 교직원</p><small>※ 세부 일정은 추후 안내</small>';
    const roles = settings.auto_format.roles;
    paper.style.fontFamily = roles.body.font;
    paper.querySelectorAll('.native-body').forEach((node) => { node.style.fontSize = roles.body.size + 'pt'; });
    paper.querySelector('h3').style.fontFamily = roles.document_title.font;
  }
  function sampleFiles() {
    return new Promise((resolve) => {
      pendingFiles?.([]);
      pendingFiles = resolve;
      const picker = document.createElement('div');
      picker.className = 'practice-file-picker';
      picker.innerHTML = '<strong>그림 선택</strong><div class="practice-file-options">' + catalogs.samples.map((src, i) =>
        '<label><img alt="예시 그림 ' + (i + 1) + '" src="' + src + '"><span><input type="checkbox" value="' + i + '">예시 그림 ' + (i + 1) + '</span></label>').join('') + '</div><div><button type="button" data-file-cancel>취소</button><button type="button" data-file-open>열기</button></div>';
      documentWindow.append(picker);
      picker.addEventListener('change', () => step(3));
      picker.querySelector('[data-file-open]').addEventListener('click', () => {
        const files = [...picker.querySelectorAll('input:checked')].map((input) => 'sample:' + input.value);
        if (!files.length) return;
        pendingFiles = null;
        picker.remove();
        resolve(files);
        setView('app');
      });
      picker.querySelector('[data-file-cancel]').addEventListener('click', () => {
        pendingFiles = null; picker.remove(); resolve([]);
      });
      setView('document');
      step(3);
      say('그림 두 개를 선택하고 ‘열기’를 누르세요.');
    });
  }
  async function perform(command, args) {
    const paper = documentWindow.querySelector('.hwp-paper');
    const editable = documentWindow.querySelector('.hwp-editable');
    const table = documentWindow.querySelector('.hwp-demo-table');
    const selected = [...documentWindow.querySelectorAll('[data-cell]')].filter((cell) => state.cells.has(cell.dataset.cell));
    const finish = (message, data = {}) => { state.complete = true; step(walkthroughs[state.kind].length - 1); say(message, true); setView('document'); return ok(data, message); };
    if (command === 'set_target_mode') { state.mode = args.mode; return ok({}, '적용 대상을 바꿨습니다.'); }
    if (command === 'settings_save') {
      state.settings = args.settings;
      if (state.kind === 'favorite') return ok();
      if (state.kind === 'title' && state.titleRegistered) return finish('등록한 문서제목 양식을 선택하고 설정을 저장했습니다.');
      say(state.kind === 'type' ? '설정을 저장했습니다. 창을 닫고 ‘본문’을 눌러 선택한 글에 적용하세요.' : '설정을 저장했습니다. 사용할 설정을 확인하고 자동 서식을 적용하세요.');
      return ok({}, '설정을 저장했습니다.');
    }
    if (command === 'card_favorite_toggle') {
      const favorites = state.favorites[args.kind];
      const i = favorites.indexOf(args.key);
      if (i < 0) favorites.push(args.key); else favorites.splice(i, 1);
      state.complete = true;
      step(walkthroughs[state.kind].length - 1);
      say(i < 0 ? '별이 채워지고 카드가 즐겨찾기 순서로 이동했습니다.' : '즐겨찾기를 해제했습니다.', true);
      return ok({ card_favorites: structuredClone(state.favorites) }, '즐겨찾기를 변경했습니다.');
    }
    if (command === 'clear_selection') { state.cells.clear(); syncSelection(); return ok({ selection: { active: false, label: '선택된 셀 없음' } }); }
    if (command === 'arrange_hwp_windows') {
      modal.classList.add('practice-arranged');
      return finish('한글과 JB에듀 폼을 나란히 배치했습니다.');
    }
    if (command === 'auto_format_report') {
      if (!selectedText()) return failure('한글에서 서식을 적용할 초안 전체를 먼저 블록 지정하세요.');
      report(args.settings);
      return finish('제목·본문·참고 서식을 적용했습니다. 원문과 결과를 비교하세요.');
    }
    if (command === 'auto_title_template_analyze') {
      if (!selectedText()) return failure('선택한 텍스트를 읽지 못했습니다. 제목 양식을 블록 지정하세요.');
      const item = catalogs.styles[0];
      say('인식한 제목 글자와 이름을 확인한 뒤 ‘이 제목 양식 저장’을 누르세요.');
      return ok({ role: args.role, pending_id: 'practice-title', preview: item.preview, title_sample: '교직원 연수 운영 계획', number_sample: '', segments: [], combined: true });
    }
    if (command === 'auto_title_template_register') {
      state.titleRegistered = true;
      say('제목 양식을 등록했습니다. 설정창 아래의 ‘저장’을 누르세요.');
      return ok({
        item: { id: 'practice-title', key: 'auto-title-user:practice-title', title: args.title, role: args.role, source: 'user', user_item: true, preview: catalogs.styles[0].preview },
      }, '제목 양식을 등록했습니다.');
    }
    if (command === 'auto_title_template_discard') return ok();
    if (command === 'auto_format_apply_role' || command === 'apply_charshape' || command === 'spacing_cleanup' || command === 'spacing_reset') {
      if (!state.selected) return failure('한글에서 적용할 글자를 먼저 블록 지정하세요.');
      if (command === 'spacing_cleanup' || command === 'spacing_reset') {
        editable.classList.toggle('spacing-applied', command === 'spacing_cleanup');
        return finish(command === 'spacing_cleanup' ? '문장과 문단 폭은 그대로 두고 글자 간격만 줄였습니다. ‘자간 초기화’를 누르면 원래 줄바꿈으로 돌아갑니다.' : '글자 간격을 0으로 복원했습니다.');
      } else if (args.script_mode) {
        const node = document.createElement(args.script_mode === 'super' ? 'sup' : args.script_mode === 'sub' ? 'sub' : 'span');
        node.textContent = state.range?.toString() || '2';
        insertContent(node);
        state.range = document.createRange();
        state.range.selectNode(node);
      } else if (command === 'auto_format_apply_role' && ['document_title', 'title', 'subtitle', 'subsubtitle', 'reference'].includes(args.role)) {
        const style = args.settings.auto_format.roles[args.role];
        const node = document.createElement(args.role === 'document_title' ? 'h3' : args.role === 'title' ? 'h4' : 'p');
        node.className = args.role === 'document_title' ? 'report-native-title' : args.role === 'title' ? 'report-native-section' : '';
        const text = state.range?.toString() || editable.textContent;
        const markers = { number_dot: '1. ', hangul_dot: '가. ', number_paren: '1) ', reference: '※ ', none: '', roman_upper: 'I. ', roman_lower: 'i. ' };
        node.textContent = (style.marker === 'custom' ? style.custom_marker + ' ' : markers[style.marker] || '') + text;
        if (args.role === 'title') {
          const badge = document.createElement('b');
          badge.textContent = (markers[style.marker] || '1').trim().replace(/[.)]$/, '');
          const body = document.createElement('span');
          body.textContent = text;
          node.replaceChildren(badge, body);
        }
        node.style.fontFamily = style.font;
        node.style.fontSize = style.size + 'pt';
        node.style.fontWeight = style.bold ? '700' : '400';
        insertContent(node);
      } else {
        const style = command === 'auto_format_apply_role' ? args.settings.auto_format.roles[args.role] : args;
        const node = document.createElement('span');
        const prefix = command === 'auto_format_apply_role' && args.role === 'body'
          ? style.marker === 'none' ? '' : style.marker === 'custom' ? style.custom_marker + ' ' : '- ' : '';
        node.textContent = prefix + (state.range?.toString() || editable.textContent);
        if (style.font_size_pt || style.size) node.style.fontSize = (style.font_size_pt || style.size) + 'pt';
        node.style.fontFamily = style.font_name || style.font || '';
        if (style.bold !== undefined) node.style.fontWeight = style.bold ? '700' : '400';
        if (style.font_color_rgb) node.style.color = 'rgb(' + style.font_color_rgb.join(',') + ')';
        insertContent(node);
        if (command === 'apply_charshape') {
          state.range = document.createRange();
          state.range.selectNode(node);
        }
      }
      if (command === 'auto_format_apply_role') { state.selected = false; state.range = null; }
      return finish('선택한 글자에 적용했습니다. 다른 글자는 그대로입니다.');
    }
    if (command === 'table_tool' || command === 'object_treat_as_char' || command === 'start_table_drawing') {
      if (!selected.length) return failure('먼저 한글 표에서 셀 범위를 선택하세요.');
      const id = args.action_id || '';
      const allCells = [...table.querySelectorAll('td,th')];
      if (id === '전체바깥선굵게변경하기') table.classList.add('table-outer-bold');
      else if (id === '기본선변경하기') {
        table.classList.remove('table-outer-bold');
        table.style.border = '';
        allCells.forEach((cell) => { cell.style.border = '1px solid #424c5d'; });
      }
      else if (id === '위쪽바깥선굵게변경하기') table.style.borderTop = '3px solid #222';
      else if (id === '아래쪽바깥선굵게변경하기') table.style.borderBottom = '3px solid #222';
      else if (id === '아래쪽바깥선이중선변경하기') table.style.borderBottom = '4px double #222';
      else if (id === '왼쪽바깥선없애기') table.querySelectorAll('tr > :first-child').forEach((cell) => { cell.style.borderLeft = '0'; });
      else if (id === '오른쪽바깥선없애기') table.querySelectorAll('tr > :last-child').forEach((cell) => { cell.style.borderRight = '0'; });
      else if (id === '내부세로선없애기') table.querySelectorAll('tr').forEach((row) => [...row.children].forEach((cell, i, cells) => {
        if (i) cell.style.borderLeft = '0';
        if (i < cells.length - 1) cell.style.borderRight = '0';
      }));
      else if (id === '내부가로선없애기') {
        const rows = [...table.rows];
        rows.forEach((row, i) => [...row.cells].forEach((cell) => {
          if (i) cell.style.borderTop = '0';
          if (i < rows.length - 1) cell.style.borderBottom = '0';
        }));
      }
      else if (id === '표전체선없애기') { table.classList.remove('table-outer-bold'); allCells.forEach((cell) => { cell.style.border = '0'; }); }
      else if (id.includes('하늘색')) selected.forEach((cell) => { cell.style.backgroundColor = '#dbe8fa'; });
      else if (id.includes('연한노랑')) selected.forEach((cell) => { cell.style.backgroundColor = '#fff5cd'; });
      else if (id.includes('배경색없애기')) selected.forEach((cell) => { cell.style.backgroundColor = ''; });
      else if (id.includes('열너비같게')) table.style.tableLayout = 'fixed';
      else if (id.includes('행높이같게')) table.querySelectorAll('tr').forEach((row) => { row.style.height = '54px'; });
      else if (id === '한줄로입력설정' || id === '한줄로입력해제') selected.forEach((cell) => { cell.style.whiteSpace = id.endsWith('설정') ? 'nowrap' : 'normal'; });
      else if (id === '제목셀설정' || id === '제목셀해제') selected.forEach((cell) => { cell.dataset.titleCell = String(id.endsWith('설정')); });
      else if (id === '빨간색강조선넣기') table.style.border = '3px solid #d32d2d';
      else return failure('이 체험에서는 ‘전체 바깥선 굵게’, ‘하늘색 배경 채우기’, ‘열 너비 같게’를 적용해 보세요.');
      return finish('선택한 표 범위에 적용했습니다.');
    }
    if (command === 'cell_text_action' || command === 'cell_clean_spaces' || command === 'cell_cleanup_excel') {
      if (!selected.length) return failure('한글 표에서 적용할 셀을 드래그하세요.');
      for (const cell of selected) {
        if (command !== 'cell_text_action') {
          cell.textContent = cell.textContent.trim();
          if (command === 'cell_cleanup_excel') { cell.style.backgroundColor = ''; cell.style.color = '#222'; }
          continue;
        }
        if (args.action === 'prefix') cell.prepend(args.value);
        if (args.action === 'suffix') cell.append(args.value);
        if (args.action === 'find_replace' && args.value) cell.textContent = cell.textContent.split(args.value).join(args.replacement || '');
      }
      return finish(selected.length + '개 셀을 수정했습니다. 선택하지 않은 셀은 그대로입니다.');
    }
    if (command === 'pick_files') return ok({ paths: await sampleFiles() }, '');
    if (command === 'insert_cell_images' || command === 'refit_cell_images') {
      if (!selected.length) return failure('그림을 넣을 셀을 먼저 선택하세요.');
      const paths = args.paths || selected.map((_, i) => 'sample:' + (i % 2));
      paths.slice(0, selected.length).forEach((path, i) => {
        const img = document.createElement('img');
        img.src = catalogs.samples[Number(path.split(':')[1])];
        img.alt = '삽입한 예시 그림';
        img.className = 'hwp-cell-image';
        img.style.objectFit = args.size_mode === 'stretch_to_cell' ? 'fill' : 'contain';
        if (args.size_mode === 'fit_width') img.style.height = 'auto';
        selected[i].replaceChildren(img);
      });
      return finish('선택한 순서대로 각 셀에 그림을 넣었습니다.');
    }
    if (command === 'insert_kedufine_form') {
      if (state.mode !== 'kedufine' || !state.cursor) return failure('기안창 본문을 클릭하고 K-에듀파인 기안창 모드로 전환하세요.');
      const item = catalogs.forms.find((item) => item.key === args.item_key);
      if (!item) return failure('양식을 다시 선택하세요.');
      const node = document.createElement('div');
      node.textContent = Array.isArray(item.body) ? item.body.join('\n') : item.body;
      node.className = 'kedufine-inserted';
      insertContent(node);
      return finish('본문에 기안문 예시를 넣었습니다. 위쪽 제목은 그대로입니다.');
    }
    if (command === 'insert_character' || command === 'compose_characters') {
      if (!state.cursor) return failure('한글 문서에서 넣을 위치를 먼저 클릭하세요.');
      const node = document.createElement('span');
      node.textContent = args.value;
      if (command === 'compose_characters') node.className = args.shape === 'square' ? 'native-compose-square' : 'native-compose-circle';
      insertContent(node);
      return finish('현재 입력 위치에 문자를 넣었습니다.');
    }
    if (command === 'user_save_symbol_group') {
      const result = finish('내 문자표를 추가했습니다. 새로 생긴 문자표를 확인하세요.');
      setView('app');
      return result;
    }
    if (command === 'insert_picture_symbol') {
      if (!state.cursor) return failure('한글에서 넣을 위치를 먼저 클릭하세요.');
      const item = catalogs.symbols.flatMap((group) => group.items).find((item) => item.key === args.item_key);
      if (!item) return failure('심볼을 다시 선택하세요.');
      const image = document.createElement('img');
      image.src = item.preview;
      image.alt = item.title;
      image.className = 'native-style-preview';
      insertContent(image);
      return finish('커서 위치에 심볼을 넣었습니다.');
    }
    if (command === 'insert_style' || command === 'insert_form') {
      if (!state.cursor && !(command === 'insert_form' && args.mode === 'new_document')) return failure('한글에서 넣을 위치를 먼저 클릭하세요.');
      const node = document.createElement('div');
      node.innerHTML = '<h3 class="report-native-title">제목</h3><p>1. 추진 배경</p><p>2. 주요 내용</p>';
      if (command === 'insert_style') {
        const item = catalogs.styles.find((item) => item.key === args.style_key);
        const structure = item && nativeStyle(item);
        if (!structure) return failure('삽입할 서식 카드를 다시 선택하세요.');
        insertContent(structure);
        const paragraph = document.createElement('p');
        paragraph.innerHTML = '<br>';
        structure.after(paragraph);
        state.range = document.createRange();
        state.range.selectNodeContents(paragraph);
        state.range.collapse(true);
        state.complete = false;
        step(2, '왼쪽에 삽입된 서식의 빈 칸을 클릭하고 제목이나 내용을 입력해 보세요.');
        setView('document');
        return ok({}, '커서 위치에 편집 가능한 서식을 삽입했습니다.');
      }
      if (args.mode === 'new_document') {
        editable.replaceChildren();
        documentWindow.querySelector('.hwp-native-title').textContent = '새 문서 - 한글';
      }
      insertContent(node);
      return finish(args.mode === 'new_document' ? '새 문서로 양식을 열었습니다.' : '커서 위치에 삽입했습니다.');
    }
    if (command === 'apply_page') {
      const item = catalogs.pages.find((item) => item.key === args.item_key);
      paper.classList.toggle('hwp-landscape', item?.orientation === 'landscape');
      paper.classList.toggle('hwp-portrait', item?.orientation !== 'landscape');
      return finish((args.scope === 'page' ? '현재 페이지' : '문서 전체') + '에 선택한 편집용지를 적용했습니다.');
    }
    return failure('현재 체험의 안내 순서에 따라 진행하세요. 이 화면에서는 실제 파일이나 설정이 변경되지 않습니다.');
  }
  function start(kind) {
    state?.resizeObserver?.disconnect();
    pendingFiles?.([]);
    pendingFiles = null;
    state = { kind, selected: false, cursor: false, range: null, cells: new Set(), mode: kind === 'draft' ? 'kedufine' : 'hwp', complete: false,
      favorites: { style: [], form: [], kedufine_form: [], symbol: [], page: [] } };
    modal.dataset.kind = kind;
    guide.innerHTML = '<ol id="practice-steps" aria-label="체험 순서"></ol><p id="practice-instruction" role="status" aria-live="polite"></p>';
    document.querySelector('#practice-title').textContent = scenarios[kind][0];
    modal.classList.remove('practice-arranged');
    makeDocument();
    const frame = document.createElement('iframe');
    frame.id = 'practice-live-app';
    frame.title = 'JB에듀 폼 연습 화면';
    frame.name = 'jbe-practice-' + kind;
    frame.setAttribute('sandbox', 'allow-scripts allow-forms');
    frame.srcdoc = appSource;
    appFrame = frame;
    mount.replaceChildren(frame);
    setView(kind === 'favorite' || kind === 'arrange' ? 'app' : 'document');
    say(scenarios[kind][1]);
    step(0);
  }
  window.addEventListener('message', async (event) => {
    if (event.source !== appFrame?.contentWindow || event.data?.source !== 'jbe-practice-app' || !modal.open) return;
    const frame = appFrame;
    const data = event.data;
    if (data.close) { modal.close(); return; }
    if (data.ready) { syncSelection(); step(state.step); return; }
    if (data.navigation || data.field) {
      const action = data.navigation || data.field;
      const next = {
        images: { '셀 안에 맞춤': 2, '셀 너비에 맞춤': 2, '셀 크기에 맞춤': 2, '셀에 그림 넣기': 3 },
        cell: { '추가할 문자': 2 },
        'cell-replace': { '바꿀 내용': 2 },
        compose: { '글자 겹치기': 2, '글자': 3 },
        'user-character': { '내 문자표 추가': 1, '문자·기호': 2 },
        type: { '서식 설정': 2, '본문 글자 크기': 3, '저장': 4 },
        title: { '서식 설정': 2, '기존 제목 양식 추가': 3, '이 제목 양식 저장': 4 },
        profile: { '사용할 설정': 2 },
      }[state.kind]?.[action];
      if (!state.complete && next !== undefined && next > state.step) {
        const detail = {
          images: next === 3 ? '그림 선택창에서 예시 그림 두 개를 체크한 뒤 ‘열기’를 누르세요.' : '오른쪽의 ‘셀에 그림 넣기’ 버튼을 누르세요.',
          cell: '오른쪽의 ‘내용 뒤에 추가’ 버튼을 누르세요.',
          'cell-replace': '오른쪽의 ‘찾아바꾸기 실행’ 버튼을 누르세요.',
          compose: next === 2 ? '‘글자’에 30을 입력하고 원 또는 네모 모양을 고르세요.' : '겹친 글자 미리보기를 확인한 뒤 ‘삽입’을 누르세요.',
          'user-character': next === 1 ? '문자표 이름과 사용할 문자·기호를 입력하세요.' : '창 아래 ‘저장’ 버튼을 누르세요.',
          type: next === 2 ? '설정창에서 ‘본문 글자 크기’ 값을 바꾸세요.' : next === 3 ? '설정창 아래 ‘저장’을 누르세요.' : '오른쪽 ‘본문’ 버튼을 눌러 선택한 글에 적용하세요.',
          title: next === 2 ? '문서제목 영역의 ‘기존 제목 양식 추가’를 누르세요.' : next === 3 ? '이름을 입력하고 ‘이 제목 양식 저장’을 누르세요.' : '설정창 아래 ‘저장’을 눌러 마무리하세요.',
          profile: '선택한 설정을 확인하고 ‘전체 서식 자동 지정하기’를 누르세요.',
        }[state.kind];
        step(next, detail);
      }
      return;
    }
    if (!Number.isInteger(data.id)) return;
    let response;
    try { response = await perform(data.command, data.args || {}); }
    catch { response = failure('체험을 다시 시작해 주세요. 실제 문서는 변경되지 않았습니다.'); }
    if (frame === appFrame) {
      frame.contentWindow.postMessage({ source: 'jbe-practice-host', id: data.id, response }, '*');
      if (!response.ok) say(response.message);
    }
  });
  launch.addEventListener('click', () => {
    const kind = launch.dataset.practiceOpen;
    if (!scenarios[kind]) return;
    opener = launch;
    start(kind);
    modal.showModal();
    close.focus({ preventScroll: true });
  });
  reset.addEventListener('click', () => start(state.kind));
  close.addEventListener('click', () => modal.close());
  modal.addEventListener('close', () => {
    pendingFiles?.([]);
    pendingFiles = null;
    appFrame = null;
    coach.clear();
    state?.resizeObserver?.disconnect();
    mount.replaceChildren();
    opener?.focus({ preventScroll: true });
  });
  modal.querySelectorAll('[data-practice-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.practiceView)));
})();
