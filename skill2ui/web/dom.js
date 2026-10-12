export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'checked' || key === 'disabled' || key === 'hidden') node[key] = !!value;
    else if (key === 'value') node.value = value;
    else node.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const paths = {
  spark: 'M12 3l2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3z',
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  layers: 'M12 3L2 8l10 5 10-5-10-5z M2 12l10 5 10-5 M2 16l10 5 10-5',
  plus: 'M12 5v14 M5 12h14',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  calculator: 'M5 2h14v20H5z M8 6h8 M8 11h1 M15 11h1 M8 15h1 M15 15h1 M8 19h1 M15 19h1',
  chart: 'M4 3v17h17 M8 15V9 M13 15V5 M18 15v-4',
  diagram: 'M9 2h6v6H9z M2 16h6v6H2z M16 16h6v6h-6z M12 8v4 M5 16v-4h14v4',
  plan: 'M8 5h13 M8 12h13 M8 19h13 M2 5l1 1 2-2 M2 12l1 1 2-2 M2 19l1 1 2-2',
  file: 'M6 2h8l5 5v15H6z M14 2v6h5 M9 13h7 M9 17h7',
  scale: 'M12 3v18 M6 21h12 M4 7h16 M6 7l-4 7h8L6 7z M18 7l-4 7h8l-4-7z',
  workflow: 'M3 3h6v6H3z M15 15h6v6h-6z M9 6h9v9 M3 18h8 M8 15l3 3-3 3',
  folder: 'M3 6h7l2 3h9v11H3z',
  settings: 'M10 3h4l.6 3 2 1.2 2.8-1 2 3.4-2.2 2v2.4l2.2 2-2 3.4-2.8-1-2 1.2-.6 3h-4l-.6-3-2-1.2-2.8 1-2-3.4 2.2-2v-2.4l-2.2-2 2-3.4 2.8 1 2-1.2.6-3z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  moon: 'M20 15a8 8 0 0 1-11-11 9 9 0 1 0 11 11z',
  sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10 M12 1v3 M12 20v3 M1 12h3 M20 12h3 M4 4l2 2 M18 18l2 2 M4 20l2-2 M18 6l2-2',
  save: 'M4 3h14l3 3v15H3V3z M7 3v6h10V3 M7 21v-8h10v8',
  close: 'M5 5l14 14 M5 19L19 5',
  check: 'M4 12l5 5L20 6',
  play: 'M7 3l14 9-14 9V3z',
  download: 'M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 11v6 M12 7h.01',
  menu: 'M3 5h18 M3 12h18 M3 19h18',
};

export function icon(name, size = 18) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.6');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  path.setAttribute('d', paths[name] || paths.grid);
  svg.append(path);
  return svg;
}

export function button(text, attrs = {}, glyph) {
  return el('button', { type: 'button', ...attrs }, glyph ? icon(glyph) : null, text);
}

export function format(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value) : '—';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value ?? '—');
}

export function safeMedia(url) {
  if (typeof url !== 'string') return null;
  if (url.startsWith('blob:')) return url;
  try {
    const parsed = new URL(url, location.origin);
    return parsed.origin === location.origin && /^\/api\/(artifacts|uploads)\//.test(parsed.pathname) ? parsed.href : null;
  } catch { return null; }
}
