import { el, button, icon, format } from './dom.js';
import { renderDocument, initialState, allComponents, actionForm, savedSnapshot } from './render.js';

const STORAGE = 'skill2ui.workspace.v1';
const demos = [
  ['calculator', 'AA 费用计算器', '多人 AA 费用计算器，包含总金额、人数和小费比例'],
  ['chart', '数据探索', '生成可以筛选、编辑 CSV、切换表格与图表的数据分析界面'],
  ['diagram', '技术图解', '用交互式结构图讲解 Skill2UI 从输入到执行的原理'],
  ['plan', '行动计划', '创建一天的行动计划，包含可编辑步骤与完成清单'],
  ['file', '文件工作台', '创建支持文件上传和预览的文件处理界面'],
  ['scale', '方案评估', '创建多维度方案评估界面，可以调整成本、质量和速度权重'],
  ['workflow', '工作流', '创建真实 Skill 任务的工作流控制台'],
];
const statusNames = { queued: '等待执行', running: '正在运行', succeeded: '执行成功', failed: '执行失败', cancelled: '已取消' };
let token, currentDoc, state = {}, render, skills = [], documents = [], model = {}, mode = 'local';
let busy = false, evaluationSequence = 0, evaluationTimer, persistTimer, currentJob, jobTimer, lastRun, preview;
let theme = localStorage.getItem('skill2ui.theme') || 'light';
let toastTimer;
const root = document.getElementById('app');
const dialog = document.getElementById('dialog');
const toast = document.getElementById('toast');
const refs = {};

function notify(message, error = false) {
  toast.textContent = message;
  toast.classList.toggle('error', error);
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, error ? 8000 : 4200);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('X-Skill2UI-Token', token);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    const detail = result.detail || result.error;
    const message = Array.isArray(detail) ? detail.map(item => `${item.loc?.slice(-1)[0] || '输入'}：${item.msg}`).join('；') : typeof detail === 'string' ? detail : `请求未完成 (${response.status})。请检查输入后重试。`;
    throw new Error(message);
  }
  return response;
}
const json = async (path, options = {}) => (await api(path, options)).json();

function setTheme(next) {
  theme = next;
  document.documentElement.dataset.theme = next;
  refs.theme?.replaceChildren(icon(next === 'dark' ? 'sun' : 'moon'));
  refs.theme?.setAttribute('aria-label', next === 'dark' ? '切换浅色主题' : '切换深色主题');
  localStorage.setItem('skill2ui.theme', next);
  if (currentDoc) { currentDoc.theme = next; persist(); }
}

function persist() {
  clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    if (!currentDoc) return;
    try { localStorage.setItem(STORAGE, JSON.stringify({ ...savedSnapshot(currentDoc, state), mode, lastJobId: currentJob?.id })); }
    catch { notify('浏览器保存空间不足。请使用“保存界面”保存在本地运行时。', true); }
  }, 200);
}

function error(message) { notify(message, true); }

