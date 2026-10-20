const assert = require('node:assert/strict');
const path = require('node:path');

async function verifyPagePresets(page, assets) {
  const tab = async () => page.locator('.tabs').getByRole('button', { name: '편집용지', exact: true }).click();
  await tab();
  const section = page.locator('[data-tour="pages"]');
  const portrait = section.getByRole('button', { name: '기본 보고서 편집용지(세로)', exact: true });
  const landscape = section.getByRole('button', { name: '기본 보고서 편집용지(가로)', exact: true });
  await portrait.waitFor();
  assert(await portrait.locator('.page-sheet').evaluate((element) => element.offsetHeight > element.offsetWidth));
  assert(await landscape.locator('.page-sheet').evaluate((element) => element.offsetWidth > element.offsetHeight));
  await section.getByRole('button', { name: '현재 페이지만', exact: true }).click();
  await landscape.click();
  await page.waitForFunction(() => window.__manualPageApplications.length === 1);
  assert.deepEqual(await page.evaluate(() => window.__manualPageApplications[0]), { item_key: 'builtin:basic_report_landscape', scope: 'page' });
  await section.getByRole('button', { name: '문서 전체', exact: true }).click();
  await portrait.click();
  await page.waitForFunction(() => window.__manualPageApplications.length === 2);
  assert.equal(await page.evaluate(() => window.__manualPageApplications[1].scope), 'document');
  await page.getByRole('button', { name: '내 편집용지 추가', exact: true }).click();
  let modal = page.locator('.modal');
  await modal.getByLabel('편집용지 이름').fill('테스트 가로');
  await modal.getByRole('button', { name: '가로', exact: true }).click();
  for (const width of [440, 500, 620]) {
    await page.setViewportSize({ width, height: 1000 });
    const fits = await modal.evaluate((element) => {
      const outer = element.getBoundingClientRect();
      const preview = element.querySelector('.page-margin-live .page-preview').getBoundingClientRect();
      const left = element.querySelector('.margin-control.is-left').getBoundingClientRect();
      const right = element.querySelector('.margin-control.is-right').getBoundingClientRect();
      if (preview.left < left.right || preview.right > right.left) return false;
      return [...element.querySelectorAll('input, button, .page-preview')].every((child) => {
        const box = child.getBoundingClientRect();
        return box.left >= outer.left && box.right <= outer.right && box.top >= outer.top && box.bottom <= outer.bottom;
      });
    });
    await modal.screenshot({ path: path.join(assets, `page-editor-${width}.png`) });
    assert(fits, `Page editor overflow at ${width}px`);
  }
  await modal.getByRole('button', { name: '등록', exact: true }).click();
  await modal.waitFor({ state: 'hidden' });
  await page.reload();
  await tab();
  const userCard = section.getByRole('button', { name: '테스트 가로', exact: true });
  await userCard.waitFor();
  assert(await userCard.locator('.page-preview').evaluate((element) => element.classList.contains('is-landscape')));
  await page.getByRole('button', { name: '사용자 편집용지 관리', exact: true }).click();
  await page.locator('.manager-row').filter({ hasText: '테스트 가로' }).getByRole('button', { name: '설정', exact: true }).click();
  modal = page.locator('.modal').filter({ has: page.locator('.page-editor') });
  assert.equal(await modal.getByRole('button', { name: '가로', exact: true }).getAttribute('aria-pressed'), 'true');
  await modal.getByRole('button', { name: '세로', exact: true }).click();
  await page.evaluate(() => { window.__manualFailPageSave = true; });
  await modal.getByRole('button', { name: '저장', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.status-bar').textContent.includes('편집용지를 저장하지 못했습니다.'));
  assert(await modal.isVisible());
  await modal.getByRole('button', { name: '저장', exact: true }).click();
  await modal.waitFor({ state: 'hidden' });
  await page.evaluate(() => localStorage.removeItem('jb-manual-pages'));
  await page.reload();
  await tab();
  await page.setViewportSize({ width: 620, height: 1000 });
  console.log('Page presets verified: A4 portrait/landscape, scope, save/reload/edit/failure, 440/500/620px.');
}

module.exports = { verifyPagePresets };
