// HTML builders for data views. Every value passes through h() before it reaches the page.

import { ICONS } from './icons.mjs';
import { editKinds, fieldLabels, kindNames, valueNames } from './labels.mjs';
import { scenarios } from './model.mjs';

export const h = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
export const icon = name => ICONS[name] || '';
export const fmtDate = s => String(s || '').replaceAll('-', ' / ');
export const money = n => new Intl.NumberFormat('zh-CN').format(n);
export const btn = (text, action, attrs = '', cls = 'text-button') =>
  `<button type="button" class="${cls}" data-action="${action}" ${attrs}>${text}</button>`;
export const list = items => `<ul class="detail-list">${items.map(t => `<li>${h(t)}</li>`).join('')}</ul>`;
export const section = (title, content, field = '') =>
  `<section class="section"><h3>${h(title)}${field ? `<small>${h(field)}</small>` : ''}</h3>${content}</section>`;
export const errorSlot = field =>
  `<span class="field-error" id="${field}-error" data-error-for="${field}" role="alert" hidden></span>`;
export const muted = text => `<p class="body-copy muted">${h(text)}</p>`;

function scalar(v) {
  if (v === null || v === undefined) return '未提供';
  if (typeof v === 'boolean') return v ? '是' : '否';
  return scenarios[v] || valueNames[v] || String(v);
}

export function dataView(value) {
  if (Array.isArray(value)) {
    if (!value.length) return muted('无');
    return value.map(v => (v && typeof v === 'object'
      ? `<div class="data-object">${dataView(v)}</div>`
      : `<p class="body-copy">${h(scalar(v))}</p>`)).join('');
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).map(([key, v]) => {
      const label = fieldLabels[key];
      const body = v && typeof v === 'object' ? dataView(v) : `<p>${h(scalar(v))}</p>`;
      return `<section class="data-block"><h4>${h(label || key)}${label ? `<small>${h(key)}</small>` : ''}</h4>${body}</section>`;
    }).join('');
  }
  return `<p class="body-copy">${h(scalar(value))}</p>`;
}

export const raw = value => `<pre class="raw-json">${h(JSON.stringify(value, null, 2))}</pre>`;

export function factsView(facts) {
  if (!facts.length) return muted('没有引用事实。');
  return facts.map(f => `<div class="fact-row"><div class="fact-id">${h(f.fact_id)}${f.internal ? ' · 仅供内部判断' : ''}</div><p>${h(f.text)}</p></div>`).join('');
}

export function planView(plan, facts) {
  const used = facts.filter(f => plan.fact_ids.includes(f.fact_id));
  const angles = plan.angles.map((a, i) => `<section class="data-object">${dataView({
    name: `${i + 1}. ${a.name}`, point: a.point, purpose: a.purpose, message_ids: a.message_ids, next_step: a.next_step,
  })}</section>`).join('');
  return section('客户当前状态', `<p class="body-copy">${h(plan.situation)}</p>`, 'situation')
    + section('本次必须回应', plan.client_asks.length ? list(plan.client_asks) : muted('没有明确提问，按场景回应。'), 'client_asks')
    + section('三个回应策略', angles, 'angles')
    + section(`三条共用的事实 · ${plan.fact_ids.length} 条`, factsView(used), 'fact_ids')
    + section('需要避免', plan.avoid.length ? list(plan.avoid) : muted('无'), 'avoid')
    + section('尚缺信息', plan.missing.length ? list(plan.missing) : muted('无'), 'missing')
    + section('场景子类型', `<p class="body-copy">${h(plan.sub_type)}</p>`, 'sub_type');
}

export function packView(pack) {
  const kinds = {};
  for (const f of pack.facts) kinds[f.kind] = (kinds[f.kind] || 0) + 1;
  return section('本次准备摘要', `<p class="body-copy">${h(pack.client.salutation || pack.client.name)} · ${h(scenarios[pack.scenario])}<br>${pack.history.length} 条对话，${pack.product_ids.length} 款商品，${pack.facts.length} 条事实。</p>`)
    + section('事实类别', list(Object.entries(kinds).map(([k, n]) => `${kindNames[k] || k}：${n} 条`)))
    + section('品牌与场景', '<p class="body-copy">品牌身份、沟通规则、当前场景的规划与写作规则会另行组装到模型指令。Writer 还会收到对应场景的一条写法参考。</p>')
    + section('程序备注', pack.notes.length ? list(pack.notes) : muted('无'))
    + section('客户卡片', dataView(pack.client));
}

