const topics = [...document.querySelector('#reader-topics').content.children];
const reader = document.querySelector('.reader');
const search = document.querySelector('#reader-search');
const outline = document.querySelector('#reader-outline');
const chapters = document.querySelector('#reader-chapter');
const subtopics = document.querySelector('#reader-topic');
const title = document.querySelector('#reader-title');
const headingSection = document.querySelector('#reader-section');
const pathLabel = document.querySelector('#reader-path');
const readArea = document.querySelector('#reader-content');
const pageLabel = document.querySelector('#reader-page');
const prev = document.querySelector('#reader-prev');
const next = document.querySelector('#reader-next');
const launch = document.querySelector('#reader-practice');
const symptom = document.querySelector('#reader-symptom');
const chapterOptions = [...chapters.options].map(({ value, text }) => ({ value, text }));
let visibleTopics = topics;
let topic = null;
let pages = [];
let pageIndex = 0;
let symptomIndex = 0;

function topicForHash() {
  const id = location.hash.slice(1).replace(/-sub-(\d+)$/, '-$1');
  return topics.find((item) => item.dataset.topic === id)
    || topics.find((item) => item.dataset.chapter === id)
    || topics.find((item) => item.dataset.topic === 'start');
}
function navigate(target, last = false) {
  if (!target) return;
  const hash = `#${target.dataset.topic}`;
  if (location.hash !== hash) history.pushState(null, '', hash);
  showTopic(target, last);
  title.focus({ preventScroll: true });
}
function outlineLink(label, target, child = false) {
  const link = document.createElement('a');
  const number = document.createElement('span');
  number.className = 'reader-nav-number';
  number.textContent = child ? target.dataset.number : target.dataset.number.split('.')[0];
  const text = document.createElement('span');
  text.textContent = label.replace(/^\d+(?:\.\d+)?\.?\s+/, '');
  link.append(number, text);
  link.href = `#${target.dataset.topic}`;
  link.className = child ? 'reader-child' : 'reader-chapter-link';
  if (child ? target === topic : target.dataset.chapter === topic?.dataset.chapter) {
    link.setAttribute('aria-current', 'page');
  }
  link.addEventListener('click', (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(target);
  });
  return link;
}
const contactDialog = document.querySelector('#reader-contact-dialog');
const contactOpen = document.querySelector('.reader-contact-open');
contactOpen.addEventListener('click', () => contactDialog.showModal());
document.querySelector('#reader-contact-close').addEventListener('click', () => contactDialog.close());
contactDialog.addEventListener('close', () => contactOpen.focus({ preventScroll: true }));
function updateOutline() {
  const nodes = [];
  const options = [];
  for (const option of chapterOptions) {
    const group = visibleTopics.filter((item) => item.dataset.chapter === option.value);
    if (!group.length) continue;
    options.push(new Option(option.text, option.value));
    nodes.push(outlineLink(option.text, group[0]));
    if (topic?.dataset.chapter === option.value) {
      const children = group.filter(({ dataset }) => dataset.number.includes('.'));
      const listed = children.length > 5 ? children.filter((item) => item === topic) : children;
      for (const item of listed) {
        nodes.push(outlineLink(`${item.dataset.number} ${item.dataset.title}`, item, true));
      }
    }
  }
  outline.replaceChildren(...nodes);
  chapters.replaceChildren(...options);
  chapters.value = topic?.dataset.chapter || '';
  chapters.disabled = !options.length;
  const group = visibleTopics.filter((item) => item.dataset.chapter === topic?.dataset.chapter);
  document.querySelector('.reader-selects').classList.toggle('reader-selects-required', group.length > 5 || topic?.dataset.chapter === 'help');
  subtopics.setAttribute('aria-label', topic?.dataset.chapter === 'help' ? '겪고 있는 증상 선택' : '소항목 선택');
  subtopics.replaceChildren(...group.map(({ dataset }) => new Option(`${dataset.number} ${dataset.title}`, dataset.topic)));
  subtopics.value = topic?.dataset.topic || '';
  subtopics.hidden = group.length <= 1;
}
function renderPage() {
  readArea.replaceChildren(...(pages[pageIndex] || []));
  const topicIndex = visibleTopics.indexOf(topic);
  prev.disabled = pageIndex === 0 && topicIndex <= 0;
  next.disabled = !topic || (pageIndex >= pages.length - 1 && topicIndex >= visibleTopics.length - 1);
  pageLabel.textContent = topic ? `${pageIndex + 1} / ${pages.length}` : '';
}
function topicUnits() {
  if (!topic) return [];
  return [...topic.children].filter((unit) => topic.dataset.chapter !== 'help'
    || unit.querySelector('[data-help-index]')?.dataset.helpIndex === String(symptomIndex));
}
function paginate(last = false) {
  if (!topic || !readArea.clientHeight) return;
  const anchor = pages[pageIndex]?.[0]?.dataset.unit;
  const units = topicUnits().map((unit, index) => {
    const clone = unit.cloneNode(true);
    clone.dataset.unit = index;
    clone.dataset.sourceUnit = index;
    return clone;
  });
  const limit = readArea.clientHeight;
  const gap = parseFloat(getComputedStyle(readArea).rowGap) || 0;
  function fitUnit(unit) {
    readArea.replaceChildren(unit);
    if (Math.ceil(unit.getBoundingClientRect().height) <= limit) return [unit];
    for (const selector of ['tbody', 'ol.steps', 'ul.bullets', '.reader-topic-list']) {
      const container = unit.querySelector(selector);
      const children = [...(container?.children || [])].filter((child) => child.matches('tr, li, a'));
      if (children.length < 2) continue;
      const half = Math.ceil(children.length / 2);
      const pair = [unit.cloneNode(true), unit.cloneNode(true)];
      pair.forEach((copy, index) => {
        const contents = [...copy.querySelector(selector).children].filter((child) => child.matches('tr, li, a'));
        contents.forEach((child, i) => { if (index === 0 ? i >= half : i < half) child.remove(); });
        copy.dataset.unit += index === 0 ? 'a' : 'b';
      });
      return pair.flatMap(fitUnit);
    }
    return [unit];
  }
  const fitted = units.flatMap(fitUnit);
  readArea.replaceChildren(...fitted);
  const groups = [[]];
  let used = 0;
  for (const unit of fitted) {
    const height = Math.ceil(unit.getBoundingClientRect().height);
    if (used && used + gap + height > limit) {
      groups.push([]);
      used = 0;
    }
    groups.at(-1).push(unit);
    used += height + (used ? gap : 0);
  }
  pages = groups;
  const anchorPage = groups.findIndex((group) => group.some((unit) => unit.dataset.unit === anchor));
  pageIndex = last ? groups.length - 1 : Math.max(0, anchorPage);
  renderPage();
}
function showTopic(target, last = false) {
  topic = target || null;
  pages = [];
  pageIndex = 0;
  const data = topic?.dataset;
  headingSection.textContent = data ? `${data.number} · ${data.label}` : '';
  title.textContent = data?.title || '검색 결과 없음';
  pathLabel.textContent = data?.path || '';
  symptom.hidden = data?.chapter !== 'help';
  if (!Number.isInteger(symptomIndex) || symptomIndex < 0 || symptomIndex >= symptom.options.length) symptomIndex = 0;
  symptom.value = String(symptomIndex);
  if (!symptom.hidden) title.textContent = symptom.selectedOptions[0].textContent;
  launch.dataset.practiceOpen = data?.practice || '';
  launch.hidden = !data?.practice;
  updateOutline();
  if (topic) paginate(last);
  else renderPage();
}
function route() {
  const query = search.value.trim().toLocaleLowerCase();
  visibleTopics = topics.filter((item) => !query
    || `${item.dataset.title} ${item.dataset.label} ${item.textContent}`.toLocaleLowerCase().includes(query));
  const target = topicForHash();
  showTopic(visibleTopics.includes(target) ? target : visibleTopics[0]);
}
chapters.addEventListener('change', () => navigate(visibleTopics.find((item) => item.dataset.chapter === chapters.value)));
subtopics.addEventListener('change', () => navigate(visibleTopics.find((item) => item.dataset.topic === subtopics.value)));
search.addEventListener('input', route);
symptom.addEventListener('change', () => {
  symptomIndex = Number(symptom.value);
  title.textContent = symptom.selectedOptions[0].textContent;
  pages = [];
  paginate();
});
document.querySelector('.reader-brand').addEventListener('click', (event) => {
  event.preventDefault();
  search.value = '';
  visibleTopics = topics;
  navigate(topics.find((item) => item.dataset.topic === 'start'));
});
prev.addEventListener('click', () => {
  if (pageIndex > 0) { pageIndex--; renderPage(); }
  else navigate(visibleTopics[visibleTopics.indexOf(topic) - 1], true);
});
next.addEventListener('click', () => {
  if (pageIndex + 1 < pages.length) { pageIndex++; renderPage(); }
  else navigate(visibleTopics[visibleTopics.indexOf(topic) + 1]);
});
window.addEventListener('hashchange', route);
window.addEventListener('popstate', route);
reader.addEventListener('click', (event) => {
  const link = event.target.closest('[data-reader-link]');
  if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(topics.find((item) => '#' + item.dataset.topic === link.hash));
});
new ResizeObserver(() => paginate()).observe(readArea);
document.fonts.ready.then(() => paginate());
route();

const zoom = document.querySelector('#image-zoom');
reader.addEventListener('click', (event) => {
  const button = event.target.closest('.screen-button');
  if (!button) return;
  const source = button.querySelector('img');
  const frame = button.closest('figure');
  const enlarged = document.querySelector('#zoom-image');
  for (const key of ['--capture-width', '--capture-ratio']) {
    enlarged.style.setProperty(key, frame.style.getPropertyValue(key));
  }
  enlarged.src = source.src;
  document.querySelector('#zoom-label').textContent = source.alt;
  zoom.showModal();
});
document.querySelector('#zoom-close').addEventListener('click', () => zoom.close());
zoom.addEventListener('click', (event) => { if (event.target === zoom) zoom.close(); });
