"""Code checks on the Writer's drafts. A problem triggers one retry with feedback;
if it remains, the drafts are returned with warnings for the CA instead of failing."""

from lacaze.domain.pack import CasePack
from lacaze.domain.plan import Drafts, Plan
from lacaze.infrastructure.data import RuntimeData


def draft_problems(drafts: Drafts, pack: CasePack, plan: Plan, data: RuntimeData) -> list[str]:
    problems = []
    for draft in drafts.drafts:
        allowed = set(plan.angles[draft.angle - 1].fact_ids)
        if extra := sorted(set(draft.fact_ids) - allowed):
            problems.append(f"第 {draft.angle} 条用了不属于它那个角度的事实 {extra}")
    return problems
