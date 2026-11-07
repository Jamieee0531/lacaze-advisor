"""Planner and Writer agents. Instructions are assembled from three layers:
business (brand, always), scenario (chosen by the route) and case (the user message)."""

import json
from dataclasses import dataclass, field

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from lacaze.application.guardrail import draft_problems
from lacaze.application.plan_checks import plan_problems, sanitize_plan
from lacaze.domain.pack import CasePack
from lacaze.domain.plan import Drafts, Plan
from lacaze.infrastructure.data import RuntimeData


@dataclass
class RunDependencies:
    """Run-local state; never shared between cases."""

    pack: CasePack
    data: RuntimeData
    plan: Plan | None = None
    warnings: list[str] = field(default_factory=list)


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)


def planner_instructions(ctx: RunContext[RunDependencies]) -> str:
    data, scenario = ctx.deps.data, ctx.deps.pack.scenario
    brand, policy = data.brand, data.scenarios[scenario]
    return "\n\n".join(
        [
            data.prompts["plan"],
            "## 品牌\n" + _dump({"identity": brand.identity, "rules": brand.rules}),
            "## 本场景\n"
            + _dump(
                {
                    "scenario": scenario.value,
                    "objective": policy.objective,
                    "sub_types": policy.sub_types,
                    "rules": policy.planner_rules,
                    "wording_rules_for_the_writer": policy.writer_rules,
                }
            ),
        ]
    )


def writer_instructions(ctx: RunContext[RunDependencies]) -> str:
    data, scenario = ctx.deps.data, ctx.deps.pack.scenario
    brand, policy = data.brand, data.scenarios[scenario]
    example = data.writer_examples[scenario.value]
    return "\n\n".join(
        [
            data.prompts["write"],
            "## 品牌\n" + _dump(brand.model_dump(exclude={"version"})),
            "## 本场景\n" + _dump({"objective": policy.objective, "rules": policy.writer_rules}),
            "## 写法参考（虚构示例，只参考语气和长度，不要使用其中的内容）\n" + example,
        ]
    )


def create_agents(model: Model, data: RuntimeData) -> tuple[Agent, Agent]:
    common = {
        "model": model,
        "deps_type": RunDependencies,
        "retries": 1,
        "model_settings": {"max_tokens": 4000},
    }
    planner = Agent(**common, output_type=Plan, name="planner", instructions=planner_instructions)
    writer = Agent(**common, output_type=Drafts, name="writer", instructions=writer_instructions)

    @planner.output_validator
    def validate_plan(ctx: RunContext[RunDependencies], plan: Plan) -> Plan:
        problems = plan_problems(plan, ctx.deps.pack, ctx.deps.data)
        if not problems:
            return plan
        if ctx.retry < ctx.max_retries:
            raise ModelRetry("计划有以下问题，请修正后重新输出：\n- " + "\n- ".join(problems))
        # Last attempt: keep going with what can be verified rather than failing the case.
        ctx.deps.warnings += [f"计划：{p}" for p in problems]
        return sanitize_plan(plan, ctx.deps.pack)

    @writer.output_validator
    def validate_drafts(ctx: RunContext[RunDependencies], drafts: Drafts) -> Drafts:
        problems = draft_problems(drafts, ctx.deps.pack, ctx.deps.plan, ctx.deps.data)
        if problems and ctx.retry < ctx.max_retries:
            raise ModelRetry("消息有以下问题，请修正后重新输出三条：\n- " + "\n- ".join(problems))
        ctx.deps.warnings += [f"消息：{p}" for p in problems]
        return drafts

    return planner, writer
