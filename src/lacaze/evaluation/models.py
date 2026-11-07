"""Evaluation contracts. The judge answers yes/no criteria; code computes the label."""

import json
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lacaze.domain.models import CaseInput, ProductInformation, Scenario


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Label(StrEnum):
    GOOD = "Good"
    NEEDS_EDIT = "Needs edit"
    NOT_ACCEPTABLE = "Not acceptable"


# true = defect; any one makes the message unusable.
UNACCEPTABLE_CRITERIA = ("fabricates_facts", "crosses_brand_redline", "contradicts_client_wish")
# true = achieved; all three are required for Good.
GOOD_CRITERIA = ("is_personal", "natural_and_on_brand", "responds_to_moment")
MESSAGE_CRITERIA = UNACCEPTABLE_CRITERIA + GOOD_CRITERIA


def compute_label(answers: Mapping[str, bool]) -> Label:
    """Raises KeyError when a criterion is missing, so partial answers never get a label."""
    if any(answers[c] for c in UNACCEPTABLE_CRITERIA):
        return Label.NOT_ACCEPTABLE
    if all(answers[c] for c in GOOD_CRITERIA):
        return Label.GOOD
    return Label.NEEDS_EDIT


def is_defect(criterion: str, answer: bool) -> bool:
    return answer if criterion in UNACCEPTABLE_CRITERIA else not answer


class Verdict(Frozen):
    answer: bool = Field(description="true = 是, false = 否")
    reason: str = Field(min_length=1, description="一句中文理由，尽量用「」引用原文")


class MessageJudgment(Frozen):
    message_index: Literal[1, 2, 3]
    fabricates_facts: Verdict
    crosses_brand_redline: Verdict
    contradicts_client_wish: Verdict
    is_personal: Verdict
    natural_and_on_brand: Verdict
    responds_to_moment: Verdict

    def answers(self) -> dict[str, bool]:
        return {c: getattr(self, c).answer for c in MESSAGE_CRITERIA}


class CaseJudgment(Frozen):
    case_id: str = Field(min_length=1)
    judge_model: str = Field(min_length=1)
    messages: list[MessageJudgment] = Field(min_length=3, max_length=3)
    distinct_angles: Verdict

    @field_validator("messages")
    @classmethod
    def one_judgment_per_message(cls, messages: list[MessageJudgment]) -> list[MessageJudgment]:
        if sorted(m.message_index for m in messages) != [1, 2, 3]:
            raise ValueError("messages must judge message_index 1, 2 and 3 exactly once")
        return sorted(messages, key=lambda m: m.message_index)


def judgment_schema_json() -> str:
    return json.dumps(CaseJudgment.model_json_schema(), ensure_ascii=False, indent=2) + "\n"


class Flag(Frozen):
    code: str
    severity: Literal["warning", "info"]
    detail: str


class EvalCase(Frozen):
    """One generated case as the generator saw it: input, visible facts and three drafts."""

    case_id: str
    scenario: Scenario
    case_date: date
    input: CaseInput
    facts: ProductInformation
    messages: tuple[str, str, str]
    app_version: str
    configuration_hash: str
    generation_model: str
    source_run: str


class LoadedRun(Frozen):
    run_dir: str
    cases: tuple[EvalCase, ...]
    skipped: list[str]