function buildShell() {
  const logo = el('a', { class: 'brand', href: '/', 'aria-label': 'Skill2UI 首页' }, el('img', { src: '/static/icon.svg', alt: '', width: 32, height: 32 }), el('span', {}, 'Skill', el('b', {}, '2'), 'UI'));
  refs.theme = button('', { class: 'icon-button', onclick: () => setTheme(theme === 'light' ? 'dark' : 'light') }, 'moon');
  refs.modelStatus = el('span', { class: 'model-status' }, '本地模式');
  refs.sidebar = el('aside', { class: 'sidebar', 'aria-label': '界面与 Skill 库' });
  const menu = button('', { class: 'icon-button mobile-menu', 'aria-label': '打开界面与 Skill 库', 'aria-expanded': false, onclick: () => { const open = refs.sidebar.classList.toggle('mobile-open'); menu.setAttribute('aria-expanded', open); } }, 'menu');
  const header = el('header', { class: 'app-header' }, el('div', { class: 'header-left' }, menu, logo, el('span', { class: 'header-divider' }), el('span', { class: 'workspace-name' }, '个人工作区')), el('div', { class: 'header-actions' }, el('span', { class: 'local-indicator' }, el('i'), '本地运行'), button('', { class: 'icon-button', 'aria-label': '模型设置', title: '模型设置', onclick: modelDialog }, 'settings'), refs.theme));
  refs.library = el('div', { class: 'skill-library' });
  refs.saved = el('div', { class: 'saved-library' });
  refs.sidebar.append(el('div', { class: 'sidebar-intro' }, el('span', { class: 'eyebrow' }, 'YOUR WORKBENCH'), el('h2', {}, '能力，触手可及。'), el('p', {}, '描述需求，或导入一个 Skill。')), button('新建界面', { class: 'button sidebar-new', onclick: newDocument }, 'plus'), el('div', { class: 'nav-label' }, '从一个场景开始'), el('nav', { class: 'demo-nav', 'aria-label': '示例场景' }, demos.map(([glyph, label, prompt]) => button(label, { class: 'nav-item', 'data-demo': glyph, onclick: () => generate(prompt, true) }, glyph))), el('div', { class: 'nav-label library-label' }, 'SKILL 库', button('', { class: 'icon-button small', 'aria-label': '导入 Skill', 'data-testid': 'skill-import', onclick: importDialog }, 'plus')), refs.library, el('div', { class: 'nav-label' }, '已保存的界面'), refs.saved, el('div', { class: 'sidebar-footer' }, el('span', { class: 'version-label' }, 'Skill2UI', el('span', {}, 'v0.1')), el('p', {}, '由意图出发，连接真实能力。')));
  refs.title = el('h1', {}, '把想法，变成可操作的界面。');
  refs.description = el('p', {}, '输入一个需求，选择适合任务的组件，直接开始操作。');
  refs.kind = el('span', { class: 'badge' }, '工作台');
  refs.mode = el('span', { class: 'generation-mode' }, '本地模板');
  refs.canvas = el('div', { id: 'canvas', class: 'canvas', tabindex: '-1', 'data-testid': 'canvas' });
  refs.prompt = el('textarea', { id: 'prompt', rows: 2, maxlength: 12000, 'data-testid': 'prompt', 'aria-label': '描述你的需求或修改当前界面', placeholder: '描述你需要的界面，例如：生成一个多人 AA 费用计算器…' });
  refs.prompt.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); generate(refs.prompt.value); } });
  refs.generate = button('生成界面', { class: 'button primary', 'data-testid': 'generate', onclick: () => generate(refs.prompt.value) }, 'spark');
  refs.composerHelp = el('span', { class: 'composer-help' }, '用自然语言描述 · Ctrl + Enter 生成');
  refs.save = button('保存界面', { class: 'button secondary', 'data-testid': 'save', onclick: saveDocument, disabled: true }, 'save');
  const composer = el('section', { class: 'composer', 'aria-label': '自然语言生成' }, el('div', { class: 'composer-icon' }, icon('spark', 22)), el('div', { class: 'composer-body' }, refs.prompt, el('div', { class: 'composer-bottom' }, refs.composerHelp, refs.generate)));
  refs.stream = el('div', { class: 'stream-status', role: 'status', 'aria-live': 'polite', hidden: true });
  const workspace = el('main', { class: 'workspace' }, el('div', { class: 'workspace-top' }, el('div', {}, el('div', { class: 'breadcrumb' }, '工作区', el('span', {}, '/'), el('span', {}, '界面画布')), refs.title, refs.description), refs.save), composer, refs.stream, el('div', { class: 'canvas-top' }, el('div', { class: 'canvas-tab' }, icon('grid', 16), '交互界面', refs.kind), el('div', { class: 'canvas-state' }, el('span', { class: 'live-dot' }), refs.mode)), refs.canvas, el('footer', { class: 'canvas-footer' }, icon('check', 13), '输入自动保存 · 执行操作需单独确认'));
  refs.inspector = el('aside', { class: 'inspector', 'aria-label': '运行与界面信息' });
  root.append(header, el('div', { class: 'app-shell' }, refs.sidebar, workspace, refs.inspector));
  showInspector();
  setTheme(theme);
}

function showLibraries() {
  refs.library.replaceChildren(...(skills.length ? skills.map(skill => button(skill.name, { class: `nav-item skill-item ${currentDoc?.skill_id === skill.id ? 'active' : ''}`, title: skill.description, 'data-skill': skill.id, onclick: () => openSkill(skill) }, ({ video: 'play', pdf: 'file', data: 'chart', automation: 'workflow' })[skill.domain] || 'layers')) : [el('p', { class: 'library-empty' }, '导入 Skill，生成专属操作界面。'), button('导入 Skill', { class: 'text-button', onclick: importDialog }, 'plus')]));
  refs.saved.replaceChildren(...(documents.length ? documents.map(doc => button(doc.title, { class: 'nav-item saved-item', onclick: () => restoreDocument(doc.id) }, 'folder')) : [el('p', { class: 'library-empty' }, '保存后的界面会显示在这里。')]));
  refs.sidebar.querySelectorAll('[data-demo]').forEach(node => node.classList.toggle('active', ({ calculator: 'calculator', data: 'chart', diagram: 'diagram', plan: 'plan', files: 'file', evaluation: 'scale', workflow: 'workflow' })[currentDoc?.kind] === node.dataset.demo));
}

