from __future__ import annotations

import re
from datetime import date, datetime
from datetime import date as CalendarDate
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scenario(StrEnum):
    BIRTHDAY_AND_FESTIVE_GREETINGS = "Birthday and festive greetings"
    PRODUCT_RECOMMENDATION = "Product recommendation"
    POST_PURCHASE_CARE = "Post-purchase care"
    REACTIVATION = "Reactivation"
    EVENT_INVITATION = "Event invitation"
    PRICE_OBJECTION = "Price objection"


class ClientTier(StrEnum):
    UNCLASSIFIED = "Unclassified"
    PROSPECT = "Prospect"
    CORE = "Core"
    VIC = "VIC"
    VVIP = "VVIP"


class SpendAmount(Contract):
    amount_cny: float = Field(ge=0)
    as_of: date
    approximate: bool = False


class ClientInformation(Contract):
    client_id: str | None = Field(
        default=None, description="Key into the store's purchase records, e.g. cl004."
    )
    name: str = Field(min_length=1)
    salutation: str | None = None
    gender: Literal["female", "male", "other"] | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    occupation: str | None = None
    birthday: str | None = Field(
        default=None, description="Known birthday as MM-DD; null means unknown."
    )
    tier: ClientTier | None = None
    cumulative_spend: SpendAmount | None = Field(
        default=None, description="Lifetime LACAZE spend, derived from purchase records."
    )
    annual_spend: SpendAmount | None = Field(
        default=None, description="Legacy v0.1.x field, kept only to read earlier artifacts."
    )

    @field_validator("birthday")
    @classmethod
    def valid_birthday(cls, value: str | None) -> str | None:
        if value is not None:
            if not re.fullmatch(r"\d{2}-\d{2}", value):
                raise ValueError("birthday must be MM-DD")
            date.fromisoformat(f"2000-{value}")
        return value


class HistoryMessage(Contract):
    message_id: str = Field(min_length=1)
    date: date
    role: Literal["client", "advisor"]
    text: str = Field(min_length=1)


class Dimensions(Contract):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    depth: float = Field(gt=0)


class Product(Contract):
    """Catalog record from data/foundation/brand/products.json; null means not provided."""

    product_id: str
    name: str
    positioning: str | None = None
    price_cny: int = Field(gt=0)
    price_type: Literal["fixed", "starting_at"] = "fixed"
    eligible_tiers: list[ClientTier]
    allocation_ratio: str | None = None
    dimensions_cm: Dimensions | None = None
    weight_g: float | None = Field(default=None, gt=0)
    leather: str | None = None
    closure: str | None = None
    interior: str | None = None
    carry: str | None = None
    colors: list[str] = Field(default_factory=list)
    fits: list[str] = Field(default_factory=list)
    does_not_fit: list[str] = Field(default_factory=list)
    craft_points: list[str] = Field(default_factory=list)
    care_notes: list[str] = Field(default_factory=list)
    # Legacy v0.1.x snapshot fields, kept only so earlier cases and artifacts still load.
    category: str | None = None
    features: list[str] = Field(default_factory=list)
    material: str | None = None
    dimensions: str | None = None
    compartments: str | None = None
    care_instructions: str | None = None


class SuppliedFact(Contract):
    fact_id: str
    text: str


class ProductInformation(Contract):
    products: list[Product] = Field(default_factory=list)
    event_facts: list[SuppliedFact] = Field(default_factory=list)
    service_facts: list[SuppliedFact] = Field(default_factory=list)
    unavailable_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> ProductInformation:
        ids = [p.product_id for p in self.products]
        ids += [f.fact_id for f in self.event_facts + self.service_facts]
        if len(ids) != len(set(ids)):
            raise ValueError("Product and supplied fact IDs must be unique")
        return self


