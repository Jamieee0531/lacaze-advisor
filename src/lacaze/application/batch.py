import asyncio
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import CaseInput


async def run_batch(
    workflow: AdvisorWorkflow, cases: list[CaseInput], output_dir: Path, concurrency: int = 1
) -> dict[str, Any]:
    """Real runs with per-case artifacts; no judge, score or ground truth."""
    if not 1 <= concurrency <= 4:
        raise ValueError("concurrency must be between 1 and 4")
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "configuration.json").write_text(
        json.dumps(workflow.data.source_files, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    async def execute_case(case: CaseInput):
        record: dict[str, Any] = {"input": case.model_dump(mode="json")}
        row = {
            "case_id": case.case_id,
            "scenario": case.scenario.value,
            "case_date": case.case_date.isoformat(),
            "client_information": case.client_information.model_dump_json(exclude_none=True),
            "conversation_history": json.dumps(
                [m.model_dump(mode="json") for m in case.conversation_history], ensure_ascii=False
            ),
            "product_information": case.product_information.model_dump_json(),
        }
        try:
            result = await workflow.generate(case)
            record.update(status="success", result=result.model_dump(mode="json"))
            row.update(
                {f"output_{i}": text for i, text in enumerate(result.candidates.messages, 1)}
            )
            row.update({f"angle_{i}": a.name for i, a in enumerate(result.plan.angles, 1)})
            # The resolved client card, so the export shows who the client is, not just an ID.
            row["client_information"] = result.pack.client.model_dump_json()
            row["warnings"] = "；".join(result.warnings)
            row["status"] = "success"
            print(
                f"{case.case_id}: success ({sum(u.requests for u in result.usage)} requests)",
                flush=True,
            )
        except Exception as exc:
            # Keep independent cases running; no retries/fabricated candidate fallback.
            # Do not persist provider exception bodies or headers, which may contain secrets.
            record.update(status="error", error_type=type(exc).__name__)
            row.update(status="error", error_type=type(exc).__name__)
            print(f"{case.case_id}: error ({type(exc).__name__})", flush=True)
        (output_dir / f"{case.case_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return row, {"case_id": case.case_id, "status": record["status"]}

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(case: CaseInput):
        async with semaphore:
            return await execute_case(case)

    completed = await asyncio.gather(*(bounded(case) for case in cases))
    rows = [row for row, _ in completed]
    results = [result for _, result in completed]

    columns = [
        "case_id",
        "scenario",
        "case_date",
        "client_information",
        "conversation_history",
        "product_information",
        "output_1",
        "output_2",
        "output_3",
        "angle_1",
        "angle_2",
        "angle_3",
        "warnings",
        "status",
        "error_type",
    ]
    with (output_dir / "outputs.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "completed_at": datetime.now(UTC).isoformat(),
        "model": workflow.model_name,
        "configuration_hash": workflow.data.configuration_hash,
        "concurrency": concurrency,
        "total": len(cases),
        "success": sum(r["status"] == "success" for r in results),
        "error": sum(r["status"] == "error" for r in results),
        "cases": results,
        "evaluation": "Execution results only. No ground truth or semantic quality score.",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary
