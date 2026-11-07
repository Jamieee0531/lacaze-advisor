"""The per-case context pack: everything Planner and Writer may use, prepared once by rules."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from lacaze.domain.models import (
    ClientTier,
    Contract,
    HistoryMessage,
    Scenario,
    SuppliedFact,
)

ProductField = Literal[
    "positioning",
    "price_cny",
    "allocation_ratio",
    "dimensions_cm",
    "weight_g",
    "leather",
    "closure",
    "interior",
    "carry",
    "colors",
    "fits",
    "does_not_fit",
    "craft_points",
    "care_notes",
]
PolicyGroup = Literal["pricing", "channels", "allocation"]


class LoadingWindows(Contract):
    calendar_before_days: int = Field(ge=0)
    calendar_after_days: int = Field(ge=0)
    upcoming_event_days: int = Field(ge=0)


class LoadingRule(Contract):
    """One row of the scenario x data loading table (data/context/loading.json)."""

    scenario: Scenario
    product_fields: list[ProductField]
    services: list[str]
    policies: list[PolicyGroup]
    event: Literal["none", "case", "upcoming"]
    calendar: bool
    last_contact: bool


class InternalFacts(Contract):
    patterns: list[str]


class LoadingTable(Contract):
    internal_facts: InternalFacts
    windows: LoadingWindows
    scenarios: list[LoadingRule]

    @model_validator(mode="after")
    def one_rule_per_scenario(self) -> LoadingTable:
        if sorted(r.scenario for r in self.scenarios) != sorted(Scenario):
            raise ValueError("loading.json needs exactly one rule for each of the six scenarios")
        return self

    def rule(self, scenario: Scenario) -> LoadingRule:
        return next(r for r in self.scenarios if r.scenario == scenario)


class GuardrailConfig(Contract):
    """data/context/guardrail.json plus the phrase lists shared with evaluation."""

    max_facts_per_angle: int = Field(gt=0)
    max_chars: int = Field(gt=0)
    internal_terms: list[str]
    internal_id_pattern: str
    similar_drafts_threshold: float = Field(gt=0, le=1)
    banned_phrases: list[str]
    discount_terms: list[str]


class ClientCard(Contract):
    """Internal view of the client. Tier and spend are for the Planner, never for the client."""

    client_id: str | None
    name: str
    salutation: str | None
    birthday: str | None
    client_since: date | None
    tier: ClientTier | None
    cumulative_spend_cny: int | None
    purchases_known: bool = Field(
        description="True when purchases come from store records; False for an inline new client."
    )


class CasePack(Contract):
    case_id: str
    scenario: Scenario
    case_date: date
    client: ClientCard
    history: list[HistoryMessage]
    product_ids: list[str] = Field(description="Products whose facts are loaded, in order.")
    facts: list[SuppliedFact]
    notes: list[str] = Field(
        default_factory=list, description="Input the program could not resolve, e.g. unknown IDs."
    )

    @model_validator(mode="after")
    def unique_fact_ids(self) -> CasePack:
        ids = [f.fact_id for f in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("Fact IDs in a case pack must be unique")
        return self

    def facts_by_id(self) -> dict[str, SuppliedFact]:
        return {f.fact_id: f for f in self.facts}