class CaseInput(Contract):
    case_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    scenario: Scenario
    case_date: date
    client_information: ClientInformation
    conversation_history: list[HistoryMessage]
    product_information: ProductInformation = Field(default_factory=ProductInformation)

    @model_validator(mode="after")
    def consistent_timeline(self) -> CaseInput:
        ids = [m.message_id for m in self.conversation_history]
        if len(ids) != len(set(ids)):
            raise ValueError("History message IDs must be unique")
        dates = [m.date for m in self.conversation_history]
        if dates != sorted(dates):
            raise ValueError("History must be chronological")
        if any(d > self.case_date for d in dates):
            raise ValueError("History cannot occur after case_date")
        info = self.client_information
        for spend in (info.cumulative_spend, info.annual_spend):
            if spend and spend.as_of > self.case_date:
                raise ValueError("spend as_of cannot be after case_date")
        return self


class BrandPolicy(Contract):
    version: str
    name: str
    identity: str
    tone: list[str]
    rules: list[str]


class ScenarioPolicy(Contract):
    scenario: Scenario
    objective: str
    rules: list[str]


class Evidence(Contract):
    message_id: str
    quote: str = Field(min_length=1, description="Exact substring of the cited history message.")
    role: Literal["client", "advisor"] | None = Field(
        default=None, description="Filled authoritatively from the cited input message."
    )
    date: CalendarDate | None = Field(
        default=None, description="Filled authoritatively from the cited input message."
    )


class CaseContext(Contract):
    needs_and_preferences: list[str]
    conversation_state: str
    relationship_and_style: list[str]
    relevant_product_names: list[str]
    evidence: list[Evidence]
    information_gaps: list[str]
    conflicts: list[str]


class PersonalizationBasis(Contract):
    detail: str
    message_ids: list[str] = Field(
        description="IDs from CaseContext.evidence, empty for direct identity facts."
    )


class CommunicationStrategy(Contract):
    salutation: str
    tone: str
    approach: str
    next_step: str | None


class FactBoundaries(Contract):
    product_ids: list[str] = Field(
        description="Canonical product_id values from supplied or queried products, e.g. odette."
    )
    service_and_event_fact_ids: list[str] = Field(
        description="Only fact_id values from product_information.event_facts or service_facts. "
        "Use [] if these lists are empty. Never put product IDs, product attributes, or prices here."
    )
    missing_information: list[str]
    prohibited_claims: list[str]
    advisor_notes: list[str] = Field(
        description="Internal notes; never copy internal data/tool terminology to a client."
    )


class CommunicationDecision(Contract):
    objective: str
    content_focus: list[str]
    personalization_basis: list[PersonalizationBasis]
    communication_strategy: CommunicationStrategy
    fact_boundaries: FactBoundaries


class CandidateMessages(Contract):
    messages: Annotated[list[str], Field(min_length=3, max_length=3)]

    @field_validator("messages")
    @classmethod
    def distinct_chinese_messages(cls, messages: list[str]) -> list[str]:
        cleaned = [m.strip() for m in messages]
        if len(set(cleaned)) != 3:
            raise ValueError("Provide three distinct candidate messages")
        if any(not re.search(r"[\u4e00-\u9fff]", m) for m in cleaned):
            raise ValueError("Each candidate must contain Chinese text")
        return cleaned


class ProductQueryResult(Contract):
    products: list[Product]
    unknown_names: list[str]
    unavailable_fields: dict[str, list[str]]


class ProductQueryRecord(Contract):
    names: list[str]
    requested_fields: list[str]
    result: ProductQueryResult


class StageUsage(Contract):
    stage: Literal["extraction", "decision", "generation"]
    duration_seconds: float
    requests: int
    input_tokens: int
    output_tokens: int


class GenerationResult(Contract):
    case_id: str
    scenario: Scenario
    case_date: date
    app_version: str
    model: str
    configuration_hash: str
    started_at: datetime
    finished_at: datetime
    context: CaseContext
    decision: CommunicationDecision
    evidence_for_generation: list[Evidence]
    facts: ProductInformation
    product_queries: list[ProductQueryRecord]
    candidates: CandidateMessages
    usage: list[StageUsage]