function showDocument(doc, restoredState = {}, oldDoc) {
  currentDoc = doc;
  state = initialState(doc, restoredState, oldDoc);
  refs.title.textContent = doc.title;
  refs.description.textContent = doc.description;
  refs.kind.textContent = ({ calculator: '计算器', data: '数据', diagram: '图解', plan: '计划', files: '文件', evaluation: '评估', workflow: '工作流', skill: 'Skill' })[doc.kind] || '界面';
  refs.mode.textContent = mode === 'model' ? '模型生成' : '本地模板';
  refs.save.disabled = false;
  refs.generate.replaceChildren(icon('spark'), '修改界面');
  refs.prompt.placeholder = '继续修改：把页面改成深色主题、增加参数滑块、折叠高级设置…';
  refs.composerHelp.textContent = '继续描述修改 · 当前输入会保留';
  const capability = skills.find(skill => skill.id === doc.skill_id);
  const callbacks = { change: () => { persist(); evaluate(); }, persist, upload, error, preview: () => preview, action: item => {
    const action = capability?.actions.find(action => action.id === item.id || action.id === item.value);
    if (action) prepareAction(capability, action, {}, null);
    else notify('此组件没有连接已注册的 Skill 操作。请导入可执行 Skill。', true);
  } };
  render = renderDocument(refs.canvas, doc, state, callbacks);
  if (capability) {
    refs.canvas.querySelector('.inputs-card')?.remove();
    refs.canvas.prepend(actionForm(capability, state, { ...callbacks, run: (action, args, form) => prepareAction(capability, action, args, form) }));
  }
  if (doc.kind === 'workflow' && !capability) refs.canvas.append(el('div', { class: 'notice' }, icon('info'), el('div', {}, el('strong', {}, '连接一个 Skill，让工作流真正运行。'), el('p', {}, '选择或导入可执行 Skill 后，配置参数并确认运行。')), button('导入 Skill', { class: 'button secondary', onclick: importDialog }, 'plus')));
  if (doc.theme !== oldDoc?.theme) setTheme(doc.theme || theme);
  if (currentJob && (currentJob.skill_id === doc.skill_id || doc.kind === 'workflow')) render.job(currentJob);
  showLibraries(); showInspector(); evaluate(); persist();
  refs.sidebar.classList.remove('mobile-open');
}

function evaluate() {
  const sequence = ++evaluationSequence;
  clearTimeout(evaluationTimer);
  if (!currentDoc || !allComponents(currentDoc.components).some(component => component.type === 'metric' && component.expression)) return;
  evaluationTimer = setTimeout(async () => {
    try {
      const result = await json('/api/evaluate', { method: 'POST', body: { document: currentDoc, state } });
      if (sequence === evaluationSequence) { render.metrics(result.metrics); refs.canvas.querySelector('.evaluation-error')?.remove(); }
    } catch (error) {
      if (sequence !== evaluationSequence) return;
      render.evaluationError(error.message);
      let message = refs.canvas.querySelector('.evaluation-error');
      if (!message) { message = el('p', { class: 'inline-error evaluation-error', role: 'alert' }); refs.canvas.append(message); }
      message.textContent = error.message;
    }
  }, 140);
}

async function streamGeneration(body) {
  const response = await api('/api/generate/stream', { method: 'POST', body });
  if (!response.headers.get('content-type')?.includes('text/event-stream')) return response.json();
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '', result, count = 0;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n');
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const part = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      const event = part.split('\n').find(line => line.startsWith('event:'))?.slice(6).trim();
      const data = part.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === 'component') {
        count++;
        refs.stream.textContent = `正在构建界面 · 已接收 ${count} 个组件`;
        const item = payload.component || payload;
        refs.stream.append(el('span', { class: 'stream-component' }, `${item.label || item.type}`));
      }
      if (event === 'document') result = payload.document ? payload : { document: payload, mode: 'local' };
      if (event === 'error') throw new Error(payload.detail || payload.message || '界面生成失败，请重试。');
    }
    if (done) break;
  }
  if (!result) throw new Error('生成流中断，请重试。当前界面与输入已保留。');
  return result;
}

