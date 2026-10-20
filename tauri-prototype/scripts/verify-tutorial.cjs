const assert = require('node:assert/strict');
const path = require('node:path');

async function verifyTutorial(page, output) {
  const requestStart = await page.evaluate(() => window.__manualRequests.length);
  const layoutStart = await page.evaluate(() => window.__manualLayoutCommands.length);
  for (const { mode, width, height } of [
    { mode: 'hwp', width: 500, height: 800 },
    { mode: 'kedufine', width: 500, height: 800 },
    { mode: 'hwp', width: 440, height: 560 },
    { mode: 'kedufine', width: 440, height: 560 },
  ]) {
    await page.setViewportSize({ width, height });
    await page.getByRole('button', { name: mode === 'hwp' ? '일반 한글' : 'K-에듀파인 기안창', exact: true }).click();
    await page.getByRole('button', { name: '설정', exact: true }).click();
    await page.getByRole('button', { name: '튜토리얼 다시 보기', exact: true }).click();
    const tutorial = page.getByRole('dialog', { name: '처음 사용 안내', exact: true });
    await page.waitForFunction(() => document.querySelector('.tutorial-progress > span')?.textContent.trim().startsWith('1 /'));
    const titles = [];
    let count = 0;
    for (let index = 0; index < 40; index += 1) {
      await tutorial.waitFor();
      const progress = (await tutorial.locator('.tutorial-progress > span').textContent()).split('/').map(Number);
      count = progress[1];
      assert.equal(progress[0], index + 1);
      const title = await tutorial.locator('.tutorial-card > strong').textContent();
      titles.push(title);
      await page.waitForFunction(() => {
        const spot = document.querySelector('.tutorial-spotlight');
        const target = spot && document.querySelector(spot.dataset.targetSelector);
        if (!target) return false;
        const rect = target.getBoundingClientRect();
        let left = Math.max(8, rect.left);
        let top = Math.max(8, rect.top);
        let right = Math.min(innerWidth - 8, rect.right);
        let bottom = Math.min(innerHeight - 8, rect.bottom);
        for (let parent = target.parentElement; parent; parent = parent.parentElement) {
          const style = getComputedStyle(parent);
          const bounds = parent.getBoundingClientRect();
          if (/^(auto|scroll|hidden|clip)$/.test(style.overflowX)) {
            left = Math.max(left, bounds.left + parent.clientLeft + 6);
            right = Math.min(right, bounds.left + parent.clientLeft + parent.clientWidth - 6);
          }
          if (/^(auto|scroll|hidden|clip)$/.test(style.overflowY)) {
            top = Math.max(top, bounds.top + parent.clientTop + 6);
            bottom = Math.min(bottom, bounds.top + parent.clientTop + parent.clientHeight - 6);
          }
        }
        const actual = spot.getBoundingClientRect();
        return right > left && bottom > top
          && Math.abs(actual.left - (left - 6)) < 2
          && Math.abs(actual.top - (top - 6)) < 2
          && Math.abs(actual.width - (right - left + 12)) < 2
          && Math.abs(actual.height - (bottom - top + 12)) < 2;
      });
      if (index === 0) {
        await page.evaluate(() => {
          const element = document.querySelector('.tutorial-spotlight');
          const watch = { element, missing: 0, removed: 0, samples: [], frame: 0, observer: null };
          watch.observer = new MutationObserver((records) => {
            for (const record of records) {
              if ([...record.removedNodes].some((node) => node === element || node.contains(element))) watch.removed += 1;
            }
          });
          watch.observer.observe(document.querySelector('.tutorial-layer'), { childList: true, subtree: true });
          const sample = () => {
            const current = document.querySelector('.tutorial-spotlight');
            if (!current || current !== element) watch.missing += 1;
            if (current) {
              const rect = current.getBoundingClientRect();
              watch.samples.push({ x: rect.x, y: rect.y });
            }
            watch.frame = requestAnimationFrame(sample);
          };
          watch.frame = requestAnimationFrame(sample);
          window.__tutorialWatch = watch;
        });
      } else {
        const continuity = await page.evaluate(() => ({
          missing: window.__tutorialWatch.missing,
          removed: window.__tutorialWatch.removed,
          same: document.querySelector('.tutorial-spotlight') === window.__tutorialWatch.element,
        }));
        assert.deepEqual(continuity, { missing: 0, removed: 0, same: true }, 'Spotlight must stay mounted between steps');
        if (mode === 'hwp' && width === 500 && index === 1) {
          assert(await page.evaluate(() => {
            const samples = window.__tutorialWatch.samples;
            const first = samples[0];
            const last = samples.at(-1);
            return first && last && samples.some((sample) =>
              Math.hypot(sample.x - first.x, sample.y - first.y) > 2
              && Math.hypot(sample.x - last.x, sample.y - last.y) > 2);
          }), 'Spotlight must move through intermediate positions instead of jumping');
        }
      }
      if (title === '서식 수동 지정') {
        assert.equal(await tutorial.locator('.tutorial-spotlight').getAttribute('data-target-selector'), '[data-tour="manual-styles"]');
        assert.equal(await page.locator('[data-tour="manual-styles"] .auto-format-group').count(), 0);
        const content = await page.locator('.content').boundingBox();
        const visibleSpot = await tutorial.locator('.tutorial-spotlight').boundingBox();
        assert(content && visibleSpot && visibleSpot.y >= content.y - 1 && visibleSpot.y + visibleSpot.height <= content.y + content.height + 1, 'Manual highlight must not include tabs or status bar');
        if (mode === 'hwp') {
          const automatic = await page.locator('.auto-format-group').boundingBox();
          const manual = await page.locator('[data-tour="manual-styles"]').boundingBox();
          const spot = await tutorial.locator('.tutorial-spotlight').boundingBox();
          assert(automatic && manual && spot && manual.y >= automatic.y + automatic.height && spot.y >= automatic.y + automatic.height);
        }
        await page.screenshot({ path: path.join(output, `tutorial-manual-styles-${mode}-${width}.png`) });
      }
      const card = await tutorial.locator('.tutorial-card').boundingBox();
      assert(card && card.x >= 0 && card.y >= 0 && card.x + card.width <= width + 1 && card.y + card.height <= height + 1);
      assert(await tutorial.locator('.tutorial-card').evaluate((element) => element.scrollWidth <= element.clientWidth));
      if (['한글과 나란히 배치', '매뉴얼 바로 열기', '설정과 내 자료 백업·복원'].includes(title)) {
        const spot = await tutorial.locator('.tutorial-spotlight').boundingBox();
        assert(spot && (card.y >= spot.y + spot.height || card.y + card.height <= spot.y || card.x >= spot.x + spot.width || card.x + card.width <= spot.x));
        if (mode === 'hwp') {
          const name = title === '한글과 나란히 배치' ? 'layout' : title === '매뉴얼 바로 열기' ? 'manual' : 'backup';
          await page.screenshot({ path: path.join(output, `tutorial-${name}-${width}.png`) });
        }
      }
      if (progress[0] === count) {
        await page.evaluate(() => {
          cancelAnimationFrame(window.__tutorialWatch.frame);
          window.__tutorialWatch.observer.disconnect();
        });
        await tutorial.getByRole('button', { name: '시작하기', exact: true }).click();
        break;
      }
      await page.evaluate(() => { window.__tutorialWatch.samples = []; });
      await tutorial.getByRole('button', { name: '다음', exact: true }).click();
    }
    assert.equal(titles.length, count);
    for (const title of ['매뉴얼 바로 열기', '즐겨찾기로 앞에 배치', '표 작업', '글자 겹치기와 문자표 순서', '설정과 내 자료 백업·복원', '업데이트 확인과 내역']) {
      assert(titles.includes(title), `Missing tutorial step: ${title}`);
    }
    assert(!titles.includes('표 그리기와 글자처럼 취급'));
    assert.equal(titles.includes('한글과 나란히 배치'), mode === 'hwp');
    assert.equal(titles.includes('전체 서식 자동 지정'), mode === 'hwp');
    assert.equal(titles.includes('여러 셀에 그림 넣기'), mode === 'hwp');
    assert.equal(titles.includes('기안창 전용 양식'), mode === 'kedufine');
    assert.equal(titles.filter((title) => title === '양식').length, mode === 'hwp' ? 1 : 0);
    await tutorial.waitFor({ state: 'hidden' });
    assert.equal(await page.locator('[data-tour="settings-backup"]').count(), 0);
    assert.equal(await page.locator('.tabs > button.is-active').innerText(), '서식');
    assert.equal(await page.locator('.content').evaluate((element) => element.scrollTop), 0);
  }
  await page.getByRole('button', { name: '편집도구', exact: true }).click();
  await page.getByRole('button', { name: '설정', exact: true }).click();
  await page.getByRole('button', { name: '튜토리얼 다시 보기', exact: true }).click();
  const tutorial = page.getByRole('dialog', { name: '처음 사용 안내', exact: true });
  for (let index = 0; index < 3; index += 1) await tutorial.getByRole('button', { name: '다음', exact: true }).click();
  await tutorial.getByRole('button', { name: '이전', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.tutorial-spotlight')?.dataset.targetSelector === '[data-tour="tabs"]');
  assert.equal(await tutorial.locator('.tutorial-card > strong').textContent(), '기능 영역 이동');
  await tutorial.getByRole('button', { name: '안내 닫기', exact: true }).click();
  assert.equal(await page.locator('.tabs > button.is-active').innerText(), '서식');
  assert.equal(await page.locator('.content').evaluate((element) => element.scrollTop), 0);
  await page.getByRole('button', { name: '양식', exact: true }).click();
  await page.getByRole('button', { name: '설정', exact: true }).click();
  await page.getByRole('button', { name: '튜토리얼 다시 보기', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.tutorial-progress > span')?.textContent.trim().startsWith('1 /'));
  assert.equal(await tutorial.locator('.tutorial-card > strong').textContent(), '작업할 한글 창 선택');
  await tutorial.getByRole('button', { name: '안내 닫기', exact: true }).click();
  assert.equal(await page.locator('.tabs > button.is-active').innerText(), '서식');
  // Viewing the tour must not insert content, move windows, or open external files.
  const requests = await page.evaluate((start) => window.__manualRequests.slice(start), requestStart);
  const documentActions = requests.filter((command) => /^(insert_|apply_|auto_format_(report|apply_role)$|table_(tool|draw)$|object_|compose_|open_manual$|user_data_(backup|restore)$)/.test(command));
  assert.deepEqual(documentActions, []);
  assert.equal(await page.evaluate(() => window.__manualLayoutCommands.length), layoutStart);
  console.log('Tutorial verified: continuous spotlight, manual-only scope, style-tab return on completion/close, both modes, 440/500px, no document actions.');
}

module.exports = { verifyTutorial };
