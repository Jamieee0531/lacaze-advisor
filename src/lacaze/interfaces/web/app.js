// Advisor workbench: one input on the left, the live run and three drafts on the right.

import { stageNames } from './labels.mjs';
import {
  MAX_HISTORY_MESSAGES, MAX_MESSAGE_CHARS, STAGES, applyEvent, consumeEvents, editableInput, historyErrors,
  dataYears, fieldsFor, fitScenario, isDate, newCaseId, newInput, newRun, normalizeBirthday, normalizeHistory, normalizeInput,
  purchasesOf, responseError, scenarios, submissionIssues, validateInput,
} from './model.mjs';
import {
  btn, clientProfileView, dataView, errorSlot, factsView, fmtDate, h, icon, libraryTabs, muted, packView,
  planView, polishView, raw, section,
} from './views.mjs';

const $ = id => document.getElementById(id);
const clone = value => structuredClone(value);
const today = () => {
  const date = new Date().toLocaleDateString('sv-SE'), range = state.boot && dataYears(foundation());
  return range && (date < range.min || date > range.max) ? range.max : date;
};

const state = {
  boot: null, sourceId: null, input: null, isNew: false, dirty: false, stale: false,
  validationAttempted: false, touched: new Set(), tab: 0, editHistory: null, run: null, controller: null,
};
const foundation = () => state.boot.foundation;
const running = () => state.run?.status === 'running';
const result = () => (state.run?.status === 'complete' ? state.run.result : null);

// ---- Input sheet -------------------------------------------------------------------------

function clientRecord() {
  return foundation().clients.find(c => c.client_id === state.input.client_information.client_id);
}

function renderInput() {
  const f = foundation(), c = state.input, record = clientRecord(), ci = c.client_information;
  const latest = [...c.conversation_history].reverse().find(m => m.role === 'client');
  const range = dataYears(f);
  const purchases = record ? purchasesOf(f, record.client_id, c.case_date) : [];
  const caseOptions = state.boot.cases.map(row => `<option value="${h(row.case_id)}" ${row.case_id === state.sourceId ? 'selected' : ''}>${h(row.case_id)} · ${h(scenarios[row.scenario])}</option>`).join('');
  const modified = state.sourceId && state.dirty ? `<span class="source-state">已修改 · ${btn('还原', 'restore')}</span>` : '';
  const clientOptions = f.clients.map(client => `<option value="${h(client.client_id)}" ${record?.client_id === client.client_id ? 'selected' : ''}>${h(client.salutation)} · ${h(client.client_id)}</option>`).join('');
  const clientBlock = record
    ? `<div class="client-identity"><span class="avatar">${h(record.name[0])}</span><div><div class="client-name">${h(record.salutation)}</div><div class="client-meta">${h(record.occupation || record.name)} · ${purchases.length} 笔购买记录</div></div></div>`
    : `<div class="new-client"><label>姓名 <span class="required-tag">必填</span><input data-field="name" value="${h(ci.name)}" required aria-describedby="name-error">${errorSlot('name')}</label><label>称呼 <span class="required-tag">必填</span><input data-field="salutation" value="${h(ci.salutation)}" placeholder="例如：林女士" required aria-describedby="salutation-error">${errorSlot('salutation')}</label><label>生日（选填）<input data-field="birthday" value="${h(ci.birthday)}" placeholder="例如：03-08" maxlength="10" aria-describedby="birthday-error">${errorSlot('birthday')}</label></div>`;
  const history = c.conversation_history;
  const recent = latest
    ? `<p class="client-meta">最近一条客户消息</p><p class="recent-message">${h(latest.text)}</p><p class="recent-date">${h(fmtDate(latest.date))}</p>`
    : `<p class="client-meta">${history.length ? '暂无客户消息。' : '暂无对话。'}</p>`;

  $('input-content').innerHTML =
    `<div class="case-field"><div class="source-heading"><label for="case-select">输入来源</label>${modified}</div><select id="case-select"><option value="__blank" ${state.isNew ? 'selected' : ''}>空白输入 · 从头填写</option><optgroup label="现有案例">${caseOptions}</optgroup></select></div>`
    + `<div class="field-grid"><label class="full">业务日期<input type="date" data-field="case_date" value="${h(c.case_date)}" min="${h(range?.min)}" max="${h(range?.max)}" required aria-describedby="date-error">${errorSlot('date')}</label><label class="full">场景<select data-field="scenario">${Object.entries(scenarios).map(([id, label]) => `<option value="${h(id)}" ${c.scenario === id ? 'selected' : ''}>${h(label)}</option>`).join('')}</select></label></div>`
    + `<section class="input-section"><div class="section-heading"><h3>客户信息</h3>${btn(`查看档案 ${icon('ArrowUpRight')}`, 'client')}</div><label class="sr-only" for="client-select">选择客户</label><select id="client-select" aria-describedby="client-error"><option value="__new" ${!record ? 'selected' : ''}>新客户 · 填写客户信息</option>${clientOptions}</select>${errorSlot('client')}${clientBlock}</section>`
    + `<section class="input-section" id="history-section"><div class="section-heading"><h3>对话历史 <span class="history-count">${history.length} 条</span></h3>${history.length ? btn('编辑', 'edit-history') : ''}</div>${recent}<div class="history-actions">${btn(`${icon('Plus')} 添加对话`, 'add-history', '', 'history-add')}${history.length ? btn('查看全部', 'history') : ''}</div>${errorSlot('history')}</section>`
    + productSection(record, purchases) + errorSlot('general');
  renderValidation();
}

