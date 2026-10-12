import { el, button, icon, format, safeMedia } from './dom.js';

const fieldTypes = new Set(['text', 'number', 'slider', 'select', 'file', 'textarea']);
const optionNames = { bar: '柱状图', line: '折线图', chart: '图表', table: '表格', true: '是', false: '否' };
const NS = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs) => {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
};

export function allComponents(components) {
  return components.flatMap(item => [item, ...allComponents(item.children || [])]);
}

export const sensitive = name => /api[_ -]?key|password|secret|credential|(?:^|[_ -])token(?:$|[_ -])|密钥|密码|令牌/i.test(name);

export function savedSnapshot(doc, state) {
  const document = JSON.parse(JSON.stringify(doc));
  const saved = { ...state };
  for (const component of allComponents(document.components)) {
    if (['text', 'textarea'].includes(component.type) && sensitive(`${component.id} ${component.label}`)) { delete saved[component.id]; component.value = ''; }
  }
  for (const action of document.actions || []) {
    for (const parameter of action.parameters || []) {
      if (parameter.type === 'string' && sensitive(`${parameter.name} ${parameter.label}`)) { delete saved[parameterId(action, parameter)]; delete parameter.default; }
    }
  }
  return { document, state: saved };
}

export function initialState(doc, previous = {}, oldDoc) {
  const state = { ...previous };
  const old = new Map(allComponents(oldDoc?.components || []).map(item => [item.id, item]));
  for (const item of allComponents(doc.components)) {
    const changedDefault = old.has(item.id) && !sensitive(`${item.id} ${item.label}`) && JSON.stringify(old.get(item.id).value) !== JSON.stringify(item.value);
    if (!(item.id in state) || changedDefault) state[item.id] = item.value ?? '';
  }
  return state;
}

export function parseCSV(text) {
  const rows = [];
  let row = [], cell = '', quoted = false;
  const source = String(text || '').replace(/\r\n?/g, '\n');
  if (source.length > 200000) throw new Error('数据过大，请将 CSV 限制在 200 KB 内。');
  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    if (ch === '"') {
      if (quoted && source[i + 1] === '"') { cell += '"'; i++; }
      else if (!quoted && cell.trim()) throw new Error('引号必须出现在 CSV 单元格开头。');
      else quoted = !quoted;
    } else if (ch === ',' && !quoted) { row.push(cell.trim()); cell = ''; }
    else if (ch === '\n' && !quoted) { row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = ''; }
    else cell += ch;
    if (rows.length > 2000) throw new Error('最多支持 2,000 行数据。');
  }
  if (quoted) throw new Error('CSV 引号未闭合，请检查数据。');
  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  if (!rows.length) return [];
  const headers = rows.shift();
  if (new Set(headers).size !== headers.length || headers.some(header => !header || ['__proto__', 'constructor', 'prototype'].includes(header))) throw new Error('CSV 列名必须非空、唯一且有效。');
  return rows.map((values, index) => {
    if (values.length !== headers.length) throw new Error(`第 ${index + 2} 行的列数与表头不一致。`);
    return Object.fromEntries(headers.map((key, i) => [key, values[i]]));
  });
}

function numeric(value, label) {
  if (value === '' || !Number.isFinite(Number(value))) throw new Error(`${label} 必须是有效数字。`);
  return Number(value);
}

export function derivedData(doc, state) {
  let data = doc.data || [];
  if (doc.kind === 'data') {
    data = parseCSV(state.dataset);
    if (data.length && !('label' in data[0] && 'value' in data[0])) throw new Error('数据需要 label 和 value 两列。');
    data = data.map(row => ({ ...row, value: numeric(row.value, `${row.label} 的值`) }));
  }
  if (doc.kind === 'evaluation') {
    const weights = ['cost', 'quality', 'speed'].map(key => numeric(state[key], '权重'));
    if (weights.some(value => value < 0) || !weights.some(value => value > 0)) throw new Error('权重必须非负，且至少有一项大于 0。');
    const total = weights.reduce((sum, value) => sum + value, 0);
    data = parseCSV(state.scores).map(row => ({ label: row.label, value: ['cost', 'quality', 'speed'].reduce((sum, key, i) => sum + numeric(row[key], `${row.label} 的${key}评分`) * weights[i] / total, 0) })).sort((a, b) => b.value - a.value);
  }
  if (state.filter) data = data.filter(row => String(row.label ?? '').toLocaleLowerCase().includes(String(state.filter).toLocaleLowerCase()));
  return data;
}