async function generate(prompt, fresh = false) {
  if (busy) return;
  if (!String(prompt).trim()) { refs.prompt.focus(); notify('先描述需要生成或修改的界面。', true); return; }
  busy = true;
  refs.generate.disabled = true;
  refs.generate.replaceChildren(el('span', { class: 'spinner' }), '正在生成');
  refs.stream.hidden = false; refs.stream.textContent = '正在理解需求…';
  const oldDoc = fresh ? null : currentDoc;
  const oldState = fresh ? {} : state;
  try {
    const body = { prompt, ...(oldDoc ? savedSnapshot(oldDoc, oldState) : {}) };
    const result = await streamGeneration(body);
    mode = result.mode;
    if (fresh && preview?.url) { URL.revokeObjectURL(preview.url); preview = null; }
    showDocument(result.document, oldState, oldDoc);
    refs.prompt.value = '';
    if (result.warning) notify(result.warning, true);
    else notify(oldDoc ? '界面已更新，当前输入已保留。' : '界面已生成，可以直接操作。');
  } catch (err) { error(err.message); }
  finally {
    busy = false; refs.generate.disabled = false; refs.stream.hidden = true;
    refs.generate.replaceChildren(icon('spark'), currentDoc ? '修改界面' : '生成界面');
  }
}

function newDocument() {
  currentDoc = null; state = {}; render = null;
  ++evaluationSequence; clearTimeout(evaluationTimer);
  localStorage.removeItem(STORAGE);
  refs.title.textContent = '把想法，变成可操作的界面。';
  refs.description.textContent = '从一个问题，到一个真正能用的工具。';
  refs.kind.textContent = '新界面'; refs.save.disabled = true;
  refs.prompt.value = ''; refs.prompt.placeholder = '描述你需要的界面，例如：生成一个多人 AA 费用计算器…';
  refs.generate.replaceChildren(icon('spark'), '生成界面');
  refs.composerHelp.textContent = '用自然语言描述 · Ctrl + Enter 生成';
  refs.canvas.replaceChildren(el('div', { class: 'welcome' }, el('div', { class: 'welcome-symbol' }, icon('layers', 36)), el('span', { class: 'eyebrow' }, 'FROM INTENT TO INTERFACE'), el('h2', {}, '你的下一件工具，', el('br'), '从一句话开始。'), el('p', {}, '计算、分析、规划，或把已有的 Skill 变成专属工作台。'), el('div', { class: 'welcome-examples' }, demos.slice(0, 3).map(([glyph, label, prompt]) => button(label, { class: 'button secondary', onclick: () => generate(prompt, true) }, glyph)))));
  showLibraries(); showInspector(); refs.prompt.focus();
}

async function saveDocument() {
  if (!currentDoc) return;
  refs.save.disabled = true;
  try {
    await json('/api/documents', { method: 'POST', body: savedSnapshot(currentDoc, state) });
    const index = documents.findIndex(doc => doc.id === currentDoc.id);
    if (index >= 0) documents[index] = currentDoc; else documents.unshift(currentDoc);
    showLibraries(); notify('界面与输入已保存到本地运行时。');
  } catch (err) { error(err.message); }
  finally { refs.save.disabled = false; }
}

async function restoreDocument(id) {
  try { const result = await json(`/api/documents/${encodeURIComponent(id)}`); showDocument(result.document, result.state); notify('界面与输入已恢复。'); }
  catch (err) { error(err.message); }
}

async function upload(file) {
  const data = new FormData(); data.append('file', file);
  const result = await json('/api/uploads', { method: 'POST', body: data });
  if (preview?.url) URL.revokeObjectURL(preview.url);
  const mediaTypes = /^(image\/(png|jpeg|webp|gif|bmp)|audio\/|video\/|application\/pdf)/;
  // shortcut: previews use this browser session's file blob; reload requires selecting the file again.
  preview = { url: mediaTypes.test(file.type) ? URL.createObjectURL(file) : null, type: file.type, name: file.name };
  if ((file.type.startsWith('text/') || /\.(csv|txt|json|md)$/i.test(file.name)) && file.size < 200000) preview.text = await file.text();
  render?.update(); return result;
}

function modal(title, subtitle, content) {
  if (dialog.open) dialog.close();
  dialog.replaceChildren(el('div', { class: 'dialog-heading' }, el('div', {}, el('h2', {}, title), el('p', {}, subtitle)), button('', { class: 'icon-button', 'aria-label': '关闭对话框', onclick: () => dialog.close() }, 'close')), content);
  dialog.showModal();
}
dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });

