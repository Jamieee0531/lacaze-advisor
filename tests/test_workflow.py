import asyncio

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import ProductInformation
from tests.conftest import ScriptedModel


def test_catalog_marks_unknown_fields_and_names(data):
    result = data.catalog.query(
        ["Sable", "Odette", "MadeUp"], ["weight_g", "interior", "stock"], ProductInformation()
    )
    assert {p.product_id for p in result.products} == {"sable", "odette"}
    assert result.unknown_names == ["MadeUp"]
    # The foundation catalog has specs; stock is deliberately never provided to advisors.
    assert result.unavailable_fields["odette"] == ["stock"]


def test_supplied_product_snapshot_is_authoritative(data, cases):
    odette = data.catalog.products["odette"].model_copy(update={"price_cny": 90000})
    supplied = ProductInformation(products=[odette])
    result = data.catalog.query(["Odette"], ["price_cny"], supplied)
    assert result.products[0].price_cny == 90000
    assert data.catalog.products["odette"].price_cny == 85000


async def test_native_loop_is_bounded_and_writer_receives_evidence_not_full_history(data, cases):
    scripted = ScriptedModel()
    flow = AdvisorWorkflow(scripted.model, data, max_product_queries=2)
    result = await flow.generate(cases[1])
    assert len(result.product_queries) == 2
    assert result.product_queries[0].result.unavailable_fields["odette"] == ["compartments"]
    assert [u.requests for u in result.usage] == [1, 3, 1]
    payload = next(p for stage, p, _ in scripted.seen if stage == "generation")
    assert "conversation_history" not in payload
    assert payload["history_evidence"][0]["quote"] == cases[1].conversation_history[0].text
    assert payload["history_evidence"][0]["role"] == cases[1].conversation_history[0].role
    assert payload["history_evidence"][0]["date"] == "2026-08-14"
    assert len(result.candidates.messages) == 3


async def test_no_tool_path_and_parallel_cases_do_not_share_state(data, cases):
    scripted = ScriptedModel(use_tools=False)
    flow = AdvisorWorkflow(scripted.model, data)
    birthday, discount = await asyncio.gather(flow.generate(cases[0]), flow.generate(cases[9]))
    assert not birthday.product_queries and not discount.product_queries
    assert not birthday.facts.products
    assert discount.facts.products[0].product_id == "margaux"
    assert all("张女士" in text for text in birthday.candidates.messages)
    assert all("吴女士" in text for text in discount.candidates.messages)
    assert not cases[0].product_information.products


def test_case_ids_resolve_from_foundation(data, cases):
    event_case = next(c for c in cases if c.product_information.event_id)
    facts = data.foundation.resolve(event_case.product_information)
    assert {p.product_id for p in facts.products} == {"margaux", "veronique"}
    assert facts.products[0].dimensions_cm is not None
    assert any("2026年11月14日" in f.text for f in facts.event_facts)
    assert any(f.fact_id == "sv_usage_demo" for f in facts.service_facts)
    assert any(f.fact_id.startswith("policy_pricing") for f in facts.service_facts)
    for case in cases:
        data.foundation.check_case(case)


def test_unknown_foundation_ids_fail_fast(data, cases):
    bad = cases[0].model_copy(
        update={"product_information": ProductInformation(product_ids=["birkin"])}
    )
    with pytest.raises(ValueError, match="Unknown product IDs"):
        data.foundation.check_case(bad)
    stranger = cases[0].client_information.model_copy(update={"client_id": "cl999"})
    with pytest.raises(ValueError, match="unknown client ID"):
        data.foundation.check_case(cases[0].model_copy(update={"client_information": stranger}))


async def test_fabricated_evidence_fails_before_decision(data, cases):
    scripted = ScriptedModel(corrupt_evidence=True)
    flow = AdvisorWorkflow(scripted.model, data)
    with pytest.raises(UnexpectedModelBehavior):
        await flow.generate(cases[0])
    assert {stage for stage, _, _ in scripted.seen} == {"extraction"}


async def test_product_attributes_cannot_be_used_as_service_fact_ids(data, cases):
    class InvalidFactModel(ScriptedModel):
        def respond(self, messages, info):
            response = super().respond(messages, info)
            args = response.parts[0].args
            if isinstance(args, dict) and "fact_boundaries" in args:
                args["fact_boundaries"]["service_and_event_fact_ids"] = ["odette.price_cny"]
            return response

    flow = AdvisorWorkflow(InvalidFactModel(use_tools=False).model, data)
    with pytest.raises(UnexpectedModelBehavior) as error:
        await flow.generate(cases[1])
    message = str(error.value.__cause__)
    assert "Allowed service_and_event_fact_ids:" in message
    assert "sv_annual_care" in message and "odette.price_cny" not in message.split(":", 1)[1]
