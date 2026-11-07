from datetime import date

import pytest
from pydantic import ValidationError

from lacaze.domain.models import CandidateMessages, CaseInput, ClientInformation, Scenario


def test_development_cases_name_clients_by_id_only(cases):
    assert len(cases) == 10
    assert {c.scenario for c in cases} == set(Scenario)
    assert cases[0].case_date == date(2026, 11, 6)
    # Identity, spend and tier live in foundation; the case only says who the client is.
    assert all(
        c.client_information.model_dump(exclude_none=True).keys() == {"client_id"} for c in cases
    )


def test_client_needs_an_id_or_an_inline_name():
    with pytest.raises(ValidationError):
        ClientInformation()
    assert ClientInformation(name="周敏").name == "周敏"


@pytest.mark.parametrize(
    "field,value",
    [
        ("scenario", "产品推荐"),
        ("scenario", {"category": "Product recommendation"}),
        ("case_date", "2026-01-01"),
    ],
)
def test_invalid_scenario_or_future_history_rejected(cases, field, value):
    raw = cases[1].model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        CaseInput.model_validate(raw)


def test_case_date_is_explicit_not_machine_clock(cases):
    raw = cases[0].model_dump(mode="json")
    del raw["case_date"]
    with pytest.raises(ValidationError):
        CaseInput.model_validate(raw)


@pytest.mark.parametrize(
    "messages",
    [
        ["您好"],
        ["您好", "您好", "再见"],
        ["Hello", "Hi", "Goodbye"],
    ],
)
def test_exactly_three_distinct_chinese_candidates(messages):
    with pytest.raises(ValidationError):
        CandidateMessages(messages=messages)
