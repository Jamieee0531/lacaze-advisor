// Pure input logic for the workbench: no DOM, so it can be tested with node:test.

export const scenarios = {
  'Birthday and festive greetings': '生日与节日问候',
  'Product recommendation': '商品推荐',
  'Post-purchase care': '售后关怀',
  'Reactivation': '客户唤醒',
  'Event invitation': '活动邀请',
  'Price objection': '价格异议',
};

export const MAX_HISTORY_MESSAGES = 100;
export const MAX_MESSAGE_CHARS = 2000;

export const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export const isText = value => typeof value === 'string' && value.trim().length > 0;

export function isDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

/** Split a Server-Sent Events buffer into parsed `data:` events and the unfinished rest. */
export function consumeEvents(buffer) {
  const events = [];
  let match;
  while ((match = /\r?\n\r?\n/.exec(buffer))) {
    const block = buffer.slice(0, match.index);
    buffer = buffer.slice(match.index + match[0].length);
    const data = block.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n');
    if (data) events.push(JSON.parse(data));
  }
  return { events, rest: buffer };
}

let sequence = 0;
export function newCaseId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `LIVE_${crypto.randomUUID().replaceAll('-', '')}`;
  }
  sequence += 1;
  return `LIVE_${Date.now()}_${sequence}`;
}

export function newInput(date) {
  return {
    case_id: newCaseId(), scenario: 'Product recommendation', case_date: date,
    client_information: { name: '', salutation: '' }, conversation_history: [],
    product_information: { product_ids: [], event_id: null },
  };
}

