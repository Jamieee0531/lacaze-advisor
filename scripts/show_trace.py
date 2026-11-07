"""Render one generation result as readable Markdown: what each stage received and returned.

uv run python scripts/show_trace.py artifacts/run/C02.json > artifacts/run/C02.trace.md
"""

import json
import sys
from pathlib import Path

PART_TITLES = {
    "user-prompt": "输入（case 层）",
    "tool-call": "模型输出",
    "text": "模型输出",
    "retry-prompt": "代码检查的反馈（触发重试）",
    "tool-return": "代码检查结果",
}


def block(value, lang="json") -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    if lang == "json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            lang = ""
    return f"```{lang}\n{text}\n```"


def render_stage(name: str, messages: list[dict]) -> list[str]:
    out = [f"## {name}"]
    shown_instructions = False
    for i, message in enumerate(messages, 1):
        if message["kind"] == "request" and message.get("instructions") and not shown_instructions:
            out += [
                "### 组装后的 instructions（品牌层 + 场景层）",
                block(message["instructions"], ""),
            ]
            shown_instructions = True
        for part in message["parts"]:
            kind = part["part_kind"]
            title = PART_TITLES.get(kind, kind)
            content = part.get("args") if kind == "tool-call" else part.get("content")
            out += [f"### {i}. {title}", block(content)]
    return out


def render(record: dict) -> str:
    result = record["result"]
    lines = [
        f"# Trace · {result['case_id']} · {result['scenario']}",
        f"版本 {result['app_version']} · 模型 {result['model']} · 业务日期 {result['case_date']}",
        "",
        "| 环节 | 请求次数 | 输入 token | 输出 token | 用时（秒） |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {u['stage']} | {u['requests']} | {u['input_tokens']} | {u['output_tokens']} | "
        f"{u['duration_seconds']} |"
        for u in result["usage"]
    ]
    lines += ["", "## 最终三条", ""]
    for angle, draft in zip(result["plan"]["angles"], result["drafts"], strict=True):
        lines += [
            f"**{draft['angle']}. {angle['name']}**（用到 {draft['fact_ids'] or '无'}）",
            "",
            f"> {draft['text']}",
            "",
        ]
    lines += ["**警告**：" + ("；".join(result["warnings"]) or "无"), ""]
    lines += ["## 准备节点产出的事实包", block(result["pack"])]
    for stage in ("planner", "writer"):
        lines += render_stage(stage.capitalize(), result["trace"].get(stage, []))
    return "\n\n".join(lines) + "\n"


if __name__ == "__main__":
    print(render(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))), end="")
