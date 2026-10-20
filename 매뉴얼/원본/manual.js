const search = document.querySelector('#manual-search');
const chapters = [...document.querySelectorAll('.chapter')];
const nav = [...document.querySelectorAll('.sidebar a')];
const groupNav = [...document.querySelectorAll('.section-nav a')];
const status = document.querySelector('#search-status');
function filterChapters() {
  const query = search.value.trim().toLocaleLowerCase();
  let found = 0;
  chapters.forEach((chapter) => {
    const matches = !query || chapter.textContent.toLocaleLowerCase().includes(query);
    chapter.hidden = !matches;
    nav.find((link) => link.hash === `#${chapter.id}`).hidden = !matches;
    if (matches) found++;
  });
  status.textContent = query ? `${found}개 항목 검색${found ? '' : ' · 다른 검색어 입력'}` : '';
  document.querySelector('#clear-search').hidden = !query;
}
search.addEventListener('input', filterChapters);
document.querySelector('#clear-search').addEventListener('click', () => { search.value = ''; filterChapters(); search.focus(); });
const menu = document.querySelector('#menu-toggle');
menu.addEventListener('click', () => {
  const open = document.querySelector('.sidebar').classList.toggle('open');
  menu.setAttribute('aria-expanded', String(open));
});
function activateChapter(chapter) {
  nav.forEach((item) => {
    const active = item.hash === `#${chapter.id}`;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'location');
    else item.removeAttribute('aria-current');
  });
  groupNav.forEach((item) => {
    const active = item.dataset.group === chapter.dataset.group;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'location');
    else item.removeAttribute('aria-current');
  });
}
[...nav, ...groupNav, ...document.querySelectorAll('.quick-links a')].forEach((link) => link.addEventListener('click', () => {
  search.value = ''; filterChapters();
  activateChapter(document.querySelector(link.hash));
  document.querySelector('.sidebar').classList.remove('open');
  menu.setAttribute('aria-expanded', 'false');
}));
let scrollPending = false;
function followChapter() {
  const header = document.querySelector('.site-header').getBoundingClientRect().height;
  document.documentElement.style.setProperty('--header-height', `${header}px`);
  const visible = chapters.filter((chapter) => !chapter.hidden);
  const current = [...visible].reverse().find((chapter) => chapter.getBoundingClientRect().top <= header + 60) || visible[0];
  if (current) activateChapter(current);
  scrollPending = false;
}
window.addEventListener('scroll', () => {
  if (!scrollPending) { scrollPending = true; requestAnimationFrame(followChapter); }
}, { passive: true });
window.addEventListener('resize', followChapter);
followChapter();
const zoom = document.querySelector('#image-zoom');
document.querySelectorAll('.screen-button').forEach((button) => button.addEventListener('click', () => {
  document.querySelector('#zoom-image').src = button.querySelector('img').src;
  document.querySelector('#zoom-label').textContent = button.querySelector('img').alt;
  zoom.showModal();
}));
document.querySelector('#zoom-close').addEventListener('click', () => zoom.close());
zoom.addEventListener('click', (event) => { if (event.target === zoom) zoom.close(); });
document.querySelector('#print-manual').addEventListener('click', () => { search.value = ''; filterChapters(); window.print(); });
