import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from lacaze.domain.models import BrandPolicy, CaseInput, Product, Scenario, ScenarioPolicy
from lacaze.domain.pack import LoadingTable
from lacaze.infrastructure.catalog import ProductCatalog
from lacaze.infrastructure.foundation import (
    CalendarDay,
    Client,
    Event,
    Foundation,
    Policies,
    Purchase,
    Service,
    Store,
)


@dataclass(frozen=True)
class RuntimeData:
    brand: BrandPolicy
    scenarios: dict[Scenario, ScenarioPolicy]
    catalog: ProductCatalog
    foundation: Foundation
    loading: LoadingTable
    prompts: dict[str, str]
    writer_examples: dict[str, str]
    configuration_hash: str
    source_files: dict[str, str]

    @classmethod
    def load(cls, directory: Path) -> "RuntimeData":
        paths = [
            "foundation/brand/brand.json",
            "foundation/brand/scenarios.json",
            "foundation/brand/products.json",
            "foundation/brand/stores.json",
            "foundation/brand/services.json",
            "foundation/brand/events.json",
            "foundation/brand/policies.json",
            "foundation/clients/clients.json",
            "foundation/clients/purchases.json",
            "foundation/brand/calendar.json",
            "context/loading.json",
            "prompts/plan.md",
            "prompts/write.md",
            "prompts/writer_examples.json",
        ]
        raw = {path: (directory / path).read_text(encoding="utf-8") for path in paths}
        brand = BrandPolicy.model_validate_json(raw[paths[0]])
        policies = TypeAdapter(list[ScenarioPolicy]).validate_json(raw[paths[1]])
        scenarios = {p.scenario: p for p in policies}
        if set(scenarios) != set(Scenario) or len(policies) != len(Scenario):
            raise ValueError("Exactly one policy is required for each of the six scenarios")
        catalog = ProductCatalog(TypeAdapter(list[Product]).validate_json(raw[paths[2]]))
        foundation = Foundation(
            catalog=catalog,
            stores=_by_id(TypeAdapter(list[Store]).validate_json(raw[paths[3]]), "store_id"),
            services=tuple(TypeAdapter(list[Service]).validate_json(raw[paths[4]])),
            events=_by_id(TypeAdapter(list[Event]).validate_json(raw[paths[5]]), "event_id"),
            policies=Policies.model_validate_json(raw[paths[6]]),
            clients=_by_id(TypeAdapter(list[Client]).validate_json(raw[paths[7]]), "client_id"),
            purchases=tuple(TypeAdapter(list[Purchase]).validate_json(raw[paths[8]])),
            calendar=tuple(TypeAdapter(list[CalendarDay]).validate_json(raw[paths[9]])),
        )
        _check_references(foundation)
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        return cls(
            brand,
            scenarios,
            catalog,
            foundation,
            LoadingTable.model_validate_json(raw[paths[10]]),
            {name: raw[f"prompts/{name}.md"] for name in ["plan", "write"]},
            _writer_examples(raw["prompts/writer_examples.json"]),
            digest,
            raw,
        )


def _writer_examples(text: str) -> dict[str, str]:
    examples = {k: v for k, v in json.loads(text).items() if not k.startswith("_")}
    if set(examples) != {s.value for s in Scenario}:
        raise ValueError("writer_examples.json needs exactly one example per scenario")
    return examples


def _by_id(records: list, key: str) -> dict:
    result = {getattr(r, key): r for r in records}
    if len(result) != len(records):
        raise ValueError(f"Duplicate {key} values in foundation data")
    return result


def _check_references(f: Foundation) -> None:
    """Every ID one foundation file uses must exist in the file that owns it."""
    products, stores = f.catalog.products, f.stores
    for p in f.purchases:
        if p.client_id not in f.clients or p.product_id not in products or p.store not in stores:
            raise ValueError(f"Purchase {p.purchase_id} references an unknown ID")
    for e in f.events.values():
        if e.store not in stores or not set(e.featured_products) <= products.keys():
            raise ValueError(f"Event {e.event_id} references an unknown ID")
    if any(c.home_store not in stores for c in f.clients.values()):
        raise ValueError("A client references an unknown store")
    if any(p.purchase_date < f.clients[p.client_id].client_since for p in f.purchases):
        raise ValueError("A purchase predates its client's client_since")


def load_cases(path: Path) -> list[CaseInput]:
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if any("case_date" not in record for record in records):
        raise ValueError("Batch fixtures must explicitly provide case_date for reproducibility")
    cases = [CaseInput.model_validate(record) for record in records]
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    return cases