const TAGS = { required: '必选', suggested: '建议选择', optional: '选填' };
const tag = need => ` <span class="required-tag">${TAGS[need]}</span>`;

/** Products and event, shown only for the scenarios that read them. */
function productSection(record, purchases) {
  const f = foundation(), c = state.input, need = fieldsFor(c.scenario);
  if (need.products === 'hidden' && need.event === 'hidden') return '';
  const pi = c.product_information || {}, selected = new Set(pi.product_ids || []);
  const care = c.scenario === 'Post-purchase care';
  const owned = new Set(purchases.map(p => p.product_id));
  // After-sales care is about a bag the client owns, so only those are offered.
  const choices = care && record ? f.products.filter(p => owned.has(p.product_id) || selected.has(p.product_id)) : f.products;
  let html = '';
  if (need.products !== 'hidden') {
    const chips = choices.map(p => `<label class="product-chip"><input type="checkbox" data-product="${h(p.product_id)}" ${selected.has(p.product_id) ? 'checked' : ''}>${h(p.name.split(' ')[0])}</label>`).join('');
    const empty = care ? (record ? '该客户在业务日期前没有购买记录。' : '请先选择已有客户。') : '';
    html += `<div class="section-heading"><h3 id="product-heading">${care ? '涉及的已购商品' : '商品信息'}${tag(need.products)}</h3>${btn(`查看资料 ${icon('ArrowUpRight')}`, 'products')}</div><div class="products" id="product-options" role="group" aria-labelledby="product-heading" aria-describedby="products-error">${chips || `<p class="client-meta">${empty}</p>`}</div>${errorSlot('products')}`;
  }
  if (need.event !== 'hidden') {
    const unknown = pi.event_id && !f.events.some(e => e.event_id === pi.event_id);
    const events = f.events.map(e => `<option value="${h(e.event_id)}" ${pi.event_id === e.event_id ? 'selected' : ''}>${h(e.name)} · ${h(fmtDate(e.date))}</option>`).join('')
      + (unknown ? `<option value="${h(pi.event_id)}" selected>${h(pi.event_id)} · 未收录</option>` : '');
    html += `<label class="event-field">相关活动${tag(need.event)}<select id="event-select" ${need.event === 'required' ? 'required aria-required="true"' : ''} aria-describedby="event-error"><option value="">请选择活动</option>${events}</select>${errorSlot('event')}</label>`;
  }
  return `<section class="input-section">${html}</section>`;
}

const fieldTarget = {
  date: () => document.querySelector('[data-field="case_date"]'),
  products: () => $('product-options'),
  event: () => $('event-select'),
  client: () => $('client-select'),
};

function renderValidation(force = false) {
  const issues = submissionIssues(state.input, foundation());
  document.querySelectorAll('[data-error-for]').forEach(node => {
    const field = node.dataset.errorFor;
    const visible = force || state.validationAttempted || state.touched.has(field);
    const messages = visible ? [...new Set(issues.filter(i => i.field === field).map(i => i.message))] : [];
    node.textContent = messages.join('\n');
    node.hidden = !messages.length;
    const target = fieldTarget[field]?.() || document.querySelector(`[data-field="${field}"]`);
    target?.setAttribute('aria-invalid', String(messages.length > 0));
  });
  return issues;
}