function importDialog() {
  let selected = 'path';
  let installed = [];
  const tabs = el('div', { class: 'dialog-tabs', role: 'tablist', 'aria-label': 'Skill 导入来源' });
  const form = el('form');
  const fields = el('div');
  const message = el('p', { class: 'inline-error', role: 'alert', hidden: true });
  const submit = button('导入并生成界面', { type: 'submit', class: 'button primary', 'data-testid': 'import-submit' }, 'arrow');
  const updateFields = () => {
    tabs.querySelectorAll('button').forEach(node => { node.classList.toggle('active', node.dataset.tab === selected); node.setAttribute('aria-selected', node.dataset.tab === selected); });
    const label = ({ path: 'Skill 目录或 SKILL.md 路径', github: 'GitHub 仓库地址', archive: 'Skill ZIP 压缩包' })[selected];
    const input = el('input', { id: 'import-source', name: 'source', type: selected === 'archive' ? 'file' : selected === 'github' ? 'url' : 'text', required: true, accept: selected === 'archive' ? '.zip' : null, placeholder: selected === 'path' ? '例如 C:\\Users\\you\\.codex\\skills\\my-skill' : 'https://github.com/owner/repository', 'data-testid': 'import-path' });
    const picker = selected === 'path' && installed.length ? el('div', { class: 'field installed-picker' }, el('label', { for: 'installed-skill' }, '选择已安装 Skill'), el('select', { id: 'installed-skill', onchange: event => { input.value = event.target.value; } }, el('option', { value: '' }, '从 Codex / Claude / Agents 中选择…'), installed.map(item => el('option', { value: item.path }, item.name)))) : null;
    fields.replaceChildren(...[picker, el('div', { class: 'field' }, el('label', { for: input.id }, label), input), el('p', { class: 'helper' }, selected === 'github' ? '支持仓库地址或仓库内 Skill 子目录地址。只读取与分析资源，导入时不会执行脚本。' : selected === 'archive' ? '压缩包需包含 SKILL.md。导入后会检查资源路径与可用操作。' : '读取 SKILL.md 和附带资源，识别参数、依赖与可执行操作。')].filter(Boolean));
  };
  for (const [id, label, glyph] of [['path', '本地目录', 'folder'], ['github', 'GitHub', 'layers'], ['archive', '压缩包', 'file']]) tabs.append(button(label, { role: 'tab', class: 'dialog-tab', 'data-tab': id, onclick: () => { selected = id; updateFields(); } }, glyph));
  form.append(tabs, fields, el('div', { class: 'notice' }, icon('info'), el('div', {}, '导入只分析能力。运行脚本前，你将看到准确的命令与权限说明。')), message, el('div', { class: 'dialog-actions' }, button('取消', { class: 'button secondary', onclick: () => dialog.close() }), submit));
  form.addEventListener('submit', async event => {
    event.preventDefault(); submit.disabled = true; message.hidden = true;
    try {
      const input = form.elements.source;
      let skill;
      if (selected === 'archive') { const data = new FormData(); data.append('file', input.files[0]); skill = await json('/api/skills/archive', { method: 'POST', body: data }); }
      else skill = await json('/api/skills/import', { method: 'POST', body: { [selected]: input.value } });
      const existing = skills.findIndex(item => item.id === skill.id);
      if (existing >= 0) skills[existing] = skill; else skills.push(skill);
      dialog.close(); await openSkill(skill); notify(`已导入 ${skill.name}。`);
    } catch (err) { message.textContent = err.message; message.hidden = false; }
    finally { submit.disabled = false; }
  });
  updateFields(); modal('把 Skill 变成界面', '连接已有能力，保留原始来源与执行方式。', form);
  json('/api/skills/discover').then(items => { installed = items; if (dialog.open && selected === 'path' && !form.elements.source.value) updateFields(); }).catch(() => {});
}

async function openSkill(skill) {
  try { const result = await json(`/api/skills/${encodeURIComponent(skill.id)}/gui`, { method: 'POST' }); mode = 'local'; showDocument(result.document); }
  catch (err) { error(err.message); }
}

