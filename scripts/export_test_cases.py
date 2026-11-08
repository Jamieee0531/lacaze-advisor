"""Export deliverable C: the 50 test cases with their three outputs, as one Excel sheet.

Usage:
    uv run --no-project --with openpyxl python scripts/export_test_cases.py \
        artifacts/development-v0.2.3-final artifacts/test-v0.2.3-final \
        --out deliverables/C_test_cases.xlsx

Each run directory holds one Cxx.json per case. Inputs are shown as the tool saw them
after preparation: the client card and purchases from store records, and the product and
event facts loaded for the scenario. Facts marked internal are for the advisor only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

COLUMNS = [
    ("Case ID", 9),
    ("Scenario", 18),
    ("Client information", 34),
    ("Conversation history", 60),
    ("Product information", 50),
    ("Output 1", 42),
    ("Output 2", 42),
    ("Output 3", 42),
]
ROLES = {"client": "客户", "advisor": "顾问"}


def client_information(pack: dict) -> str:
    c = pack["client"]
    rows = [
        ("姓名", c["name"]),
        ("称呼", c["salutation"]),
        ("层级", c["tier"]),
        ("成为客户", c["client_since"]),
        ("累计消费", f"{c['cumulative_spend_cny']:,} 元" if c["cumulative_spend_cny"] else None),
        ("生日", c["birthday"]),
    ]
    lines = [f"{k}：{v}" for k, v in rows if v]
    if not c["purchases_known"]:
        lines.append("新客户，无门店购买记录")
    lines += [f["text"] for f in pack["facts"] if f["kind"] == "purchase"]
    return "\n".join(lines)


def conversation_history(pack: dict) -> str:
    lines = [f"（当天日期：{pack['case_date']}）"]
    if not pack["history"]:
        return "\n".join([*lines, "无对话历史"])
    lines += [f"{m['date']} {ROLES[m['role']]}：{m['text']}" for m in pack["history"]]
    return "\n".join(lines)


def product_information(pack: dict) -> str:
    facts = [f for f in pack["facts"] if f["kind"] in ("product", "event")]
    if not facts:
        return "不适用"
    return "\n".join(f["text"] + ("（内部，不对客户说）" if f["internal"] else "") for f in facts)


def row(result: dict) -> list[str]:
    pack = result["pack"]
    return [
        result["case_id"],
        result["scenario"],
        client_information(pack),
        conversation_history(pack),
        product_information(pack),
        *result["candidates"]["messages"],
    ]


def load(run_dirs: list[Path]) -> list[dict]:
    results = []
    for run_dir in run_dirs:
        for path in sorted(run_dir.glob("C*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["status"] != "success":
                raise SystemExit(f"{path} did not succeed; rerun it before exporting")
            results.append(record["result"])
    return sorted(results, key=lambda r: int(r["case_id"][1:]))


def write(results: list[dict], out: Path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Test cases"
    sheet.append([name for name, _ in COLUMNS])
    for result in results:
        sheet.append(row(result))
    for i, (_, width) in enumerate(COLUMNS, 1):
        sheet.column_dimensions[sheet.cell(1, i).column_letter].width = width
    header = PatternFill("solid", fgColor="E7E2D8")
    for cell in sheet[1]:
        cell.font, cell.fill = Font(bold=True), header
    for line in sheet.iter_rows():
        for cell in line:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions

    about = book.create_sheet("About")
    first = results[0]
    for line in [
        ("Tool version", first["app_version"]),
        ("Generation model", first["model"]),
        ("Cases", f"{len(results)}: C01–C10 development set, C11–C50 held-out test set"),
        ("Brand", "LACAZE is fictional; all clients, products and events are invented."),
        ("Inputs", "As the tool saw them after preparation; purchases come from store records."),
    ]:
        about.append(line)
    about.column_dimensions["A"].width, about.column_dimensions["B"].width = 18, 90

    out.parent.mkdir(parents=True, exist_ok=True)
    book.save(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results = load(args.runs)
    write(results, args.out)
    print(f"{len(results)} cases -> {args.out}")


if __name__ == "__main__":
    main()
