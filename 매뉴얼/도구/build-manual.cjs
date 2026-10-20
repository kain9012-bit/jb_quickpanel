const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '../..');
const app = path.join(root, 'tauri-prototype');
const manual = path.join(root, '매뉴얼/원본');
const content = JSON.parse(fs.readFileSync(path.join(manual, 'content.json'), 'utf8'));
const version = JSON.parse(fs.readFileSync(path.join(app, 'package.json'), 'utf8')).version;
const output = path.join(root, '매뉴얼/배포본');
const htmlName = `JBEdu_FORM_사용자매뉴얼_v.${version}.html`;
const tracked = [
  'tauri-prototype/src/App.tsx', 'tauri-prototype/src/TutorialOverlay.tsx',
  'tauri-prototype/backend/server.py', 'tauri-prototype/backend/full_features.py',
  'tauri-prototype/backend/auto_format_runner.py', 'tauri-prototype/src/updater.ts',
  'src/jb_quickpanel/bridges/hwp_bridge.py', 'src/jb_quickpanel/bridges/wxs_bridge.py',
  'src/jb_quickpanel/features/auto_format.py', 'src/jb_quickpanel/features/untagged_report.py',
  'src/jb_quickpanel/features/auto_format_transaction.py',
  'src/jb_quickpanel/features/auto_format_settings.py', 'src/jb_quickpanel/services/user_backup.py',
  'src/jb_quickpanel/features/page_layout.py', 'src/jb_quickpanel/services/user_content.py',
  'src/jb_quickpanel/services/app_config.py',
  'tauri-prototype/src/index.css', 'tauri-prototype/src/favorites.ts',
  'src/jb_quickpanel/features/registry.py', 'config/config.json',
  'config/kedufine_forms.json', '매뉴얼/원본/content.json', '매뉴얼/원본/manual.css',
  '매뉴얼/원본/manual.js', '매뉴얼/원본/fixture.py', '매뉴얼/도구/build-manual.cjs',
  'tauri-prototype/CHANGELOG.md', 'tauri-prototype/src-tauri/src/lib.rs',
  'tauri-prototype/src-tauri/tauri.conf.json',
  'tauri-prototype/src-tauri/src/window_layout.rs',
  'tauri-prototype/src/backend.ts',
  'tauri-prototype/backend/tauri_hwp_bridge.py',
  'src/jb_quickpanel/features/object_properties.py',
  'src/jb_quickpanel/features/character_effects.py',
  'src/jb_quickpanel/features/cell_edges.py',
  'src/jb_quickpanel/features/line_spacing.py',
  'tauri-prototype/src/TableToolPreview.tsx',
];
function sourceFingerprint(text) {
  return crypto.createHash('sha256').update(text.replace(/\r\n/g, '\n')
    .replace(/v\.\d+\.\d+\.\d+/g, 'v.VERSION')).digest('hex');
}
function fingerprints() {
  return Object.fromEntries(tracked.map((file) => {
    return [file, sourceFingerprint(fs.readFileSync(path.join(root, file), 'utf8'))];
  }));
}
function reviewChanges(current, reviewed) {
  return Object.entries(current).filter(([file, hash]) => reviewed[file] !== hash).map(([file]) => file);
}
function validate() {
  const ids = content.sections.map((section) => section.id);
  if (new Set(ids).size !== ids.length) throw Error('Duplicate manual chapter IDs');
  for (const section of content.sections) {
    if (!section.title || !section.lead || !section.blocks?.length) throw Error(`Incomplete chapter: ${section.id}`);
  }
  if (!process.argv.includes('--reviewed')) {
    const reviewFile = path.join(manual, 'review.json');
    if (!fs.existsSync(reviewFile)) throw Error('매뉴얼 검토 기록이 없습니다. 내용 확인 후 manual:build -- --reviewed를 실행하세요.');
    const reviewed = JSON.parse(fs.readFileSync(reviewFile, 'utf8')).files;
    const changes = reviewChanges(fingerprints(), reviewed);
    if (changes.length) throw Error(`매뉴얼 검토가 필요한 변경입니다:\n${changes.join('\n')}\n설명 원본을 확인·수정한 뒤 manual:build -- --reviewed를 실행하세요.`);
  }
}
function playwrightModule() {
  const candidates = [process.env.MANUAL_PLAYWRIGHT_PATH, 'playwright',
    path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')];
  for (const candidate of candidates.filter(Boolean)) {
    try { return require(candidate); } catch (error) { if (error.code !== 'MODULE_NOT_FOUND') throw error; }
  }
  throw Error('매뉴얼 생성용 Playwright를 찾지 못했습니다. 매뉴얼/README.md의 실행 환경을 확인하세요.');
}
const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
function imageBlock(name, caption) {
  const encoded = fs.readFileSync(path.join(manual, 'assets', `${name}.png`)).toString('base64');
  return `<figure><button class="screen-button" type="button" aria-label="${escape(caption)} 확대"><img src="data:image/png;base64,${encoded}" alt="${escape(caption)}"></button><figcaption>${escape(caption)} <span class="screen-only">· 클릭하여 확대</span></figcaption></figure>`;
}
function bulletList(items) {
  return `<ul class="bullets">${items.map((item) => `<li>${escape(item)}</li>`).join('')}</ul>`;
}
function renderBlock(block, fixture) {
  switch (block.type) {
    case 'paragraph': return `<p>${escape(block.text)}</p>`;
    case 'note': return `<aside class="note"><strong>${escape(block.title)}</strong>${block.items ? bulletList(block.items) : `<p>${escape(block.text)}</p>`}</aside>`;
    case 'bullets': return `${block.title ? `<h3>${escape(block.title)}</h3>` : ''}${bulletList(block.items)}`;
    case 'example': return `<div class="example"><h3>${escape(block.title)}</h3><pre>${escape(block.text)}</pre></div>`;
    case 'steps': return `${block.title ? `<h3>${escape(block.title)}</h3>` : ''}<ol class="steps">${block.items.map((item, index) => `<li><span class="step-label">${index + 1}단계</span><span>${escape(item)}</span></li>`).join('')}</ol>`;
    case 'table': return `<div class="table-wrap"><table><thead><tr>${block.headers.map((cell) => `<th scope="col">${escape(cell)}</th>`).join('')}</tr></thead><tbody>${block.rows.map((row) => `<tr>${row.map((cell) => `<td>${escape(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    case 'image': return imageBlock(block.image, block.caption);
    case 'catalog': return `<h3>${escape(block.title)}</h3><ul class="catalog">${fixture.table_catalog.items.map((item) => `<li>${escape(item.title)}</li>`).join('')}</ul>`;
    case 'faq': return block.items.map(([question, answer]) => `<div class="faq"><h3>${escape(question)}</h3>${Array.isArray(answer) ? bulletList(answer) : `<p>${escape(answer)}</p>`}</div>`).join('');
    default: throw Error(`Unknown manual block: ${block.type}`);
  }
}
function chapterGroups(section) {
  const groups = [];
  for (const block of section.blocks) {
    if (block.type === 'subsection') { groups.push({ ...block, blocks: [...block.blocks] }); continue; }
    if (block.title && ['steps', 'bullets'].includes(block.type)) {
      groups.push({ title: block.title, blocks: [{ ...block, title: undefined }] });
    } else {
      if (!groups.length) groups.push({ blocks: [] });
      groups[groups.length - 1].blocks.push(block);
    }
  }
  return groups;
}
function renderChapterBlocks(section, index, fixture) {
  let subsection = 0;
  return chapterGroups(section).map((group) => {
    if (!group.title) return group.blocks.map((block) => renderBlock(block, fixture)).join('');
    const number = `${String(index + 1).padStart(2, '0')}.${++subsection}`;
    return `<section class="subsection" aria-labelledby="${section.id}-sub-${subsection}"><h3 id="${section.id}-sub-${subsection}"><span class="subsection-number">${number}</span>${escape(group.title)}</h3>${group.path ? `<p class="control-path">${escape(group.path)}</p>` : ''}${group.blocks.map((block) => renderBlock(block, fixture)).join('')}</section>`;
  }).join('');
}
function render(fixture, options = {}) {
  const pdf = options.pdfName || `JBEdu_FORM_사용자매뉴얼_v.${version}.pdf`;
  const logo = fs.readFileSync(path.join(app, 'src-tauri/icons/icon.ico')).toString('base64');
  const groups = [...new Set(content.sections.map((section) => section.group))];
  const groupLinks = groups.map((name) => `<a href="#${content.sections.find((section) => section.group === name).id}" data-group="${escape(name)}">${escape(name)}</a>`).join('');
  let group = '';
  const links = content.sections.map((section) => {
    const heading = group === section.group ? '' : `<div class="nav-group">${escape(section.group)}</div>`;
    group = section.group;
    return `${heading}<a href="#${section.id}"><span class="nav-number">${String(content.sections.indexOf(section) + 1).padStart(2, '0')}</span><span>${escape(section.title)}</span></a>`;
  }).join('');
  const body = content.sections.map((section, index) => `<section class="chapter" id="${section.id}" data-group="${escape(section.group)}"><span class="chapter-group screen-only">${escape(section.group)}</span><div class="chapter-heading"><span class="chapter-number">${String(index + 1).padStart(2, '0')}</span><h2>${escape(section.title)}</h2></div><p class="lead">${escape(section.lead)}</p>${section.image ? imageBlock(section.image, `${section.title} 화면`) : ''}${renderChapterBlocks(section, index, fixture)}</section>`).join('\n');
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="JBEdu FORM (JB에듀 폼) 사용자 매뉴얼"><title>${escape(content.title)} ${escape(content.subtitle)}</title><style>${fs.readFileSync(path.join(manual, 'manual.css'), 'utf8')}</style></head><body>
  <a href="#main" class="skip-link">본문 바로가기</a><div class="meta-strip"><div><span>사용자 매뉴얼</span></div></div><header class="site-header"><div class="topbar"><a class="brand" href="#overview"><img src="data:image/x-icon;base64,${logo}" width="36" height="36" alt=""><span><strong>${escape(content.title)}</strong><small>${escape(content.subtitle)}</small></span></a><button id="menu-toggle" class="mobile-menu" aria-expanded="false" aria-controls="manual-nav">목차</button><nav class="section-nav" aria-label="주요 영역">${groupLinks}</nav></div></header>
  <section class="intro" id="overview" aria-label="매뉴얼 안내"><div class="intro-inner"><div class="intro-content"><div class="intro-meta"><span>사용자 매뉴얼</span><span>v.${version}</span></div><h1>${escape(content.title)}</h1><p>일반 한글 · K-에듀파인 기안창 사용 안내</p><label class="search-wrap screen-only"><input id="manual-search" type="search" placeholder="기능·증상으로 찾기 (예: 자동 서식, 셀 정리)" aria-label="매뉴얼 검색"><button id="clear-search" type="button" aria-label="검색어 지우기" hidden>×</button></label><p id="search-status" role="status" aria-live="polite"></p></div><div class="intro-actions screen-only"><span>매뉴얼 내려받기</span><a class="button primary-button" href="${escape(pdf)}" download>PDF 다운로드</a><button id="print-manual" type="button">매뉴얼 인쇄</button></div><div class="quick-links"><a href="#quick"><strong>빠른 시작</strong><span>AI 초안 자동 서식 →</span></a><a href="#cell"><strong>표 편집</strong><span>셀 내용 정리 →</span></a><a href="#settings"><strong>설정 관리</strong><span>백업·복원 →</span></a><a href="#help"><strong>도움말</strong><span>문제 해결 →</span></a></div><div class="print-only"><h2 class="print-toc-title">목차</h2><ol class="print-toc">${content.sections.map((section) => `<li><a href="#${section.id}">${escape(section.title)}</a></li>`).join('')}</ol></div></div></section>
  <div class="layout"><nav class="sidebar" id="manual-nav" aria-label="매뉴얼 목차"><div class="sidebar-title">전체 목차 <span>${content.sections.length}</span></div>${links}</nav><main id="main">${body}<footer>${escape(content.title)} 사용자 매뉴얼</footer></main></div>
  <dialog id="image-zoom" aria-labelledby="zoom-label"><div class="zoom-head"><strong id="zoom-label"></strong><button id="zoom-close" type="button">닫기</button></div><img id="zoom-image" alt="확대한 프로그램 화면"></dialog><script>${fs.readFileSync(path.join(manual, 'manual.js'), 'utf8')}</script></body></html>`;
}
function stageInstallResources(html, pdfPath, changelogPath, bundleRoot) {
  const manualDir = path.join(bundleRoot, 'manual');
  const supportDir = path.join(bundleRoot, 'support');
  fs.mkdirSync(manualDir, { recursive: true });
  fs.mkdirSync(supportDir, { recursive: true });
  fs.writeFileSync(path.join(manualDir, 'index.html'), html);
  fs.copyFileSync(pdfPath, path.join(manualDir, 'manual.pdf'));
  fs.copyFileSync(changelogPath, path.join(supportDir, 'CHANGELOG.md'));
}
async function captureScreens(browser, url, fixture) {
  const page = await browser.newPage({ viewport: { width: 620, height: 1000 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.addInitScript((data) => {
    let settings = structuredClone(data.settings);
    let characterGroups = structuredClone(data.character_catalog.groups);
    let pageItems = structuredClone(data.page_catalog.items);
    let layoutActive = false;
    try {
      const savedSettings = localStorage.getItem('jb-manual-settings');
      if (savedSettings) settings = JSON.parse(savedSettings);
      const savedGroups = localStorage.getItem('jb-manual-character-groups');
      if (savedGroups) characterGroups = JSON.parse(savedGroups);
      const savedPages = localStorage.getItem('jb-manual-pages');
      if (savedPages) pageItems = JSON.parse(savedPages);
    } catch {}
    const selection = { active: true, dragging: false, label: 'A1 ~ C3', rows: 3, columns: 3 };
    window.__manualRequests = [];
    window.__manualObjectSettings = [];
    window.__manualCharacterEffects = [];
    window.__manualLayoutCommands = [];
    window.__manualPageApplications = [];
    window.__TAURI_INTERNALS__ = {
      metadata: { currentWindow: { label: 'main' }, currentWebview: { label: 'main' } },
      transformCallback: () => 1, unregisterCallback: () => {},
      invoke: async (command, args = {}) => {
        if (command === 'plugin:event|listen') return 1;
        if (command === 'window_layout_state') return { active: layoutActive };
        if (command === 'arrange_hwp_windows') {
          window.__manualLayoutCommands.push(command);
          if (window.__manualFailLayout) {
            window.__manualFailLayout = false;
            throw Error('배치 테스트 실패');
          }
          layoutActive = true;
          return { active: layoutActive, message: '창 배치 테스트 완료' };
        }
        if (command !== 'hwp_request') return null;
        window.__manualRequests.push(args.command);
        if (args.command === 'apply_page') window.__manualPageApplications.push(args.args);
        if (args.command === 'object_treat_as_char') window.__manualObjectSettings.push(args.args.enabled);
        if (args.command === 'compose_characters' || (args.command === 'apply_charshape' && args.args.script_mode)) {
          window.__manualCharacterEffects.push({ command: args.command, args: args.args });
        }
        let result = {};
        if (args.command === 'settings_get') result = { settings, integration: { startup: false, start_menu: true }, had_user_data: false };
        else if (args.command === 'window_layout_target') result = { hwnd: 101, pid: 123 };
        else if (args.command === 'set_target_mode') { settings.target_mode = args.args.mode; result = { connected: true, selection }; }
        else if (args.command === 'settings_set') { settings = { ...settings, ...args.args.settings }; result = { settings }; }
        else if (args.command === 'settings_save') {
          if (window.__manualFailOrderSave && args.args.changes.character_group_order) {
            window.__manualFailOrderSave = false;
            return { ok: false, message: '문자표 순서를 저장하지 못했습니다.', data: {} };
          }
          settings = { ...settings, ...args.args.changes };
          localStorage.setItem('jb-manual-settings', JSON.stringify(settings));
          result = { settings };
        }
        else if (args.command === 'character_catalog') result = { groups: characterGroups };
        else if (args.command === 'page_catalog') result = { items: pageItems };
        else if (args.command === 'user_save_page') {
          if (window.__manualFailPageSave) {
            window.__manualFailPageSave = false;
            return { ok: false, message: '편집용지를 저장하지 못했습니다.', data: {} };
          }
          let item = pageItems.find((entry) => entry.id === args.args.item_id);
          if (!item) {
            const id = `page-${Date.now()}`;
            item = { id, key: `user:${id}`, source: 'user', user_item: true, preview: '' };
            pageItems.push(item);
          }
          Object.assign(item, { title: args.args.title, margins: args.args.margins, orientation: args.args.orientation });
          localStorage.setItem('jb-manual-pages', JSON.stringify(pageItems));
          result = { item };
        }
        else if (args.command === 'user_save_symbol_group') {
          let item = characterGroups.find((group) => group.id === args.args.item_id);
          if (item) {
            item.title = args.args.title;
            item.chars = args.args.chars.split(/\s+/).filter(Boolean);
          } else {
            const ranks = new Map(settings.character_group_order.map((id, index) => [id, index]));
            const order = characterGroups.map((group, index) => ({ id: group.id, rank: ranks.get(group.id) ?? ranks.size + index }))
              .sort((a, b) => a.rank - b.rank).map((group) => group.id);
            item = { id: `manual:user:${Date.now()}:${characterGroups.length}`, title: args.args.title, chars: args.args.chars.split(/\s+/).filter(Boolean), user_item: true };
            characterGroups.unshift(item);
            settings.character_group_order = [item.id, ...order];
          }
          localStorage.setItem('jb-manual-character-groups', JSON.stringify(characterGroups));
          localStorage.setItem('jb-manual-settings', JSON.stringify(settings));
          result = { item, character_group_order: settings.character_group_order };
        }
        else if (args.command === 'user_delete_symbol_group') {
          if (window.__manualFailSymbolDelete) {
            window.__manualFailSymbolDelete = false;
            return { ok: false, message: '문자표를 삭제하지 못했습니다.', data: {} };
          }
          characterGroups = characterGroups.filter((group) => group.id !== args.args.item_id);
          localStorage.setItem('jb-manual-character-groups', JSON.stringify(characterGroups));
        }
        else if (args.command === 'status' || args.command === 'connect') result = { connected: true, selection };
        else if (data[args.command]) result = data[args.command];
        return { ok: true, message: '한글 프로그램에 연결했습니다.', data: result };
      },
    };
  }, fixture);
  await page.goto(url);
  await page.locator('.content-card').first().waitFor();
  await page.evaluate(() => document.fonts.ready);
  if ((await page.evaluate(() => window.__manualLayoutCommands)).length) throw Error('Startup must not arrange windows automatically');
  await page.getByRole('button', { name: '한글과 나란히 배치', exact: true }).click();
  await page.getByText('창 배치 테스트 완료', { exact: true }).waitFor();
  await page.getByRole('button', { name: '한글과 나란히 배치', exact: true }).click();
  await page.waitForFunction(() => window.__manualLayoutCommands.length === 2);
  await page.waitForFunction(() => !document.querySelector('.window-layout-button').disabled);
  await page.getByRole('button', { name: '한글과 나란히 배치', exact: true }).waitFor();
  await page.evaluate(() => { window.__manualFailLayout = true; });
  await page.getByRole('button', { name: '한글과 나란히 배치', exact: true }).click();
  await page.getByText('창 배치 실패: Error: 배치 테스트 실패', { exact: true }).waitFor();
  if (await page.getByRole('button', { name: '원래 창 배치 복원', exact: true }).count()) throw Error('Restore button must not be present');
  if (JSON.stringify(await page.evaluate(() => window.__manualLayoutCommands)) !== JSON.stringify(['arrange_hwp_windows', 'arrange_hwp_windows', 'arrange_hwp_windows'])) {
    throw Error('Window layout buttons did not invoke their dedicated commands');
  }
  await page.getByRole('button', { name: '한글과 나란히 배치', exact: true }).click();
  await page.waitForFunction(() => window.__manualLayoutCommands.length === 4 && !document.querySelector('.window-layout-button').disabled);
  await page.getByText('창 배치 테스트 완료', { exact: true }).waitFor();
  if ((await page.evaluate(() => window.__manualRequests.filter((command) => command === 'window_layout_target'))).length !== 4) {
    throw Error('Each layout click must resolve the currently connected HWP window');
  }
  const save = async (name, selector, maxHeight = 360) => {
    await page.locator(selector).first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(100);
    const box = await page.locator(selector).first().boundingBox();
    if (!box) throw Error(`No screenshot target: ${name}`);
    await page.screenshot({ path: path.join(manual, 'assets', `${name}.png`), clip: { x: box.x, y: box.y, width: box.width, height: Math.min(box.height, maxHeight) } });
  };
  const tab = async (name) => page.locator('.tabs').getByRole('button', { name, exact: true }).click();
  await page.screenshot({ path: path.join(manual, 'assets/start.png'), clip: { x: 0, y: 0, width: 620, height: 140 } });
  for (const width of [440, 500, 620]) {
    await page.setViewportSize({ width, height: 1000 });
    const fits = await page.locator('.toolbar').evaluate((toolbar) => {
      const outer = toolbar.getBoundingClientRect();
      return [...toolbar.querySelectorAll('button')].every((button) => {
        const box = button.getBoundingClientRect();
        return box.left >= outer.left && box.right <= outer.right && box.top >= outer.top && box.bottom <= outer.bottom;
      }) && toolbar.scrollWidth <= toolbar.clientWidth;
    });
    if (!fits) throw Error(`Toolbar does not fit at ${width}px`);
    await page.locator('.toolbar').screenshot({ path: path.join(manual, 'assets', `toolbar-${width}.png`) });
  }
  await page.setViewportSize({ width: 620, height: 1000 });
  await save('auto', '.auto-format-group', 310);
  await save('manual-style', '.content-card-grid', 330);
  await page.getByRole('button', { name: '서식 설정', exact: true }).click();
  await save('auto-settings', '.auto-format-settings-modal', 250);
  await save('auto-profiles', '.auto-format-profile-section', 150);
  await save('title-templates', '.auto-format-template-section', 240);
  await save('auto-roles', '.auto-format-role-section', 650);
  await page.locator('.auto-format-settings-modal').getByRole('button', { name: '취소', exact: true }).click();
  await tab('편집도구');
  const tableButtons = page.locator('.table-tool-grid > button');
  const lastLabels = (await tableButtons.allInnerTexts()).slice(-3).map((label) => label.trim());
  if (JSON.stringify(lastLabels) !== JSON.stringify(['표 그리기', '글자처럼 취급', '글자처럼 취급 해제'])) {
    throw Error('Object layout buttons must follow table drawing at the end');
  }
  await page.getByRole('button', { name: '표 그리기', exact: true }).click();
  if (!(await page.evaluate(() => window.__manualRequests.includes('table_draw')))) {
    throw Error('Table drawing button did not invoke its dedicated backend command');
  }
  await page.getByRole('button', { name: '글자처럼 취급', exact: true }).click();
  await page.getByRole('button', { name: '글자처럼 취급 해제', exact: true }).click();
  if (JSON.stringify(await page.evaluate(() => window.__manualObjectSettings)) !== JSON.stringify([true, false])) {
    throw Error('Object layout buttons did not invoke distinct enable/disable commands');
  }
  for (const width of [440, 500, 620]) {
    await page.setViewportSize({ width, height: 1400 });
    const fits = await tableButtons.evaluateAll((buttons) => buttons.every((button) => {
      const label = button.lastElementChild.getBoundingClientRect();
      const card = button.getBoundingClientRect();
      const preview = button.firstElementChild.getBoundingClientRect();
      const graphic = button.firstElementChild.firstElementChild.getBoundingClientRect();
      return card.height === 84 && preview.height === 62
        && label.left >= card.left && label.right <= card.right && label.top >= preview.bottom && label.bottom <= card.bottom
        && graphic.top >= preview.top && graphic.bottom <= preview.bottom;
    }));
    if (!fits) throw Error(`Table tool size or label layout is incorrect at ${width}px`);
    const previews = await tableButtons.evaluateAll((buttons) => buttons.slice(-3).every((button) => {
      const svg = button.querySelector('.table-tool-preview > svg');
      return svg?.getAttribute('viewBox') === '72 78 368 304' && svg.querySelector('rect');
    }));
    if (!previews) throw Error('New table tools must use table-based previews');
    const iconSizes = await tableButtons.evaluateAll((buttons) => buttons.every((button, index) => {
      const svg = button.querySelector('.table-tool-preview > svg');
      const scale = svg.getScreenCTM().a;
      if (index < buttons.length - 3 && svg.getAttribute('viewBox') !== '72 52 368 304') return false;
      const bounds = index < buttons.length - 3 ? svg.querySelector('image') : svg.querySelector('rect');
      return bounds && scale * 280 >= 55 && scale * 280 <= 60;
    }));
    if (!iconSizes) throw Error('Table icons must retain their original visible width, not shrink with the cards');
    await save(`object-tools-${width}`, '.table-tool-grid', 1200);
  }
  await page.setViewportSize({ width: 620, height: 1000 });
  await save('table', '.table-tool-grid', 1000);
  await save('cell-images', '.picture-tool', 300);
  await page.getByRole('button', { name: '셀 정리', exact: true }).click();
  await save('cell', '.cell-tools', 560);
  await page.getByRole('button', { name: '글자 작업', exact: true }).click();
  await save('text', '.text-tools', 350);
  for (const label of ['위첨자', '아래첨자', '첨자 해제']) {
    await page.getByRole('button', { name: label, exact: true }).click();
  }
  await save('scripts', '.script-tools', 180);
  await tab('문자표');
  await save('characters', '[data-tour="characters"]', 380);
  await page.getByRole('button', { name: '네모문자 1', exact: true }).click();
  if (await page.getByRole('heading', { name: /^네모문자-(한글|영문)$/ }).count()) {
    throw Error('Only numbered square characters should be shown');
  }
  for (const width of [440, 500, 620]) {
    await page.setViewportSize({ width, height: 1000 });
    const fits = await page.locator('.square-character').evaluateAll((characters) => characters.every((character) => {
      const glyph = character.getBoundingClientRect();
      const button = character.parentElement.getBoundingClientRect();
      return glyph.left >= button.left && glyph.right <= button.right && glyph.height <= button.height;
    }));
    if (!fits) throw Error(`Square character does not fit at ${width}px`);
  }
  await page.setViewportSize({ width: 620, height: 1400 });
  const squareGroups = page.locator('.character-group').filter({ has: page.locator('.square-character') });
  await squareGroups.first().scrollIntoViewIfNeeded();
  const firstSquare = await squareGroups.first().boundingBox();
  const lastSquare = await squareGroups.last().boundingBox();
  await page.screenshot({ path: path.join(manual, 'assets/square-characters.png'), clip: {
    x: firstSquare.x, y: firstSquare.y, width: firstSquare.width, height: lastSquare.y + lastSquare.height - firstSquare.y,
  } });
  await page.getByRole('button', { name: '글자 겹치기', exact: true }).click();
  await page.locator('.modal input').fill('30');
  await save('compose-characters', '.modal', 430);
  await page.locator('.modal').getByRole('button', { name: '삽입', exact: true }).click();
  const effects = await page.evaluate(() => window.__manualCharacterEffects);
  if (JSON.stringify(effects.map((effect) => effect.args.script_mode || `${effect.args.shape}:${effect.args.value}`))
      !== JSON.stringify(['super', 'sub', 'normal', 'square:1', 'circle:30'])) {
    throw Error('Character buttons did not invoke their expected backend commands');
  }
  const headings = page.locator('.character-group .group-heading h2');
  const originalOrder = await headings.allTextContents();
  if (await page.getByRole('button', { name: /위로 이동$/ }).count()) throw Error('Reorder arrows should be hidden initially');
  await page.getByRole('button', { name: '순서 변경', exact: true }).click();
  if (!(await page.getByRole('button', { name: `${originalOrder[0]} 위로 이동`, exact: true }).isDisabled())) throw Error('First group cannot move up');
  if (!(await page.getByRole('button', { name: `${originalOrder.at(-1)} 아래로 이동`, exact: true }).isDisabled())) throw Error('Last group cannot move down');
  await page.getByRole('button', { name: `${originalOrder[1]} 위로 이동`, exact: true }).click();
  await page.waitForFunction((title) => document.querySelector('.character-group h2')?.textContent === title, originalOrder[1]);
  await page.reload();
  await page.locator('.content-card').first().waitFor();
  await tab('문자표');
  if (await headings.first().textContent() !== originalOrder[1]) throw Error('Character order did not survive reload');
  if (await page.getByRole('button', { name: /위로 이동$/ }).count()) throw Error('Reorder mode should reset after reload');
  await page.getByRole('button', { name: '순서 변경', exact: true }).click();
  await page.evaluate(() => { window.__manualFailOrderSave = true; });
  await page.getByRole('button', { name: `${originalOrder[1]} 아래로 이동`, exact: true }).click();
  await page.getByText('문자표 순서를 저장하지 못했습니다.', { exact: true }).waitFor();
  if (await headings.first().textContent() !== originalOrder[1]) throw Error('Failed save must not reorder the displayed groups');
  await page.getByRole('button', { name: `${originalOrder[1]} 아래로 이동`, exact: true }).click();
  await page.waitForFunction((title) => document.querySelector('.character-group h2')?.textContent === title, originalOrder[0]);
  for (const width of [440, 500, 620]) {
    await page.setViewportSize({ width, height: 1400 });
    const fits = await page.locator('.character-actions, .character-group .group-heading').evaluateAll((rows) => rows.every((row) => {
      const bounds = row.getBoundingClientRect();
      return [...row.querySelectorAll('button')].every((button) => {
        const box = button.getBoundingClientRect();
        return box.left >= bounds.left && box.right <= bounds.right;
      }) && row.scrollWidth <= row.clientWidth;
    }));
    if (!fits) throw Error(`Character reorder controls do not fit at ${width}px`);
  }
  await save('characters-order', '[data-tour="characters"]', 380);
  if ((await page.evaluate(() => window.__manualRequests)).some((command) => ['insert_character', 'compose_characters'].includes(command))) {
    throw Error('Changing group order must not insert anything into HWP');
  }
  await page.getByRole('button', { name: '완료', exact: true }).click();
  if (await page.getByRole('button', { name: /위로 이동$/ }).count()) throw Error('Done must hide reorder arrows');
  await require(path.join(app, 'scripts/verify-character-order.cjs')).verifyCharacterOrder(page, path.join(manual, 'assets'));
  await page.getByRole('button', { name: '내 문자표 추가', exact: true }).click();
  await save('characters-add', '.modal', 360);
  await page.locator('.modal-header').getByRole('button').click();
  await tab('심볼');
  await save('symbols', '[data-tour="symbols"]', 400);
  await tab('양식');
  await save('forms', '[data-tour="forms"]', 460);
  await page.getByRole('button', { name: 'K-에듀파인 기안창', exact: true }).click();
  if (await page.locator('.window-layout-button').count()) throw Error('K-edufine mode must not show window layout controls');
  await tab('양식');
  await save('drafts', '[data-tour="forms"]', 320);
  await page.getByRole('button', { name: '일반 한글', exact: true }).click();
  if (await page.locator('.window-layout-button').count() !== 1) throw Error('HWP mode must show window layout control');
  await tab('편집용지');
  await require('../../tauri-prototype/scripts/verify-page-presets.cjs').verifyPagePresets(page, path.join(manual, 'assets'));
  await save('pages', '[data-tour="pages"]', 330);
  await page.getByRole('button', { name: '내 편집용지 추가', exact: true }).click();
  await save('pages-add', '.modal', 650);
  await page.locator('.modal-header').getByRole('button').click();
  await page.getByRole('button', { name: '설정', exact: true }).click();
  await save('settings', '.settings-sections > section:has(.settings-backup-grid)', 150);
  await save('settings-display', '.settings-sections > section', 250);
  await page.locator('.modal-header').getByRole('button').click();
  try {
    await require(path.join(app, 'scripts/verify-tutorial.cjs')).verifyTutorial(page, path.join(manual, 'assets'));
  } catch (error) {
    await page.screenshot({ path: path.join(manual, 'assets/tutorial-failure.png') });
    console.error('Tutorial failure:', await page.locator('body').innerText());
    throw error;
  }
  if (errors.length) throw Error(errors.join('\n'));
  await page.close();
}
async function main() {
  validate();
  if (process.argv.includes('--check')) { console.log(`Manual review verified for v.${version}`); return; }
  if (!fs.existsSync(path.join(app, 'dist/index.html'))) throw Error('먼저 npm run build를 실행하세요.');
  fs.mkdirSync(path.join(manual, 'assets'), { recursive: true });
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'jb-manual-'));
  const python = process.env.MANUAL_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  let server;
  let browser;
  try {
    const fixture = JSON.parse(execFileSync(python, [path.join(manual, 'fixture.py')], {
      cwd: app, env: { ...process.env, APPDATA: scratch, PYTHONPATH: `${app}${path.delimiter}${root}`, PYTHONIOENCODING: 'utf-8' },
      encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
    }));
    server = http.createServer((req, res) => {
      const target = path.resolve(app, 'dist', `.${decodeURIComponent(req.url.split('?')[0] === '/' ? '/index.html' : req.url.split('?')[0])}`);
      if (!target.startsWith(path.join(app, 'dist') + path.sep) || !fs.existsSync(target)) { res.writeHead(404); res.end(); return; }
      const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.png': 'image/png' };
      res.setHeader('Content-Type', mime[path.extname(target)] || 'application/octet-stream');
      fs.createReadStream(target).pipe(res);
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    browser = await playwrightModule().chromium.launch({ headless: true });
    await captureScreens(browser, `http://127.0.0.1:${server.address().port}`, fixture);
    fs.mkdirSync(output, { recursive: true });
    fs.writeFileSync(path.join(output, htmlName), render(fixture));
    const pdfName = `JBEdu_FORM_사용자매뉴얼_v.${version}.pdf`;
    const page = await browser.newPage();
    await page.goto(require('node:url').pathToFileURL(path.join(output, htmlName)).href);
    await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].filter((img) => img.getAttribute('src')).map((img) => img.decode())); });
    await page.pdf({ path: path.join(output, pdfName), format: 'A4', printBackground: true, displayHeaderFooter: true,
      headerTemplate: '<span></span>', footerTemplate: '<div style="width:100%;text-align:center;font-size:8px;color:#626977;font-family:Arial"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
      preferCSSPageSize: true, tagged: true, outline: true });
    await page.close();
    stageInstallResources(render(fixture, { pdfName: 'manual.pdf' }), path.join(output, pdfName),
      path.join(app, 'CHANGELOG.md'), path.join(app, 'src-tauri'));
    if (process.argv.includes('--reviewed')) {
      fs.writeFileSync(path.join(manual, 'review.json'), JSON.stringify({ version, files: fingerprints() }, null, 2) + '\n');
    }
    console.log(`Manual generated: ${path.join(output, htmlName)}\nPDF: ${path.join(output, pdfName)}`);
  } finally {
    if (browser) await browser.close();
    if (server) await new Promise((resolve) => server.close(resolve));
    if (!path.resolve(scratch).startsWith(path.resolve(os.tmpdir()) + path.sep)) throw Error('Unsafe scratch cleanup path');
    fs.rmSync(scratch, { recursive: true, force: true });
  }
}
module.exports = { sourceFingerprint, reviewChanges, escape, renderBlock, render, chapterGroups, stageInstallResources };
if (require.main === module) main().catch((error) => { console.error(error.message); process.exitCode = 1; });
