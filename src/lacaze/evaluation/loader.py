"""Read existing batch artifacts without re-running generation."""

import json
from pathlib import Path

from lacaze.domain.models import CaseInput, ProductInformation, SuppliedFact
from lacaze.evaluation.models import EvalCase, LoadedRun


def load_run(run_dir: Path) -> LoadedRun:
    """Successful case records become EvalCases; failed records are listed as skipped."""
    paths = sorted(run_dir.glob("*.json"))
    records = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in paths
        if p.stem not in {"summary", "configuration"}
    }
    if not records:
        raise FileNotFoundError(f"No case records found in {run_dir}")
    cases, skipped = [], []
    for stem, record in records.items():
        if record.get("status") != "success":
            skipped.append(stem)
            continue
        cases.append(_to_eval_case(record, run_dir.name))
    return LoadedRun(run_dir=str(run_dir), cases=tuple(cases), skipped=skipped)


def _to_eval_case(record: dict, run_name: str) -> EvalCase:
    case = CaseInput.model_validate(record["input"])
    result = record["result"]
    if result["case_id"] != case.case_id:
        raise ValueError(f"Result case_id {result['case_id']} does not match input {case.case_id}")
    provenance = record.get("provenance") or {}
    if "pack" in result:  # v0.2+: the prepared pack is exactly what the generator saw
        client = result["pack"]["client"]
        facts = tuple(SuppliedFact.model_validate(f) for f in result["pack"]["facts"])
    else:
        client = case.client_information.model_dump(mode="json", exclude_none=True)
        facts = _legacy_facts(ProductInformation.model_validate(result["facts"]))
    return EvalCase(
        case_id=case.case_id,
        scenario=case.scenario,
        case_date=case.case_date,
        input=case,
        client=client,
        facts=facts,
        messages=tuple(result["candidates"]["messages"]),
        app_version=result["app_version"],
        configuration_hash=result["configuration_hash"],
        generation_model=result["model"],
        source_run=provenance.get("source_run", run_name),
    )


def read_eval_case(raw: dict) -> EvalCase:
    """Read a stored EvalCase, including ones saved before v0.2 (no client, nested facts)."""
    if isinstance(raw.get("facts"), dict):
        case = CaseInput.model_validate(raw["input"])
        raw = {
            **raw,
            "client": case.client_information.model_dump(mode="json", exclude_none=True),
            "facts": _legacy_facts(ProductInformation.model_validate(raw["facts"])),
        }
    return EvalCase.model_validate(raw)


def _legacy_facts(info: ProductInformation) -> tuple[SuppliedFact, ...]:
    """v0.1.x results stored products and supplied facts separately; flatten them."""
    facts = []
    for p in info.products:
        details = p.model_dump(mode="json", exclude_none=True, exclude={"product_id", "name"})
        details = {k: v for k, v in details.items() if v != []}
        text = f"{p.name}：价格 {p.price_cny:,} 元；" + json.dumps(details, ensure_ascii=False)
        facts.append(SuppliedFact(fact_id=p.product_id, text=text, kind="product"))
    facts += [f.model_copy(update={"kind": "event"}) for f in info.event_facts]
    facts += [
        f.model_copy(update={"kind": "policy" if f.fact_id.startswith("policy_") else "service"})
        for f in info.service_facts
    ]
    facts += [
        SuppliedFact(fact_id=f"unavailable_{i}", text=f"未提供：{t}")
        for i, t in enumerate(info.unavailable_information, 1)
    ]
    return tuple(facts)