function modelDialog() {
  const form = el('form');
  const fields = [
    ['base_url', 'Base URL', 'url', model.base_url || 'https://api.openai.com/v1'],
    ['model', 'Model', 'text', model.model || ''],
    ['api_key', 'API Key', 'password', ''],
    ['timeout', '超时（秒）', 'number', model.timeout || 45],
  ];
  for (const [name, label, type, value] of fields) form.append(el('div', { class: 'field' }, el('label', { for: `model-${name}` }, label), el('input', { id: `model-${name}`, name, type, value, required: name !== 'api_key', autocomplete: name === 'api_key' ? 'off' : undefined, min: name === 'timeout' ? 1 : undefined, max: name === 'timeout' ? 180 : undefined, placeholder: name === 'model' ? '填写服务商提供的模型名称' : name === 'api_key' ? '可留空用于本地模型' : undefined })));
  const message = el('p', { class: 'inline-error', role: 'alert', hidden: true });
  const submit = button('保存模型设置', { class: 'button primary', type: 'submit' }, 'check');
  form.append(el('div', { class: 'notice' }, icon('info'), el('div', {}, 'API Key 仅保存在运行时内存，重启后需要重新配置。默认使用可交互的本地模板。')), message, el('div', { class: 'dialog-actions' }, button('取消', { class: 'button secondary', onclick: () => dialog.close() }), submit));
  form.addEventListener('submit', async event => {
    event.preventDefault(); submit.disabled = true; message.hidden = true;
    try { model = await json('/api/model', { method: 'POST', body: { base_url: form.elements.base_url.value, model: form.elements.model.value, api_key: form.elements.api_key.value, timeout: Number(form.elements.timeout.value) } }); form.elements.api_key.value = ''; dialog.close(); showInspector(); notify('模型设置已保存。'); }
    catch (err) { message.hidden = false; message.textContent = err.message; }
    finally { submit.disabled = false; }
  });
  modal('模型设置', '使用 OpenAI-compatible API 或本地模型规划专用界面。', form);
}

async function prepareAction(skill, action, args, form) {
  const submit = form?.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    const approval = await json('/api/actions/prepare', { method: 'POST', body: { skill_id: skill.id, action_id: action.id, arguments: args } });
    const message = el('p', { class: 'inline-error', role: 'alert', hidden: true });
    const confirm = button('确认并运行', { class: 'button primary', 'data-testid': 'confirm-run' }, 'play');
    confirm.addEventListener('click', async () => {
      confirm.disabled = true; message.hidden = true;
      try {
        currentJob = await json('/api/jobs', { method: 'POST', body: { approval_id: approval.approval_id, confirmed: true } });
        lastRun = { skill, action, args }; dialog.close(); showInspector(); render?.job(currentJob); pollJob(); persist(); notify('任务已提交，运行状态来自本地执行记录。');
      } catch (err) { message.textContent = err.message; message.hidden = false; confirm.disabled = false; }
    });
    const command = approval.command.map(part => JSON.stringify(part)).join(' ');
    modal('确认执行操作', `${skill.name} / ${action.label}`, el('div', {}, el('div', { class: 'warning' }, icon('info'), el('p', {}, approval.warning)), el('h3', {}, '实际执行命令'), el('pre', { class: 'command-preview', 'data-testid': 'command' }, command), el('h3', {}, '所需权限'), el('ul', { class: 'permissions' }, approval.permissions.map(permission => el('li', {}, permission))), message, el('div', { class: 'dialog-actions' }, button('取消', { class: 'button secondary', onclick: () => dialog.close() }), confirm)));
  } catch (err) { error(err.message); }
  finally { if (submit) submit.disabled = false; }
}

