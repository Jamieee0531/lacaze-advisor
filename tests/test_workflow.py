import asyncio

from lacaze.application.workflow import AdvisorWorkflow
from tests.conftest import ScriptedModel


def stage_payloads(scripted, stage):
    return [payload for s, payload, _ in scripted.seen if s == stage]


async def test_planner_sees_pack_and_writer_sees_only_cited_facts(data, cases):
    scripted = ScriptedModel()
    result = await AdvisorWorkflow(scripted.model, data).generate(cases[1])
    plan_input = stage_payloads(scripted, "planner")[0]
    assert plan_input["client"]["tier"] == "Core"  # internal, for the Planner only
    assert {f["fact_id"] for f in plan_input["facts"]} == {f.fact_id for f in result.pack.facts}
    write_input = stage_payloads(scripted, "writer")[0]
    assert "client" not in write_input and "tier" not in str(write_input)
    assert write_input["conversation_history"] == plan_input["conversation_history"]
    for angle, planned in zip(write_input["angles"], result.plan.angles, strict=True):
        assert [f["fact_id"] for f in angle["facts"]] == planned.fact_ids
        assert [q["message_id"] for q in angle["quotes"]] == planned.message_ids
        # Quotes are copied by code from the history, never retyped by a model.
        assert all(q["text"] for q in angle["quotes"])
    assert [u.stage for u in result.usage] == ["planner", "writer", "polish"]
    assert result.candidates.messages == [d.text for d in result.drafts]
    assert not result.warnings


async def test_internal_facts_reach_the_planner_only(data, cases):
    scripted = ScriptedModel()
    await AdvisorWorkflow(scripted.model, data).generate(cases[6])  # event invitation
    plan_input = stage_payloads(scripted, "planner")[0]
    internal = {f["fact_id"] for f in plan_input["internal_facts_for_judgement_only"]}
    assert "ev_classic_details_2611.not_included" in internal
    assert "ev_classic_details_2611.eligibility" in internal
    assert not internal & {f["fact_id"] for f in plan_input["facts"]}
    write_input = stage_payloads(scripted, "writer")[0]
    assert "not_included" not in str(write_input)
    assert write_input["wording_rules"] == data.scenarios[cases[6].scenario].writer_rules


async def test_instructions_are_layered_by_scenario(data, cases):
    scripted = ScriptedModel()
    await AdvisorWorkflow(scripted.model, data).generate(cases[9])  # price objection
    (planner_text,) = [t for s, _, t in scripted.seen if s == "planner"]
    (writer_text,) = [t for s, _, t in scripted.seen if s == "writer"]
    price = data.scenarios[cases[9].scenario]
    assert price.planner_rules[0] in planner_text and price.planner_rules[0] not in writer_text
    # Wording rules reach the Writer, and the Planner too so its points never contradict them.
    assert price.writer_rules[0] in writer_text and price.writer_rules[0] in planner_text
    assert data.brand.tone[0] in writer_text and data.brand.tone[0] not in planner_text
    assert data.brand.rules[0] in planner_text and data.brand.rules[0] in writer_text


async def test_parallel_cases_do_not_share_state(data, cases):
    flow = AdvisorWorkflow(ScriptedModel().model, data)
    birthday, discount = await asyncio.gather(flow.generate(cases[0]), flow.generate(cases[9]))
    assert all("张女士" in text for text in birthday.candidates.messages)
    assert all("吴女士" in text for text in discount.candidates.messages)
    assert birthday.pack.client.client_id == "cl004"
    assert discount.pack.client.client_id == "cl001"


async def test_plan_with_unknown_fact_is_retried_with_feedback(data, cases):
    scripted = ScriptedModel(plan_fault="unknown_fact")
    result = await AdvisorWorkflow(scripted.model, data).generate(cases[1])
    assert result.usage[0].requests == 2
    assert "made_up_fact" not in result.plan.angles[0].fact_ids
    assert not result.warnings


async def test_persistent_plan_problem_is_dropped_and_reported(data, cases):
    scripted = ScriptedModel(plan_fault="unknown_fact", persistent=True)
    result = await AdvisorWorkflow(scripted.model, data).generate(cases[1])
    assert "made_up_fact" not in result.plan.angles[0].fact_ids
    assert any("made_up_fact" in w for w in result.warnings)


async def test_draft_using_another_angles_fact_is_retried(data, cases):
    scripted = ScriptedModel(draft_fault="foreign_fact")
    result = await AdvisorWorkflow(scripted.model, data).generate(cases[1])
    assert result.usage[1].requests == 2 and not result.warnings
