import asyncio

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import ProductInformation
from tests.conftest import ScriptedModel


def test_catalog_marks_unknown_fields_and_names(data):
    result = data.catalog.query(
        ["Sable", "Odette", "MadeUp"], ["weight_g", "compartments"], ProductInformation()
    )
    assert {p.product_id for p in result.products} == {"sable", "odette"}
    assert result.unknown_names == ["MadeUp"]
    assert result.unavailable_fields["odette"] == ["weight_g", "compartments"]


def test_supplied_product_snapshot_is_authoritative(data, cases):
    supplied = cases[1].product_information.model_copy(deep=True)
    supplied.products[0].price_cny = 90000
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
    assert "Allowed service_and_event_fact_ids: []" in str(error.value.__cause__)
