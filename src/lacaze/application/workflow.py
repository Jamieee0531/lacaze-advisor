import json
from datetime import UTC, datetime
from time import perf_counter

from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from lacaze import __version__
from lacaze.application.agents import RunDependencies, create_agents
from lacaze.domain.models import CaseInput, GenerationResult, StageUsage
from lacaze.infrastructure.data import RuntimeData


class AdvisorWorkflow:
    """One public operation: validated case -> context, decision and three drafts."""

    def __init__(self, model: Model, data: RuntimeData, max_product_queries: int = 2):
        self.model_name = model.model_name
        self.data = data
        self.max_product_queries = max_product_queries
        self.extractor, self.decider, self.writer = create_agents(model, data)

    async def generate(self, case: CaseInput) -> GenerationResult:
        started_at = datetime.now(UTC)
        # Run-local state: facts and tools must never leak between clients or requests.
        deps = RunDependencies(
            case=case,
            data=self.data,
            max_product_queries=self.max_product_queries,
            facts=self.data.foundation.resolve(case.product_information),
        )
        usage: list[StageUsage] = []

        async def run_stage(agent, stage: str, payload: dict, request_limit: int):
            start = perf_counter()
            result = await agent.run(
                json.dumps(payload, ensure_ascii=False),
                deps=deps,
                usage_limits=UsageLimits(request_limit=request_limit),
            )
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

        # Scenario is already a validated enum; no classifier model is needed.
        resolved_case = {
            **case.model_dump(mode="json"),
            "product_information": deps.facts.model_dump(mode="json"),
        }
        deps.context = await run_stage(self.extractor, "extraction", resolved_case, 2)
        common = {
            "case_id": case.case_id,
            "scenario": case.scenario.value,
            "case_date": case.case_date.isoformat(),
            "client_information": case.client_information.model_dump(mode="json"),
        }
        deps.decision = await run_stage(
            self.decider,
            "decision",
            {
                **common,
                "context": deps.context.model_dump(mode="json"),
                "product_information": deps.facts.model_dump(mode="json"),
                "max_product_queries": self.max_product_queries,
            },
            self.max_product_queries + 3,
        )

        selected_ids = {
            message_id
            for basis in deps.decision.personalization_basis
            for message_id in basis.message_ids
        }
        evidence = [e for e in deps.context.evidence if e.message_id in selected_ids]
        candidates = await run_stage(
            self.writer,
            "generation",
            {
                **common,
                "decision": deps.decision.model_dump(mode="json"),
                "history_evidence": [e.model_dump(mode="json") for e in evidence],
                "product_information": deps.facts.model_dump(mode="json"),
            },
            2,
        )
        return GenerationResult(
            case_id=case.case_id,
            scenario=case.scenario,
            case_date=case.case_date,
            app_version=__version__,
            model=self.model_name,
            configuration_hash=self.data.configuration_hash,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            context=deps.context,
            decision=deps.decision,
            evidence_for_generation=evidence,
            facts=deps.facts,
            product_queries=deps.queries,
            candidates=candidates,
            usage=usage,
        )
