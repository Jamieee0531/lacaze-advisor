"""Code checks on the Planner's output: every citation exists and each angle is personal."""

from lacaze.domain.pack import CasePack
from lacaze.domain.plan import Plan
from lacaze.infrastructure.data import RuntimeData


def plan_problems(plan: Plan, pack: CasePack, data: RuntimeData) -> list[str]:
    problems = []
    sub_types = data.scenarios[pack.scenario].sub_types
    if plan.sub_type not in sub_types:
        problems.append(f"sub_type 只能是 {sub_types} 之一")
    message_ids = {m.message_id for m in pack.history}
    fact_ids = {f.fact_id for f in pack.facts}
    purchase_ids = {f.fact_id for f in pack.facts if f.kind == "purchase"}
    internal_ids = {f.fact_id for f in pack.facts if f.internal}
    if unknown := sorted(set(plan.fact_ids) - fact_ids):
        problems.append(f"fact_ids 引用了不存在的事实 ID {unknown}")
    if internal := sorted(set(plan.fact_ids) & internal_ids):
        problems.append(
            f"fact_ids 里有只供判断的内部事实 {internal}，请移出，需要时体现在 avoid 里"
        )
    limit = data.guardrail.max_plan_facts
    if len(plan.fact_ids) > limit:
        problems.append(
            f"fact_ids 有 {len(plan.fact_ids)} 条，最多 {limit} 条，请只留回答本次所需的"
        )
    owns_purchase = bool(set(plan.fact_ids) & purchase_ids)
    for i, angle in enumerate(plan.angles, 1):
        if unknown := sorted(set(angle.message_ids) - message_ids):
            problems.append(f"角度 {i} 引用了不存在的对话编号 {unknown}")
        personal = set(angle.message_ids) & message_ids or owns_purchase
        if (message_ids or purchase_ids) and not personal:
            problems.append(f"角度 {i} 没有落在这位客户身上，请引用她的对话或购买记录")
    names = [a.name.strip() for a in plan.angles]
    if len(set(names)) != 3:
        problems.append("三个角度的名称重复")
    return problems


def sanitize_plan(plan: Plan, pack: CasePack) -> Plan:
    """Drop citations that do not exist, so the Writer never sees an unverifiable source."""
    message_ids = {m.message_id for m in pack.history}
    fact_ids = {f.fact_id for f in pack.facts if not f.internal}
    angles = [
        a.model_copy(update={"message_ids": [m for m in a.message_ids if m in message_ids]})
        for a in plan.angles
    ]
    return plan.model_copy(
        update={"angles": angles, "fact_ids": [f for f in plan.fact_ids if f in fact_ids]}
    )
