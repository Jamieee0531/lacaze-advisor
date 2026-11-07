"""Evaluation configuration files under data/: rubric, judge prompt, schema, checks, policies."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, TypeAdapter

from lacaze.domain.models import BrandPolicy, Product, Scenario, ScenarioPolicy
from lacaze.evaluation.models import Frozen

EVALUATION_FILES = {
    "rubric_sha256": "evaluation/rubric.md",
    "judge_prompt_sha256": "evaluation/judge.md",
    "schema_sha256": "evaluation/judgment.schema.json",
    "checks_sha256": "evaluation/checks.json",
}
POLICY_FILES = ("foundation/brand/brand.json", "foundation/brand/scenarios.json")


class CheckConfig(Frozen):
    max_chars: int = Field(gt=0)
    banned_phrases: list[str]
    discount_terms: list[str]
    discount_normal_scenarios: list[Scenario]


@dataclass(frozen=True)
class EvaluationMaterials:
    rubric: str
    judge_prompt: str
    schema_json: str
    checks: CheckConfig
    brand: BrandPolicy
    scenarios: dict[Scenario, ScenarioPolicy]
    product_names: tuple[str, ...]
    hashes: dict[str, str]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_materials(data_dir: Path) -> EvaluationMaterials:
    """Both versions are judged against these same files; their hashes identify the eval version."""
    raw = {path: (data_dir / path).read_text(encoding="utf-8") for path in EVALUATION_FILES.values()}
    policies = {path: (data_dir / path).read_text(encoding="utf-8") for path in POLICY_FILES}
    hashes = {key: sha256(raw[path]) for key, path in EVALUATION_FILES.items()}
    hashes["policies_sha256"] = sha256(json.dumps(policies, sort_keys=True))
    hashes["evaluation_config_hash"] = sha256(json.dumps(hashes, sort_keys=True))
    scenario_list = TypeAdapter(list[ScenarioPolicy]).validate_json(policies[POLICY_FILES[1]])
    products = TypeAdapter(list[Product]).validate_json(
        (data_dir / "foundation/brand/products.json").read_text(encoding="utf-8")
    )
    return EvaluationMaterials(
        rubric=raw[EVALUATION_FILES["rubric_sha256"]],
        judge_prompt=raw[EVALUATION_FILES["judge_prompt_sha256"]],
        schema_json=raw[EVALUATION_FILES["schema_sha256"]],
        checks=CheckConfig.model_validate_json(raw[EVALUATION_FILES["checks_sha256"]]),
        brand=BrandPolicy.model_validate_json(policies[POLICY_FILES[0]]),
        scenarios={p.scenario: p for p in scenario_list},
        product_names=tuple(p.name.split()[0] for p in products),
        hashes=hashes,
    )
