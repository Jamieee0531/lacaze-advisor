"""Blind human labelling and human-vs-judge agreement."""

import csv
import json
from collections import Counter
from pathlib import Path

from lacaze.evaluation.models import MESSAGE_CRITERIA, Label, compute_label
from lacaze.evaluation.pipeline import load_collected, load_eval_cases
from lacaze.evaluation.report import render_blind_review

TEMPLATE_COLUMNS = [
    "case_id",
    "scenario",
    "message_index",
    "message",
    *MESSAGE_CRITERIA,
    "distinct_angles",
    "note",
]
TRUE_VALUES = {"是", "y", "yes", "true", "1"}
FALSE_VALUES = {"否", "n", "no", "false", "0"}


def write_template(eval_dir: Path) -> tuple[Path, Path]:
    """CSV with empty criteria plus a review page; neither contains judge output."""
    directory = eval_dir / "calibration"
    directory.mkdir(exist_ok=True)
    template, review = directory / "human_labels.csv", directory / "review.html"
    if template.exists():
        raise FileExistsError(f"{template} exists; it may already contain human labels")
    cases = load_eval_cases(eval_dir)
    with template.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        for case in cases:
            for index, message in enumerate(case.messages, 1):
                writer.writerow(
                    {
                        "case_id": case.case_id,
                        "scenario": case.scenario.value,
                        "message_index": index,
                        "message": message,
                        **{c: "" for c in MESSAGE_CRITERIA},
                        "distinct_angles": "",
                        "note": "",
                    }
                )
    review.write_text(render_blind_review(cases), encoding="utf-8")
    return template, review


def _parse(value: str, where: str) -> bool | None:
    text = value.strip().casefold()
    if not text:
        return None
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError(f"{where}: cannot read “{value}”; use 是 or 否")


def _kappa(pairs: list[tuple[str, str]]) -> float:
    total = len(pairs)
    if not total:
        return 0.0
    observed = sum(h == j for h, j in pairs) / total
    human, judge = Counter(h for h, _ in pairs), Counter(j for _, j in pairs)
    expected = sum(human[k] * judge[k] for k in human) / (total * total)
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return round((observed - expected) / (1 - expected), 4)


def agreement(eval_dir: Path, human_csv: Path) -> dict:
    """Compare completed human rows with judge results; unlabelled rows are ignored."""
    _, results = load_collected(eval_dir)
    judge_rows = {(r["case_id"], r["message_index"]): r for r in results["messages"]}
    judge_cases = {c["case_id"]: c for c in results["cases"]}
    with human_csv.open(encoding="utf-8-sig") as file:
        human_rows = list(csv.DictReader(file))

    pairs, criterion_hits, disagreements = [], Counter(), []
    angle_pairs = []
    for line, row in enumerate(human_rows, 2):
        key = (row["case_id"], int(row["message_index"]))
        if key not in judge_rows:
            raise ValueError(f"Line {line}: {key} is not in the evaluated results")
        answers = {c: _parse(row[c], f"Line {line} {c}") for c in MESSAGE_CRITERIA}
        if all(v is None for v in answers.values()):
            continue
        if any(v is None for v in answers.values()):
            raise ValueError(f"Line {line}: fill all six criteria or leave the row empty")
        judge = judge_rows[key]
        judge_answers = {c: judge["criteria"][c]["answer"] for c in MESSAGE_CRITERIA}
        human_label = compute_label(answers).value
        pairs.append((human_label, judge["label"]))
        differing = [c for c in MESSAGE_CRITERIA if answers[c] != judge_answers[c]]
        criterion_hits.update(c for c in MESSAGE_CRITERIA if c not in differing)
        if differing:
            disagreements.append(
                {
                    "case_id": key[0],
                    "message_index": key[1],
                    "human_label": human_label,
                    "judge_label": judge["label"],
                    "differing_criteria": differing,
                }
            )
        if key[1] == 1:
            angles = _parse(row.get("distinct_angles", ""), f"Line {line} distinct_angles")
            if angles is not None:
                angle_pairs.append(angles == judge_cases[key[0]]["distinct_angles"]["answer"])

    compared = len(pairs)
    labels = [label.value for label in Label]
    result = {
        "human_csv": str(human_csv),
        "compared_messages": compared,
        "label_agreement": round(sum(h == j for h, j in pairs) / compared, 4) if compared else None,
        "label_kappa": _kappa(pairs),
        "criterion_agreement": {
            c: round(criterion_hits[c] / compared, 4) if compared else None
            for c in MESSAGE_CRITERIA
        },
        "distinct_angles_agreement": round(sum(angle_pairs) / len(angle_pairs), 4)
        if angle_pairs
        else None,
        "confusion": {h: {j: sum(p == (h, j) for p in pairs) for j in labels} for h in labels},
        "confusion_axes": "confusion[human_label][judge_label]",
        "disagreements": disagreements,
    }
    (eval_dir / "calibration").mkdir(exist_ok=True)
    (eval_dir / "calibration/agreement.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result