// ---- Workspace ---------------------------------------------------------------------------

function stageStatus(key) {
  const stage = state.run?.stages[key];
  if (!stage || stage.status === 'idle') return ['idle', running() ? '等待' : '待执行'];
  if (stage.status === 'running') return ['running', stage.retries ? '重新生成中' : key === 'writer' ? '生成中' : '进行中'];
  if (stage.status === 'skipped') return ['skipped', '无需修整'];
  if (stage.status === 'error') return ['error', '未完成'];
  return ['completed', '已完成'];
}

function renderPipeline() {
  $('pipeline').innerHTML = STAGES.map((key, i) => {
    const [name, desc] = stageNames[key], [status, label] = stageStatus(key);
    const mark = { completed: icon('Check'), skipped: icon('Minus'), error: icon('X') }[status] || i + 1;
    return `<button class="step ${status}" data-action="stage" data-stage="${key}" aria-label="${h(`${name}，${desc}，${label}`)}"><span class="step-title"><span class="step-number">${mark}</span>${name}</span><span class="step-status">${label}</span></button>`;
  }).join('');
}

function renderReady() {
  return `<section class="ready-state"><span class="ready-icon" aria-hidden="true">${icon('MessageSquare')}</span><h2>准备生成三条建议</h2><p>完善左侧的沟通内容后，点击“生成三条建议”。</p>${btn(`查看准备资料 ${icon('ArrowUpRight')}`, 'stage', 'data-stage="prepare"')}</section>`;
}

const activity = {
  planner: ['正在制定回应计划', '已完成'],
  writer: ['正在起草三条消息', '已完成'],
  polish: ['正在修整表达', '已完成'],
};

function stageBlock(key) {
  const stage = state.run.stages[key], [name] = stageNames[key];
  const mark = {
    running: '<span class="spinner" aria-hidden="true"></span>',
    completed: `<span class="completion-icon" aria-hidden="true">${icon('Check')}</span>`,
    skipped: `<span class="completion-icon" aria-hidden="true">${icon('Minus')}</span>`,
    error: `<span class="completion-icon failed" aria-hidden="true">${icon('X')}</span>`,
  }[stage.status];
  const label = stage.status === 'running'
    ? (stage.retries ? '首次结果未通过检查，正在重新生成' : activity[key][0])
    : { completed: '已完成', skipped: '未命中修整规则，无需修整', error: '未完成' }[stage.status];
  let body = '';
  if (key === 'planner' && stage.output) {
    const plan = stage.output;
    body = `<section class="asks"><h4>本次需要回应</h4><div class="ask-items">${plan.client_asks.length ? plan.client_asks.map(a => `<span class="ask-item">${icon('Check')}${h(a)}</span>`).join('') : '按本次场景与对话时机回应'}</div></section>`
      + `<div class="running-angles">${plan.angles.map((a, i) => `<section class="angle-column"><h4>${i + 1}. ${h(a.name)}</h4><p>${h(a.point)}</p></section>`).join('')}</div>`;
  } else if (key === 'planner' && stage.status === 'running') {
    body = `<div class="running-angles" aria-hidden="true">${[1, 2, 3].map(() => '<div class="skeleton planning"><i></i><i></i><i></i></div>').join('')}</div>`;
  } else if (key === 'writer' && stage.status === 'running') {
    body = `<div class="skeleton-grid" aria-hidden="true">${[1, 2, 3].map(() => '<div class="skeleton"><i></i><i></i><i></i><i></i></div>').join('')}</div>`;
  }
  return `<section class="execution-stage" aria-label="${h(`${name} ${label}`)}"><header class="execution-stage-header"><div class="stage-heading">${mark}<h3>${name}</h3><span class="${stage.status === 'running' ? 'stage-activity' : 'stage-complete'}">${h(label)}</span></div>${btn(`查看 ${name} ${icon('ArrowUpRight')}`, 'stage', `data-stage="${key}"`)}</header>${body}</section>`;
}

function renderProgress() {
  const run = state.run;
  const heading = { running: '正在生成建议', cancelled: '已停止生成', error: '生成未完成' }[run.status];
  const started = ['planner', 'writer', 'polish'].filter(key => run.stages[key].status !== 'idle');
  const waiting = running() && !started.length
    ? '<section class="writing-state"><span class="spinner" aria-hidden="true"></span><div><h3>正在准备资料</h3><p>按场景整理客户、商品与对话中的事实。</p></div></section>'
    : '';
  return `<header class="content-heading run-overview"><h2>${heading}</h2>${running() ? btn(`${icon('X')} 停止生成`, 'cancel') : ''}</header>`
    + (run.error ? `<div class="alert danger run-error" role="alert">${h(run.error)}</div>` : '')
    + waiting + started.map(stageBlock).join('');
}