/** Accepts "3-8", "03/08", "3.8", "0308", "3月8号", "1990-03-08"; returns MM-DD, or the text as typed. */
export function normalizeBirthday(value) {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const match = /^(?:\d{4}\s*[-/.年]\s*)?(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*[日号]?$/.exec(trimmed)
    || /^(\d{2})(\d{2})$/.exec(trimmed);
  return match ? `${match[1].padStart(2, '0')}-${match[2].padStart(2, '0')}` : trimmed;
}

export const validBirthday = value =>
  !value || (typeof value === 'string' && /^\d{2}-\d{2}$/.test(value) && isDate(`2000-${value}`));

/** Sort by date (stable within a day) and number the messages m001, m002, ... */
export function normalizeHistory(messages) {
  if (!Array.isArray(messages) || messages.some(m => !isObject(m))) return messages;
  return messages
    .map((m, index) => ({ m, index }))
    .sort((a, b) => String(a.m.date || '').localeCompare(String(b.m.date || '')) || a.index - b.index)
    .map(({ m }, i) => ({ message_id: `m${String(i + 1).padStart(3, '0')}`, date: m.date, role: m.role, text: m.text }));
}

/** Give an edited input its internal IDs back and tidy the fields people type by hand. */
export function normalizeInput(value, caseId) {
  if (!isObject(value)) return value;
  const input = structuredClone(value);
  input.case_id = caseId || newCaseId();
  input.conversation_history = normalizeHistory(input.conversation_history ?? []);
  if (isObject(input.client_information) && input.client_information.birthday != null) {
    input.client_information.birthday = normalizeBirthday(input.client_information.birthday);
  }
  return input;
}

/** The JSON a person edits: no case ID and no message IDs, both are assigned on apply. */
export function editableInput(input) {
  const value = structuredClone(input);
  delete value.case_id;
  value.conversation_history = value.conversation_history.map(({ message_id, ...message }) => message);
  return value;
}

export function historyErrors(messages, caseDate, checkIds = true) {
  if (!Array.isArray(messages)) return ['对话历史必须是消息列表。'];
  const errors = [];
  const ids = new Set();
  let previous = '';
  if (messages.length > MAX_HISTORY_MESSAGES) errors.push(`对话最多 ${MAX_HISTORY_MESSAGES} 条。`);
  for (const [i, m] of messages.entries()) {
    const prefix = `第 ${i + 1} 条消息`;
    if (!isObject(m)) { errors.push(`${prefix}格式不正确。`); continue; }
    if (checkIds) {
      if (!isText(m.message_id) || ids.has(m.message_id)) errors.push(`${prefix}编号无效。`);
      ids.add(m.message_id);
    }
    if (!['client', 'advisor'].includes(m.role)) errors.push(`${prefix}请选择客户或顾问。`);
    if (typeof m.text !== 'string' || !m.text.trim()) errors.push(`${prefix}内容不能为空。`);
    else if (Array.from(m.text).length > MAX_MESSAGE_CHARS) errors.push(`${prefix}最多 ${MAX_MESSAGE_CHARS} 字。`);
    if (!isDate(m.date)) errors.push(`${prefix}请填写有效日期。`);
    else if (isDate(caseDate) && m.date > caseDate) errors.push(`${prefix}日期不能晚于业务日期。`);
    if (checkIds && isDate(m.date) && previous && m.date < previous) errors.push('对话历史需要按日期排序。');
    previous = m.date;
  }
  return [...new Set(errors)];
}

/** Shape checks that match the backend contract. */
export function validateInput(input) {
  if (!isObject(input)) return ['输入必须是一个 JSON 对象。'];
  const errors = [];
  if (typeof input.case_id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(input.case_id)) errors.push('内部 Case ID 无效。');
  if (typeof input.scenario !== 'string' || !Object.hasOwn(scenarios, input.scenario)) errors.push('请选择六种场景之一。');
  if (!isDate(input.case_date)) errors.push('请填写有效的业务日期。');
  const client = input.client_information;
  if (!isObject(client) || (!isText(client.client_id) && !isText(client.name))) errors.push('请选择客户，或填写新客户姓名。');
  if (isObject(client)) {
    for (const key of ['client_id', 'name', 'salutation', 'birthday']) {
      if (client[key] != null && typeof client[key] !== 'string') errors.push(`客户信息 ${key} 必须是文本。`);
    }
    if (typeof client.birthday === 'string' && !validBirthday(client.birthday)) errors.push('生日请填写有效的月-日，例如 03-08。');
  }
  errors.push(...historyErrors(input.conversation_history, input.case_date));
  const product = input.product_information;
  if (product !== undefined) {
    if (!isObject(product)) errors.push('商品信息必须是一个对象。');
    else {
      if (product.product_ids !== undefined && (!Array.isArray(product.product_ids) || !product.product_ids.every(isText))) errors.push('商品编号必须是文本列表。');
      if (product.event_id != null && typeof product.event_id !== 'string') errors.push('活动编号必须是文本。');
    }
  }
  return [...new Set(errors)];
}

/** Which optional inputs each scenario uses: the backend loading table reads no others. */
export const SCENARIO_FIELDS = {
  'Birthday and festive greetings': { products: 'hidden', event: 'hidden' },
  // Optional: a client may ask for something the catalogue lacks (see C21).
  'Product recommendation': { products: 'suggested', event: 'hidden' },
  'Post-purchase care': { products: 'required', event: 'hidden' },
  'Reactivation': { products: 'hidden', event: 'hidden' },
  'Event invitation': { products: 'optional', event: 'required' },
  'Price objection': { products: 'required', event: 'hidden' },
};

export const fieldsFor = scenario => SCENARIO_FIELDS[scenario] || { products: 'optional', event: 'optional' };

/**
 * Drop inputs the scenario does not use, so nothing hidden is sent. For after-sales care, keep only
 * bags the chosen client actually bought.
 */
export function fitScenario(input, foundation = null) {
  const fields = fieldsFor(input.scenario), pi = input.product_information || {};
  let productIds = fields.products === 'hidden' ? [] : (pi.product_ids || []);
  const clientId = input.client_information?.client_id;
  if (input.scenario === 'Post-purchase care' && foundation && clientId) {
    const owned = new Set(purchasesOf(foundation, clientId, input.case_date).map(p => p.product_id));
    productIds = productIds.filter(id => owned.has(id));
  }
  return {
    ...input,
    product_information: { product_ids: productIds, event_id: fields.event === 'hidden' ? null : (pi.event_id ?? null) },
  };
}

/** Purchases of a known client up to the business date. */
export const purchasesOf = (foundation, clientId, caseDate) =>
  foundation.purchases.filter(p => p.client_id === clientId && (!isDate(caseDate) || p.purchase_date <= caseDate));

function fieldOf(message, knownClient) {
  if (/第 .*消息|对话/.test(message)) return 'history';
  if (/业务日期/.test(message)) return 'date';
  if (/生日|birthday/.test(message)) return 'birthday';
  if (/salutation/.test(message)) return 'salutation';
  if (/客户|姓名/.test(message)) return knownClient ? 'client' : 'name';
  return 'general';
}

/** First and last date the store data covers (holiday calendar and events). */
export function dataYears(foundation) {
  const years = foundation.calendar.map(c => c.date.slice(0, 4)).sort();
  return years.length ? { min: `${years[0]}-01-01`, max: `${years.at(-1)}-12-31` } : null;
}

/**
 * Everything that blocks generation, each tied to the form field that should show it. Stricter than
 * the backend contract: an input must also make business sense (an invitation names an event, after-sales
 * care concerns a bag the client bought). Real edge cases stay open, e.g. asking for a bag the catalogue lacks.
 */
export function submissionIssues(input, foundation) {
  const record = foundation.clients.find(c => c.client_id === input.client_information?.client_id);
  const issues = validateInput(input).map(message => ({ field: fieldOf(message, record), message }));
  const add = (field, message) => issues.push({ field, message });
  if (!record && !isText(input.client_information?.name) && !issues.some(i => i.field === 'name')) add('name', '请填写新客户姓名。');
  // Without a salutation the model would guess one, gender included.
  if (!isText(record?.salutation || input.client_information?.salutation)) add(record ? 'client' : 'salutation', '请填写客户称呼，例如“林女士”。');
  const range = dataYears(foundation);
  if (range && isDate(input.case_date) && (input.case_date < range.min || input.case_date > range.max)) {
    add('date', `业务日期请选在 ${range.min.slice(0, 4)}–${range.max.slice(0, 4)} 年内，门店资料只覆盖这段时间。`);
  }
  const pi = input.product_information || {};
  const chosen = (Array.isArray(pi.product_ids) ? pi.product_ids : []).filter(id => foundation.products.some(p => p.product_id === id));
  const history = Array.isArray(input.conversation_history) ? input.conversation_history : [];
  if (input.scenario === 'Post-purchase care') {
    if (!record) add('client', '售后关怀针对已购买的客户，请选择已有客户。');
    else {
      const owned = new Set(purchasesOf(foundation, record.client_id, input.case_date).map(p => p.product_id));
      if (!owned.size) add('client', '该客户在业务日期前没有购买记录，无法做售后关怀。');
      else if (!chosen.length) add('products', '请选择这次售后关怀涉及的商品。');
      else if (chosen.some(id => !owned.has(id))) add('products', '只能选择该客户已购买的商品。');
    }
  }
  if (input.scenario === 'Price objection') {
    if (!chosen.length) add('products', '请选择客户在问价格的商品。');
    if (!history.some(m => m?.role === 'client' && isText(m.text))) add('history', '价格异议需要客户的原话，请在对话中添加客户消息。');
  }
  if (input.scenario === 'Event invitation') {
    const event = foundation.events.find(e => e.event_id === pi.event_id);
    if (!event) add('event', '请选择要邀请的活动。');
    else if (isDate(input.case_date) && event.date < input.case_date) add('event', '该活动在业务日期前已经结束，请更换活动或调整业务日期。');
  }
  return issues;
}

/** A readable message for a non-OK HTTP response from the backend. */
export function responseError(status, body) {
  const detail = body?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) return `输入不符合要求：${detail[0].msg || '请检查各字段'}。`;
  if (status === 429) return '今日演示次数已用完，请明天再试。';
  return `生成服务暂时不可用（HTTP ${status}），请稍后重试。`;
}