export function chart(data, type = 'bar', title = '数据图表') {
  if (!data.length) return el('div', { class: 'empty compact' }, icon('chart', 28), el('p', {}, '没有匹配的数据'), el('span', {}, '调整筛选条件或添加数据。'));
  const values = data.map(row => Number(row.value));
  if (values.some(value => !Number.isFinite(value))) return el('p', { class: 'inline-error', role: 'alert' }, '图表的 value 必须为有效数字。');
  const width = 680, height = 278, left = 54, right = 20, top = 25, bottom = 45;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const low = Math.min(0, ...values), high = Math.max(1, ...values);
  const y = value => top + (high - value) / (high - low) * plotHeight;
  const result = svg('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': `${title}：${data.map(row => `${row.label} ${format(row.value)}`).join('，')}`, class: 'chart-svg' });
  for (let i = 0; i < 5; i++) {
    const value = low + (high - low) * i / 4;
    result.append(svg('line', { x1: left, x2: width - right, y1: y(value), y2: y(value), class: 'chart-grid' }));
    const label = svg('text', { x: left - 10, y: y(value) + 4, 'text-anchor': 'end', class: 'chart-axis' });
    label.textContent = format(value); result.append(label);
  }
  // shortcut: labels are sampled after 12 rows, use a richer chart adapter for dense analytics.
  const shown = data.slice(0, 120);
  const step = plotWidth / shown.length;
  if (type === 'line') {
    result.append(svg('polyline', { points: shown.map((row, i) => `${left + step * (i + .5)},${y(Number(row.value))}`).join(' '), class: 'chart-line', fill: 'none' }));
  }
  shown.forEach((row, i) => {
    const x = left + step * (i + .5), value = Number(row.value);
    const mark = type === 'line' ? svg('circle', { cx: x, cy: y(value), r: shown.length > 30 ? 2 : 4, class: 'chart-point' }) : svg('rect', { x: x - Math.min(step * .6, 54) / 2, y: Math.min(y(value), y(0)), width: Math.min(step * .6, 54), height: Math.max(2, Math.abs(y(value) - y(0))), rx: 4, class: i === shown.length - 1 ? 'chart-bar accent' : 'chart-bar' });
    const tooltip = svg('title', {}); tooltip.textContent = `${row.label}: ${format(value)}`; mark.append(tooltip); result.append(mark);
    if (shown.length <= 12 || i % Math.ceil(shown.length / 12) === 0) {
      const label = svg('text', { x, y: height - 15, 'text-anchor': 'middle', class: 'chart-axis' });
      label.textContent = String(row.label).slice(0, 12); result.append(label);
    }
  });
  return el('div', { class: 'chart-container' }, result, data.length > 120 ? el('p', { class: 'helper' }, '图表显示前 120 项；表格保留全部数据。') : null);
}

export function table(data) {
  if (!data.length) return el('p', { class: 'helper' }, '没有匹配的数据。');
  const columns = [...new Set(data.flatMap(row => Object.keys(row)))];
  return el('div', { class: 'table-scroll' }, el('table', {}, el('thead', {}, el('tr', {}, columns.map(key => el('th', { scope: 'col' }, key === 'label' ? '项目' : key === 'value' ? '数值' : key)))), el('tbody', {}, data.map(row => el('tr', {}, columns.map(key => el('td', {}, format(row[key]))))))));
}

