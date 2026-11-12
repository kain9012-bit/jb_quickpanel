// The same pointer layer guides the document and the isolated app frame.
function createPracticeCoach(container, boundary = container) {
  const layer = document.createElement('div');
  layer.className = 'practice-coach-layer';
  layer.setAttribute('aria-hidden', 'true');
  container.append(layer);
  const tag = document.createElement('div');
  tag.className = 'practice-coach-tag';
  const number = document.createElement('span');
  const caption = document.createElement('strong');
  tag.append(number, caption);
  layer.append(tag);
  let targets = [];
  let boxes = [];
  let raf;
  let active = false;
  function place() {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      if (!active) return;
      layer.hidden = false;
      const origin = layer.getBoundingClientRect();
      const limit = boundary.getBoundingClientRect();
      if (!origin.width || !limit.width) { layer.hidden = true; return; }
      const visible = targets.filter((node) => node.isConnected && node.getClientRects().length).map((node) => {
        const rect = node.getBoundingClientRect();
        return node.matches('.hwp-editable,.hwp-paper') && rect.height > 100
          ? { left: rect.left, right: rect.right, top: rect.top, bottom: rect.top + 44, width: rect.width, height: 44 } : rect;
      })
        .filter((r) => r.width && r.height && r.bottom > limit.top && r.top < limit.bottom && r.right > limit.left && r.left < limit.right);
      if (!visible.length) { layer.hidden = true; return; }
      layer.hidden = false;
      boxes.forEach((box, index) => {
        const r = visible[index];
        box.hidden = !r;
        if (!r) return;
        const left = Math.max(limit.left + 4, r.left - 4);
        const top = Math.max(limit.top + 4, r.top - 4);
        Object.assign(box.style, { left: left - origin.left + 'px', top: top - origin.top + 'px',
          width: Math.max(0, Math.min(limit.right - 4, r.right + 4) - left) + 'px',
          height: Math.max(0, Math.min(limit.bottom - 4, r.bottom + 4) - top) + 'px' });
      });
      const union = { left: Math.min(...visible.map((r) => r.left)), right: Math.max(...visible.map((r) => r.right)),
        top: Math.min(...visible.map((r) => r.top)), bottom: Math.max(...visible.map((r) => r.bottom)) };
      tag.style.maxWidth = Math.min(330, limit.width - 20) + 'px';
      const label = tag.getBoundingClientRect();
      const above = union.top - label.height - 16 >= limit.top + 8;
      const left = Math.max(limit.left + 8, Math.min(limit.right - label.width - 8, union.left - 4));
      const top = above ? union.top - label.height - 14 : Math.min(limit.bottom - label.height - 8, union.bottom + 14);
      tag.dataset.side = above ? 'above' : 'below';
      Object.assign(tag.style, { left: left - origin.left + 'px', top: top - origin.top + 'px' });
      tag.style.setProperty('--coach-arrow', Math.max(16, Math.min(label.width - 16, visible[0].left + Math.min(visible[0].width / 2, 28) - left)) + 'px');
    });
  }
  const observer = new ResizeObserver(place);
  observer.observe(boundary);
  window.addEventListener('resize', place);
  document.addEventListener('scroll', place, true);
  layer.hidden = true;
  return {
    set(nodes, text, stepNumber) {
      const previous = targets[0];
      targets.forEach((node) => observer.unobserve(node));
      targets = [...new Set(nodes)].slice(0, 8);
      if (targets[0] && targets[0] !== previous) targets[0].scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' });
      targets.forEach((node) => observer.observe(node));
      while (boxes.length < targets.length) {
        const box = document.createElement('div');
        box.className = 'practice-coach-box';
        layer.prepend(box);
        boxes.push(box);
      }
      boxes.forEach((box, i) => { box.hidden = i >= targets.length; });
      caption.textContent = text;
      number.textContent = stepNumber;
      active = targets.length > 0;
      layer.hidden = !active;
      place();
    },
    clear() { active = false; layer.hidden = true; },
    refresh: place,
    destroy() {
      observer.disconnect(); cancelAnimationFrame(raf); window.removeEventListener('resize', place);
      document.removeEventListener('scroll', place, true); layer.remove();
    },
  };
}
