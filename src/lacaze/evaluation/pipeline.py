"""prepare -> (judge) -> collect -> compare. Each step reads and writes one evaluation directory."""

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from lacaze.evaluation.checks import run_checks
from lacaze.evaluation.executors import read_judgment
from lacaze.evaluation.loader import load_run, read_eval_case
from lacaze.evaluation.materials import load_materials, sha256
from lacaze.evaluation.models import (
    MESSAGE_CRITERIA,
    CaseJudgment,
    EvalCase,
    Label,
    compute_label,
    is_defect,
)
from lacaze.evaluation.packets import render_packet

YES_NO = {True: "是", False: "否"}


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_eval_cases(eval_dir: Path) -> list[EvalCase]:
    return [read_eval_case(c) for c in _read_json(eval_dir / "cases.json")]


def prepare(run_dir: Path, eval_dir: Path, data_dir: Path, judge_model: str) -> dict:
    """Export blind packets and code checks for every successful case in an existing run."""
    if not judge_model.strip():
        raise ValueError("judge_model is required")
    loaded = load_run(run_dir)
    materials = load_materials(data_dir)
    eval_dir.mkdir(parents=True, exist_ok=False)
    (eval_dir / "packets").mkdir()
    (eval_dir / "judgments").mkdir()

    manifest_cases, code_checks = [], {}
    for case in loaded.cases:
        packet = render_packet(case, materials, judge_model)
        (eval_dir / "packets" / f"{case.case_id}.md").write_text(packet, encoding="utf-8")
        code_checks[case.case_id] = [
            [f.model_dump() for f in run_checks(m, case, materials)] for m in case.messages
        ]
        manifest_cases.append(
            {
                "case_id": case.case_id,
                "scenario": case.scenario.value,
                "app_version": case.app_version,
                "configuration_hash": case.configuration_hash,
                "generation_model": case.generation_model,
                "source_run": case.source_run,
                "packet_sha256": sha256(packet),
            }
        )
    manifest = {
        "run_dir": str(run_dir),
        "judge_model": judge_model,
        "prepared_at": datetime.now(UTC).isoformat(),
        "evaluation_config": materials.hashes,
        "cases": manifest_cases,
        "skipped": loaded.skipped,
    }
    _write_json(eval_dir / "manifest.json", manifest)
    _write_json(eval_dir / "cases.json", [c.model_dump(mode="json") for c in loaded.cases])
    _write_json(eval_dir / "code_checks.json", code_checks)
    return manifest


def _load_judgments(eval_dir: Path, manifest: dict) -> dict[str, CaseJudgment]:
    expected = [c["case_id"] for c in manifest["cases"]]
    missing = [cid for cid in expected if not (eval_dir / "judgments" / f"{cid}.json").is_file()]
    if missing:
        raise FileNotFoundError(f"Missing judgments: {', '.join(missing)}")
    judgments = {}
    for case_id in expected:
        path = eval_dir / "judgments" / f"{case_id}.json"
        try:
            judgment = read_judgment(path)
        except ValidationError as exc:
            raise ValueError(f"Invalid judgment {path.name}: {exc}") from exc
        if judgment.case_id != case_id:
            raise ValueError(f"{path.name}: case_id is {judgment.case_id}, expected {case_id}")
        if judgment.judge_model != manifest["judge_model"]:
            raise ValueError(
                f"{path.name}: judge_model is {judgment.judge_model}, "
                f"expected {manifest['judge_model']}"
            )
        judgments[case_id] = judgment
    return judgments


def _label_counts(labels) -> dict[str, int]:
    counts = Counter(labels)
    return {label.value: counts.get(label.value, 0) for label in Label}


def collect(eval_dir: Path, data_dir: Path) -> dict:
    """Validate judgments, compute labels in code and write results plus summary."""
    manifest = _read_json(eval_dir / "manifest.json")
    current = load_materials(data_dir).hashes["evaluation_config_hash"]
    if manifest["evaluation_config"]["evaluation_config_hash"] != current:
        raise ValueError(
            "The evaluation configuration changed after prepare; run prepare again "
            "so packets and judgments use the same rubric, prompt and policies."
        )
    judgments = _load_judgments(eval_dir, manifest)
    cases = {c.case_id: c for c in load_eval_cases(eval_dir)}
    code_checks = _read_json(eval_dir / "code_checks.json")

    message_rows, case_rows = [], []
    for case_id, judgment in judgments.items():
        case = cases[case_id]
        labels = []
        for item in judgment.messages:
            label = compute_label(item.answers()).value
            labels.append(label)
            message_rows.append(
                {
                    "case_id": case_id,
                    "scenario": case.scenario.value,
                    "app_version": case.app_version,
                    "configuration_hash": case.configuration_hash,
                    "message_index": item.message_index,
                    "message": case.messages[item.message_index - 1],
                    "label": label,
                    "criteria": {
                        c: {
                            "answer": getattr(item, c).answer,
                            "reason": getattr(item, c).reason,
                            "defect": is_defect(c, getattr(item, c).answer),
                        }
                        for c in MESSAGE_CRITERIA
                    },
                    "flags": code_checks[case_id][item.message_index - 1],
                }
            )
        case_rows.append(
            {
                "case_id": case_id,
                "scenario": case.scenario.value,
                "app_version": case.app_version,
                "labels": labels,
                "distinct_angles": judgment.distinct_angles.model_dump(),
            }
        )

    summary = _summarize(eval_dir, manifest, message_rows, case_rows)
    _write_json(eval_dir / "results.json", {"messages": message_rows, "cases": case_rows})
    _write_csv(eval_dir / "results.csv", message_rows, case_rows)
    _write_json(eval_dir / "summary.json", summary)
    return summary