function showInspector() {
  const skill = skills.find(skill => skill.id === currentDoc?.skill_id);
  const source = el('section', { class: 'inspector-section' }, el('div', { class: 'inspector-heading' }, el('h2', {}, '界面信息'), icon('layers', 16)), el('dl', { class: 'properties' }, el('dt', {}, '生成方式'), el('dd', {}, mode === 'model' ? '模型规划' : '本地模板'), el('dt', {}, '交互组件'), el('dd', {}, currentDoc ? allComponents(currentDoc.components).length : '—'), el('dt', {}, '保存位置'), el('dd', {}, '本地运行时')));
  if (skill) source.append(el('div', { class: 'source-card' }, el('span', { class: 'eyebrow' }, 'CONNECTED SKILL'), el('h3', {}, skill.name), el('p', {}, skill.description), el('div', { class: 'source-badges' }, el('span', { class: 'badge' }, ({ script: '脚本型', tool: '工具型', guide: '指导型' })[skill.category]), el('span', { class: 'badge ready' }, `${skill.actions.filter(action => action.status === 'ready').length} 个可执行操作`)), el('dl', { class: 'properties' }, el('dt', {}, '来源'), el('dd', { class: 'path-value' }, skill.source.path), el('dt', {}, '版本'), el('dd', {}, skill.source.version || '未指定'), el('dt', {}, '资源'), el('dd', {}, `${skill.resources.length} 项`)), skill.warnings.length ? el('div', { class: 'warning small-warning' }, skill.warnings.join('\n')) : null, el('details', { class: 'skill-instructions' }, el('summary', {}, '查看 Skill 使用说明'), el('pre', {}, skill.instructions))));
  const runtime = el('section', { class: 'inspector-section runtime-section' }, el('div', { class: 'inspector-heading' }, el('h2', {}, '执行记录'), el('span', { class: 'badge' }, currentJob ? statusNames[currentJob.status] : '就绪')));
  if (!currentJob) runtime.append(el('div', { class: 'job-empty' }, el('div', { class: 'terminal-symbol' }, '›_'), el('strong', {}, '等待第一个任务'), el('p', {}, 'Skill 的执行日志、结果与输出文件会显示在这里。')));
  else {
    const job = currentJob;
    const active = ['queued', 'running'].includes(job.status);
    runtime.append(el('div', { class: `job-status ${job.status}` }, el('span', { class: active ? 'spinner' : 'status-symbol' }, active ? '' : job.status === 'succeeded' ? '✓' : '!'), el('div', {}, el('strong', {}, statusNames[job.status]), el('small', {}, job.id))));
    if (active || job.progress) runtime.append(el('progress', { max: 100, ...(active && !job.progress ? {} : { value: job.progress }), 'aria-label': '任务执行进度' }), el('p', { class: 'helper' }, active && !job.progress ? '脚本尚未报告可测量的进度。' : `${job.progress}%`));
    runtime.append(el('pre', { class: 'job-logs', 'data-testid': 'job-logs', 'aria-label': '真实执行日志', tabindex: 0 }, job.logs.join('\n') || '等待脚本输出…'));
    if (job.error) runtime.append(el('p', { class: 'inline-error', role: 'alert' }, job.error));
    if (job.result != null) runtime.append(el('details', { class: 'result-details', open: true }, el('summary', {}, '执行结果'), el('pre', { 'data-testid': 'job-result' }, format(job.result))));
    if (job.artifacts.length) runtime.append(el('div', { class: 'artifacts' }, el('h3', {}, '输出文件'), job.artifacts.map(artifact => el('div', { class: 'artifact-row' }, button(artifact.name, { class: 'artifact-button', title: `${format(artifact.size)} 字节`, onclick: () => downloadArtifact(job, artifact) }, 'download'), /\.(png|jpe?g|webp|gif|bmp|mp4|webm|mov|mp3|wav|ogg|m4a|pdf|txt|csv|json|md)$/i.test(artifact.name) && artifact.size <= 50 * 1024 * 1024 ? button('预览', { class: 'text-button', 'aria-label': `预览 ${artifact.name}`, onclick: () => previewArtifact(job, artifact) }) : null))));
    runtime.append(el('div', { class: 'job-actions' }, active ? button('取消任务', { class: 'button secondary small', onclick: cancelJob }, 'close') : lastRun && job.skill_id === lastRun.skill.id ? button('重新运行', { class: 'button secondary small', onclick: () => prepareAction(lastRun.skill, lastRun.action, lastRun.args, null) }, 'play') : null, button('查看历史', { class: 'text-button', onclick: jobHistory })));
  }
  refs.inspector.replaceChildren(source, runtime, el('section', { class: 'inspector-section model-card' }, el('span', { class: 'eyebrow' }, 'GENERATION ENGINE'), el('div', { class: 'model-name' }, el('i', { class: 'live-dot' }), el('strong', {}, model.configured ? model.model : '本地模板')), el('p', {}, model.configured ? '可为自定义需求规划界面。' : '内置场景即开即用。配置模型后，探索更多自定义需求。'), button('模型设置', { class: 'text-button', onclick: modelDialog }, 'settings')));
}

async function pollJob() {
  clearTimeout(jobTimer);
  if (!currentJob || !['queued', 'running'].includes(currentJob.status)) return;
  const id = currentJob.id;
  jobTimer = setTimeout(async () => {
    try {
      const job = await json(`/api/jobs/${encodeURIComponent(id)}`);
      if (currentJob?.id !== id) return;
      currentJob = job; showInspector();
      if (currentDoc?.skill_id === job.skill_id || currentDoc?.kind === 'workflow') render?.job(job);
      persist(); pollJob();
      if (!['queued', 'running'].includes(job.status)) notify(statusNames[job.status], job.status === 'failed');
    } catch (err) { error(`无法刷新任务状态：${err.message}`); jobTimer = setTimeout(pollJob, 3000); }
  }, 700);
}

