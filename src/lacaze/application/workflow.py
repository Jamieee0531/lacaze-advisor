import json
from datetime import UTC, datetime
from time import perf_counter

from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from lacaze import __version__
from lacaze.application.agents import RunDependencies, create_agents
from lacaze.application.fact_text import WEEKDAYS
from lacaze.application.guardrail import soft_warnings
from lacaze.application.preparation import prepare
from lacaze.domain.models import CandidateMessages, CaseInput, StageUsage
from lacaze.domain.pack import CasePack
from lacaze.domain.plan import Plan
from lacaze.domain.result import GenerationResult
from lacaze.infrastructure.data import RuntimeData

# One call plus one retry with feedback per stage.
REQUEST_LIMIT = 2


class AdvisorWorkflow:
    """Case -> preparation (rules) -> Planner -> Writer -> three drafts with angle notes."""

    def __init__(self, model: Model, data: RuntimeData):
        self.model_name = model.model_name
        self.data = data
        self.planner, self.writer = create_agents(model, data)

    async def generate(self, case: CaseInput) -> GenerationResult:
        started_at = datetime.now(UTC)
        pack = prepare(case, self.data)
        deps = RunDependencies(pack=pack, data=self.data)
        usage: list[StageUsage] = []
        trace: dict[str, list] = {}

        async def run_stage(agent, stage: str, payload: dict):
            start = perf_counter()
            result = await agent.run(
                json.dumps(payload, ensure_ascii=False, indent=1),
                deps=deps,
                usage_limits=UsageLimits(request_limit=REQUEST_LIMIT),
            )
            # Exact exchange with the model: assembled instructions, inputs, outputs, retries.
            trace[stage] = ModelMessagesTypeAdapter.dump_python(result.all_messages(), mode="json")
            counters = result.usage
            usage.append(
                StageUsage(
                    stage=stage,
                    duration_seconds=round(perf_counter() - start, 3),
                    requests=counters.requests,
                    input_tokens=counters.input_tokens,
                    output_tokens=counters.output_tokens,
                )
            )
            return result.output

        deps.plan = await run_stage(self.planner, "planner", planner_payload(pack))
        rules = self.data.scenarios[pack.scenario].writer_rules
        drafts = await run_stage(self.writer, "writer", writer_payload(pack, deps.plan, rules))
        deps.warnings += soft_warnings(drafts, pack, self.data)
        return GenerationResult(
            case_id=case.case_id,
            scenario=case.scenario,
            case_date=case.case_date,
            app_version=__version__,
            model=self.model_name,
            configuration_hash=self.data.configuration_hash,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            pack=pack,
            plan=deps.plan,
            drafts=drafts.drafts,
            candidates=CandidateMessages(messages=[d.text for d in drafts.drafts]),
            warnings=deps.warnings,
            usage=usage,
            trace=trace,
        )


def _history(pack: CasePack) -> list[dict]:
    return [m.model_dump(mode="json") for m in pack.history]


def _business_date(pack: CasePack) -> str:
    return f"{pack.case_date.isoformat()}（星期{WEEKDAYS[pack.case_date.weekday()]}）"


def _fact(fact) -> dict:
    return fact.model_dump(mode="json", exclude_none=True, exclude={"internal"})


def planner_payload(pack: CasePack) -> dict:
    return {
        "scenario": pack.scenario.value,
        "business_date": _business_date(pack),
        "client": pack.client.model_dump(mode="json"),
        "conversation_history": _history(pack),
        "facts": [_fact(f) for f in pack.facts if not f.internal],
        "internal_facts_for_judgement_only": [_fact(f) for f in pack.facts if f.internal],
        "program_notes": pack.notes,
    }


def writer_payload(pack: CasePack, plan: Plan, wording_rules: list[str]) -> dict:
    """The Writer sees the whole history but only the facts each angle cites."""
    messages = {m.message_id: m for m in pack.history}
    facts = pack.facts_by_id()
    angles = [
        {
            "angle": i,
            "name": a.name,
            "point": a.point,
            "purpose": a.purpose,
            "quotes": [messages[m].model_dump(mode="json") for m in a.message_ids],
            "facts": [{"fact_id": f, "text": facts[f].text} for f in a.fact_ids],
            "next_step": a.next_step,
        }
        for i, a in enumerate(plan.angles, 1)
    ]
    return {
        "salutation": pack.client.salutation,
        "business_date": _business_date(pack),
        "conversation_history": _history(pack),
        "wording_rules": wording_rules,
        "situation": plan.situation,
        "avoid": plan.avoid,
        "missing": plan.missing,
        "angles": angles,
    }