function renderComplete() {
  const r = result();
  const seconds = Math.round((new Date(r.finished_at) - new Date(r.started_at)) / 1000);
  const replies = r.drafts.map(d => `<article class="reply"><header class="reply-header"><span class="reply-number">${String(d.angle).padStart(2, '0')}</span><h3 class="reply-title">${h(r.plan.angles[d.angle - 1]?.name || '')}</h3></header><p class="reply-text">${h(d.text)}</p><footer class="reply-footer"><button class="evidence-link" data-action="evidence" data-angle="${d.angle}">${d.fact_ids.length} 条事实依据</button><button class="copy-button" data-action="copy" data-angle="${d.angle}">${icon('Copy')}复制消息</button></footer></article>`).join('');
  return `<header class="content-heading"><h2>三条候选消息</h2>${btn(`查看生成过程 ${icon('ArrowUpRight')}`, 'process')}</header>`
    + (r.warnings.length ? `<div class="alert">需要顾问留意：<br>${r.warnings.map(h).join('<br>')}</div>` : '')
    + `<div class="reply-grid">${replies}</div>`
    + `<p class="outcome-note"><span>${h(r.model)} · 用时 ${seconds} 秒</span></p>`;
}

function renderMain() {
  const c = state.input;
  const label = state.isNew ? '新建沟通' : state.dirty ? `基于 ${h(state.sourceId)} · 已修改` : h(c.case_id);
  $('case-stamp').innerHTML = `<strong>${label}</strong><span>${h(scenarios[c.scenario] || c.scenario)}</span><span>${h(fmtDate(c.case_date))}</span>`;
  $('notice').innerHTML = state.stale && state.run && !running()
    ? '<div class="alert">输入已修改。下方内容对应修改前的输入，重新生成后更新。</div>' : '';
  $('workspace-content').innerHTML = !state.run ? renderReady() : result() ? renderComplete() : renderProgress();
  $('input-sheet').inert = running();
  const generate = $('generate');
  generate.disabled = running();
  generate.innerHTML = `${running() ? '正在生成…' : state.run ? '重新生成' : '生成三条建议'}${running() ? '' : icon('ArrowRight')}`;
  renderPipeline();
  renderValidation();
}

function render() { renderInput(); renderMain(); }

function markDirty() {
  // An edited case is no longer that case: it gets its own ID, so results never carry the case's name.
  if (state.sourceId && state.input.case_id === state.sourceId) state.input = { ...state.input, case_id: newCaseId() };
  state.dirty = true;
  if (state.run) state.stale = true;
  renderMain();
}

function resetTo(input, { sourceId = null, isNew = false } = {}) {
  Object.assign(state, { input, sourceId, isNew, dirty: isNew, stale: false, run: null, validationAttempted: false });
  state.touched.clear();
  render();
}

function importCase(id) {
  const input = state.boot.cases.find(row => row.case_id === id);
  if (input) resetTo(clone(input), { sourceId: id });
}

// ---- Dialogs -----------------------------------------------------------------------------

let restoreFocus = null, dialogTabs = [];

function openDialog(title, description, tabs, footer = '', initial = 0) {
  const dialog = $('detail-dialog');
  restoreFocus = dialog.open ? restoreFocus : document.activeElement;
  $('dialog-title').textContent = title;
  $('dialog-description').textContent = description;
  $('dialog-description').hidden = !description;
  dialogTabs = tabs;
  state.tab = initial;
  $('dialog-tabs').innerHTML = tabs.length > 1 ? tabs.map(([name], i) => `<button data-action="tab" data-tab="${i}">${h(name)}</button>`).join('') : '';
  $('dialog-footer').innerHTML = footer;
  $('dialog-footer').hidden = !footer;
  renderTab();
  if (!dialog.open) dialog.showModal();
  document.body.style.overflow = 'hidden';
  dialog.querySelector('[data-action="close"]').focus();
}

