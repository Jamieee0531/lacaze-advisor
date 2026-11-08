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
from lacaze.application.polish import apply_rewrites, find_flags, polish_payload
from lacaze.application.preparation import prepare
from lacaze.application.progress import ProgressObserver, report
from lacaze.domain.models import CandidateMessages, CaseInput, StageUsage
from lacaze.domain.pack import CasePack
from lacaze.domain.plan import Draft, Drafts, Edit, Plan
from lacaze.domain.result import GenerationResult
from lacaze.infrastructure.data import RuntimeData

# One call plus one retry with feedback per stage.
REQUEST_LIMIT = 2


class AdvisorWorkflow:
    """Case -> preparation (rules) -> Planner -> Writer -> polish -> three drafts with notes."""

    def __init__(self, model: Model, data: RuntimeData):
        self.model_name = model.model_name
        self.data = data
        self.planner, self.writer, self.polisher = create_agents(model, data)

    async def generate(
        self, case: CaseInput, *, observer: ProgressObserver | None = None
    ) -> GenerationResult:
        started_at = datetime.now(UTC)
        await report(
            observer,
            {"type": "stage_started", "stage": "prepare", "input": case.model_dump(mode="json")},
        )
        pack = prepare(case, self.data)
        await report(
            observer,
            {"type": "stage_completed", "stage": "prepare", "output": pack.model_dump(mode="json")},
        )
        run = _Run(RunDependencies(pack=pack, data=self.data, observer=observer))
        run.deps.plan = await run.stage(self.planner, "planner", planner_payload(pack))
        rules = self.data.scenarios[pack.scenario].writer_rules
        written = await run.stage(self.writer, "writer", writer_payload(pack, run.deps.plan, rules))
        drafts, edits = await self._polish(run, written.drafts)
        run.deps.warnings += soft_warnings(Drafts(drafts=drafts), pack, self.data)
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
            plan=run.deps.plan,
            drafts=drafts,
            edits=edits,
            candidates=CandidateMessages(messages=[d.text for d in drafts]),
            warnings=run.deps.warnings,
            usage=run.usage,
            trace=run.trace,
        )

    async def repolish(self, result: GenerationResult) -> GenerationResult:
        """Apply the polish stage to an earlier result, for before/after comparisons."""
        deps = RunDependencies(pack=result.pack, data=self.data, plan=result.plan)
        run = _Run(deps, usage=list(result.usage), trace=dict(result.trace))
        drafts, edits = await self._polish(run, result.drafts)
        return result.model_copy(
            update={
                "app_version": __version__,
                "configuration_hash": self.data.configuration_hash,
                "finished_at": datetime.now(UTC),
                "drafts": drafts,
                "edits": edits,
                "candidates": CandidateMessages(messages=[d.text for d in drafts]),
                "warnings": [*result.warnings, *deps.warnings],
                "usage": run.usage,
                "trace": run.trace,
            }
        )

    async def _polish(self, run: "_Run", drafts: list[Draft]) -> tuple[list[Draft], list[Edit]]:
        """Only drafts with a flagged sentence cost a model call."""
        run.deps.flags = find_flags(drafts, self.data.polish)
        if not run.deps.flags:
            await report(
                run.deps.observer,
                {"type": "stage_skipped", "stage": "polish", "reason": "未命中修整规则"},
            )
            return drafts, []
        payload = polish_payload(run.deps.pack, drafts, run.deps.flags, self.data)
        rewrites = await run.stage(self.polisher, "polish", payload)
        polished, edits = apply_rewrites(drafts, rewrites.rewrites, run.deps.flags)
        await report(
            run.deps.observer,
            {
                "type": "stage_completed",
                "stage": "polish",
                "output": {
                    "drafts": [d.model_dump(mode="json") for d in polished],
                    "edits": [e.model_dump(mode="json") for e in edits],
                },
                "usage": run.usage[-1].model_dump(mode="json"),
            },
        )
        return polished, edits


class _Run:
    """Per-case usage and trace, collected stage by stage."""

    def __init__(self, deps: RunDependencies, usage=None, trace=None):
        self.deps = deps
        self.usage: list[StageUsage] = usage if usage is not None else []
        self.trace: dict[str, list] = trace if trace is not None else {}

    async def stage(self, agent, stage: str, payload: dict):
        start = perf_counter()
        await report(
            self.deps.observer, {"type": "stage_started", "stage": stage, "input": payload}
        )
        result = await agent.run(
            json.dumps(payload, ensure_ascii=False, indent=1),
            deps=self.deps,
            usage_limits=UsageLimits(request_limit=REQUEST_LIMIT),
        )
        # Exact exchange with the model: assembled instructions, inputs, outputs, retries.
        self.trace[stage] = ModelMessagesTypeAdapter.dump_python(result.all_messages(), mode="json")
        counters = result.usage
        self.usage.append(
            StageUsage(
                stage=stage,
                duration_seconds=round(perf_counter() - start, 3),
                requests=counters.requests,
                input_tokens=counters.input_tokens,
                output_tokens=counters.output_tokens,
            )
        )
        # Polish completion includes the spliced drafts and is emitted by _polish.
        if stage != "polish":
            await report(
                self.deps.observer,
                {
                    "type": "stage_completed",
                    "stage": stage,
                    "output": result.output.model_dump(mode="json"),
                    "usage": self.usage[-1].model_dump(mode="json"),
                },
            )
        return result.output


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
    """The Writer sees the whole history and one set of planned facts shared by all angles."""
    messages = {m.message_id: m for m in pack.history}
    facts = pack.facts_by_id()
    angles = [
        {
            "angle": i,
            "name": a.name,
            "point": a.point,
            "purpose": a.purpose,
            "quotes": [messages[m].model_dump(mode="json") for m in a.message_ids],
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
        "client_asks": plan.client_asks,
        "avoid": plan.avoid,
        "missing": plan.missing,
        "facts": [{"fact_id": f, "text": facts[f].text} for f in plan.fact_ids],
        "angles": angles,
    }
