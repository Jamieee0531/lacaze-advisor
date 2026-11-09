import test from 'node:test';
import assert from 'node:assert/strict';
import {
  applyEvent, consumeEvents, editableInput, fitScenario, newInput, newRun, normalizeBirthday, normalizeHistory,
  normalizeInput, responseError, submissionIssues, validateInput,
} from '../src/lacaze/interfaces/web/model.mjs';

const foundation = {
  clients: [{ client_id: 'cl001', salutation: '林女士' }],
  products: [{ product_id: 'odette' }, { product_id: 'colette' }],
  purchases: [{ client_id: 'cl001', product_id: 'odette', purchase_date: '2026-03-01' }],
  events: [{ event_id: 'ev01', date: '2026-11-20' }],
  calendar: [{ date: '2026-01-01' }, { date: '2027-12-25' }],
};

test('SSE parser keeps partial JSON and ignores keepalive comments', () => {
  const first = consumeEvents(': keepalive\n\ndata: {"type":"stage_started","sta');
  assert.deepEqual(first.events, []);
  const second = consumeEvents(first.rest + 'ge":"planner"}\n\ndata: {"type":"result"}\n\n');
  assert.deepEqual(second.events.map(e => e.type), ['stage_started', 'result']);
  assert.equal(second.rest, '');
});

test('SSE parser supports CRLF and refuses invalid event JSON', () => {
  assert.equal(consumeEvents('data: {"type":"result"}\r\n\r\n').events[0].type, 'result');
  assert.throws(() => consumeEvents('data: invalid\n\n'));
});

test('new inputs get an internal case ID and need a client', () => {
  const input = newInput('2026-11-08');
  assert.match(input.case_id, /^LIVE_[A-Za-z0-9_]+$/);
  assert.ok(validateInput(input).some(x => x.includes('客户')));
  input.client_information = { name: '测试客户', salutation: '李女士' };
  assert.deepEqual(validateInput(input), []);
});

test('history is sorted by date, stable within a day, and renumbered', () => {
  const sorted = normalizeHistory([
    { date: '2026-11-07', role: 'client', text: 'b' },
    { date: '2026-11-01', role: 'advisor', text: 'a' },
    { date: '2026-11-07', role: 'advisor', text: 'c' },
  ]);
  assert.deepEqual(sorted.map(m => [m.message_id, m.text]), [['m001', 'a'], ['m002', 'b'], ['m003', 'c']]);
});

test('messages after the business date are refused', () => {
  const input = { ...newInput('2026-11-08'), client_information: { name: '测试' } };
  input.conversation_history = normalizeHistory([{ date: '2026-11-09', role: 'client', text: '你好' }]);
  assert.ok(validateInput(input).some(x => x.includes('晚于业务日期')));
});

test('edited JSON drops IDs and gets them back on apply', () => {
  const input = normalizeInput({ ...newInput('2026-11-08'), conversation_history: [{ date: '2026-11-01', role: 'client', text: '你好' }] });
  const editable = editableInput(input);
  assert.equal(editable.case_id, undefined);
  assert.equal(editable.conversation_history[0].message_id, undefined);
  const applied = normalizeInput(editable, input.case_id);
  assert.equal(applied.case_id, input.case_id);
  assert.equal(applied.conversation_history[0].message_id, 'm001');
});

test('raw input rejects malformed nested values without throwing', () => {
  for (const patch of [
    { client_information: { name: 42 } },
    { client_information: [] },
    { product_information: { product_ids: 'odette' } },
    { product_information: { product_ids: [42] } },
    { product_information: null },
    { scenario: 'toString' },
    { case_date: '2026-02-30' },
    { conversation_history: 'none' },
  ]) {
    const input = { ...newInput('2026-11-08'), client_information: { name: '测试' }, ...patch };
    assert.ok(validateInput(input).length, JSON.stringify(patch));
  }
});

const errors = input => submissionIssues(input, foundation).filter(i => i.level === 'error').map(i => i.field);
const hints = input => submissionIssues(input, foundation).filter(i => i.level === 'hint').map(i => i.field).sort();

