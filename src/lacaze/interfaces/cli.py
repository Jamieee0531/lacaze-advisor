import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from lacaze.application.batch import run_batch
from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import CaseInput, Scenario
from lacaze.evaluation import cli as evaluation_cli
from lacaze.infrastructure.data import RuntimeData, load_cases
from lacaze.infrastructure.provider import create_model
from lacaze.infrastructure.settings import Settings


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="LACAZE fictional client-advisor workflow")
    sub = root.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-data", help="Validate data without a model call")
    validate.add_argument("--cases", type=Path)
    single = sub.add_parser("generate", help="Generate one case with the configured model")
    source = single.add_mutually_exclusive_group(required=True)
    source.add_argument("--case-id")
    source.add_argument("--input", type=Path, help="One CaseInput JSON file, with case_date")
    single.add_argument("--output", type=Path)
    batch = sub.add_parser("batch", help="Run cases and export JSON/CSV, without quality scoring")
    batch.add_argument("--cases", type=Path)
    batch.add_argument("--case-ids", nargs="+")
    batch.add_argument("--output-dir", type=Path)
    batch.add_argument("--concurrency", type=int, choices=range(1, 5), default=1)
    evaluation_cli.add_parser(sub)
    return root


async def execute(args: argparse.Namespace) -> int:
    settings = Settings()
    if args.command == "evaluate":
        return evaluation_cli.run(args, settings.data_dir)
    data = RuntimeData.load(settings.data_dir)
    cases_path = getattr(args, "cases", None) or settings.data_dir / "cases/development.jsonl"
    if args.command == "validate-data":
        cases = load_cases(cases_path)
        print(
            json.dumps(
                {
                    "cases": len(cases),
                    "covered_scenarios": sorted({c.scenario.value for c in cases}),
                    "all_scenarios_covered": {c.scenario for c in cases} == set(Scenario),
                    "products": len(data.catalog.products),
                    "configuration_hash": data.configuration_hash,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "generate" and args.input:
        cases = [CaseInput.model_validate_json(args.input.read_text(encoding="utf-8"))]
    else:
        cases = load_cases(cases_path)
        requested = [args.case_id] if args.command == "generate" else args.case_ids
        if requested:
            selected = {c.case_id: c for c in cases}
            unknown = set(requested) - selected.keys()
            if unknown:
                raise ValueError(f"Unknown case IDs: {sorted(unknown)}")
            cases = [selected[cid] for cid in dict.fromkeys(requested)]
    model, client = create_model(settings)
    workflow = AdvisorWorkflow(model, data, settings.max_product_queries)
    try:
        if args.command == "generate":
            result = await workflow.generate(cases[0])
            text = result.model_dump_json(indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                # Avoid overwriting a previous experiment accidentally.
                with args.output.open("x", encoding="utf-8") as file:
                    file.write(text + "\n")
            print(text)
            return 0
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        directory = args.output_dir or Path("artifacts") / stamp
        summary = await run_batch(workflow, cases, directory, args.concurrency)
        print(f"Results: {directory.resolve()}")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if summary["error"] else 0
    finally:
        await client.close()


def main() -> None:
    raise SystemExit(asyncio.run(execute(parser().parse_args())))