export const STAGES = ['prepare', 'planner', 'writer', 'polish'];

export function newRun() {
  return {
    status: 'running', meta: null, result: null, error: null,
    stages: Object.fromEntries(STAGES.map(s => [s, { status: 'idle', input: null, output: null, usage: null, retries: 0, reason: '' }])),
  };
}

/** Fold one stream event into a run, returning a new run object. */
export function applyEvent(run, event) {
  const next = structuredClone(run);
  const stage = next.stages[event.stage];
  if (event.type === 'run_started') next.meta = { version: event.version, model: event.model };
  else if (event.type === 'stage_started' && stage) Object.assign(stage, { status: 'running', input: event.input });
  else if (event.type === 'stage_retry' && stage) stage.retries += 1;
  else if (event.type === 'stage_completed' && stage) Object.assign(stage, { status: 'completed', output: event.output, usage: event.usage ?? null });
  else if (event.type === 'stage_skipped' && stage) Object.assign(stage, { status: 'skipped', reason: event.reason || '' });
  else if (event.type === 'result') Object.assign(next, { status: 'complete', result: event.result, replayed: Boolean(event.replayed) });
  else if (event.type === 'error') {
    Object.assign(next, { status: 'error', error: event.message || '本次生成未完成，请重新生成。' });
    if (stage) stage.status = 'error';
  }
  return next;
}
