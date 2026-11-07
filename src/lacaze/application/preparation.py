"""Preparation node: select and compute this case's facts by the loading table. No model call.

Strict about facts (only foundation records become facts), lenient about input: an unknown
product or event ID becomes a note for the Planner instead of an error.
"""

from datetime import date, timedelta
from fnmatch import fnmatch

from lacaze.application import fact_text
from lacaze.domain.models import CaseInput, ClientTier, SuppliedFact
from lacaze.domain.pack import CasePack, ClientCard, LoadingRule, LoadingWindows
from lacaze.domain.text import mentioned
from lacaze.infrastructure.data import RuntimeData
from lacaze.infrastructure.foundation import Event, Foundation, Purchase

TIER_ORDER = list(ClientTier)


def prepare(case: CaseInput, data: RuntimeData) -> CasePack:
    f = data.foundation
    rule = data.loading.rule(case.scenario)
    windows = data.loading.windows
    notes: list[str] = []
    client, purchases = _client(case, f, notes)
    events = _events(case, rule, windows, f, client, notes)

    product_ids = _product_rows(case, f, events, notes)
    facts: list[SuppliedFact] = []
    for pid in product_ids:
        facts += fact_text.product_facts(f.catalog.products[pid], rule.product_fields)
    facts += [
        fact_text.purchase_fact(p, f.catalog.products[p.product_id], case.case_date)
        for p in purchases
    ]
    services = {s.service_id: s for s in f.services}
    for sid in rule.services:
        facts += fact_text.service_facts(services[sid])
    facts += _policy_facts(rule, f, product_ids)
    for event in events:
        facts += fact_text.event_facts(event, f.stores[event.store].name, case.case_date)
        facts.append(_eligibility_fact(event, client))
    if rule.calendar:
        facts += _calendar_facts(case.case_date, client.birthday, windows, f)
    if rule.last_contact:
        facts.append(_last_contact_fact(case))
    patterns = data.loading.internal_facts.patterns
    facts = [
        f.model_copy(update={"internal": True})
        if any(fnmatch(f.fact_id, p) for p in patterns)
        else f
        for f in facts
    ]
    return CasePack(
        case_id=case.case_id,
        scenario=case.scenario,
        case_date=case.case_date,
        client=client,
        history=case.conversation_history,
        product_ids=product_ids,
        facts=facts,
        notes=notes,
    )


def _client(case: CaseInput, f: Foundation, notes: list[str]) -> tuple[ClientCard, list[Purchase]]:
    info = case.client_information
    record = f.clients.get(info.client_id) if info.client_id else None
    if record:
        purchases = f.purchases_of(record.client_id, case.case_date)
        spend = sum(p.price_cny for p in purchases)
        card = ClientCard(
            client_id=record.client_id,
            name=record.name,
            salutation=record.salutation,
            birthday=record.birthday,
            client_since=record.client_since,
            tier=f.policies.tier_for(len(purchases), spend),
            cumulative_spend_cny=spend,
            purchases_known=True,
        )
        return card, purchases
    if info.name is None:
        raise ValueError(f"Unknown client ID {info.client_id} and no inline client information")
    if info.client_id:
        notes.append(f"门店记录中没有客户 {info.client_id}，按输入中的客户信息处理")
    notes.append("没有门店消费记录可查，不知道客户买过什么")
    card = ClientCard(
        client_id=info.client_id,
        name=info.name,
        salutation=info.salutation,
        birthday=info.birthday,
        client_since=None,
        tier=info.tier,
        cumulative_spend_cny=None,
        purchases_known=False,
    )
    return card, []


def _product_rows(
    case: CaseInput, f: Foundation, events: list[Event], notes: list[str]
) -> list[str]:
    """Products under discussion: case, event and history-mentioned ones, without duplicates.

    A product the client merely owns is represented by its purchase fact, not its specs.
    """
    catalog = f.catalog.products
    unknown = [pid for pid in case.product_information.product_ids if pid not in catalog]
    if unknown:
        notes.append(f"资料中没有这些商品：{'、'.join(unknown)}")
    history = "\n".join(m.text for m in case.conversation_history)
    said = mentioned(history, [fact_text.short_name(p) for p in catalog.values()])
    rows = [pid for pid in case.product_information.product_ids if pid in catalog]
    rows += [pid for e in events for pid in e.featured_products]
    rows += [pid for pid, p in catalog.items() if fact_text.short_name(p) in said]
    return list(dict.fromkeys(rows))


