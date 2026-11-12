const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');

async function verifyPractice(browser, htmlPath, options = {}) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const errors = [];
  const network = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => { if (/^https?:/.test(request.url())) network.push(request.url()); });
  const base = pathToFileURL(htmlPath).href;
  const frame = page.frameLocator('#practice-live-app');
  async function open(topic) {
    if (await page.locator('#practice-dialog').isVisible()) {
      await page.locator('#practice-close').click();
    }
    await page.goto(base + '#' + topic);
    await page.waitForFunction((id) => document.querySelector('#reader-practice').dataset.practiceOpen && location.hash === '#' + id, topic);
    await page.locator('#reader-practice').click();
    await frame.locator('html.practice-configured').waitFor();
    await frame.locator('.status-bar').waitFor();
    assert.ok(await page.locator('#practice-steps [aria-current="step"]').isVisible());
    assert.ok((await page.locator('#practice-instruction').innerText()).length > 10);
    for (const button of await frame.locator('.tabs button:not(.is-active)').all()) assert.ok(await button.isDisabled());
    console.log('Practice opened: ' + topic);
  }
  async function editTab(name) {
    assert.equal(await frame.locator('.tabs .is-active').innerText(), '편집도구');
    assert.equal(await frame.locator('.subtabs .is-active').innerText(), name);
    const inactive = frame.locator('.tabs button:not(.is-active),.subtabs[aria-label="편집도구"] button:not(.is-active)');
    for (const button of await inactive.all()) assert.ok(await button.isDisabled());
  }
  async function dragCells() {
    const cells = page.locator('#practice-document td[data-cell]');
    const a = await cells.first().boundingBox();
    const b = await cells.last().boundingBox();
    await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
    await page.mouse.down();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 8 });
    await page.mouse.up();
  }
  async function complete(tag = '') {
    await page.locator('#practice-guide[data-complete="true"]').waitFor();
    if (options.captureDir) {
      const fs = require('node:fs');
      const path = require('node:path');
      fs.mkdirSync(options.captureDir, { recursive: true });
      const id = await page.evaluate(() => location.hash.slice(1));
      await page.screenshot({ path: path.join(options.captureDir, id + (tag ? '-' + tag : '') + '.png'), animations: 'disabled' });
    }
  }
  try {
    await open('quick');
    await page.locator('#practice-dialog > .practice-coach-layer:not([hidden]) .practice-coach-tag').waitFor();
    assert.match(await page.locator('#practice-dialog > .practice-coach-layer .practice-coach-tag').innerText(), /전체 선택/);
    await frame.getByRole('button', { name: '전체 서식 자동 지정하기', exact: true }).click();
    assert.match(await page.locator('#practice-guide').innerText(), /블록 지정/);
    await page.locator('.hwp-draft').focus();
    await page.locator('.hwp-draft').press('Control+a');
    await frame.locator('.practice-coach-layer:not([hidden]) .practice-coach-tag').waitFor();
    assert.match(await frame.locator('.practice-coach-tag').innerText(), /클릭하세요/);
    await frame.getByRole('button', { name: '전체 서식 자동 지정하기', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.report-native-section').count(), 2);
    await page.locator('#practice-reset').click();
    await frame.locator('html.practice-configured').waitFor();
    assert.ok(await page.locator('.hwp-draft').isVisible());

    await open('cell-3');
    await editTab('셀 정리');
    assert.ok(await frame.getByRole('button', { name: '내용 뒤에 추가', exact: true }).isDisabled());
    await dragCells();
    await frame.locator('.cell-tools').getByLabel('추가할 문자').fill('%');
    await frame.getByRole('button', { name: '내용 뒤에 추가', exact: true }).click();
    await complete();
    assert.deepEqual(await page.locator('#practice-document td').allTextContents(), ['34.5%', '56.0%', '62.5%', '81.2%']);

    await open('table-2');
    assert.ok(await frame.locator('.table-tool-grid').isHidden());
    assert.ok(await frame.locator('.picture-tool').isVisible());
    await dragCells();
    await editTab('표 작업');
    await frame.getByRole('button', { name: '셀 크기에 맞춤', exact: true }).click();
    await frame.getByRole('button', { name: '셀에 그림 넣기', exact: true }).click();
    await page.locator('.practice-file-options input').nth(0).check();
    await page.locator('.practice-file-options input').nth(1).check();
    await page.getByRole('button', { name: '열기', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.hwp-cell-image').count(), 2);
    assert.equal(await page.locator('.hwp-cell-image').first().evaluate((image) => image.style.objectFit), 'fill');

    await open('forms-2');
    const subject = await page.getByLabel('기안문 제목').inputValue();
    await page.getByRole('textbox', { name: '기안문 본문', exact: true }).click();
    assert.equal(await frame.locator('.tabs .is-active').innerText(), '양식');
    assert.ok(await frame.getByRole('button', { name: '일반 한글', exact: true }).isDisabled());
    await frame.locator('.kedufine-form-card').filter({ hasText: '추진 계획 수립' }).click();
    await complete();
    assert.match(await page.locator('.kedufine-inserted').innerText(), /\n\n붙임/);
    assert.equal(await page.getByLabel('기안문 제목').inputValue(), subject);

    await open('text-3');
    await page.locator('#hwp-select').click();
    await editTab('글자 작업');
    await frame.getByRole('button', { name: '위첨자', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.hwp-editable sup').innerText(), '2');

    await open('characters-1');
    await page.locator('.hwp-editable').click();
    assert.equal(await frame.locator('.tabs .is-active').innerText(), '문자표');
    await frame.getByRole('button', { name: '글자 겹치기', exact: true }).click();
    await frame.getByLabel('글자', { exact: true }).fill('30');
    await frame.getByRole('button', { name: '삽입', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.native-compose-circle').innerText(), '30');

    await open('auto-settings-3');
    await page.locator('#hwp-select').click();
    await frame.getByRole('button', { name: '서식 설정', exact: true }).click();
    await frame.getByLabel('본문 글자 크기', { exact: true }).fill('17');
    await frame.getByRole('button', { name: '저장', exact: true }).click();
    await frame.getByRole('button', { name: '본문', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.hwp-editable span').first().evaluate((node) => node.style.fontSize), '17pt');

    await open('auto-settings-2');
    await page.locator('#hwp-select').click();
    await frame.getByRole('button', { name: '서식 설정', exact: true }).click();
    await frame.getByRole('button', { name: '기존 제목 양식 추가', exact: true }).first().click();
    await frame.getByLabel('목록에 표시할 이름').fill('연수 제목');
    await frame.getByRole('button', { name: '이 제목 양식 저장', exact: true }).click();
    await frame.getByRole('button', { name: '저장', exact: true }).click();
    await complete();

    await open('auto-settings-1');
    await page.locator('#hwp-select').click();
    await frame.getByLabel('사용할 자동 서식 설정').selectOption('meeting');
    await frame.getByRole('button', { name: '전체 서식 자동 지정하기', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.native-body').first().evaluate((node) => node.style.fontSize), '14pt');

    await open('table-1');
    await dragCells();
    await editTab('표 작업');
    await frame.getByRole('button', { name: '전체 바깥선 굵게', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.table-outer-bold').count(), 1);

    await open('text-2');
    await page.waitForFunction(() => document.querySelector('.spacing-text')?.textContent.length > 10);
    const spacingBefore = await page.locator('.spacing-text').evaluate((node) => {
      const range = document.createRange();
      range.selectNodeContents(node);
      return { text: node.textContent, width: node.clientWidth, lines: new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size,
        paragraph: node.parentElement.clientWidth, br: node.querySelectorAll('br').length };
    });
    assert.ok(spacingBefore.lines > 1, 'The original text must wrap naturally');
    assert.ok(spacingBefore.width / spacingBefore.paragraph > .9, 'The paragraph must fill the document width');
    assert.equal(spacingBefore.br, 0);
    await page.locator('#hwp-select').click();
    await editTab('글자 작업');
    await frame.getByRole('button', { name: '자간 정리 1단계', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.spacing-applied').count(), 1);
    await page.waitForFunction(() => {
      const range = document.createRange();
      range.selectNodeContents(document.querySelector('.spacing-text'));
      return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size === 1;
    });
    assert.equal(await page.locator('.spacing-text').textContent(), spacingBefore.text);
    assert.equal(await page.locator('.spacing-text').evaluate((node) => node.clientWidth), spacingBefore.width);
    await frame.getByRole('button', { name: '자간 초기화', exact: true }).click();
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.spacing-text')).letterSpacing === 'normal'
      || getComputedStyle(document.querySelector('.spacing-text')).letterSpacing === '0px');

    await open('characters');
    await page.locator('.hwp-editable').click();
    assert.equal(await frame.locator('.tabs .is-active').innerText(), '문자표');
    await frame.getByRole('button', { name: '※', exact: true }).click();
    await complete();
    assert.match(await page.locator('.hwp-editable').innerText(), /※/);

    await open('manual-style');
    await page.locator('.hwp-editable').click();
    await frame.locator('.content-card').first().click();
    assert.equal(await page.locator('.native-style img').count(), 0);
    assert.equal(await page.locator('.native-style-table[data-layout="title"] tr').count(), 3);
    assert.equal((await page.locator('.native-style [data-style-slot]').innerText()).trim(), '');
    assert.match(await page.locator('#practice-steps [aria-current="step"]').innerText(), /빈 칸에 내용 입력/);
    await page.locator('.native-style [data-style-slot]').fill('교직원 연수 운영 계획');
    await complete();
    assert.equal(await page.locator('.native-style [data-style-slot]').innerText(), '교직원 연수 운영 계획');
    for (const [name, layout, rows, slots] of [
      ['붙임박스', 'attachment', 1, 1], ['표박스', 'grid', 3, 12], ['소제목박스', 'section', 1, 1],
      ['3단계절차박스', 'process', 2, 3], ['4단계절차박스', 'process', 2, 4],
    ]) {
      await page.locator('#practice-reset').click();
      await frame.locator('html.practice-configured').waitFor();
      await page.locator('.hwp-editable').click();
      await frame.locator('.content-card').filter({ hasText: name }).click();
      assert.equal(await page.locator('.native-style img').count(), 0);
      assert.equal(await page.locator('.native-style-table[data-layout="' + layout + '"] tr').count(), rows);
      assert.equal(await page.locator('.native-style [data-style-slot]').count(), slots);
      await page.locator('.native-style [data-style-slot]').first().fill('내용 입력');
      await complete(name);
    }
    await page.locator('#practice-reset').click();
    await frame.locator('html.practice-configured').waitFor();
    await page.locator('.hwp-editable').click();
    await frame.locator('.content-card').filter({ hasText: '참고박스' }).click();
    assert.equal(await page.locator('.native-reference legend').innerText(), '< 참고 >');
    await page.locator('.native-reference [data-style-slot]').fill('참고 사항 입력');
    await complete('참고박스');

    await open('forms-1');
    assert.equal(await frame.locator('.tabs .is-active').innerText(), '양식');
    await frame.getByRole('button', { name: '새 문서로 열기', exact: true }).click();
    await frame.locator('.content-card').first().click();
    await complete();
    assert.equal(await page.locator('.hwp-native-title').innerText(), '새 문서 - 한글');

    await open('pages');
    assert.equal(await frame.locator('.tabs .is-active').innerText(), '편집용지');
    await frame.getByRole('button', { name: '현재 페이지만', exact: true }).click();
    await frame.locator('.content-card').filter({ hasText: '가로' }).first().click();
    await complete();
    assert.equal(await page.locator('.hwp-landscape').count(), 1);
    assert.match(await page.locator('#practice-guide').innerText(), /현재 페이지/);

    await open('symbols-2');
    assert.equal(await frame.locator('.tabs .is-active').innerText(), '심볼');
    await frame.locator('.favorite-toggle').first().click();
    await complete();
    assert.equal(await frame.locator('.favorite-toggle[aria-pressed="true"]').count(), 1);

    for (const [label, result] of [
      ['문서제목', '.report-native-title'], ['1단계 제목', '.report-native-section'],
      ['2단계 제목', '.hwp-editable p'], ['3단계 제목', '.hwp-editable p'],
      ['본문', '.hwp-editable span'], ['참고', '.hwp-editable p'],
    ]) {
      await open('auto');
      assert.ok(await frame.locator('.auto-format-primary').isHidden());
      await page.locator('#hwp-select').click();
      await frame.getByRole('button', { name: label, exact: true }).click();
      await complete(label);
      assert.equal(await page.locator(result).count(), 1, label);
    }
    await open('cell-1');
    await dragCells();
    await frame.getByRole('button', { name: '공백·배경색 한 번에 정리', exact: true }).click();
    await complete();
    for (const cell of await page.locator('#practice-document td').all()) {
      const text = await cell.innerText();
      assert.equal(text, text.trim());
      assert.equal(await cell.evaluate((element) => element.style.backgroundColor), '');
    }
    await open('cell-2');
    await dragCells();
    await frame.getByLabel('찾을 내용').fill('연수');
    await frame.getByLabel('바꿀 내용').fill('교육');
    await frame.getByRole('button', { name: '찾아바꾸기 실행', exact: true }).click();
    await complete();
    assert.ok((await page.locator('#practice-document td').allTextContents()).every((value) => value.startsWith('교육')));
    await open('text-1');
    await page.locator('#hwp-select').click();
    await frame.getByRole('button', { name: '파랑', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.hwp-editable span').evaluate((element) => element.style.color), 'rgb(0, 70, 200)');
    assert.ok(await frame.locator('.spacing-tools').isHidden());
    await open('characters-2');
    await frame.getByRole('button', { name: '내 문자표 추가', exact: true }).click();
    await frame.getByLabel('문자표 이름').fill('내 표시');
    await frame.getByLabel('문자·기호').fill('★ ✓');
    await frame.getByRole('button', { name: '저장', exact: true }).click();
    await complete();
    await frame.getByRole('heading', { name: '내 문자표 · 내 표시', exact: true }).waitFor();
    assert.equal(await frame.locator('.character-group:visible').count(), 1);
    await open('symbols');
    await page.locator('.hwp-editable').click();
    await frame.locator('.symbol-card').first().click();
    await complete();
    assert.equal(await page.locator('.native-style-preview').count(), 1);

    await open('start');
    await frame.getByRole('button', { name: '한글과 나란히 배치', exact: true }).click();
    await complete();
    assert.equal(await page.locator('.practice-arranged').count(), 1);

    await page.keyboard.press('Escape');
    await page.locator('#practice-dialog').waitFor({ state: 'hidden' });
    assert.ok(await page.locator('#reader-practice').evaluate((button) => document.activeElement === button));
    assert.deepEqual(errors, []);
    assert.deepEqual(network, []);
    console.log('Real frontend verified: native tabs/dialogs, text/cell selection, images, K-edufine, superscript, compose; offline only.');
  } catch (error) {
    console.error('Practice guide:', await page.locator('#practice-guide').textContent());
    await page.screenshot({ path: require('node:path').resolve(__dirname, '../../.codex_tmp/practice-failure.png') });
    throw error;
  } finally {
    await page.close();
  }
}
module.exports = { verifyPractice };
