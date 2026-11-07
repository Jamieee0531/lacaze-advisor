"""Read existing batch artifacts without re-running generation."""

import json
from pathlib import Path

from lacaze.domain.models import CaseInput, ProductInformation
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
    return EvalCase(
        case_id=case.case_id,
        scenario=case.scenario,
        case_date=case.case_date,
        input=case,
        # Facts visible at generation time: supplied snapshot plus catalog query results.
        facts=ProductInformation.model_validate(result["facts"]),
        messages=tuple(result["candidates"]["messages"]),
        app_version=result["app_version"],
        configuration_hash=result["configuration_hash"],
        generation_model=result["model"],
        source_run=provenance.get("source_run", run_name),
    )