function renderTab() {
  document.querySelectorAll('[data-tab]').forEach(b => {
    const active = Number(b.dataset.tab) === state.tab;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });
  $('dialog-body').innerHTML = dialogTabs[state.tab]?.[1]() || '';
  $('dialog-body').scrollTop = 0;
  if ($('history-editor')) {
    document.querySelectorAll('[data-message]').forEach(row => {
      row.querySelector('[name="text"]').value = state.editHistory[Number(row.dataset.message)].text;
    });
    updateHistoryValidation();
  }
}

const closeDialog = () => $('detail-dialog').close();

function stageOutput(key) {
  const stage = state.run.stages[key], pack = state.run.stages.prepare.output;
  if (key === 'polish' && (stage.status === 'skipped' || stage.output)) return polishView(stage, result());
  if (!stage.output) return muted(stage.status === 'running' ? '该阶段正在进行，完成后显示输出。' : '该阶段没有输出。');
  if (key === 'prepare') return packView(stage.output);
  if (key === 'planner') return planView(stage.output, pack?.facts || []);
  return dataView(stage.output);
}

async function previewPrepare() {
  const errors = validateInput(state.input);
  if (errors.length) { toast(errors[0]); return; }
  const input = clone(state.input);
  try {
    const response = await fetch('/demo/prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(responseError(response.status, body));
    openDialog('Prepare · 准备资料', '按当前输入整理的资料，未调用模型。', [
      ['输出摘要', () => packView(body)], ['完整事实', () => factsView(body.facts)],
      ['输入数据', () => dataView(input)], ['完整 JSON', () => raw({ input, output: body })],
    ]);
  } catch (error) {
    toast(error instanceof TypeError ? '无法连接服务，请稍后重试。' : error.message);
  }
}

function showStage(key) {
  if (!stageNames[key]) return;
  const stage = state.run?.stages[key], [name, desc] = stageNames[key];
  if (!stage || stage.status === 'idle') {
    if (key === 'prepare') { previewPrepare(); return; }
    openDialog(`${name} · ${desc}`, '', [['当前状态', () => muted(running() ? '该阶段尚未开始，前面的阶段完成后自动执行。' : '该阶段尚未执行。点击“生成三条建议”后开始。')]]);
    return;
  }
  const tabs = [['输出摘要', () => stageOutput(key)]];
  if (key === 'prepare' && stage.output) tabs.push(['完整事实', () => factsView(stage.output.facts)]);
  if (stage.input) tabs.push(['输入数据', () => dataView(stage.input)]);
  tabs.push(['完整 JSON', () => raw({ input: stage.input, output: stage.output, usage: stage.usage })]);
  openDialog(`${name} · ${desc}`, `${state.run.stages.prepare.input?.case_id || ''} · 本次生成`, tabs);
}

function showProcess() {
  if (!result()) return;
  openDialog('生成过程', '', STAGES.map(key => {
    const [name, desc] = stageNames[key], stage = state.run.stages[key];
    return [name, () => `<header class="process-stage-header"><h3>${h(name)} · ${h(desc)}</h3><span>${h(stageStatus(key)[1])}</span></header>`
      + section('输出', stageOutput(key))
      + `<details class="process-payload"><summary>展开输入数据</summary>${stage.input ? dataView(stage.input) : muted('此阶段未调用模型。')}</details>`
      + `<details class="process-payload"><summary>展开完整 JSON</summary>${raw({ input: stage.input, output: stage.output, usage: stage.usage })}</details>`];
  }));
}

function showHistory() {
  const messages = state.input.conversation_history;
  const view = () => messages.map(m => `<article class="history-message ${h(m.role)}"><div class="history-meta"><strong>${m.role === 'client' ? '客户' : '顾问'}</strong><span>${h(m.date)}</span></div><p>${h(m.text)}</p></article>`).join('') || muted('暂无对话。');
  openDialog('完整对话', `${messages.length} 条，按时间排列`, [['对话', view]], btn('编辑对话', 'edit-history', '', 'secondary-button'));
}

function showClient() {
  const f = foundation(), record = clientRecord() || state.input.client_information;
  const purchases = record.client_id ? f.purchases.filter(p => p.client_id === record.client_id && p.purchase_date <= state.input.case_date) : [];
  const card = state.stale ? null : state.run?.stages.prepare.output?.client;
  openDialog('客户档案', '', [['档案与购买记录', () => clientProfileView(record, purchases, card, f)]]);
}

function showLibrary(initial = '品牌设定') {
  const tabs = libraryTabs(foundation());
  openDialog('品牌与资料', '', tabs, '', Math.max(0, tabs.findIndex(([name]) => name === initial)));
}

function showInput() {
  openDialog('完整业务输入', 'CaseInput · 只包含既定业务字段', [['内容', () => dataView(state.input)], ['JSON', () => raw(state.input)]],
    running() ? '' : btn('编辑 JSON', 'edit-input', '', 'secondary-button'));
}

function editInput() {
  openDialog('编辑完整输入', '系统会自动补齐内部编号。', [['JSON', () => '<label class="sr-only" for="raw-editor">完整输入 JSON</label><textarea id="raw-editor" class="raw-editor" spellcheck="false"></textarea><div id="edit-error" class="alert danger" hidden></div>']],
    btn('取消', 'close', '', 'secondary-button') + btn('应用输入', 'apply-input', '', 'primary'));
  $('raw-editor').value = JSON.stringify(editableInput(state.input), null, 2);
}

function applyInput() {
  let input;
  try { input = normalizeInput(JSON.parse($('raw-editor').value), state.input.case_id); } catch { errorsAt('edit-error', ['JSON 格式不正确，请检查后重试。']); return; }
  const errors = validateInput(input);
  if (errors.length) { errorsAt('edit-error', errors); return; }
  state.input = input;
  markDirty();
  renderInput();
  closeDialog();
  toast('输入已更新');
}

// ---- Conversation editor -----------------------------------------------------------------

/** A new row continues the conversation: same day as the last message, the other speaker. */
function nextMessage(messages) {
  const last = messages.at(-1);
  return { date: last?.date || state.input.case_date || today(), role: last?.role === 'client' ? 'advisor' : 'client', text: '' };
}

function editHistory(append = false) {
  state.editHistory = clone(state.input.conversation_history);
  if ((append || !state.editHistory.length) && state.editHistory.length < MAX_HISTORY_MESSAGES) state.editHistory.push(nextMessage(state.editHistory));
  openDialog('编辑对话历史', '保存时按日期排序，同一天保留录入顺序；没有内容的空行不会保存。', [['编辑', historyEditor]],
    btn('取消', 'close', '', 'secondary-button') + btn('保存对话', 'save-history', '', 'primary'));
  if (append) $('dialog-body').scrollTop = $('dialog-body').scrollHeight;
}

function historyEditor() {
  const rows = state.editHistory.map((m, i) => `<section class="history-editor" data-message="${i}"><div class="history-editor-header"><label>日期<input type="date" name="date" value="${h(m.date)}" max="${h(state.input.case_date)}" aria-describedby="message-date-error-${i}"></label><label>角色<select name="role"><option value="client" ${m.role === 'client' ? 'selected' : ''}>客户</option><option value="advisor" ${m.role === 'advisor' ? 'selected' : ''}>顾问</option></select></label>${btn('删除', 'delete-message', `data-index="${i}"`)}</div><span class="field-error" id="message-date-error-${i}" data-message-date-error hidden></span><label class="sr-only" for="text-${i}">第 ${i + 1} 条消息</label><textarea id="text-${i}" name="text" maxlength="${MAX_MESSAGE_CHARS}" placeholder="输入客户或顾问的原话" aria-describedby="message-text-error-${i}"></textarea><div class="message-footer"><span class="field-error" id="message-text-error-${i}" data-message-text-error hidden></span><span class="message-count" data-message-count></span></div></section>`).join('');
  return `<div id="history-editor">${rows}</div>${btn(`${icon('Plus')} 添加一条消息`, 'add-message', state.editHistory.length >= MAX_HISTORY_MESSAGES ? 'disabled' : '', 'secondary-button')}<p class="history-limit">最多 ${MAX_HISTORY_MESSAGES} 条，每条最多 ${MAX_MESSAGE_CHARS} 字。</p><div id="history-error" class="alert danger" hidden></div>`;
}

const readHistory = () => [...document.querySelectorAll('[data-message]')]
  .map(row => Object.fromEntries(['date', 'role', 'text'].map(key => [key, row.querySelector(`[name="${key}"]`).value])));

function updateHistoryValidation() {
  document.querySelectorAll('[data-message]').forEach(row => {
    const date = row.querySelector('[name="date"]'), text = row.querySelector('[name="text"]');
    const dateError = row.querySelector('[data-message-date-error]'), textError = row.querySelector('[data-message-text-error]');
    const future = isDate(date.value) && isDate(state.input.case_date) && date.value > state.input.case_date;
    dateError.textContent = future ? '消息日期不能晚于业务日期。' : '';
    dateError.hidden = !future;
    date.setAttribute('aria-invalid', String(future));
    const length = Array.from(text.value).length;
    row.querySelector('[data-message-count]').textContent = `${length} / ${MAX_MESSAGE_CHARS}`;
    textError.textContent = length > MAX_MESSAGE_CHARS ? `每条消息最多 ${MAX_MESSAGE_CHARS} 字。` : '';
    textError.hidden = length <= MAX_MESSAGE_CHARS;
    text.setAttribute('aria-invalid', String(length > MAX_MESSAGE_CHARS));
  });
}

function saveHistory() {
  const messages = readHistory().filter(m => m.text.trim()), errors = historyErrors(messages, state.input.case_date, false);
  updateHistoryValidation();
  if (errors.length) { errorsAt('history-error', errors); return; }
  state.input = { ...state.input, conversation_history: normalizeHistory(messages) };
  state.touched.add('history');
  markDirty();
  renderInput();
  closeDialog();
}

function errorsAt(id, errors) { $(id).textContent = errors.join('\n'); $(id).hidden = !errors.length; }

// ---- Generation --------------------------------------------------------------------------

function setRun(run) { state.run = run; renderMain(); }

function focusIssue(field) {
  const target = {
    products: () => document.querySelector('[data-product]'),
    history: () => document.querySelector('[data-action="edit-history"], [data-action="add-history"]'),
  }[field]?.() || fieldTarget[field]?.() || document.querySelector(`[data-field="${field}"]`);
  target?.focus();
  target?.scrollIntoView?.({ block: 'nearest' });
}

async function generate() {
  if (running()) return;
  state.validationAttempted = true;
  const issues = renderValidation(true);
  if (issues.length) { focusIssue(issues[0].field); return; }
  const input = clone(state.input), controller = new AbortController();
  state.controller = controller;
  state.stale = false;
  setRun(newRun());
  try {
    const response = await fetch('/generate/stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal: controller.signal,
    });
    if (!response.ok) throw new Error(responseError(response.status, await response.json().catch(() => null)));
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const parsed = consumeEvents(buffer + decoder.decode(value, { stream: true }));
      buffer = parsed.rest;
      for (const event of parsed.events) setRun(applyEvent(state.run, event));
    }
    if (running()) throw new Error('连接中断，本次生成未完成，请重新生成。');
  } catch (error) {
    if (state.controller === controller && state.run) {
      const message = error instanceof TypeError ? '无法连接生成服务，请检查网络后重新生成。' : error.message;
      setRun(controller.signal.aborted ? { ...state.run, status: 'cancelled' } : { ...state.run, status: 'error', error: message });
    }
  } finally {
    if (state.controller === controller) state.controller = null;
    renderMain();
  }
}