test('only what the backend would reject blocks generation', () => {
  const base = { ...newInput('2026-11-08'), client_information: { client_id: 'cl001' } };
  assert.deepEqual(errors(base), [], 'a recommendation may name no product');
  assert.deepEqual(errors({ ...newInput('2026-11-08'), client_information: { salutation: '周女士' } }), ['name']);
  assert.deepEqual(errors({ ...newInput('2026-11-08'), client_information: { name: '周敏' } }), ['salutation']);
  for (const scenario of ['Post-purchase care', 'Event invitation', 'Price objection', 'Birthday and festive greetings']) {
    assert.deepEqual(errors({ ...base, scenario, case_date: '2028-06-01' }), [], scenario);
  }
  assert.deepEqual(errors({ ...newInput('2026-11-08'), client_information: { name: '周敏', salutation: '周女士' }, scenario: 'Post-purchase care' }), []);
});

test('missing context becomes a hint on the field it concerns', () => {
  const base = { ...newInput('2026-11-08'), client_information: { client_id: 'cl001' } };
  assert.deepEqual(hints({ ...base, scenario: 'Event invitation' }), ['event']);
  assert.deepEqual(hints({ ...base, scenario: 'Event invitation', case_date: '2026-11-25', product_information: { event_id: 'ev01' } }), ['event']);
  assert.deepEqual(hints({ ...base, scenario: 'Price objection' }), ['history', 'products']);
  const said = normalizeHistory([{ date: '2026-11-07', role: 'client', text: '有点贵' }]);
  assert.deepEqual(hints({ ...base, scenario: 'Price objection', conversation_history: said, product_information: { product_ids: ['odette'] } }), []);
  const care = { ...base, scenario: 'Post-purchase care' };
  assert.deepEqual(hints(care), ['products']);
  assert.deepEqual(hints({ ...care, product_information: { product_ids: ['colette'] } }), ['products']);
  assert.deepEqual(hints({ ...care, product_information: { product_ids: ['odette'] } }), []);
  assert.deepEqual(hints({ ...care, case_date: '2026-01-02' }), ['client']);
  assert.deepEqual(hints({ ...base, case_date: '2028-01-02' }), ['date']);
});

test('birthdays in common written forms are accepted', () => {
  for (const typed of ['3-8', '03/08', '3.8', '0308', '3月8日', '3月8号', '1990-03-08', '1990年3月8日']) {
    assert.equal(normalizeBirthday(typed), '03-08', typed);
  }
  assert.equal(normalizeBirthday('2-29'), '02-29');
  const input = { ...newInput('2026-11-08'), client_information: { name: '测试', birthday: normalizeBirthday('2月30日') } };
  assert.ok(validateInput(input).some(x => x.includes('生日')));
});

test('switching scenario drops inputs the new scenario does not read', () => {
  const input = { ...newInput('2026-11-08'), product_information: { product_ids: ['odette'], event_id: 'ev01' } };
  assert.deepEqual(fitScenario({ ...input, scenario: 'Reactivation' }).product_information, { product_ids: [], event_id: null });
  assert.deepEqual(fitScenario({ ...input, scenario: 'Event invitation' }).product_information, { product_ids: ['odette'], event_id: 'ev01' });
  assert.deepEqual(fitScenario({ ...input, scenario: 'Price objection' }).product_information, { product_ids: ['odette'], event_id: null });
});

test('backend errors become readable messages', () => {
  assert.equal(responseError(429, { detail: '今日演示次数已用完，请明天再试。' }), '今日演示次数已用完，请明天再试。');
  assert.match(responseError(422, { detail: [{ msg: 'Field required' }] }), /Field required/);
  assert.match(responseError(502, null), /HTTP 502/);
});

test('stream events build up a run without mutating the previous one', () => {
  const start = newRun();
  let run = applyEvent(start, { type: 'stage_started', stage: 'planner', input: { a: 1 } });
  run = applyEvent(run, { type: 'stage_retry', stage: 'planner', problems: ['x'] });
  run = applyEvent(run, { type: 'stage_completed', stage: 'planner', output: { angles: [] } });
  run = applyEvent(run, { type: 'stage_skipped', stage: 'polish', reason: '未命中修整规则' });
  assert.equal(start.stages.planner.status, 'idle');
  assert.equal(run.stages.planner.status, 'completed');
  assert.equal(run.stages.planner.retries, 1);
  assert.equal(run.stages.polish.status, 'skipped');
  const failed = applyEvent(run, { type: 'error', stage: 'writer', message: '本次生成未完成。' });
  assert.equal(failed.status, 'error');
  assert.equal(failed.stages.writer.status, 'error');
  assert.equal(applyEvent(run, { type: 'result', result: { drafts: [] } }).status, 'complete');
});
