"""Code checks on the Planner's output: every citation exists and the angles differ."""

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
    for i, angle in enumerate(plan.angles, 1):
        if unknown := sorted(set(angle.message_ids) - message_ids):
            problems.append(f"角度 {i} 引用了不存在的对话编号 {unknown}")
        if unknown := sorted(set(angle.fact_ids) - fact_ids):
            problems.append(f"角度 {i} 引用了不存在的事实 ID {unknown}")
        if (message_ids or fact_ids) and not (angle.message_ids or angle.fact_ids):
            problems.append(f"角度 {i} 没有任何依据，请引用对话编号或事实 ID")
    names = [a.name.strip() for a in plan.angles]
    if len(set(names)) != 3:
        problems.append("三个角度的名称重复")
    cited = [frozenset(a.message_ids) | frozenset(a.fact_ids) for a in plan.angles]
    for i in range(3):
        for j in range(i + 1, 3):
            if cited[i] and cited[i] == cited[j]:
                problems.append(f"角度 {i + 1} 和角度 {j + 1} 的依据完全相同，请让它们真正不同")
    return problems


def sanitize_plan(plan: Plan, pack: CasePack) -> Plan:
    """Drop citations that do not exist, so the Writer never sees an unverifiable source."""
    message_ids = {m.message_id for m in pack.history}
    fact_ids = {f.fact_id for f in pack.facts}
    angles = [
        a.model_copy(
            update={
                "message_ids": [m for m in a.message_ids if m in message_ids],
                "fact_ids": [f for f in a.fact_ids if f in fact_ids],
            }
        )
        for a in plan.angles
    ]
    return plan.model_copy(update={"angles": angles})
