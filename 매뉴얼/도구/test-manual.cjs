const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const os = require('node:os');
const { sourceFingerprint, reviewChanges, escape, renderBlock, render, chapterGroups, stageInstallResources } = require('./build-manual.cjs');

test('version-only and line ending changes do not require rewriting descriptions', () => {
  assert.equal(sourceFingerprint('const VERSION = "v.4.2.1";\r\n'), sourceFingerprint('const VERSION = "v.4.2.2";\n'));
});
test('changed or new feature sources need a manual review', () => {
  assert.deepEqual(reviewChanges({ old: 'abc', new: 'def' }, { old: 'abc' }), ['new']);
  assert.deepEqual(reviewChanges({ old: 'changed' }, { old: 'abc' }), ['old']);
});
test('manual content is escaped and examples preserve literal tags', () => {
  assert.equal(escape('<script>"&'), '&lt;script&gt;&quot;&amp;');
  const result = renderBlock({ type: 'example', title: '예시', text: '(표시작)\n구분|내용\n(표끝)' }, {});
  assert(result.includes('(표시작)\n구분|내용\n(표끝)'));
});
test('unsupported blocks cannot silently disappear', () => {
  assert.throws(() => renderBlock({ type: 'unknown' }, {}), /Unknown manual block/);
});
test('manual descriptions use compact bullet points and retain important limitations', () => {
  const content = JSON.parse(fs.readFileSync(path.join(__dirname, '../원본/content.json'), 'utf8'));
  const descriptions = [];
  for (const section of content.sections) {
    descriptions.push(section.lead);
    const blocks = section.blocks.flatMap(function walk(block) { return block.type === 'subsection' ? block.blocks.flatMap(walk) : [block]; });
    for (const block of blocks) {
      assert.notEqual(block.type, 'paragraph');
      if (block.type === 'faq') descriptions.push(...block.items.flatMap(([question, answers]) => [question, ...answers]));
      else if (block.type !== 'example') {
        if (block.items) descriptions.push(...block.items);
        if (block.rows) descriptions.push(...block.rows.flat());
      }
    }
  }
  assert(descriptions.every((text) => !/(?:습니다|합니다|하세요|됩니다)[.!?]?$/.test(text)));
  const text = descriptions.join('\n');
  for (const required of ['HWP', 'HWPX', '최대 10개', '굴림체 12포인트', '병합 아님', '3개 보존', '5~72포인트', '기존 표 너비 자동 맞춤 미지원']) assert(text.includes(required), required);
  const result = renderBlock({ type: 'note', title: '주의', items: ['<항목>', '두 번째'] }, {});
  assert(result.includes('<ul class="bullets">'));
  assert(result.includes('&lt;항목&gt;'));
});
test('chapters, subsections and action steps use distinct hierarchy and title registration has its own screen', () => {
  const content = JSON.parse(fs.readFileSync(path.join(__dirname, '../원본/content.json'), 'utf8'));
  assert(!JSON.stringify(content).includes('태그'));
  const settings = content.sections.find((section) => section.id === 'auto-settings');
  assert.deepEqual(chapterGroups(settings).map((group) => group.title), ['설정 선택·저장', '문서제목·1단계 제목 양식 추가', '글자·번호·앞 기호 변경']);
  assert(settings.blocks[1].path.includes('문서제목·1단계 제목 양식'));
  assert(settings.blocks[1].blocks.some((block) => block.image === 'title-templates'));
  const table = content.sections.find((section) => section.id === 'table');
  assert(table.blocks[1].blocks.some((block) => block.image === 'cell-images'));
  const steps = renderBlock({ type: 'steps', items: ['실행', '확인'] }, {});
  assert(steps.includes('class="step-label">1단계'));
  assert(steps.includes('class="step-label">2단계'));
});
test('new layout preserves every chapter and uses resolvable group links and offline images', () => {
  const content = JSON.parse(fs.readFileSync(path.join(__dirname, '../원본/content.json'), 'utf8'));
  const html = render({ table_catalog: { items: [{ title: '표 작업' }] } });
  assert.equal((html.match(/class="chapter" /g) || []).length, content.sections.length);
  for (const section of content.sections) {
    assert(html.includes(`id="${section.id}" data-group="${section.group}"`));
    assert(html.includes(escape(section.lead)));
  }
  assert.equal((html.match(/data-group=/g) || []).length, content.sections.length + new Set(content.sections.map((item) => item.group)).size);
  assert(html.includes('data:image/png;base64,'));
  assert(!/src="https?:/.test(html));
  const version = JSON.parse(fs.readFileSync(path.join(__dirname, '../../tauri-prototype/package.json'), 'utf8')).version;
  assert(html.includes(`사용자매뉴얼_v.${version}.pdf`));
  assert.equal(html.split(`>v.${version}<`).length - 1, 1);
  assert(!html.includes('환경별 차이'));
  assert(!html.includes('사용 환경에 따라'));
  assert(html.includes('class="meta-strip"'));
  assert(html.indexOf('class="intro"') < html.indexOf('class="layout"'));
  assert(html.indexOf('id="manual-search"') < html.indexOf('class="layout"'));
  assert(html.includes('data:image/x-icon;base64,'));
});
test('character categories are not expanded as separate manual workflows', () => {
  const content = JSON.parse(fs.readFileSync(path.join(__dirname, '../원본/content.json'), 'utf8'));
  const characters = content.sections.find((section) => section.id === 'characters');
  assert(!JSON.stringify(characters).includes('네모문자'));
  assert(!JSON.stringify(characters).includes('square-characters'));
  assert(characters.blocks.some((block) => block.title === '글자 겹치기'));
});
test('search, group navigation, mobile menu and image zoom keep their behavior', () => {
  const element = (props = {}) => {
    const handlers = {};
    const classes = new Set();
    return { hidden: false, value: '', dataset: {}, attrs: {}, handlers,
      classList: { toggle(name, force) { const on = force ?? !classes.has(name); if (on) classes.add(name); else classes.delete(name); return on; }, remove(name) { classes.delete(name); } },
      addEventListener(name, fn) { handlers[name] = fn; }, setAttribute(name, value) { this.attrs[name] = value; }, removeAttribute(name) { delete this.attrs[name]; },
      getBoundingClientRect() { return { top: 500, height: 120 }; }, focus() { this.focused = true; }, ...props };
  };
  const chapters = [element({ id: 'start', textContent: '처음 사용하기', dataset: { group: '시작' } }), element({ id: 'cell', textContent: '셀 정리 찾아바꾸기', dataset: { group: '편집도구' } })];
  const nav = chapters.map((chapter) => element({ hash: `#${chapter.id}` }));
  const groupNav = chapters.map((chapter) => element({ hash: `#${chapter.id}`, dataset: { group: chapter.dataset.group } }));
  const image = { src: 'data:image/png;base64,ABC', alt: '화면' };
  const button = element({ querySelector() { return image; } });
  const zoom = element({ showModal() { this.open = true; }, close() { this.open = false; } });
  const nodes = { '#manual-search': element(), '#search-status': element(), '#clear-search': element(), '#menu-toggle': element(), '.sidebar': element(), '.site-header': element(), '#image-zoom': zoom, '#zoom-image': element(), '#zoom-label': element(), '#zoom-close': element(), '#print-manual': element(), '#start': chapters[0], '#cell': chapters[1] };
  const document = { querySelector: (name) => nodes[name], querySelectorAll: (name) => ({ '.chapter': chapters, '.sidebar a': nav, '.section-nav a': groupNav, '.quick-links a': [], '.screen-button': [button] })[name], documentElement: { style: { setProperty() {} } } };
  const window = element({ print() { this.printed = true; } });
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../원본/manual.js'), 'utf8'), { document, window, requestAnimationFrame: (fn) => fn() });
  nodes['#manual-search'].value = '찾아바꾸기';
  nodes['#manual-search'].handlers.input();
  assert.equal(chapters[0].hidden, true);
  assert.equal(chapters[1].hidden, false);
  assert.equal(nav[0].hidden, true);
  nodes['#manual-search'].value = '없는검색어';
  nodes['#manual-search'].handlers.input();
  assert(nodes['#search-status'].textContent.startsWith('0개'));
  groupNav[0].handlers.click();
  assert(chapters.every((chapter) => !chapter.hidden));
  assert.equal(nav[0].attrs['aria-current'], 'location');
  nodes['#menu-toggle'].handlers.click();
  assert.equal(nodes['#menu-toggle'].attrs['aria-expanded'], 'true');
  nav[1].handlers.click();
  assert.equal(nodes['#menu-toggle'].attrs['aria-expanded'], 'false');
  button.handlers.click();
  assert.equal(zoom.open, true);
  assert.equal(nodes['#zoom-image'].src, image.src);
  nodes['#zoom-close'].handlers.click();
  assert.equal(zoom.open, false);
  nodes['#print-manual'].handlers.click();
  assert.equal(window.printed, true);
});
test('installer resources have stable names and use the bundled PDF link', () => {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'jb-manual-package-'));
  try {
    const pdf = path.join(scratch, 'versioned.pdf');
    const changelog = path.join(scratch, 'changelog-source.md');
    fs.writeFileSync(pdf, '%PDF-test');
    fs.writeFileSync(changelog, '# Changes');
    const html = render({}, { pdfName: 'manual.pdf' });
    const destination = path.join(scratch, 'bundle');
    stageInstallResources(html, pdf, changelog, destination);
    assert.equal(fs.readFileSync(path.join(destination, 'manual/index.html'), 'utf8'), html);
    assert(html.includes('href="manual.pdf" download'));
    assert.equal(fs.readFileSync(path.join(destination, 'manual/manual.pdf'), 'utf8'), '%PDF-test');
    assert.equal(fs.readFileSync(path.join(destination, 'support/CHANGELOG.md'), 'utf8'), '# Changes');
    const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../../tauri-prototype/src-tauri/tauri.conf.json'), 'utf8'));
    for (const file of ['manual/index.html', 'manual/manual.pdf', 'support/CHANGELOG.md']) assert(config.bundle.resources.includes(file));
  } finally {
    assert(path.resolve(scratch).startsWith(path.resolve(os.tmpdir()) + path.sep));
    fs.rmSync(scratch, { recursive: true, force: true });
  }
});