async function cancelJob() {
  try { currentJob = await json(`/api/jobs/${encodeURIComponent(currentJob.id)}/cancel`, { method: 'POST' }); showInspector(); render?.job(currentJob); pollJob(); }
  catch (err) { error(err.message); }
}

async function jobHistory() {
  try {
    const jobs = await json('/api/jobs');
    modal('执行历史', '来自本地运行时保存的真实任务记录。', el('div', { class: 'history-list' }, jobs.length ? jobs.map(job => {
      const node = button('', { class: 'history-item', onclick: () => { currentJob = job; dialog.close(); showInspector(); pollJob(); } });
      node.append(el('div', {}, el('strong', {}, job.action_id), el('small', {}, job.created_at)), el('span', { class: 'badge' }, statusNames[job.status])); return node;
    }) : el('p', { class: 'helper' }, '还没有执行记录。')));
  } catch (err) { error(err.message); }
}

async function downloadArtifact(job, artifact) {
  try {
    const response = await api(`/api/artifacts/${encodeURIComponent(job.id)}/${encodeURIComponent(artifact.name)}`);
    const url = URL.createObjectURL(await response.blob());
    const link = el('a', { href: url, download: artifact.name }); document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (err) { error(err.message); }
}

async function previewArtifact(job, artifact) {
  try {
    const response = await api(`/api/artifacts/${encodeURIComponent(job.id)}/${encodeURIComponent(artifact.name)}`);
    const blob = await response.blob();
    const extension = artifact.name.split('.').pop().toLowerCase();
    let content, url;
    if (['txt', 'csv', 'json', 'md'].includes(extension)) content = el('pre', { class: 'text-preview' }, (await blob.text()).slice(0, 200000));
    else {
      const mime = ({ png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif', bmp: 'image/bmp', mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime', mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg', m4a: 'audio/mp4', pdf: 'application/pdf' })[extension];
      if (!mime) throw new Error('此格式不支持直接预览，请下载查看。');
      url = URL.createObjectURL(new Blob([blob], { type: mime }));
      if (mime.startsWith('image/')) content = el('img', { src: url, alt: artifact.name });
      else if (mime.startsWith('audio/')) content = el('audio', { src: url, controls: true, 'aria-label': artifact.name });
      else if (mime.startsWith('video/')) content = el('video', { src: url, controls: true, 'aria-label': artifact.name });
      else content = el('div', { class: 'pdf-container' }, el('iframe', { src: url, title: `PDF 预览：${artifact.name}`, sandbox: 'allow-scripts', class: 'pdf-preview' }), el('a', { href: url, target: '_blank', rel: 'noopener', class: 'text-button' }, '在新标签页打开 PDF'));
    }
    modal(artifact.name, '已验证的任务输出文件。', el('div', { class: 'artifact-preview media-preview' }, content));
    if (url) dialog.addEventListener('close', () => URL.revokeObjectURL(url), { once: true });
  } catch (err) { error(err.message); }
}

async function start() {
  buildShell();
  refs.canvas.append(el('div', { class: 'empty' }, el('span', { class: 'spinner' }), el('p', {}, '正在连接本地运行时…')));
  try {
    const boot = await json('/api/bootstrap');
    token = boot.token; skills = boot.skills || []; documents = boot.documents || []; model = boot.model || {};
    let cached;
    try { cached = JSON.parse(localStorage.getItem(STORAGE)); } catch { localStorage.removeItem(STORAGE); }
    if (cached?.document?.version === '1.0' && Array.isArray(cached.document.components)) { mode = cached.mode || 'local'; showDocument(cached.document, cached.state || {}); }
    else if (documents.length) await restoreDocument(documents[0].id);
    else { newDocument(); refs.prompt.blur(); }
    if (cached?.lastJobId) {
      try { currentJob = await json(`/api/jobs/${encodeURIComponent(cached.lastJobId)}`); showInspector(); pollJob(); } catch { /* An expired local history pointer does not block the workspace. */ }
    }
    showLibraries(); showInspector();
  } catch (err) {
    refs.canvas.replaceChildren(el('div', { class: 'empty' }, icon('info', 30), el('h2', {}, '未能连接本地运行时'), el('p', {}, err.message), button('重新连接', { class: 'button primary', onclick: () => location.reload() }, 'arrow')));
    refs.generate.disabled = true;
  }
}
start();
