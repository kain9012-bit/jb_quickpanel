const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.MANUAL_PLAYWRIGHT_PATH || path.join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const root = path.resolve(__dirname, '../..');
const version = JSON.parse(fs.readFileSync(path.join(root, 'tauri-prototype/package.json'), 'utf8')).version;
const distribution = path.join(root, '매뉴얼/배포본');
const manualUrl = pathToFileURL(path.join(distribution, `JBEdu_FORM_사용자매뉴얼_v.${version}.html`)).href;
(async () => {
  const output = path.join(__dirname, '검증결과');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.goto(manualUrl);
    assert.equal(await page.locator('.chapter').count(), 14);
    assert.equal(await page.locator('img[src]').evaluateAll((imgs) => imgs.every((img) => img.complete && img.naturalWidth > 0)), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(output, 'desktop.png') });
    await page.locator('#manual-search').fill('복원');
    assert((await page.locator('.chapter:visible').count()) < 14);
    assert((await page.locator('.chapter:visible').count()) > 0);
    await page.locator('#manual-search').fill('존재하지않는검색어1234');
    assert.equal(await page.locator('.chapter:visible').count(), 0);
    assert((await page.locator('#search-status').textContent()).includes('0개'));
    await page.locator('#clear-search').click();
    assert.equal(await page.locator('.chapter:visible').count(), 14);
    await page.locator('.sidebar a[href="#auto-settings"]').click();
    assert.equal(new URL(page.url()).hash, '#auto-settings');
    await page.locator('#auto-settings .screen-button').first().click();
    assert.equal(await page.locator('#image-zoom').evaluate((dialog) => dialog.open), true);
    await page.getByRole('button', { name: '닫기', exact: true }).click();
    assert.equal(await page.locator('#image-zoom').evaluate((dialog) => dialog.open), false);
    const pdf = await page.getByRole('link', { name: 'PDF 다운로드' }).getAttribute('href');
    assert(fs.existsSync(path.join(distribution, pdf)));
    for (const width of [390, 768]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(manualUrl);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.locator('#menu-toggle').click();
      assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'true');
      await page.locator('.sidebar a[href="#quick"]').click();
      assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
      await page.screenshot({ path: path.join(output, `mobile-${width}.png`) });
    }
    await page.locator('#manual-search').fill('복원');
    await page.emulateMedia({ media: 'print' });
    assert.equal(await page.locator('.chapter:visible').count(), 14);
    assert.deepEqual(errors, []);
    console.log('Manual QA passed: offline images, PDF link, search/empty/reset, navigation, zoom, 390/768/1440px, complete print chapters.');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