export function renderDocument(container, doc, state, callbacks) {
  container.replaceChildren();
  container.dataset.kind = doc.kind;
  const dynamic = [], metrics = new Map();
  const value = item => state[item.id] ?? item.value ?? '';
  const change = (item, next) => { state[item.id] = next; callbacks.change(item.id, next); update(); };
  const inputs = el('div', { class: 'input-grid' });
  const outputs = el('div', { class: 'output-grid' });
  const uploadField = item => {
    const details = el('span', { class: 'file-name' }, typeof value(item) === 'string' && value(item) ? value(item).split(/[\\/]/).pop() : '支持图片、PDF、音视频和数据文件');
    const field = el('input', { id: `field-${item.id}`, type: 'file', 'aria-label': item.label, onchange: async event => {
      const file = event.target.files[0];
      if (!file) return;
      try {
        field.disabled = true; details.textContent = '正在导入…';
        const result = await callbacks.upload(file, item.id);
        details.textContent = `${result.name} · ${format(Math.round(result.size / 1024))} KB`;
        change(item, result.path);
      } catch (error) { details.textContent = error.message; callbacks.error(error.message); }
      finally { field.disabled = false; }
    } });
    return el('div', { class: 'field file-field' }, el('label', { for: field.id }, item.label), el('div', { class: 'file-drop' }, icon('file', 28), el('strong', {}, '选择本地文件'), details, field));
  };
  function component(item) {
    if (item.type === 'group') {
      const group = el('details', { class: 'component-group', open: item.id !== 'advanced' }, el('summary', {}, item.label));
      const children = el('div', { class: 'input-grid group-body' });
      item.children?.forEach(child => children.append(component(child)));
      group.append(children); return group;
    }
    if (item.type === 'file') return uploadField(item);
    if (fieldTypes.has(item.type)) {
      const attrs = { id: `field-${item.id}`, 'data-component': item.id, value: value(item), 'aria-label': item.label };
      let control;
      if (item.type === 'textarea' && !sensitive(`${item.id} ${item.label}`)) control = el('textarea', { ...attrs, rows: item.id === 'dataset' || item.id === 'scores' ? 7 : 4, spellcheck: 'false', oninput: event => change(item, event.target.value) });
      else if (item.type === 'select') control = el('select', { ...attrs, onchange: event => change(item, event.target.value) }, (item.options || []).map(option => el('option', { value: option, selected: String(option) === String(value(item)) }, optionNames[option] || option)));
      else control = el('input', { ...attrs, type: item.type === 'slider' ? 'range' : item.type === 'number' ? 'number' : sensitive(`${item.id} ${item.label}`) ? 'password' : 'text', min: item.min, max: item.max, step: item.step ?? 'any', placeholder: item.id === 'filter' ? '输入项目名称…' : null, oninput: event => change(item, item.type === 'number' || item.type === 'slider' ? event.target.value === '' ? '' : Number(event.target.value) : event.target.value) });
      const label = el('label', { for: attrs.id }, item.label);
      if (item.type === 'slider') {
        const output = el('output', { for: attrs.id, class: 'range-value' }, format(value(item)));
        label.append(output);
        control.addEventListener('input', () => { output.textContent = format(value(item)); });
      }
      return el('div', { class: `field ${item.type === 'textarea' ? 'wide' : ''}` }, label, control, control.type === 'password' ? el('p', { class: 'helper' }, '仅本次会话使用，不随界面保存。') : null, item.type === 'slider' ? el('div', { class: 'range-extents' }, el('span', {}, item.min ?? 0), el('span', {}, item.max ?? 100)) : null);
    }
    if (item.type === 'metric') {
      const output = el('output', { class: 'metric-value', 'data-testid': item.id, 'aria-live': 'polite' }, item.expression ? '—' : format(value(item)));
      metrics.set(item.id, output);
      return el('section', { class: 'metric-card' }, el('span', { class: 'metric-label' }, item.label), output, el('span', { class: 'metric-detail' }, item.expression ? '随输入实时计算' : '当前结果'));
    }
    if (item.type === 'chart' || item.type === 'table') {
      const content = el('div');
      const wrapper = el('section', { class: `output-card ${item.type}-card` }, el('div', { class: 'card-heading' }, el('h3', {}, item.label), el('span', { class: 'data-count' })), content);
      dynamic.push(() => {
        try {
          const data = derivedData(doc, state);
          wrapper.hidden = doc.kind === 'data' && ((item.type === 'chart' && state.view === 'table') || (item.type === 'table' && state.view !== 'table'));
          wrapper.querySelector('.data-count').textContent = `${data.length} 项`;
          content.replaceChildren(item.type === 'chart' ? chart(data, state.chart_type || 'bar', item.label) : table(data));
        } catch (error) { content.replaceChildren(el('p', { class: 'inline-error', role: 'alert' }, error.message)); }
      });
      return wrapper;
    }
    if (item.type === 'timeline' || item.type === 'diagram') {
      const content = el('div', { class: item.type === 'timeline' ? 'timeline' : 'diagram' });
      dynamic.push(() => {
        const entries = state.steps != null ? String(state.steps).split('\n').filter(line => line.trim()) : Array.isArray(item.value) ? item.value.map(String) : ['配置输入', '执行操作', '查看结果'];
        content.replaceChildren(...entries.map((entry, index) => {
          if (item.type === 'diagram') {
            const [name, ...explanation] = entry.split('|');
            return el('details', { class: 'diagram-step', open: !!state[`expanded:${item.id}:${entry}`], ontoggle: event => { state[`expanded:${item.id}:${entry}`] = event.target.open; callbacks.persist(); } }, el('summary', {}, el('span', { class: 'step-number' }, String(index + 1).padStart(2, '0')), el('strong', {}, name.trim()), icon('arrow', 15)), el('p', {}, explanation.join('|').trim() || '完成此步骤后继续下一项。'));
          }
          const key = `done:${item.id}:${entry}`;
          return el('label', { class: `timeline-step ${state[key] ? 'completed' : ''}` }, el('input', { type: 'checkbox', checked: !!state[key], onchange: event => { state[key] = event.target.checked; event.target.closest('label').classList.toggle('completed', event.target.checked); callbacks.persist(); } }), el('span', { class: 'timeline-dot' }), el('span', {}, entry));
        }));
      });
      return el('section', { class: 'output-card' }, el('h3', {}, item.label), content);
    }
    if (item.type === 'log') return el('section', { class: 'output-card' }, el('h3', {}, item.label), el('pre', { class: 'log-output', 'data-log': item.id }, value(item) || '等待执行。导入 Skill 并启动任务后，这里会显示真实日志。'));
    if (item.type === 'progress') return el('section', { class: 'output-card progress-card' }, el('h3', {}, item.label), el('progress', { max: 100, value: Number(value(item)) || 0, 'aria-label': item.label, 'data-progress': item.id }), el('span', { class: 'helper', 'data-progress-status': '' }, '尚未运行'));
    if (item.type === 'media') {
      const content = el('div', { class: 'media-preview' });
      dynamic.push(() => {
        const preview = callbacks.preview();
        const url = safeMedia(preview?.url || value(item));
        if (preview?.text != null) { content.replaceChildren(el('pre', { class: 'text-preview' }, preview.text)); return; }
        if (!url) { content.replaceChildren(icon('file', 30), el('p', {}, '选择文件后在这里预览'), el('span', { class: 'helper' }, '图片、PDF、音频与视频可直接查看。')); return; }
        let media;
        if (preview?.type.startsWith('image/')) media = el('img', { src: url, alt: preview.name });
        else if (preview?.type.startsWith('audio/')) media = el('audio', { src: url, controls: true, 'aria-label': preview.name });
        else if (preview?.type.startsWith('video/')) media = el('video', { src: url, controls: true, 'aria-label': preview.name });
        else if (preview?.type === 'application/pdf') media = el('div', { class: 'pdf-container' }, el('iframe', { src: url, title: `PDF 预览：${preview.name}`, sandbox: 'allow-scripts', class: 'pdf-preview' }), el('a', { href: url, target: '_blank', rel: 'noopener', class: 'text-button' }, '在新标签页打开 PDF'));
        else media = el('p', {}, `${preview?.name || '文件'}已导入，此格式暂不支持直接预览。`);
        content.replaceChildren(media);
      });
      return el('section', { class: 'output-card' }, el('h3', {}, item.label), content);
    }
    if (item.type === 'action') return button(item.label, { class: 'button primary', onclick: () => callbacks.action(item) }, 'play');
    return el('div', { class: 'text-component' }, el('h3', {}, item.label), el('p', {}, typeof value(item) === 'string' ? value(item) : format(value(item))));
  }
  for (const item of doc.components) (fieldTypes.has(item.type) || item.type === 'group' ? inputs : outputs).append(component(item));
  if (inputs.childElementCount) container.append(el('section', { class: 'inputs-card' }, el('div', { class: 'section-caption' }, icon('settings', 15), '调整输入', el('span', { class: 'caption-hint' }, '修改后自动更新')), inputs));
  if (outputs.childElementCount) container.append(outputs);
  const update = () => dynamic.forEach(callback => callback());
  update();
  return {
    update,
    metrics: result => { for (const [id, output] of metrics) output.textContent = format(result[id]); },
    evaluationError: message => { for (const output of metrics.values()) { output.textContent = '—'; output.title = message; } },
    job: job => {
      container.querySelectorAll('[data-log]').forEach(node => { node.textContent = job.logs.join('\n') || '任务已启动，等待日志…'; });
      container.querySelectorAll('[data-progress]').forEach(node => { node.value = job.progress || 0; if (job.status === 'running' && !job.progress) node.removeAttribute('value'); });
      container.querySelectorAll('[data-progress-status]').forEach(node => { node.textContent = job.status === 'running' && !job.progress ? '正在运行 · 尚无可测量的进度' : `${job.status} · ${job.progress || 0}%`; });
    },
  };
}

