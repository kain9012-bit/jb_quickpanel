// This bridge serves the real frontend inside an offline sandbox, never COM.
function startPracticeApp(fixture) {
  const scenario = window.name.replace('jbe-practice-', '');
  const settings = structuredClone(fixture.settings);
  settings.target_mode = scenario === 'draft' ? 'kedufine' : 'hwp';
  settings.tutorial_completed = true;
  settings.check_updates_on_startup = false;
  settings.global_hotkeys_enabled = false;
  settings.card_favorites = { style: [], form: [], kedufine_form: [], symbol: [], page: [] };
  settings.auto_format_profiles = [{
    id: 'default', name: '기본 설정', settings: structuredClone(settings.auto_format),
  }, {
    id: 'meeting', name: '회의 계획', settings: structuredClone(settings.auto_format),
  }];
  settings.auto_format_profiles[1].settings.roles.body.size = 14;
  settings.active_auto_format_profile = 'default';
  let selection = { active: false, dragging: false, label: '선택된 셀 없음', rows: 0, columns: 0 };
  let sequence = 0;
  const pending = new Map();
  let tutorialStep = 0;
  const hintTargets = {
    auto: { 1: ['button:전체 서식 자동 지정하기'] },
    direct: { 1: ['.direct-auto-format-grid button'] },
    arrange: { 0: ['[data-tour="window-layout"]'] },
    profile: { 1: ['.auto-format-profile-picker select'], 2: ['button:전체 서식 자동 지정하기'] },
    title: { 1: ['button:서식 설정'], 2: ['button:기존 제목 양식 추가'], 3: ['label:목록에 표시할 이름', 'button:이 제목 양식 저장'], 4: ['button:저장'] },
    type: { 1: ['button:서식 설정'], 2: ['input[aria-label="본문 글자 크기"]'], 3: ['button:저장'], 4: ['button:본문'] },
    'insert-style': { 1: ['.content-card:first-child'] },
    table: { 1: ['.table-tool-card:first-child'] },
    images: { 1: ['button:셀 안에 맞춤', 'button:셀 너비에 맞춤', 'button:셀 크기에 맞춤'], 2: ['button:셀에 그림 넣기'] },
    cell: { 1: ['label:추가할 문자'], 2: ['button:내용 뒤에 추가'] },
    'cell-clean': { 1: ['button:공백·배경색 한 번에 정리', 'button:불필요한 앞뒤 공백 제거'] },
    'cell-replace': { 1: ['label:찾을 내용', 'label:바꿀 내용'], 2: ['button:찾아바꾸기 실행'] },
    font: { 1: ['.text-colors button', '.font-list button'] },
    spacing: { 1: ['button:자간 정리 1단계'] },
    script: { 1: ['button:위첨자'] },
    character: { 1: ['.character-group button:first-child'] },
    compose: { 1: ['button:글자 겹치기'], 2: ['label:글자'], 3: ['button:삽입'] },
    favorite: { 0: ['.favorite-toggle:first-of-type'] },
    'hwp-form': { 1: ['.content-card:first-child'] },
    draft: { 1: ['.kedufine-form-card:first-child'] },
    'user-character': { 0: ['button:내 문자표 추가'], 1: ['label:문자표 이름', 'label:문자·기호'], 2: ['button:저장'] },
    symbol: { 1: ['.symbol-card:first-child'] },
    paper: { 1: ['.page-apply-scope button', '.content-card:first-child'] },
  };
  const coach = createPracticeCoach(document.body, document.documentElement);
  const hintCaptions = {
    auto: { 1: '이 버튼을 클릭하세요' },
    direct: { 1: '적용할 서식을 클릭하세요' },
    arrange: { 0: '나란히 배치 버튼을 클릭하세요' },
    profile: { 1: '사용할 설정을 고르세요', 2: '이 버튼을 클릭하세요' },
    title: { 1: '서식 설정을 클릭하세요', 2: '제목 양식 추가를 클릭하세요', 3: '이름을 입력하고 저장하세요', 4: '설정을 저장하세요' },
    type: { 1: '서식 설정을 클릭하세요', 2: '본문 글자 크기를 바꾸세요', 3: '설정을 저장하세요', 4: '본문 버튼을 클릭하세요' },
    'insert-style': { 1: '예시로 제목박스를 클릭하세요' },
    table: { 1: '표 작업 카드를 클릭하세요' },
    images: { 1: '그림 맞춤 방식을 고르세요', 2: '이 버튼을 클릭하세요' },
    cell: { 1: '여기에 %를 입력하세요', 2: '내용 뒤에 추가를 클릭하세요' },
    'cell-clean': { 1: '정리할 범위를 선택하세요' },
    'cell-replace': { 1: '찾을 글자와 바꿀 글자를 입력하세요', 2: '찾아바꾸기를 실행하세요' },
    font: { 1: '글자색이나 글꼴을 고르세요' },
    spacing: { 1: '자간 정리 1단계를 클릭하세요' },
    script: { 1: '위첨자를 클릭하세요' },
    character: { 1: '입력할 문자를 클릭하세요' },
    compose: { 1: '글자 겹치기를 클릭하세요', 2: '겹칠 글자 30을 입력하세요', 3: '삽입을 클릭하세요' },
    favorite: { 0: '이 별을 클릭하세요' },
    'hwp-form': { 1: '사용할 양식을 클릭하세요' }, draft: { 1: '기안문 양식을 클릭하세요' },
    'user-character': { 0: '내 문자표 추가를 클릭하세요', 1: '이름과 문자를 입력하세요', 2: '저장을 클릭하세요' },
    symbol: { 1: '사용할 심볼을 클릭하세요' }, paper: { 1: '적용할 편집용지를 클릭하세요' },
  };
  function updateHint() {
    document.querySelectorAll('[data-practice-hint]').forEach((node) => node.removeAttribute('data-practice-hint'));
    const nodes = [];
    for (const target of hintTargets[scenario]?.[tutorialStep] || []) {
      const split = target.indexOf(':');
      const kind = target.slice(0, split);
      const matches = ['button', 'label'].includes(kind)
        ? [...document.querySelectorAll(kind)].filter((node) => node.textContent.trim() === target.slice(split + 1))
        : [...document.querySelectorAll(target)];
      matches.filter((node) => node.getClientRects().length && !node.disabled).forEach((node) => {
        node.setAttribute('data-practice-hint', '');
        nodes.push(node.matches('label') ? node.querySelector('input,textarea,select') || node : node);
      });
    }
    coach.set(nodes, hintCaptions[scenario]?.[tutorialStep] || '이곳에서 진행하세요', tutorialStep + 1);
  }
  function ask(command, args) {
    return new Promise((resolve) => {
      const id = ++sequence;
      pending.set(id, resolve);
      parent.postMessage({ source: 'jbe-practice-app', id, command, args }, '*');
    });
  }
  window.addEventListener('message', (event) => {
    if (event.source !== parent || event.data?.source !== 'jbe-practice-host') return;
    if (event.data.selection) selection = event.data.selection;
    if (event.data.refreshHints) updateHint();
    if (Number.isInteger(event.data.tutorialStep)) { tutorialStep = event.data.tutorialStep; updateHint(); }
    const resolve = pending.get(event.data.id);
    if (resolve) { pending.delete(event.data.id); resolve(event.data.response); }
  });
  const ok = (data = {}, message = '') => ({ ok: true, message, data });
  const editKinds = ['table', 'images', 'cell', 'cell-clean', 'cell-replace', 'font', 'spacing', 'script'];
  const targetTab = editKinds.includes(scenario) ? '편집도구'
    : ['character', 'compose', 'user-character'].includes(scenario) ? '문자표'
    : ['favorite', 'symbol'].includes(scenario) ? '심볼'
    : ['draft', 'hwp-form'].includes(scenario) ? '양식'
    : scenario === 'paper' ? '편집용지' : '서식';
  const subtab = ['table', 'images'].includes(scenario) ? '표 작업'
    : ['cell', 'cell-clean', 'cell-replace'].includes(scenario) ? '셀 정리'
    : ['font', 'spacing', 'script'].includes(scenario) ? '글자 작업' : '';
  const style = document.createElement('style');
  const hidden = [
    '.toolbar-actions > :not([data-tour="window-layout"])',
    '.content .user-action-bar:not(.character-actions)', '.favorite-toggle',
  ];
  if (scenario !== 'arrange') hidden.push('.toolbar-actions');
  if (scenario === 'images') hidden.push('.table-tool-grid');
  if (scenario === 'table') hidden.push('.picture-tool');
  if (['cell', 'cell-clean', 'cell-replace'].includes(scenario)) {
    const bands = scenario === 'cell' ? [1, 2, 3] : scenario === 'cell-replace' ? [1, 2, 4] : [3, 4];
    bands.forEach((band) => hidden.push('.cell-tools .tool-band:nth-of-type(' + (band + 1) + ')'));
  }
  if (['font', 'spacing', 'script'].includes(scenario)) {
    for (const group of ['text-colors', 'font-list', 'spacing-tools', 'script-tools']) {
      if (scenario === 'font' ? !['text-colors', 'font-list'].includes(group)
        : scenario === 'spacing' ? group !== 'spacing-tools' : group !== 'script-tools') hidden.push('.' + group);
    }
  }
  if (targetTab === '서식') {
    if (scenario !== 'insert-style') hidden.push('[data-tour="manual-styles"]', '[data-tour="user-style"]');
    if (scenario === 'insert-style' || scenario === 'arrange') hidden.push('.auto-format-group');
    if (['auto', 'profile'].includes(scenario)) hidden.push('.direct-auto-format-grid');
    if (scenario === 'auto') hidden.push('.auto-format-secondary');
    if (scenario === 'profile') hidden.push('.auto-format-secondary:not([data-tour="auto-format-settings"])', '.auto-format-template-section', '.auto-format-role-section');
    if (scenario === 'auto') hidden.push('.auto-format-profile-picker');
    if (scenario === 'direct') hidden.push('.auto-format-toolbar', '.auto-format-profile-picker');
    if (['title', 'type'].includes(scenario)) {
      hidden.push('.auto-format-primary', '.auto-format-stop', '.auto-format-secondary:not([data-tour="auto-format-settings"])', '.auto-format-profile-picker', '.auto-format-profile-section');
      if (scenario === 'title') hidden.push('.direct-auto-format-grid', '.auto-format-role-section');
      else hidden.push('.auto-format-template-section', '.auto-format-role-note');
    }
  }
  if (scenario === 'favorite') hidden.splice(hidden.indexOf('.favorite-toggle'), 1);
  if (['compose', 'user-character', 'character'].includes(scenario)) {
    hidden.push('.content .character-actions');
    if (scenario !== 'character') {
      hidden.pop();
      hidden.push('.character-group');
      const allowed = scenario === 'compose' ? '글자 겹치기' : '내 문자표 추가';
      document.documentElement.dataset.characterCommand = allowed;
    }
  }
  style.textContent = '#root{visibility:hidden}html.practice-configured #root{visibility:visible}'
    + '[hidden]{display:none!important}'
    + hidden.join(',') + '{display:none!important}'
    + '.tabs button:not(.is-active),.subtabs[aria-label="편집도구"] button:not(.is-active){pointer-events:none;opacity:.45}'
    + (scenario === 'user-character' ? '.character-group[data-character-group-id="practice-character"]{display:block!important}' : '')
    + '.direct-auto-format-grid{margin-top:12px}'
    + '[data-practice-hint]{outline:none!important}';
  document.head.append(style);
  let configured = false;
  let queued = false;
  const observer = new MutationObserver((records) => {
    if (records.every((record) => record.target instanceof Element && record.target.closest('.practice-coach-layer'))) return;
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      const tabs = [...document.querySelectorAll('.tabs button')];
      const target = tabs.find((button) => button.textContent.trim() === targetTab);
      if (!target) return;
      if (!target.classList.contains('is-active')) { target.click(); return; }
      if (subtab) {
        const button = [...document.querySelectorAll('.subtabs[aria-label="편집도구"] button')].find((button) => button.textContent.trim() === subtab);
        if (!button) return;
        if (!button.classList.contains('is-active')) { button.click(); return; }
      }
      for (const button of document.querySelectorAll('.tabs button,.subtabs[aria-label="편집도구"] button,.target-switch button')) {
        if (!button.classList.contains('is-active') && !button.disabled) button.disabled = true;
      }
      if (scenario === 'type') document.querySelectorAll('.auto-format-role-row').forEach((row) => {
        row.hidden = row.querySelector('input[aria-label="본문 글자 크기"]') === null;
      });
      if (scenario === 'type') document.querySelectorAll('.direct-auto-format-grid button').forEach((button) => {
        button.hidden = button.textContent.trim() !== '본문';
      });
      if (scenario === 'table') document.querySelectorAll('.table-tool-card').forEach((button) => {
        button.hidden = /표 그리기|글자처럼/.test(button.textContent);
      });
      if (['compose', 'user-character'].includes(scenario)) {
        const allowed = document.documentElement.dataset.characterCommand;
        document.querySelectorAll('.character-actions button').forEach((button) => { button.hidden = !button.textContent.includes(allowed); });
      }
      if (!configured) {
        configured = true;
        document.documentElement.classList.add('practice-configured');
        parent.postMessage({ source: 'jbe-practice-app', ready: true }, '*');
      }
      updateHint();
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
  document.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (button) parent.postMessage({ source: 'jbe-practice-app', navigation: button.textContent.trim() }, '*');
  });
  for (const name of ['input', 'change']) document.addEventListener(name, (event) => {
    const field = event.target.closest('input,textarea,select');
    if (!field || !field.value) return;
    const labelNode = field.closest('label')?.cloneNode(true);
    labelNode?.querySelectorAll('input,textarea,select').forEach((control) => control.remove());
    const label = field.getAttribute('aria-label') || labelNode?.textContent.trim();
    if (label) parent.postMessage({ source: 'jbe-practice-app', field: label }, '*');
  });
  window.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const close = [...document.querySelectorAll('.modal-header button[aria-label="닫기"]')].at(-1);
    event.preventDefault();
    event.stopPropagation();
    if (close) close.click();
    else parent.postMessage({ source: 'jbe-practice-app', close: true }, '*');
  }, true);
  window.__TAURI_INTERNALS__ = {
    metadata: { currentWindow: { label: 'main' }, currentWebview: { label: 'main' } },
    transformCallback: () => 1, unregisterCallback: () => {},
    invoke: async (command, args = {}) => {
      if (command === 'plugin:event|listen') return 1;
      if (command === 'window_layout_state') return { active: false };
      if (command === 'arrange_hwp_windows') {
        const response = await ask(command, args);
        if (!response.ok) throw Error(response.message);
        return { active: true, message: response.message };
      }
      if (command === 'cancel_auto_format') return { ok: true, message: '연습을 중지했습니다.' };
      if (command !== 'hwp_request') return null;
      const name = args.command;
      const data = args.args || {};
      if (name === 'settings_get') return ok({ settings, integration: { startup: false, start_menu: true }, had_user_data: false });
      if (name === 'integration_prepare') return ok({ integration: { startup: false, start_menu: true } });
      if (['status', 'connect', 'selection_state'].includes(name)) return ok({ connected: true, selection }, '연습 문서에 연결했습니다.');
      if (name === 'window_layout_target') return ok({ hwnd: 101, pid: 123 });
      if (name === 'set_target_mode') {
        settings.target_mode = data.mode;
        await ask(name, data);
        return ok({ connected: true, selection });
      }
      if (name === 'settings_save') {
        Object.assign(settings, data.changes);
        const response = await ask(name, { ...data, settings });
        return response.ok ? ok({ settings }, response.message) : response;
      }
      if (name === 'card_favorite_toggle') {
        const response = await ask(name, data);
        if (response.ok && response.data?.card_favorites) settings.card_favorites = response.data.card_favorites;
        return response;
      }
      if (name === 'user_save_symbol_group') {
        const item = { id: 'practice-character', title: data.title, chars: data.chars.split(/\s+/).filter(Boolean), user_item: true };
        fixture.character_catalog.groups.unshift(item);
        await ask(name, data);
        return ok({ item, character_group_order: [item.id, ...settings.character_group_order] }, '내 문자표를 추가했습니다.');
      }
      if (fixture[name]) return ok(fixture[name]);
      const response = await ask(name, { ...data, target_mode: settings.target_mode, settings });
      if (name === 'auto_title_template_register' && response.ok) {
        fixture.auto_title_template_catalog.items.push(response.data.item);
      }
      return response;
    },
  };
}
