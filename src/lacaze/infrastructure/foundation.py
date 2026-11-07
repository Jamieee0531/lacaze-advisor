"""Business data from data/foundation and resolution of a case's product and event IDs."""

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict

from lacaze.domain.models import CaseInput, ClientTier, ProductInformation, SuppliedFact
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
        try:
            self.resolve(case.product_information)
        except ValueError as exc:
            raise ValueError(f"{case.case_id}: {exc}") from exc

    def resolve(self, info: ProductInformation) -> ProductInformation:
        """Expand product and event IDs into the facts the model may use."""
        unknown = [pid for pid in info.product_ids if pid not in self.catalog.products]
        if unknown:
            raise ValueError(f"Unknown product IDs: {unknown}")
        if info.event_id and info.event_id not in self.events:
            raise ValueError(f"Unknown event ID: {info.event_id}")
        products = {p.product_id: p for p in info.products}
        products |= {pid: self.catalog.products[pid] for pid in info.product_ids}
        event_facts = list(info.event_facts)
        if info.event_id:
            event_facts += self._event_facts(self.events[info.event_id])
        return info.model_copy(
            update={
                "products": list(products.values()),
                "event_facts": event_facts,
                "service_facts": list(info.service_facts) + self._service_facts(),
            }
        )

    def _event_facts(self, event: Event) -> list[SuppliedFact]:
        store = self.stores[event.store].name
        items = {
            "name": f"活动名称：{event.name}",
            "time": f"时间：{_chinese_date(event.date)} {event.time}",
            "store": f"地点：{store}",
            "audience": f"参加范围：{event.audience}",
            "content": f"内容：{event.content}",
            "appointment": f"接待安排：{event.appointment}",
            "not_included": f"不包含：{'、'.join(event.not_included)}",
            "note": event.note,
        }
        return [SuppliedFact(fact_id=f"{event.event_id}.{k}", text=v) for k, v in items.items()]

    def _service_facts(self) -> list[SuppliedFact]:
        facts = [
            SuppliedFact(
                fact_id=s.service_id,
                text=f"{s.name}：{s.description}适用：{s.eligibility}；办理：{s.how}",
            )
            for s in self.services
        ]
        for group in ("pricing", "channels", "allocation"):
            facts += [
                SuppliedFact(fact_id=f"policy_{group}_{i}", text=text)
                for i, text in enumerate(getattr(self.policies, group), 1)
            ]
        return facts


def _chinese_date(iso: str) -> str:
    year, month, day = (int(part) for part in iso.split("-"))
    return f"{year}年{month}月{day}日"
