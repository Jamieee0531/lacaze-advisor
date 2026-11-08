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
import math
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

COLUMNS = [
    ("Case ID", 9),
    ("Scenario", 30),
    ("Client information", 40),
    ("Conversation history", 60),
    ("Product information", 64),
    ("Output 1", 42),
    ("Output 2", 42),
    ("Output 3", 42),
]
ROLES = {"client": "客户", "advisor": "顾问"}
LINE_POINTS = 15
MAX_ROW_POINTS = 409  # Excel's limit
PURCHASE = re.compile(r"购买记录：(\d+)年(\d+)月(\d+)日购入 (.+?)，距今 \d+ 天")


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
    purchases = [purchase(f["text"]) for f in pack["facts"] if f["kind"] == "purchase"]
    if purchases:
        lines.append("购买记录：" + "；".join(purchases))
    return "\n".join(lines)


def purchase(text: str) -> str:
    """'购买记录：2024年12月14日购入 Margaux 翻盖包（黑色），距今 692 天' -> '2024-12-14 Margaux 翻盖包（黑色）'"""
    match = PURCHASE.fullmatch(text)
    if not match:
        return text
    year, month, day, item = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d} {item}"


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
    groups: dict[str, list[dict]] = {}
    for fact in facts:
        groups.setdefault(fact["fact_id"].split(".")[0], []).append(fact)
    return "\n".join(product_paragraph(group) for group in groups.values())


def product_paragraph(facts: list[dict]) -> str:
    """One product or event per paragraph; later facts drop the repeated product name."""
    name = facts[0]["text"].split(" ")[0] + " "
    parts = []
    for i, fact in enumerate(facts):
        text = (fact["text"] if i == 0 else fact["text"].removeprefix(name)).rstrip("。")
        parts.append(text + ("（内部）" if fact["internal"] and "内部" not in text else ""))
    return "；".join(parts)


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


def row_height(cells) -> float:
    """Tall enough to show the longest cell without opening it."""
    lines = max(
        sum(math.ceil(max(display_width(part), 1) / width) for part in str(cell.value).split("\n"))
        for cell, (_, width) in zip(cells, COLUMNS, strict=True)
    )
    return min(lines * LINE_POINTS, MAX_ROW_POINTS)


def display_width(text: str) -> float:
    """Excel column width units: a Chinese character takes about two, a Latin one about one."""
    return sum(2 if ord(ch) >= 0x2E80 else 1.1 for ch in text)


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
    for r in range(2, sheet.max_row + 1):
        sheet.row_dimensions[r].height = row_height(sheet[r])
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions

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