export function polishView(stage, result) {
  if (stage.status === 'skipped') return `<p class="body-copy">没有触发表达修整，无需调用 Polisher。</p>`;
  const edits = stage.output?.edits ?? result?.edits ?? [];
  if (!edits.length) return '<p class="body-copy">执行过修整检查，本次保留原有表达。</p>';
  return section('局部表达修整', edits.map(e => `<div class="edit-record"><strong>候选 ${e.angle} · ${h(e.kinds.map(k => editKinds[k] || k).join('、'))}</strong><del>${h(e.before)}</del><ins>${h(e.after || '（删除该句）')}</ins></div>`).join(''));
}

export function purchaseView(purchases, foundation) {
  if (!purchases.length) return muted('暂无购买记录。');
  return `<div class="purchase-records">${[...purchases].sort((a, b) => b.purchase_date.localeCompare(a.purchase_date)).map(p => {
    const product = foundation.products.find(v => v.product_id === p.product_id);
    const store = foundation.stores.find(v => v.store_id === p.store);
    return `<article class="purchase-record"><div><h4>${h(product?.name || p.product_id)}</h4><span>${h(p.purchase_date)}</span></div><p>${h(p.color)} · ¥${money(p.price_cny)}${store ? ` · ${h(store.name)}` : ''}</p></article>`;
  }).join('')}</div>`;
}

export function clientProfileView(record, purchases, card, foundation) {
  const profile = { ...record, ...(card || {}) };
  const store = foundation.stores.find(v => v.store_id === profile.home_store);
  if (store) profile.home_store = store.name;
  return section('客户档案', dataView(profile)) + section('购买记录', purchaseView(purchases, foundation));
}

function policyView(policies) {
  const { tiers } = policies;
  const basis = tiers.basis.replace('（由消费记录计算，不手工填写）', '');
  const rows = tiers.levels.map(l => `<tr><th scope="row">${h(l.tier)}</th><td>${h(l.rule)}</td></tr>`).join('');
  return section('定价政策', list(policies.pricing)) + section('销售渠道', list(policies.channels))
    + section('配额规则', list(policies.allocation))
    + section('层级规则', `<p class="body-copy tier-basis">${h(basis)}</p><table class="tier-table"><thead><tr><th scope="col">层级</th><th scope="col">规则</th></tr></thead><tbody>${rows}</tbody></table>`);
}

/** Tabs for the 品牌与资料 dialog. Scenario prompt rules are deliberately not shown. */
export function libraryTabs(f) {
  const grid = (items, title, description) => () => `<div class="library-grid">${items.map(v => `<article class="library-item"><h3>${h(title(v))}</h3><p>${h(description(v) || '')}</p><details><summary>展开完整资料</summary>${dataView(v)}</details></article>`).join('')}</div>`;
  const clients = () => `<div class="library-grid">${f.clients.map(c => {
    const purchases = f.purchases.filter(p => p.client_id === c.client_id);
    return `<article class="library-item"><h3>${h(c.salutation)} · ${h(c.name)}</h3><p>${h(c.occupation || '')}</p><details><summary>查看档案与 ${purchases.length} 笔购买记录</summary>${clientProfileView(c, purchases, null, f)}</details></article>`;
  }).join('')}</div>`;
  return [
    ['品牌设定', () => `<p class="library-intro">${h(f.brand.identity)}</p>${section('品牌语气', `<p class="body-copy">${h(f.brand.tone.join('、'))}</p>`)}${section('沟通与业务规则', list(f.brand.rules))}`],
    ['客户档案', clients],
    ['商品信息', grid(f.products, p => p.name, p => `${p.positioning}\n¥${money(p.price_cny)}${p.price_type === 'starting_at' ? ' 起' : ''}`)],
    ['服务', grid(f.services, s => s.name, s => s.description)],
    ['活动', grid(f.events, e => e.name, e => `${e.date} ${e.time}\n${e.content}`)],
    ['政策与层级', () => policyView(f.policies)],
  ];
}
