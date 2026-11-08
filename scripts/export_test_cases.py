"""Export deliverable C: the 50 test cases with their three outputs, as one Excel sheet.

Usage:
    uv run --no-project --with openpyxl python scripts/export_test_cases.py \
        artifacts/development-v0.2.3-final artifacts/test-v0.2.3-final \
        --out deliverables/C_test_cases.xlsx

Each run directory holds one Cxx.json per case. The input columns show the case input as
given to the tool: a client ID (or name and salutation for a new client), the conversation,
and product or event IDs. Names in brackets are looked up from data/foundation for reading
only; everything else the tool retrieves during preparation is not shown here.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

COLUMNS = [
    ("Case ID", 9),
    ("Scenario", 30),
    ("Client information", 26),
    ("Conversation history", 60),
    ("Product information", 40),
    ("Output 1", 42),
    ("Output 2", 42),
    ("Output 3", 42),
]
ROLES = {"client": "客户", "advisor": "顾问"}
GENDERS = {"male": "男", "female": "女"}
LINE_POINTS = 15
MAX_ROW_POINTS = 409  # Excel's limit
FOUNDATION = Path(__file__).resolve().parents[1] / "data" / "foundation"


def names(path: str, key: str) -> dict[str, str]:
    rows = json.loads((FOUNDATION / path).read_text(encoding="utf-8"))
    return {r[key]: r["name"] for r in rows}


CLIENTS = names("clients/clients.json", "client_id")
PRODUCTS = names("brand/products.json", "product_id")
EVENTS = names("brand/events.json", "event_id")


def client_information(client: dict) -> str:
    if client["client_id"]:
        return f"client_id：{client['client_id']}\n姓名：{CLIENTS[client['client_id']]}"
    rows = [
        ("姓名", client["name"]),
        ("称呼", client["salutation"]),
        ("性别", GENDERS.get(client["gender"], client["gender"])),
    ]
    return "\n".join(["新客户，无 client_id", *(f"{k}：{v}" for k, v in rows if v)])


def conversation_history(case: dict) -> str:
    lines = [f"（当天日期：{case['case_date']}）"]
    history = case["conversation_history"]
    if not history:
        return "\n".join([*lines, "无对话历史"])
    lines += [f"{m['date']} {ROLES[m['role']]}：{m['text']}" for m in history]
    return "\n".join(lines)


def product_information(product: dict) -> str:
    lines = [f"product_id：{p}（{PRODUCTS[p]}）" for p in product["product_ids"]]
    if product["event_id"]:
        lines.append(f"event_id：{product['event_id']}（{EVENTS[product['event_id']]}）")
    return "\n".join(lines) or "不适用"


def row(record: dict) -> list[str]:
    case = record["input"]
    return [
        case["case_id"],
        case["scenario"],
        client_information(case["client_information"]),
        conversation_history(case),
        product_information(case["product_information"]),
        *record["result"]["candidates"]["messages"],
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
            results.append(record)
    return sorted(results, key=lambda r: int(r["input"]["case_id"][1:]))


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