async function copyReply(angle) {
  const draft = result()?.drafts.find(d => d.angle === angle);
  if (!draft) return;
  try { await navigator.clipboard.writeText(draft.text); toast('消息已复制'); } catch {
    openDialog('复制消息', '可选中下方正文手动复制。', [['消息', () => `<textarea class="raw-editor" readonly aria-label="待复制消息">${h(draft.text)}</textarea>`]]);
  }
}

function showEvidence(angle) {
  const r = result(), draft = r?.drafts.find(d => d.angle === angle);
  if (!draft) return;
  const facts = r.pack.facts.filter(f => draft.fact_ids.includes(f.fact_id));
  openDialog(`候选 ${angle} · 事实依据`, '引用来自本案例的共享事实池。', [['引用事实', () => factsView(facts)], ['JSON', () => raw(facts)]]);
}

function toast(text) {
  $('toast').textContent = text;
  $('toast').hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { $('toast').hidden = true; }, 3000);
}

// ---- Events ------------------------------------------------------------------------------

const actions = {
  home: () => window.scrollTo({ top: 0 }),
  library: () => showLibrary(),
  close: closeDialog,
  tab: button => { state.tab = Number(button.dataset.tab); renderTab(); },
  stage: button => showStage(button.dataset.stage),
  process: showProcess,
  input: showInput,
  history: showHistory,
  'add-history': () => editHistory(true),
  'edit-history': () => editHistory(),
  client: showClient,
  products: () => showLibrary('商品信息'),
  copy: button => copyReply(Number(button.dataset.angle)),
  evidence: button => showEvidence(Number(button.dataset.angle)),
  restore: () => { importCase(state.sourceId); toast('已还原为原始案例'); },
  generate,
  cancel: () => state.controller?.abort(),
  'edit-input': () => (running() ? toast('生成完成后再修改输入。') : editInput()),
  'apply-input': applyInput,
  'save-history': saveHistory,
  'add-message': () => {
    state.editHistory = readHistory();
    if (state.editHistory.length >= MAX_HISTORY_MESSAGES) { errorsAt('history-error', [`对话最多 ${MAX_HISTORY_MESSAGES} 条。`]); return; }
    state.editHistory.push(nextMessage(state.editHistory));
    renderTab();
    $('dialog-body').scrollTop = $('dialog-body').scrollHeight;
  },
  'delete-message': button => {
    state.editHistory = readHistory().filter((_, i) => i !== Number(button.dataset.index));
    renderTab();
  },
};

