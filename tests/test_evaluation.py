import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lacaze.evaluation import calibration, checks, pipeline, report
from lacaze.evaluation.loader import load_run
from lacaze.evaluation.materials import load_materials
from lacaze.evaluation.models import (
    CaseJudgment,
    Label,
    compute_label,
    judgment_schema_json,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
JUDGE_MODEL = "test-judge-model"
GOOD = {
    "fabricates_facts": False,
    "crosses_brand_redline": False,
    "contradicts_client_wish": False,
    "is_personal": True,
    "natural_and_on_brand": True,
    "responds_to_moment": True,
}


def verdict(answer: bool) -> dict:
    return {"answer": answer, "reason": "「原文」测试理由"}


def judgment_payload(case_id: str, answers: list[dict], distinct: bool = True) -> dict:
    return {
        "case_id": case_id,
        "judge_model": JUDGE_MODEL,
        "messages": [
            {"message_index": i, **{k: verdict(v) for k, v in a.items()}}
            for i, a in enumerate(answers, 1)
        ],
        "distinct_angles": verdict(distinct),
    }


def write_run(directory: Path, cases, messages_by_case: dict, version: str) -> Path:
    directory.mkdir(parents=True)
    by_id = {c.case_id: c for c in cases}
    for case_id, messages in messages_by_case.items():
        case = by_id[case_id]
        record = {
            "input": case.model_dump(mode="json"),
            "status": "success",
            "result": {
                "case_id": case_id,
                "scenario": case.scenario.value,
                "case_date": case.case_date.isoformat(),
                "app_version": version,
                "model": "generator-model",
                "configuration_hash": f"hash-{version}",
                "facts": case.product_information.model_dump(mode="json"),
                "candidates": {"messages": messages},
            },
            "provenance": {"source_run": f"source-{version}"},
        }
        (directory / f"{case_id}.json").write_text(json.dumps(record, ensure_ascii=False))
    (directory / "C99.json").write_text(json.dumps({"input": {}, "status": "error"}))
    return directory


C02_MESSAGES = [
    "林女士您好，Odette 公文托特 8.5 万元，偏商务；Margaux 翻盖包 6.8 万元。",
    "林女士，Odette 大容量、外观干练，您开会时可以考虑。",
    "林女士，先发两款给您比较，Héritage 也很合适！",
]
C10_MESSAGES = [
    "吴女士，LACAZE 不打折也不议价，Margaux 是 6.8 万元。",
    "吴女士，亲爱的，我们统一定价，没法给九折。",
    "吴女士，九折确实给不了，您可以来店里再看看实物。",
]


@pytest.fixture
def run_dir(tmp_path, cases):
    return write_run(
        tmp_path / "run-v2", cases, {"C02": C02_MESSAGES, "C10": C10_MESSAGES}, "0.2.0"
    )


@pytest.fixture
def materials():
    return load_materials(DATA_DIR)


# --- labels and judgment contract -------------------------------------------------


def test_label_is_computed_from_criteria():
    assert compute_label(GOOD) is Label.GOOD
    assert compute_label({**GOOD, "is_personal": False}) is Label.NEEDS_EDIT
    assert compute_label({**GOOD, "fabricates_facts": True}) is Label.NOT_ACCEPTABLE
    # Not acceptable takes precedence over failed Good criteria.
    unacceptable = {**GOOD, "contradicts_client_wish": True, "is_personal": False}
    assert compute_label(unacceptable) is Label.NOT_ACCEPTABLE
    with pytest.raises(KeyError):
        compute_label({"is_personal": True})


def test_judgment_requires_three_indexed_messages_and_reasons():
    CaseJudgment.model_validate(judgment_payload("C02", [GOOD] * 3))
    with pytest.raises(ValidationError):
        CaseJudgment.model_validate(judgment_payload("C02", [GOOD] * 2))
    duplicated = judgment_payload("C02", [GOOD] * 3)
    duplicated["messages"][2]["message_index"] = 1
    with pytest.raises(ValidationError):
        CaseJudgment.model_validate(duplicated)
    empty_reason = judgment_payload("C02", [GOOD] * 3)
    empty_reason["messages"][0]["is_personal"]["reason"] = ""
    with pytest.raises(ValidationError):
        CaseJudgment.model_validate(empty_reason)
    with pytest.raises(ValidationError):
        CaseJudgment.model_validate({**judgment_payload("C02", [GOOD] * 3), "label": "Good"})


def test_schema_file_matches_judgment_model():
    on_disk = json.loads((DATA_DIR / "evaluation/judgment.schema.json").read_text())
    assert on_disk == json.loads(judgment_schema_json())


# --- loader -------------------------------------------------------------------------


def test_loader_reads_versions_facts_and_skips_failed_records(run_dir):
    loaded = load_run(run_dir)
    assert [c.case_id for c in loaded.cases] == ["C02", "C10"]
    assert loaded.skipped == ["C99"]
    c02 = loaded.cases[0]
    assert c02.app_version == "0.2.0"
    assert c02.configuration_hash == "hash-0.2.0"
    assert c02.source_run == "source-0.2.0"
    assert {p.product_id for p in c02.facts.products} == {"odette", "margaux", "sable"}
    assert c02.messages == tuple(C02_MESSAGES)


def test_loader_reads_existing_artifact_formats_when_present():
    root = Path(__file__).resolve().parents[1] / "artifacts"
    for name in ["review-v0.1.2", "development-v0.1.1"]:
        if not (root / name).is_dir():
            pytest.skip("local artifacts are not part of the repository")
        loaded = load_run(root / name)
        assert len(loaded.cases) == 10 and not loaded.skipped
        assert all(len(c.messages) == 3 for c in loaded.cases)


# --- code checks ------------------------------------------------------------------


def codes(flags) -> list[str]:
    return [f.code for f in flags]


def test_checks_flag_facts_outside_case_scope(run_dir, materials):
    c02 = load_run(run_dir).cases[0]
    first, _, third = (checks.run_checks(m, c02, materials) for m in C02_MESSAGES)
    assert first == []  # supplied prices and products are allowed
    assert "product_out_of_scope" in codes(third)
    assert "exclamation" in codes(third)
    unknown_price = checks.run_checks("林女士，Odette 现在是七万五。", c02, materials)
    assert codes(unknown_price) == ["unsupported_price"]


def test_checks_use_phrases_not_single_characters(run_dir, materials):
    c02 = load_run(run_dir).cases[0]
    harmless = "林女士，亲自试背会更直观，这些宝贵的意见我记下了，颜色很抢眼。"
    assert checks.run_checks(harmless, c02, materials) == []
    assert "banned_phrase" in codes(checks.run_checks(C10_MESSAGES[1], c02, materials))


def test_discount_terms_note_scenario_instead_of_failing(run_dir, materials):
    loaded = load_run(run_dir)
    c02, c10 = loaded.cases
    in_price_objection = checks.run_checks(C10_MESSAGES[0], c10, materials)
    assert codes(in_price_objection) == ["discount_term"]
    assert in_price_objection[0].severity == "info"
    assert "Price objection" in in_price_objection[0].detail
    elsewhere = checks.run_checks("林女士，Odette 不打折。", c02, materials)
    assert elsewhere[0].severity == "warning"
    assert "Product recommendation" in elsewhere[0].detail


def test_checks_dates_times_salutation_and_length(cases, tmp_path, materials):
    run = write_run(tmp_path / "event-run", cases, {"C07": ["x", "y", "z"]}, "0.2.0")
    c07 = load_run(run).cases[0]
    supported = "张女士，11月14日14:00至17:00在上海澄园店，可提出15:30的意向时段。"
    assert checks.run_checks(supported, c07, materials) == []
    wrong = "11月15日16:00见。"
    assert set(codes(checks.run_checks(wrong, c07, materials))) == {
        "unsupported_date",
        "unsupported_time",
        "missing_salutation",
    }
    assert "too_long" in codes(checks.run_checks("张女士" + "很" * 200, c07, materials))


def test_chinese_numeral_prices_are_parsed():
    assert checks.extract_prices("六万八") == {68000}
    assert checks.extract_prices("十五万元") == {150000}
    assert checks.extract_prices("8.5 万元，¥42,000") == {85000, 42000}


# --- prepare / collect ------------------------------------------------------------


def write_judgments(eval_dir: Path, payloads: dict[str, dict]) -> None:
    for case_id, payload in payloads.items():
        path = eval_dir / "judgments" / f"{case_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False))


def test_prepare_writes_blind_packets_with_policies_and_generation_facts(run_dir, tmp_path):
    eval_dir = tmp_path / "eval"
    manifest = pipeline.prepare(run_dir, eval_dir, DATA_DIR, JUDGE_MODEL)
    assert [c["case_id"] for c in manifest["cases"]] == ["C02", "C10"]
    assert manifest["judge_model"] == JUDGE_MODEL
    assert set(manifest["evaluation_config"]) >= {
        "rubric_sha256",
        "judge_prompt_sha256",
        "policies_sha256",
        "evaluation_config_hash",
    }
    packet = (eval_dir / "packets/C02.md").read_text()
    for expected in ["不打折、不议价", "Product recommendation", "Odette", C02_MESSAGES[2]]:
        assert expected in packet
    for hidden in ["0.2.0", "hash-0.2.0", "source-0.2.0", "product_out_of_scope"]:
        assert hidden not in packet
    assert JUDGE_MODEL in packet
    assert (eval_dir / "judgments").is_dir()
    with pytest.raises(FileExistsError):
        pipeline.prepare(run_dir, eval_dir, DATA_DIR, JUDGE_MODEL)


def test_collect_validates_judgments_and_computes_summary(run_dir, tmp_path):
    eval_dir = tmp_path / "eval"
    pipeline.prepare(run_dir, eval_dir, DATA_DIR, JUDGE_MODEL)
    with pytest.raises(FileNotFoundError, match="C02"):
        pipeline.collect(eval_dir, DATA_DIR)
    fabricated = {**GOOD, "fabricates_facts": True}
    impersonal = {**GOOD, "is_personal": False}
    write_judgments(
        eval_dir,
        {
            "C02": judgment_payload("C02", [GOOD, impersonal, fabricated], distinct=False),
            "C10": judgment_payload("C10", [GOOD, GOOD, impersonal]),
        },
    )
    summary = pipeline.collect(eval_dir, DATA_DIR)
    assert summary["label_counts"] == {"Good": 3, "Needs edit": 2, "Not acceptable": 1}
    assert summary["defect_counts"]["fabricates_facts"] == 1
    assert summary["defect_counts"]["is_personal"] == 2
    assert summary["distinct_angles"] == {"pass": 1, "total": 2}
    assert summary["versions"]["app_versions"] == ["0.2.0"]
    assert summary["judge_model"] == JUDGE_MODEL
    results = json.loads((eval_dir / "results.json").read_text())
    third = next(r for r in results["messages"] if r["case_id"] == "C02" and r["message_index"] == 3)
    assert third["label"] == "Not acceptable"
    assert "product_out_of_scope" in [f["code"] for f in third["flags"]]
    with (eval_dir / "results.csv").open(encoding="utf-8-sig") as file:
        assert len(list(csv.DictReader(file))) == 6


def test_collect_rejects_wrong_case_or_judge_model(run_dir, tmp_path):
    eval_dir = tmp_path / "eval"
    pipeline.prepare(run_dir, eval_dir, DATA_DIR, JUDGE_MODEL)
    wrong_model = {**judgment_payload("C02", [GOOD] * 3), "judge_model": "other"}
    write_judgments(eval_dir, {"C02": wrong_model, "C10": judgment_payload("C10", [GOOD] * 3)})
    with pytest.raises(ValueError, match="judge_model"):
        pipeline.collect(eval_dir, DATA_DIR)
    write_judgments(eval_dir, {"C02": judgment_payload("C10", [GOOD] * 3)})
    with pytest.raises(ValueError, match="case_id"):
        pipeline.collect(eval_dir, DATA_DIR)


def test_collect_rejects_changed_evaluation_configuration(run_dir, tmp_path):
    eval_dir = tmp_path / "eval"
    pipeline.prepare(run_dir, eval_dir, DATA_DIR, JUDGE_MODEL)
    manifest = json.loads((eval_dir / "manifest.json").read_text())
    manifest["evaluation_config"]["evaluation_config_hash"] = "stale"
    (eval_dir / "manifest.json").write_text(json.dumps(manifest))
    write_judgments(
        eval_dir,
        {"C02": judgment_payload("C02", [GOOD] * 3), "C10": judgment_payload("C10", [GOOD] * 3)},
    )
    with pytest.raises(ValueError, match="evaluation configuration"):
        pipeline.collect(eval_dir, DATA_DIR)


# --- comparison and report --------------------------------------------------------


def collected_eval(tmp_path, cases, name, version, answers_by_case) -> Path:
    run = write_run(
        tmp_path / f"run-{name}", cases, {"C02": C02_MESSAGES, "C10": C10_MESSAGES}, version
    )
    eval_dir = tmp_path / f"eval-{name}"
    pipeline.prepare(run, eval_dir, DATA_DIR, JUDGE_MODEL)
    write_judgments(
        eval_dir, {cid: judgment_payload(cid, answers) for cid, answers in answers_by_case.items()}
    )
    pipeline.collect(eval_dir, DATA_DIR)
    return eval_dir


def test_comparison_and_report(tmp_path, cases):
    bad = {**GOOD, "fabricates_facts": True}
    old = collected_eval(tmp_path, cases, "old", "0.1.0", {"C02": [bad] * 3, "C10": [GOOD] * 3})
    new = collected_eval(tmp_path, cases, "new", "0.2.0", {"C02": [GOOD] * 3, "C10": [GOOD] * 3})
    comparison = pipeline.compare(old, new)
    assert comparison["baseline"]["app_versions"] == ["0.1.0"]
    assert comparison["target"]["app_versions"] == ["0.2.0"]
    c02 = next(c for c in comparison["cases"] if c["case_id"] == "C02")
    assert c02["baseline"] == {"Good": 0, "Needs edit": 0, "Not acceptable": 3}
    assert c02["target"] == {"Good": 3, "Needs edit": 0, "Not acceptable": 0}
    assert comparison["label_delta"]["Not acceptable"] == -3

    path = report.write_report(new, compare_with=old)
    html = path.read_text()
    for section in ["Good", "Needs edit", "Not acceptable", "0.1.0", "0.2.0", "C02", JUDGE_MODEL]:
        assert section in html
    assert C02_MESSAGES[0].split("，")[0] in html
    assert "<script" not in html.lower()
    # Message text is escaped, never injected as markup.
    assert report.escape_text("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"


# --- calibration ------------------------------------------------------------------


def test_calibration_template_is_blind(tmp_path, cases):
    bad = {**GOOD, "fabricates_facts": True}
    eval_dir = collected_eval(tmp_path, cases, "cal", "0.2.0", {"C02": [bad] * 3, "C10": [GOOD] * 3})
    template, review = calibration.write_template(eval_dir)
    text = template.read_text(encoding="utf-8-sig")
    assert "测试理由" not in text and "Not acceptable" not in text
    assert "测试理由" not in review.read_text()
    with template.open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 6
    assert all(rows[0][criterion] == "" for criterion in GOOD)


def test_agreement_between_human_and_judge(tmp_path, cases):
    bad = {**GOOD, "fabricates_facts": True}
    eval_dir = collected_eval(tmp_path, cases, "agr", "0.2.0", {"C02": [bad] * 3, "C10": [GOOD] * 3})
    template, _ = calibration.write_template(eval_dir)
    with template.open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    yes_no = {True: "是", False: "否"}
    for row in rows:
        # Human agrees on C02; on C10 disagrees for message 3 only.
        answers = bad if row["case_id"] == "C02" else GOOD
        if row["case_id"] == "C10" and row["message_index"] == "3":
            answers = {**GOOD, "is_personal": False}
        row.update({k: yes_no[v] for k, v in answers.items()})
        if row["message_index"] == "1":
            row["distinct_angles"] = "是"
    human = tmp_path / "human.csv"
    with human.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    result = calibration.agreement(eval_dir, human)
    assert result["compared_messages"] == 6
    assert result["label_agreement"] == pytest.approx(5 / 6, abs=1e-4)
    assert result["criterion_agreement"]["is_personal"] == pytest.approx(5 / 6, abs=1e-4)
    assert result["criterion_agreement"]["fabricates_facts"] == 1.0
    assert result["distinct_angles_agreement"] == 1.0
    assert result["confusion"]["Needs edit"]["Good"] == 1
    assert len(result["disagreements"]) == 1
    assert -1.0 <= result["label_kappa"] <= 1.0
    assert (eval_dir / "calibration/agreement.json").is_file()


def test_agreement_rejects_invalid_human_values(tmp_path, cases):
    eval_dir = collected_eval(tmp_path, cases, "inv", "0.2.0", {"C02": [GOOD] * 3, "C10": [GOOD] * 3})
    template, _ = calibration.write_template(eval_dir)
    with template.open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    rows[0].update({k: "是" for k in GOOD}, fabricates_facts="也许")
    human = tmp_path / "human.csv"
    with human.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="也许"):
        calibration.agreement(eval_dir, human)


# --- CLI --------------------------------------------------------------------------


def test_cli_runs_full_offline_evaluation(run_dir, tmp_path, monkeypatch, capsys):
    from lacaze.interfaces.cli import main

    eval_dir = tmp_path / "cli-eval"

    def run(*argv: str) -> None:
        monkeypatch.setattr("sys.argv", ["lacaze", "evaluate", *argv])
        with pytest.raises(SystemExit) as exit_info:
            main()
        assert exit_info.value.code == 0

    run("prepare", "--run", str(run_dir), "--out", str(eval_dir), "--judge-model", JUDGE_MODEL)
    write_judgments(
        eval_dir,
        {"C02": judgment_payload("C02", [GOOD] * 3), "C10": judgment_payload("C10", [GOOD] * 3)},
    )
    run("collect", "--eval-dir", str(eval_dir))
    run("report", "--eval-dir", str(eval_dir))
    run("calibration-template", "--eval-dir", str(eval_dir))
    assert (eval_dir / "report.html").is_file()
    assert (eval_dir / "calibration/human_labels.csv").is_file()
    assert "Report:" in capsys.readouterr().out
