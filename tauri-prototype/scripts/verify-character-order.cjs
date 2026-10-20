const assert = require('node:assert/strict');
const path = require('node:path');

async function verifyCharacterOrder(page, output) {
  const headings = page.locator('.character-group .group-heading h2');
  const original = await headings.allTextContents();
  const requestsBefore = await page.evaluate(() => window.__manualRequests.length);
  let nativeDialogs = 0;
  const nativeDialog = async (dialog) => { nativeDialogs += 1; await dialog.dismiss(); };
  page.on('dialog', nativeDialog);
  const group = (title) => page.locator('.character-group').filter({ has: page.getByRole('heading', { name: `내 문자표 · ${title}`, exact: true }) });
  const add = async (title) => {
    await page.getByRole('button', { name: '내 문자표 추가', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '내 문자표 추가', exact: true });
    await dialog.locator('input').fill(title);
    await dialog.locator('textarea').fill('★\n◇');
    await dialog.getByRole('button', { name: '저장', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    await page.waitForFunction((title) => document.querySelector('.character-group h2')?.textContent === `내 문자표 · ${title}`, title);
  };
  const remove = async (title) => {
    await group(title).getByRole('button', { name: `${title} 삭제`, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '내 문자표 삭제', exact: true });
    await dialog.getByRole('button', { name: '삭제', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    assert.equal(await group(title).count(), 0);
  };
  try {
    await add('첫 문자표');
    const title = '자주 사용하는 교육행정 문자표 순서와 삭제 확인';
    await add(title);
    assert.deepEqual(await headings.allTextContents(), [`내 문자표 · ${title}`, '내 문자표 · 첫 문자표', ...original]);
    await page.reload();
    await page.locator('.content-card').first().waitFor();
    await page.locator('.tabs').getByRole('button', { name: '문자표', exact: true }).click();
    assert.equal(await headings.first().textContent(), `내 문자표 · ${title}`);
    await page.getByRole('button', { name: '순서 변경', exact: true }).click();
    assert(await group(title).getByRole('button', { name: `${title} 맨 위로 이동`, exact: true }).isDisabled());
    await group(title).getByRole('button', { name: `${title} 맨 아래로 이동`, exact: true }).click();
    await page.waitForFunction((title) => [...document.querySelectorAll('.character-group h2')].at(-1)?.textContent === `내 문자표 · ${title}`, title);
    assert.deepEqual(await headings.allTextContents(), ['내 문자표 · 첫 문자표', ...original, `내 문자표 · ${title}`]);
    assert(await group(title).getByRole('button', { name: `${title} 맨 아래로 이동`, exact: true }).isDisabled());
    await group(title).getByRole('button', { name: `${title} 맨 위로 이동`, exact: true }).click();
    await page.waitForFunction((title) => document.querySelector('.character-group h2')?.textContent === `내 문자표 · ${title}`, title);
    assert.deepEqual(await headings.allTextContents(), [`내 문자표 · ${title}`, '내 문자표 · 첫 문자표', ...original]);
    await page.evaluate(() => { window.__manualFailOrderSave = true; });
    await group(title).getByRole('button', { name: `${title} 맨 아래로 이동`, exact: true }).click();
    await page.getByText('문자표 순서를 저장하지 못했습니다.', { exact: true }).waitFor();
    assert.equal(await headings.first().textContent(), `내 문자표 · ${title}`);
    for (const width of [440, 500, 620]) {
      await page.setViewportSize({ width, height: 800 });
      assert(await group(title).locator('.group-heading').evaluate((row) => {
        const bounds = row.getBoundingClientRect();
        return row.scrollWidth <= row.clientWidth && [...row.querySelectorAll('button')].every((button) => {
          const rect = button.getBoundingClientRect();
          return rect.left >= bounds.left && rect.right <= bounds.right && rect.top >= bounds.top && rect.bottom <= bounds.bottom;
        });
      }), `Order buttons overflow at ${width}px`);
      await group(title).scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `character-order-${width}.png`) });
    }
    await page.getByRole('button', { name: '완료', exact: true }).click();
    await group(title).getByRole('button', { name: `${title} 삭제`, exact: true }).click();
    const deletion = page.getByRole('dialog', { name: '내 문자표 삭제', exact: true });
    assert((await deletion.innerText()).includes(`‘${title}’ 문자표를 삭제할까요?`));
    await deletion.getByRole('button', { name: '취소', exact: true }).click();
    assert.equal(await group(title).count(), 1);
    await group(title).getByRole('button', { name: `${title} 삭제`, exact: true }).click();
    await page.evaluate(() => { window.__manualFailSymbolDelete = true; });
    await deletion.getByRole('button', { name: '삭제', exact: true }).click();
    await deletion.getByRole('alert').waitFor();
    assert.equal(await group(title).count(), 1);
    await page.screenshot({ path: path.join(output, 'character-delete.png') });
    await deletion.getByRole('button', { name: '삭제', exact: true }).click();
    await deletion.waitFor({ state: 'hidden' });
    assert.equal(await group(title).count(), 0);
    await remove('첫 문자표');
    assert.deepEqual(await headings.allTextContents(), original);
    assert.equal(nativeDialogs, 0, 'No tauri.localhost/browser confirmation may open');
    const commands = await page.evaluate((start) => window.__manualRequests.slice(start), requestsBefore);
    assert(!commands.some((command) => /^(insert_|compose_characters|apply_charshape|spacing_)/.test(command)), 'Ordering/registration/deletion must not modify a HWP document');
    console.log('Character UI verified: new groups first, jump to top/bottom, preserved relative order, reload, failure, cancel/delete, 440/500/620px, no native dialogs/document actions.');
  } finally {
    page.off('dialog', nativeDialog);
    await page.setViewportSize({ width: 620, height: 1000 });
  }
}

module.exports = { verifyCharacterOrder };