document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled || !state.boot) return;
  event.preventDefault();
  actions[button.dataset.action]?.(button);
});

function updateField(target, commit) {
  const field = target.dataset.field;
  if (!field) return;
  if (field === 'scenario') state.input = fitScenario({ ...state.input, scenario: target.value }, foundation());
  else if (field === 'case_date') state.input = { ...state.input, case_date: target.value };
  else if (['name', 'salutation', 'birthday'].includes(field)) {
    const value = field === 'birthday' && commit ? normalizeBirthday(target.value) : target.value;
    state.input = { ...state.input, client_information: { ...state.input.client_information, [field]: value || null } };
    if (field === 'birthday' && commit) target.value = value || '';
  }
  if (commit) state.touched.add(field === 'case_date' ? 'date' : field);
  markDirty();
  if (commit && ['case_date', 'scenario'].includes(field)) renderInput();
}

function updateProducts(patch, touched) {
  state.input = { ...state.input, product_information: { ...state.input.product_information, ...patch } };
  state.touched.add(touched);
  markDirty();
}

document.addEventListener('input', event => {
  const target = event.target;
  if (target.closest('[data-message]')) { updateHistoryValidation(); return; }
  if (target.matches('input[data-field]')) updateField(target, false);
});

document.addEventListener('change', event => {
  const target = event.target;
  if (target.closest('[data-message]')) { updateHistoryValidation(); return; }
  if (target.id === 'case-select') {
    if (target.value === '__blank') { resetTo(newInput(today()), { isNew: true }); toast('已切换为空白输入'); } else importCase(target.value);
    return;
  }
  if (target.id === 'client-select') {
    const client = target.value === '__new' ? { name: '', salutation: '' } : { client_id: target.value };
    state.input = fitScenario({ ...state.input, client_information: client }, foundation());
    state.touched.add('client');
    markDirty();
    renderInput();
    return;
  }
  if (target.id === 'event-select') { updateProducts({ event_id: target.value || null }, 'event'); return; }
  if (target.dataset.product) {
    const known = new Set(foundation().products.map(p => p.product_id));
    const unknown = (state.input.product_information?.product_ids || []).filter(id => !known.has(id));
    const chosen = [...document.querySelectorAll('[data-product]:checked')].map(x => x.dataset.product);
    updateProducts({ product_ids: [...chosen, ...unknown] }, 'products');
    return;
  }
  updateField(target, true);
});

$('detail-dialog').addEventListener('close', () => {
  document.body.style.overflow = '';
  if (restoreFocus?.isConnected) restoreFocus.focus();
});
$('detail-dialog').addEventListener('click', event => {
  if (event.target !== $('detail-dialog')) return;
  const r = event.target.getBoundingClientRect();
  if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) closeDialog();
});

// ---- Start -------------------------------------------------------------------------------

async function boot() {
  document.querySelectorAll('[data-icon]').forEach(node => { node.innerHTML = icon(node.dataset.icon); });
  try {
    const response = await fetch('/demo/bootstrap');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.boot = await response.json();
  } catch {
    $('input-content').innerHTML = '<div class="alert danger">无法加载案例与资料，请刷新页面重试。</div>';
    return;
  }
  document.querySelectorAll('[data-action="library"], [data-action="input"]').forEach(b => { b.disabled = false; });
  const first = state.boot.cases.find(c => c.case_id === 'C02') || state.boot.cases[0];
  if (first) importCase(first.case_id);
  else resetTo(newInput(today()), { isNew: true });
}

boot();
