"""Code checks on the Writer's drafts.

Hard problems trigger one retry with feedback; if they remain, the drafts are still returned
with warnings for the CA, because a person reviews every draft before sending. Soft problems
are only reported. The price, date, time and product extractors are shared with evaluation.
"""

import re

from lacaze.application.fact_text import short_name
from lacaze.domain.models import Scenario
from lacaze.domain.pack import CasePack
from lacaze.domain.plan import Draft, Drafts, Plan
from lacaze.domain.text import extract_dates, extract_prices, extract_times, mentioned
from lacaze.infrastructure.data import RuntimeData

SCOPE_KINDS = {"product", "purchase", "event"}
EXCLAMATION = re.compile(r"[!！]")


def draft_problems(drafts: Drafts, pack: CasePack, plan: Plan, data: RuntimeData) -> list[str]:
    """Hard problems, phrased as instructions the Writer can act on."""
    problems = []
    for draft in drafts.drafts:
        problems += [f"第 {draft.angle} 条{p}" for p in _hard(draft, pack, plan, data)]
    return problems


def soft_warnings(drafts: Drafts, pack: CasePack, data: RuntimeData) -> list[str]:
    config = data.guardrail
    warnings = []
    for d in drafts.drafts:
        if EXCLAMATION.search(d.text):
            warnings.append(f"第 {d.angle} 条用了感叹号")
        discount = [t for t in config.discount_terms if t in d.text]
        if discount and pack.scenario != Scenario.PRICE_OBJECTION:
            warnings.append(f"第 {d.angle} 条提到{'、'.join(discount)}，本场景通常不该出现")
    texts = [d.text for d in drafts.drafts]
    for i in range(3):
        for j in range(i + 1, 3):
            if _similarity(texts[i], texts[j]) > config.similar_drafts_threshold:
                warnings.append(f"第 {i + 1} 条和第 {j + 1} 条措辞过于相似")
    return warnings


def _hard(draft: Draft, pack: CasePack, plan: Plan, data: RuntimeData) -> list[str]:
    config, text = data.guardrail, draft.text
    sources = [m.text for m in pack.history] + [f.text for f in pack.facts]
    joined = "\n".join(sources)
    problems = []
    if extra := sorted(set(draft.fact_ids) - set(plan.angles[draft.angle - 1].fact_ids)):
        problems.append(f"用了不属于它那个角度的事实 {extra}")
    if prices := sorted(extract_prices(text) - extract_prices(joined)):
        problems.append(f"出现了事实中没有的价格 {prices}，请删除或改用事实中的价格")
    allowed_dates = extract_dates(joined) | {(pack.case_date.month, pack.case_date.day)}
    allowed_dates |= {(m.date.month, m.date.day) for m in pack.history}
    if pack.client.birthday:
        month, day = pack.client.birthday.split("-")
        allowed_dates.add((int(month), int(day)))
    if dates := sorted(extract_dates(text) - allowed_dates):
        problems.append(f"出现了事实中没有的日期 {[f'{m}月{d}日' for m, d in dates]}")
    if times := sorted(extract_times(text) - extract_times(joined)):
        problems.append(f"出现了事实中没有的时间 {times}")
    if products := sorted(_mentioned(text, data) - _in_scope(pack, data)):
        problems.append(f"提到了本次不涉及的商品 {products}")
    if banned := [p for p in config.banned_phrases if p in text]:
        problems.append(f"用了不合品牌口吻的说法 {banned}")
    internal = [t for t in config.internal_terms if t in text]
    internal += re.findall(config.internal_id_pattern, text)
    if internal:
        problems.append(f"出现了内部信息 {internal}，不能对客户说")
    salutation = pack.client.salutation
    if salutation and salutation not in text:
        problems.append(f"没有使用称呼「{salutation}」")
    length = len(re.sub(r"\s", "", text))
    if length > config.max_chars:
        problems.append(f"有 {length} 字，请压缩到 {config.max_chars} 字以内")
    return problems


def _names(data: RuntimeData) -> list[str]:
    return [short_name(p) for p in data.catalog.products.values()]


def _mentioned(text: str, data: RuntimeData) -> set[str]:
    return mentioned(text, _names(data))


def _in_scope(pack: CasePack, data: RuntimeData) -> set[str]:
    """Products the case is about, owns or the event features. Policies do not count."""
    texts = [m.text for m in pack.history] + [f.text for f in pack.facts if f.kind in SCOPE_KINDS]
    return _mentioned("\n".join(texts), data)


def _similarity(a: str, b: str) -> float:
    """Jaccard overlap of character bigrams."""
    grams_a = {a[i : i + 2] for i in range(len(a) - 1)}
    grams_b = {b[i : i + 2] for i in range(len(b) - 1)}
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)
