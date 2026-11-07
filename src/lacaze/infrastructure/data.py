import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from lacaze.domain.models import BrandPolicy, CaseInput, Product, Scenario, ScenarioPolicy
from lacaze.infrastructure.catalog import ProductCatalog


@dataclass(frozen=True)
class RuntimeData:
    brand: BrandPolicy
    scenarios: dict[Scenario, ScenarioPolicy]
    catalog: ProductCatalog
    prompts: dict[str, str]
    configuration_hash: str
    source_files: dict[str, str]

    @classmethod
    def load(cls, directory: Path) -> "RuntimeData":
        paths = [
            "policies/brand.json",
            "policies/scenarios.json",
            "catalog/products.json",
            "prompts/extract.md",
            "prompts/decide.md",
            "prompts/generate.md",
        ]
        raw = {path: (directory / path).read_text(encoding="utf-8") for path in paths}
        brand = BrandPolicy.model_validate_json(raw[paths[0]])
        policies = TypeAdapter(list[ScenarioPolicy]).validate_json(raw[paths[1]])
        scenarios = {p.scenario: p for p in policies}
        if set(scenarios) != set(Scenario) or len(policies) != len(Scenario):
            raise ValueError("Exactly one policy is required for each of the six scenarios")
        products = TypeAdapter(list[Product]).validate_json(raw[paths[2]])
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        return cls(
            brand,
            scenarios,
            ProductCatalog(products),
            {name: raw[f"prompts/{name}.md"] for name in ["extract", "decide", "generate"]},
            digest,
            raw,
        )


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
