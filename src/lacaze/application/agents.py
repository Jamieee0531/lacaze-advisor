import json
from dataclasses import dataclass, field

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.tools import ToolDefinition

from lacaze.domain.models import (
    CandidateMessages,
    CaseContext,
    CaseInput,
    CommunicationDecision,
    ProductInformation,
    ProductQueryRecord,
    ProductQueryResult,
)
from lacaze.infrastructure.data import RuntimeData


@dataclass
class RunDependencies:
    case: CaseInput
    data: RuntimeData
    max_product_queries: int
    facts: ProductInformation
    context: CaseContext | None = None
    decision: CommunicationDecision | None = None
    queries: list[ProductQueryRecord] = field(default_factory=list)


def shared_instructions(ctx: RunContext[RunDependencies]) -> str:
    data, case = ctx.deps.data, ctx.deps.case
    return json.dumps(
        {
            "brand_policy": data.brand.model_dump(mode="json"),
            "scenario_policy": data.scenarios[case.scenario].model_dump(mode="json"),
        },
        ensure_ascii=False,
    )


async def prepare_product_tool(
    ctx: RunContext[RunDependencies], tool: ToolDefinition
) -> ToolDefinition | None:
    return tool if len(ctx.deps.queries) < ctx.deps.max_product_queries else None


def create_agents(model: Model, data: RuntimeData) -> tuple[Agent, Agent, Agent]:
    common = {
        "model": model,
        "deps_type": RunDependencies,
        "retries": 1,
        "model_settings": {"max_tokens": 5000},
    }
    extractor = Agent(
        **common,
        output_type=CaseContext,
        name="context_extraction",
        instructions=[data.prompts["extract"], shared_instructions],
    )
    decider = Agent(
        **common,
        output_type=CommunicationDecision,
        name="communication_decision",
        instructions=[data.prompts["decide"], shared_instructions],
    )
    writer = Agent(
        **common,
        output_type=CandidateMessages,
        name="message_generation",
        instructions=[data.prompts["generate"], shared_instructions],
    )

    @extractor.output_validator
    def validate_evidence(ctx: RunContext[RunDependencies], output: CaseContext) -> CaseContext:
        messages = {m.message_id: m for m in ctx.deps.case.conversation_history}
        for evidence in output.evidence:
            if (
                evidence.message_id not in messages
                or evidence.quote not in messages[evidence.message_id].text
            ):
                raise ModelRetry(
                    "Evidence must cite an existing message_id and an exact substring of its text."
                )
            source = messages[evidence.message_id]
            evidence.role = source.role
            evidence.date = source.date
        return output

    @decider.tool(prepare=prepare_product_tool, sequential=True)
    def query_products(
        ctx: RunContext[RunDependencies], names: list[str], requested_fields: list[str]
    ) -> ProductQueryResult:
        """Read the fictional LACAZE catalog when a communication decision needs product facts.

        Args:
            names: Product IDs or names. An empty list lists all six products for discovery.
            requested_fields: Fields needed for the decision, such as compartments, dimensions,
                weight_g, price_cny or care_instructions. Unknown fields are returned as unavailable.
        """
        deps = ctx.deps
        if len(deps.queries) >= deps.max_product_queries:
            raise ModelRetry(
                "Product query budget exhausted. Finish the decision and preserve missing facts."
            )
        result = deps.data.catalog.query(names, requested_fields, deps.facts)
        deps.queries.append(
            ProductQueryRecord(names=names, requested_fields=requested_fields, result=result)
        )
        products = {p.product_id: p for p in deps.facts.products}
        products.update({p.product_id: p for p in result.products})
        deps.facts = deps.facts.model_copy(update={"products": list(products.values())})
        return result

    @decider.output_validator
    def validate_decision(
        ctx: RunContext[RunDependencies], output: CommunicationDecision
    ) -> CommunicationDecision:
        deps = ctx.deps
        evidence_ids = {e.message_id for e in deps.context.evidence} if deps.context else set()
        for basis in output.personalization_basis:
            if not set(basis.message_ids) <= evidence_ids:
                raise ModelRetry(
                    "Personalization can only cite message IDs supplied in CaseContext.evidence."
                )
        product_ids = {p.product_id for p in deps.facts.products}
        fact_ids = {f.fact_id for f in deps.facts.event_facts + deps.facts.service_facts}
        if not set(output.fact_boundaries.product_ids) <= product_ids:
            raise ModelRetry(
                "A selected product needs supplied or queried facts. Query it or remove its ID."
            )
        if not set(output.fact_boundaries.service_and_event_fact_ids) <= fact_ids:
            raise ModelRetry(
                f"Allowed service_and_event_fact_ids: {sorted(fact_ids)}. "
                "Use [] when this list is empty. Product attributes do not belong here; "
                "reference products using product_ids."
            )
        salutation = deps.case.client_information.salutation
        if salutation and output.communication_strategy.salutation != salutation:
            raise ModelRetry(f"Use the explicit client salutation: {salutation}")
        return output

    return extractor, decider, writer
