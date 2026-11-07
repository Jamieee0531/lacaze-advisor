"""`lacaze evaluate ...` subcommands. No model call happens here."""

import argparse
import json
from pathlib import Path

from lacaze.evaluation import calibration, pipeline, report


def add_parser(subparsers) -> None:
    evaluate = subparsers.add_parser("evaluate", help="Evaluate existing generation results")
    steps = evaluate.add_subparsers(dest="step", required=True)

    prepare = steps.add_parser("prepare", help="Export blind judge packets and code checks")
    prepare.add_argument("--run", type=Path, required=True, help="Existing artifacts run directory")
    prepare.add_argument("--out", type=Path, required=True, help="New evaluation directory")
    prepare.add_argument("--judge-model", required=True, help="Model that will write judgments")

    collect = steps.add_parser("collect", help="Validate judgments and compute labels")
    collect.add_argument("--eval-dir", type=Path, required=True)

    render = steps.add_parser("report", help="Write a static HTML report")
    render.add_argument("--eval-dir", type=Path, required=True)
    render.add_argument("--compare", type=Path, help="Earlier evaluation directory (baseline)")

    template = steps.add_parser("calibration-template", help="Blind human labelling CSV")
    template.add_argument("--eval-dir", type=Path, required=True)

    agree = steps.add_parser("agreement", help="Human vs judge agreement")
    agree.add_argument("--eval-dir", type=Path, required=True)
    agree.add_argument("--human", type=Path, required=True)


def run(args: argparse.Namespace, data_dir: Path) -> int:
    if args.step == "prepare":
        manifest = pipeline.prepare(args.run, args.out, data_dir, args.judge_model)
        print(f"Packets: {(args.out / 'packets').resolve()}")
        print(f"Write judgments to: {(args.out / 'judgments').resolve()}")
        print(json.dumps({k: manifest[k] for k in ["judge_model", "skipped"]}, ensure_ascii=False))
        print(f"Cases: {len(manifest['cases'])}")
    elif args.step == "collect":
        summary = pipeline.collect(args.eval_dir, data_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.step == "report":
        print(f"Report: {report.write_report(args.eval_dir, args.compare).resolve()}")
    elif args.step == "calibration-template":
        template, review = calibration.write_template(args.eval_dir)
        print(f"Template: {template.resolve()}\nReview page: {review.resolve()}")
    elif args.step == "agreement":
        result = calibration.agreement(args.eval_dir, args.human)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
