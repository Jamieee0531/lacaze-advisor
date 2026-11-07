"""Business data from data/foundation and resolution of a case's product and event IDs."""

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict

from lacaze.domain.models import CaseInput, ClientTier
from lacaze.infrastructure.catalog import ProductCatalog


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Store(Record):
    store_id: str
    name: str
    city: str


class Service(Record):
    service_id: str
    name: str
    description: str
    eligibility: str
    how: str


class Event(Record):
    event_id: str
    name: str
    date: str
    time: str
    store: str
    audience: str
    min_tier: ClientTier | None = None
    content: str
    featured_products: list[str]
    appointment: str
    not_included: list[str]
    note: str


class Client(Record):
    client_id: str
    name: str
    salutation: str
    gender: str
    age: int
    occupation: str
    birthday: str | None
    home_store: str
    client_since: date


class Purchase(Record):
    purchase_id: str
    client_id: str
    product_id: str
    color: str
    purchase_date: date
    price_cny: int
    store: str


class CalendarDay(Record):
    date: date
    name: str
    type: str


class TierLevel(Record):
    tier: ClientTier
    min_cny: int | None = None
    rule: str


class TierPolicy(Record):
    basis: str
    levels: list[TierLevel]
    usage: str


class Policies(Record):
    pricing: list[str]
    channels: list[str]
    allocation: list[str]
    tiers: TierPolicy

    def tier_for(self, purchase_count: int, spend_cny: int) -> ClientTier:
        """Unclassified means no purchases; otherwise the highest threshold reached."""
        if purchase_count == 0:
            return ClientTier.UNCLASSIFIED
        reached = [
            lv for lv in self.tiers.levels if lv.min_cny is not None and spend_cny >= lv.min_cny
        ]
        return max(reached, key=lambda lv: lv.min_cny).tier


@dataclass(frozen=True)
class Foundation:
    catalog: ProductCatalog
    stores: dict[str, Store]
    services: tuple[Service, ...]
    events: dict[str, Event]
    policies: Policies
    clients: dict[str, Client]
    purchases: tuple[Purchase, ...]
    calendar: tuple[CalendarDay, ...]

    def purchases_of(self, client_id: str, until: date) -> list[Purchase]:
        rows = [p for p in self.purchases if p.client_id == client_id and p.purchase_date <= until]
        return sorted(rows, key=lambda p: p.purchase_date)

    def check_case(self, case: CaseInput) -> None:
        """Strict check for our own test cases: every ID exists and inline identity agrees."""
        info = case.client_information
        if info.client_id is not None:
            client = self.clients.get(info.client_id)
            if client is None:
                raise ValueError(f"{case.case_id}: unknown client ID {info.client_id}")
            for field in ("name", "salutation", "gender", "occupation", "birthday"):
                value = getattr(info, field)
                if value is not None and value != getattr(client, field):
                    raise ValueError(
                        f"{case.case_id}: client_information.{field} disagrees with clients.json"
                    )
        info = case.product_information
        if unknown := [pid for pid in info.product_ids if pid not in self.catalog.products]:
            raise ValueError(f"{case.case_id}: Unknown product IDs: {unknown}")
        if info.event_id and info.event_id not in self.events:
            raise ValueError(f"{case.case_id}: Unknown event ID: {info.event_id}")
