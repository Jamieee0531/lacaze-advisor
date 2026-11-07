from datetime import date

import pytest
from pydantic import ValidationError

from lacaze.domain.models import CandidateMessages, CaseInput, Scenario


def test_development_cases_preserve_scenarios_dates_and_unknowns(cases):
    assert len(cases) == 10
    assert {c.scenario for c in cases} == set(Scenario)
    assert cases[0].case_date == date(2026, 11, 6)
    assert cases[0].client_information.birthday == "11-06"
    assert cases[1].client_information.birthday is None
    assert cases[2].client_information.cumulative_spend.amount_cny == 0
    assert cases[0].client_information.client_id == "cl004"


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