def _summarize(eval_dir: Path, manifest: dict, message_rows: list, case_rows: list) -> dict:
    total = len(message_rows)
    counts = _label_counts(r["label"] for r in message_rows)
    by_scenario: dict[str, list[str]] = {}
    for row in message_rows:
        by_scenario.setdefault(row["scenario"], []).append(row["label"])
    flags = Counter(f["code"] for r in message_rows for f in r["flags"])
    return {
        "eval_dir": str(eval_dir),
        "run_dir": manifest["run_dir"],
        "judge_model": manifest["judge_model"],
        "evaluation_config": manifest["evaluation_config"],
        "versions": {
            "app_versions": sorted({c["app_version"] for c in manifest["cases"]}),
            "configuration_hashes": sorted({c["configuration_hash"] for c in manifest["cases"]}),
            "generation_models": sorted({c["generation_model"] for c in manifest["cases"]}),
        },
        "total_cases": len(case_rows),
        "total_messages": total,
        "label_counts": counts,
        "label_rates": {k: round(v / total, 4) if total else 0.0 for k, v in counts.items()},
        "defect_counts": {
            c: sum(r["criteria"][c]["defect"] for r in message_rows) for c in MESSAGE_CRITERIA
        },
        "distinct_angles": {
            "pass": sum(c["distinct_angles"]["answer"] for c in case_rows),
            "total": len(case_rows),
        },
        "by_scenario": {s: _label_counts(labels) for s, labels in by_scenario.items()},
        "flag_counts": dict(sorted(flags.items())),
        "collected_at": datetime.now(UTC).isoformat(),
    }


def _write_csv(path: Path, message_rows: list, case_rows: list) -> None:
    distinct = {c["case_id"]: c["distinct_angles"] for c in case_rows}
    columns = ["case_id", "scenario", "app_version", "message_index", "message", "label"]
    for criterion in MESSAGE_CRITERIA:
        columns += [criterion, f"{criterion}_reason"]
    columns += ["distinct_angles", "distinct_angles_reason", "flags"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in message_rows:
            record = {k: row[k] for k in columns[:6]}
            for criterion in MESSAGE_CRITERIA:
                record[criterion] = YES_NO[row["criteria"][criterion]["answer"]]
                record[f"{criterion}_reason"] = row["criteria"][criterion]["reason"]
            angles = distinct[row["case_id"]]
            record["distinct_angles"] = YES_NO[angles["answer"]]
            record["distinct_angles_reason"] = angles["reason"]
            record["flags"] = "；".join(f"{f['code']}: {f['detail']}" for f in row["flags"])
            writer.writerow(record)


def load_collected(eval_dir: Path) -> tuple[dict, dict]:
    if not (eval_dir / "summary.json").is_file():
        raise FileNotFoundError(f"Run collect first: {eval_dir}")
    return _read_json(eval_dir / "summary.json"), _read_json(eval_dir / "results.json")


def compare(baseline_dir: Path, target_dir: Path) -> dict:
    """Case-level comparison. Message order is not paired across versions, label counts are."""
    base_summary, base_results = load_collected(baseline_dir)
    target_summary, target_results = load_collected(target_dir)
    base_cases = {c["case_id"]: c for c in base_results["cases"]}
    target_cases = {c["case_id"]: c for c in target_results["cases"]}

    def side(summary: dict, directory: Path) -> dict:
        return {
            "eval_dir": str(directory),
            "app_versions": summary["versions"]["app_versions"],
            "configuration_hashes": summary["versions"]["configuration_hashes"],
            "label_counts": summary["label_counts"],
            "defect_counts": summary["defect_counts"],
            "distinct_angles": summary["distinct_angles"],
        }

    rows = []
    for case_id in sorted(base_cases.keys() & target_cases.keys()):
        base, target = base_cases[case_id], target_cases[case_id]
        rows.append(
            {
                "case_id": case_id,
                "scenario": target["scenario"],
                "baseline": _label_counts(base["labels"]),
                "target": _label_counts(target["labels"]),
                "baseline_distinct": base["distinct_angles"]["answer"],
                "target_distinct": target["distinct_angles"]["answer"],
            }
        )
    return {
        "baseline": side(base_summary, baseline_dir),
        "target": side(target_summary, target_dir),
        "same_evaluation_config": base_summary["evaluation_config"]["evaluation_config_hash"]
        == target_summary["evaluation_config"]["evaluation_config_hash"],
        "same_judge_model": base_summary["judge_model"] == target_summary["judge_model"],
        "label_delta": {
            k: target_summary["label_counts"][k] - base_summary["label_counts"][k]
            for k in base_summary["label_counts"]
        },
        "defect_delta": {
            k: target_summary["defect_counts"][k] - base_summary["defect_counts"][k]
            for k in base_summary["defect_counts"]
        },
        "cases": rows,
        "unmatched_cases": sorted(base_cases.keys() ^ target_cases.keys()),
    }