def _policy_facts(rule: LoadingRule, f: Foundation, product_ids: list[str]) -> list[SuppliedFact]:
    facts = []
    for group in rule.policies:
        lines = getattr(f.policies, group)
        for i, text in enumerate(lines, 1):
            if group == "allocation" and not _allocation_line_applies(text, f, product_ids):
                continue
            facts.append(SuppliedFact(fact_id=f"policy_{group}_{i}", text=text, kind="policy"))
    return facts


def _allocation_line_applies(text: str, f: Foundation, product_ids: list[str]) -> bool:
    """A line naming a restricted product applies only when that product is loaded;
    general lines apply when any restricted product is loaded."""
    restricted = {pid: p for pid, p in f.catalog.products.items() if p.allocation_ratio}
    loaded = [pid for pid in product_ids if pid in restricted]
    if not loaded:
        return False
    named = [pid for pid, p in restricted.items() if fact_text.short_name(p) in text]
    return not named or any(pid in loaded for pid in named)


def _events(
    case: CaseInput,
    rule: LoadingRule,
    windows: LoadingWindows,
    f: Foundation,
    client: ClientCard,
    notes: list[str],
) -> list[Event]:
    if rule.event == "case":
        event_id = case.product_information.event_id
        if event_id and event_id not in f.events:
            notes.append(f"资料中没有活动 {event_id}")
        return [f.events[event_id]] if event_id in f.events else []
    if rule.event == "upcoming":
        # Only events the client can actually attend can serve as a reason to get in touch.
        horizon = case.case_date + timedelta(days=windows.upcoming_event_days)
        return [
            e
            for e in f.events.values()
            if case.case_date <= date.fromisoformat(e.date) <= horizon
            and _eligible(e, client) is True
        ]
    return []


def _eligible(event: Event, client: ClientCard) -> bool | None:
    if event.min_tier is None:
        return True
    if client.tier is None:
        return None
    return TIER_ORDER.index(client.tier) >= TIER_ORDER.index(event.min_tier)


def _eligibility_fact(event: Event, client: ClientCard) -> SuppliedFact:
    verdict = {
        True: "客户在本活动参加范围内",
        False: "客户不在本活动参加范围内，不能邀请",
        None: "无法判断客户是否在本活动参加范围内，需顾问确认",
    }[_eligible(event, client)]
    return SuppliedFact(
        fact_id=f"{event.event_id}.eligibility",
        text=f"资格判断（内部，不向客户提层级）：{verdict}",
        kind="event",
    )


def _calendar_facts(
    today: date, birthday: str | None, windows: LoadingWindows, f: Foundation
) -> list[SuppliedFact]:
    def in_window(day: date) -> bool:
        delta = (day - today).days
        return -windows.calendar_before_days <= delta <= windows.calendar_after_days

    facts = []
    if birthday:
        month, day = (int(x) for x in birthday.split("-"))
        for year in (today.year - 1, today.year, today.year + 1):
            try:
                occurrence = date(year, month, day)
            except ValueError:  # 02-29 outside a leap year
                continue
            if in_window(occurrence):
                facts.append(
                    SuppliedFact(
                        fact_id="calendar.birthday",
                        text=f"客户生日：{month}月{day}日（{fact_text.relative(occurrence, today)}）",
                        kind="calendar",
                    )
                )
    for entry in f.calendar:
        if in_window(entry.date):
            facts.append(
                SuppliedFact(
                    fact_id=f"calendar.{entry.date.isoformat()}",
                    text=f"{entry.name}：{fact_text.chinese_date(entry.date)}"
                    f"（{fact_text.relative(entry.date, today)}）",
                    kind="calendar",
                )
            )
    return facts


def _last_contact_fact(case: CaseInput) -> SuppliedFact:
    if not case.conversation_history:
        text = "此前没有对话记录"
    else:
        last = case.conversation_history[-1].date
        text = (
            f"上一次对话：{fact_text.chinese_date(last)}（距今 {(case.case_date - last).days} 天）"
        )
    return SuppliedFact(fact_id="contact.last", text=text, kind="contact")
