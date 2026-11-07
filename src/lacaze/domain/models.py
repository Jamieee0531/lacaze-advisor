from __future__ import annotations

import re
from datetime import date
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
    """A known client is given by client_id alone; a new client is written inline."""

    client_id: str | None = Field(
        default=None, description="Key into the store's client and purchase records, e.g. cl004."
    )
    name: str | None = Field(default=None, min_length=1)
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

    @model_validator(mode="after")
    def identified(self) -> ClientInformation:
        if self.client_id is None and self.name is None:
            raise ValueError("client_information needs a client_id or an inline name")
        return self


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


FactKind = Literal["product", "purchase", "service", "policy", "event", "calendar", "contact"]


class SuppliedFact(Contract):
    fact_id: str
    text: str
    kind: FactKind | None = None


class ProductInformation(Contract):
    """A case names products and an event by ID; the program resolves them from foundation.

    The fact lists are filled by that resolution. Earlier v0.1.x cases wrote them inline.
    """

    product_ids: list[str] = Field(default_factory=list)
    event_id: str | None = None
    products: list[Product] = Field(default_factory=list)
    event_facts: list[SuppliedFact] = Field(default_factory=list)
    service_facts: list[SuppliedFact] = Field(
        default_factory=list, description="Store services and brand policies."
    )
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
    """Planner rules are judgement (what situation is this, what may be offered);
    writer rules are wording. Sub-types are the situations the Planner chooses from."""

    scenario: Scenario
    objective: str
    sub_types: list[str] = Field(min_length=1)
    planner_rules: list[str]
    writer_rules: list[str]


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


class StageUsage(Contract):
    stage: Literal["planner", "writer"]
    duration_seconds: float
    requests: int
    input_tokens: int
    output_tokens: int