export function parameterId(action, parameter) {
  return `p_${(action.id + '_' + parameter.name).replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 61)}`;
}

export function actionForm(capability, state, callbacks) {
  return el('div', { class: 'skill-actions' }, capability.actions.map(action => {
    const form = el('form', { class: 'action-form', 'data-action': action.id });
    form.append(el('div', { class: 'action-heading' }, el('h3', {}, action.label), el('span', { class: `badge ${action.status === 'ready' ? 'ready' : ''}` }, ({ ready: '可执行', missing_dependency: '缺少依赖', needs_configuration: '等待配置', guide: '操作向导' })[action.status])));
    if (action.description) form.append(el('p', { class: 'helper' }, action.description));
    const fields = el('div', { class: 'input-grid' });
    for (const parameter of action.parameters || []) {
      const id = parameterId(action, parameter);
      if (!(id in state)) state[id] = parameter.default ?? (parameter.type === 'boolean' ? false : '');
      let control;
      const attrs = { id: `param-${id}`, name: parameter.name, required: parameter.required && parameter.type !== 'boolean', value: state[id], 'data-parameter': parameter.name };
      if (parameter.type === 'boolean') control = el('input', { ...attrs, type: 'checkbox', checked: state[id] === true || state[id] === 'true', onchange: event => { state[id] = event.target.checked; callbacks.persist(); } });
      else if (parameter.type === 'choice') control = el('select', { ...attrs, onchange: event => { state[id] = event.target.value; callbacks.persist(); } }, (parameter.choices || []).map(choice => el('option', { value: choice, selected: choice === state[id] }, choice)));
      else control = el('input', { ...attrs, type: ['number', 'integer'].includes(parameter.type) ? 'number' : parameter.type === 'string' && sensitive(`${parameter.name} ${parameter.label}`) ? 'password' : 'text', step: parameter.type === 'integer' ? 1 : 'any', autocomplete: 'off', placeholder: parameter.type === 'file' ? '输入文件路径，或选择文件' : parameter.type === 'directory' ? '输入目录路径' : '', oninput: event => { state[id] = ['number', 'integer'].includes(parameter.type) && event.target.value !== '' ? Number(event.target.value) : event.target.value; callbacks.persist(); } });
      const field = el('div', { class: `field ${parameter.type === 'boolean' ? 'checkbox-field' : ''}` }, el('label', { for: control.id }, parameter.label || parameter.name, parameter.required ? el('span', { class: 'required', 'aria-label': '必填' }, ' *') : null), control);
      if (control.type === 'password') field.append(el('p', { class: 'helper' }, '仅本次会话使用，不随界面保存。'));
      if (parameter.type === 'file') {
        const upload = el('input', { type: 'file', 'aria-label': `上传${parameter.label || parameter.name}`, onchange: async event => {
          const file = event.target.files[0]; if (!file) return;
          try { upload.disabled = true; const result = await callbacks.upload(file, id); state[id] = result.path; control.value = result.path; callbacks.persist(); }
          catch (error) { callbacks.error(error.message); } finally { upload.disabled = false; }
        } });
        field.append(upload);
      }
      fields.append(field);
    }
    form.append(fields);
    if (action.status !== 'ready') {
      form.append(el('div', { class: 'notice' }, icon('info'), el('div', {}, action.status === 'guide' ? '此 Skill 提供操作说明，没有已注册的脚本入口。请按右侧说明操作。' : action.status === 'missing_dependency' ? `先安装所需依赖：${(action.dependencies || []).join('、') || action.interpreter || '查看 Skill 使用说明'}。安装后重新导入 Skill。` : '此操作需要额外配置。查看右侧 Skill 使用说明，完成环境与凭据配置后重新导入。')));
    } else form.append(button('运行操作', { type: 'submit', class: 'button primary' }, 'play'));
    form.addEventListener('submit', event => {
      event.preventDefault();
      const args = Object.fromEntries((action.parameters || []).map(parameter => [parameter.name, state[parameterId(action, parameter)]]).filter(([, input]) => input !== '' && input != null));
      callbacks.run(action, args, form);
    });
    return form;
  }));
}
