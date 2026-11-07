"""Static, screenshot-friendly HTML. No scripts, no external resources."""

import html
from pathlib import Path

from lacaze.evaluation.models import MESSAGE_CRITERIA, UNACCEPTABLE_CRITERIA, EvalCase, Label

CRITERION_NAMES = {
    "fabricates_facts": "编造事实",
    "crosses_brand_redline": "碰品牌红线",
    "contradicts_client_wish": "违背客户意愿",
    "is_personal": "个性化",
    "natural_and_on_brand": "自然且符合调性",
    "responds_to_moment": "回应当下",
}
DEFECT_NAMES = {
    "fabricates_facts": "编造事实",
    "crosses_brand_redline": "碰品牌红线",
    "contradicts_client_wish": "违背客户意愿",
    "is_personal": "不够个性化",
    "natural_and_on_brand": "不自然 / 不符调性",
    "responds_to_moment": "未回应当下",
}
LABEL_CLASS = {"Good": "good", "Needs edit": "edit", "Not acceptable": "bad"}
ROLE_NAMES = {"client": "客户", "advisor": "CA"}

CSS = """
:root{--ink:#1f1d1a;--muted:#6b665e;--line:#e4dfd6;--paper:#fbf9f5;--card:#fff;
--good:#2f7d4f;--good-bg:#e6f2ea;--edit:#a06a12;--edit-bg:#fbf0dc;--bad:#b3362c;--bad-bg:#f9e3e0}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:15px/1.6 -apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
main{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 12px}
.meta{color:var(--muted);font-size:13px}.meta code{font-size:12px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .n{font-size:28px;font-weight:650}.card .l{color:var(--muted);font-size:13px}
.card.good .n{color:var(--good)}.card.edit .n{color:var(--edit)}.card.bad .n{color:var(--bad)}
.stack{display:flex;height:26px;border-radius:6px;overflow:hidden;border:1px solid var(--line)}
.stack div{display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px}
.stack .good,.badge.good{background:var(--good)}.stack .edit,.badge.edit{background:var(--edit)}
.stack .bad,.badge.bad{background:var(--bad)}
.bars{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.bar{display:grid;grid-template-columns:150px 1fr 44px;gap:10px;align-items:center;margin:6px 0}
.bar .track{background:#f0ece4;border-radius:4px;height:14px}
.bar .fill{background:#8a5a44;border-radius:4px;height:14px}.bar .fill.na{background:var(--bad)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
border-radius:10px;overflow:hidden;font-size:14px}
th,td{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f4f0e8;font-weight:600}td.num{text-align:center}
.up{color:var(--good);font-weight:600}.down{color:var(--bad);font-weight:600}
.case{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}
.case h3{margin:0;font-size:17px}.case .sub{color:var(--muted);font-size:13px;margin:2px 0 10px}
.ctx{background:#f6f3ee;border-radius:8px;padding:10px 12px;font-size:13px;margin-bottom:12px}
.msg{border-top:1px dashed var(--line);padding:12px 0 4px}
.msg .text{background:#f2f7f2;border-radius:10px;padding:10px 12px;margin:6px 0 8px;white-space:pre-wrap}
.badge{display:inline-block;color:#fff;border-radius:999px;padding:1px 10px;font-size:12px;font-weight:600}
.crit{display:grid;grid-template-columns:22px 118px 1fr;gap:4px 6px;font-size:13px}
.ok{color:var(--good)}.ng{color:var(--bad)}
.flags{margin-top:6px;font-size:12px}.flag{display:inline-block;border:1px solid var(--line);
border-radius:6px;padding:1px 7px;margin:2px 4px 0 0;background:#fffaf0}.flag.info{background:#f2f4f8}
.angles{font-size:13px;margin-top:4px}.note{color:var(--muted);font-size:13px}
"""


def escape_text(value) -> str:
    return html.escape(str(value), quote=True)


def _page(title: str, body: str) -> str:
    return (
        f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape_text(title)}</title><style>{CSS}</style></head>"
        f"<body><main>{body}</main></body></html>\n"
    )


def _rate(count: int, total: int) -> str:
    return f"{count / total:.0%}" if total else "–"


def _cards(summary: dict) -> str:
    total, counts = summary["total_messages"], summary["label_counts"]
    angles = summary["distinct_angles"]
    cards = [f'<div class="card"><div class="n">{total}</div><div class="l">条话术 · '
             f'{summary["total_cases"]} 个 case</div></div>']
    for label in Label:
        n = counts[label.value]
        cards.append(
            f'<div class="card {LABEL_CLASS[label.value]}"><div class="n">{_rate(n, total)}</div>'
            f'<div class="l">{label.value} · {n} 条</div></div>'
        )
    cards.append(
        f'<div class="card"><div class="n">{angles["pass"]}/{angles["total"]}</div>'
        f'<div class="l">三条为不同角度的 case</div></div>'
    )
    return '<div class="cards">' + "".join(cards) + "</div>"


def _stack(counts: dict, total: int) -> str:
    parts = "".join(
        f'<div class="{LABEL_CLASS[k]}" style="width:{v / total * 100:.2f}%">{v}</div>'
        for k, v in counts.items()
        if v and total
    )
    return f'<div class="stack">{parts}</div>'


def _defect_bars(summary: dict) -> str:
    total = summary["total_messages"] or 1
    rows = []
    for criterion, n in summary["defect_counts"].items():
        fill = "fill na" if criterion in UNACCEPTABLE_CRITERIA else "fill"
        rows.append(
            f'<div class="bar"><span>{DEFECT_NAMES[criterion]}</span>'
            f'<div class="track"><div class="{fill}" style="width:{n / total * 100:.2f}%"></div></div>'
            f"<span>{n}</span></div>"
        )
    return '<div class="bars">' + "".join(rows) + "</div>"


def _scenario_table(summary: dict) -> str:
    rows = "".join(
        f"<tr><td>{escape_text(s)}</td>"
        + "".join(f'<td class="num">{counts[label.value]}</td>' for label in Label)
        + "</tr>"
        for s, counts in summary["by_scenario"].items()
    )
    head = "".join(f'<th class="num">{label.value}</th>' for label in Label)
    return f"<table><tr><th>场景</th>{head}</tr>{rows}</table>"


def _delta(value: int, lower_is_better: bool) -> str:
    if value == 0:
        return "0"
    better = value < 0 if lower_is_better else value > 0
    return f'<span class="{"up" if better else "down"}">{value:+d}</span>'


def _comparison(comparison: dict) -> str:
    base, target = comparison["baseline"], comparison["target"]
    base_v, target_v = "/".join(base["app_versions"]), "/".join(target["app_versions"])
    notes = []
    if not comparison["same_evaluation_config"]:
        notes.append("两次评估使用的评估配置不同，结果不可直接比较。")
    if not comparison["same_judge_model"]:
        notes.append("两次评估的 judge 模型不同。")
    lower_better = {"Good": False, "Needs edit": True, "Not acceptable": True}
    summary_rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{base['label_counts'][k]}</td>"
        f"<td class='num'>{target['label_counts'][k]}</td>"
        f"<td class='num'>{_delta(v, lower_better[k])}</td></tr>"
        for k, v in comparison["label_delta"].items()
    )
    summary_rows += "".join(
        f"<tr><td>缺陷：{DEFECT_NAMES[k]}</td><td class='num'>{base['defect_counts'][k]}</td>"
        f"<td class='num'>{target['defect_counts'][k]}</td>"
        f"<td class='num'>{_delta(v, True)}</td></tr>"
        for k, v in comparison["defect_delta"].items()
    )
    summary_rows += (
        f"<tr><td>三条为不同角度</td><td class='num'>{base['distinct_angles']['pass']}</td>"
        f"<td class='num'>{target['distinct_angles']['pass']}</td><td class='num'>"
        f"{_delta(target['distinct_angles']['pass'] - base['distinct_angles']['pass'], False)}"
        f"</td></tr>"
    )

    def triple(counts: dict) -> str:
        return " / ".join(str(counts[label.value]) for label in Label)

    case_rows = "".join(
        f"<tr><td>{escape_text(c['case_id'])}</td><td>{escape_text(c['scenario'])}</td>"
        f"<td class='num'>{triple(c['baseline'])}</td><td class='num'>{triple(c['target'])}</td>"
        f"<td class='num'>{'是' if c['baseline_distinct'] else '否'} → "
        f"{'是' if c['target_distinct'] else '否'}</td></tr>"
        for c in comparison["cases"]
    )
    note_html = "".join(f'<p class="note">⚠ {escape_text(n)}</p>' for n in notes)
    return (
        f"<h2>版本对比：v{escape_text(base_v)} → v{escape_text(target_v)}</h2>{note_html}"
        f"<table><tr><th>指标</th><th class='num'>v{escape_text(base_v)}</th>"
        f"<th class='num'>v{escape_text(target_v)}</th><th class='num'>变化</th></tr>{summary_rows}</table>"
        f"<p class='note'>逐 case 标签数（Good / Needs edit / Not acceptable）：</p>"
        f"<table><tr><th>Case</th><th>场景</th><th class='num'>v{escape_text(base_v)}</th>"
        f"<th class='num'>v{escape_text(target_v)}</th><th class='num'>不同角度</th></tr>{case_rows}</table>"
    )


def _flags(flags: list[dict]) -> str:
    if not flags:
        return ""
    items = "".join(
        f'<span class="flag {escape_text(f["severity"])}">{escape_text(f["code"])}：'
        f'{escape_text(f["detail"])}</span>'
        for f in flags
    )
    return f'<div class="flags">代码检查：{items}</div>'


def _context(case: EvalCase) -> str:
    client_messages = [m for m in case.input.conversation_history if m.role == "client"]
    latest = (
        f"客户最近一条（{client_messages[-1].date.isoformat()}）：「{escape_text(client_messages[-1].text)}」"
        if client_messages
        else "无客户历史消息"
    )
    info = case.input.client_information
    return (
        f'<div class="ctx">{escape_text(info.name)}（{escape_text(info.salutation or "未记录称呼")}）'
        f" · 业务日期 {case.case_date.isoformat()}<br>{latest}</div>"
    )


def _case_detail(case: EvalCase, case_row: dict, message_rows: list[dict]) -> str:
    angles = case_row["distinct_angles"]
    mark = '<span class="ok">✓</span>' if angles["answer"] else '<span class="ng">✗</span>'
    parts = [
        f'<div class="case" id="{escape_text(case.case_id)}"><h3>{escape_text(case.case_id)} · '
        f"{escape_text(case.scenario.value)}</h3>"
        f'<div class="sub">v{escape_text(case.app_version)} · 来源批次 {escape_text(case.source_run)}</div>',
        _context(case),
        f'<div class="angles">{mark} 三条为不同角度：{escape_text(angles["reason"])}</div>',
    ]
    for row in message_rows:
        criteria = []
        for criterion in MESSAGE_CRITERIA:
            item = row["criteria"][criterion]
            icon = '<span class="ng">✗</span>' if item["defect"] else '<span class="ok">✓</span>'
            criteria.append(
                f"{icon}<span>{CRITERION_NAMES[criterion]}</span><span>{escape_text(item['reason'])}</span>"
            )
        parts.append(
            f'<div class="msg"><span class="badge {LABEL_CLASS[row["label"]]}">{escape_text(row["label"])}'
            f'</span> 话术 {row["message_index"]}<div class="text">{escape_text(row["message"])}</div>'
            f'<div class="crit">{"".join(criteria)}</div>{_flags(row["flags"])}</div>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_report(
    summary: dict, results: dict, cases: list[EvalCase], comparison: dict | None = None
) -> str:
    versions = summary["versions"]
    config = summary["evaluation_config"]
    flag_rows = "".join(
        f"<tr><td>{escape_text(code)}</td><td class='num'>{n}</td></tr>"
        for code, n in summary["flag_counts"].items()
    ) or "<tr><td colspan='2'>无</td></tr>"
    case_rows = {c["case_id"]: c for c in results["cases"]}
    details = "".join(
        _case_detail(
            case,
            case_rows[case.case_id],
            [r for r in results["messages"] if r["case_id"] == case.case_id],
        )
        for case in cases
        if case.case_id in case_rows
    )
    body = (
        f"<h1>LACAZE 话术评估报告</h1>"
        f'<div class="meta">生成版本 v{escape_text("/".join(versions["app_versions"]))} · '
        f'生成模型 {escape_text("/".join(versions["generation_models"]))} · '
        f'Judge 模型 {escape_text(summary["judge_model"])}<br>'
        f'评估配置 <code>{escape_text(config["evaluation_config_hash"][:12])}</code> '
        f'（rubric <code>{escape_text(config["rubric_sha256"][:8])}</code>，'
        f'judge prompt <code>{escape_text(config["judge_prompt_sha256"][:8])}</code>，'
        f'规则 <code>{escape_text(config["policies_sha256"][:8])}</code>）'
        f' · 生成配置 <code>{escape_text("/".join(h[:12] for h in versions["configuration_hashes"]))}</code>'
        f' · 汇总于 {escape_text(summary["collected_at"][:19].replace("T", " "))} UTC</div>'
        f"{_cards(summary)}"
        f"<h2>三档标签分布</h2>{_stack(summary['label_counts'], summary['total_messages'])}"
        f'<p class="note">标签由代码根据 judge 的逐项判断计算：命中任一“不可接受”项 → Not acceptable；'
        f"三项 Good 条件全部满足 → Good；其余 → Needs edit。</p>"
        f"<h2>缺陷类型（条数）</h2>{_defect_bars(summary)}"
        f"<h2>按场景</h2>{_scenario_table(summary)}"
        + (_comparison(comparison) if comparison else "")
        + f"<h2>代码检查 flag（仅提示，不参与判定）</h2>"
        f"<table><tr><th>flag</th><th class='num'>条数</th></tr>{flag_rows}</table>"
        f"<h2>逐 case 明细</h2>{details}"
    )
    return _page("LACAZE 评估报告", body)


def write_report(eval_dir: Path, compare_with: Path | None = None) -> Path:
    # Imported here to keep report rendering importable by calibration without a cycle.
    from lacaze.evaluation.pipeline import compare, load_collected, load_eval_cases

    summary, results = load_collected(eval_dir)
    comparison = compare(compare_with, eval_dir) if compare_with else None
    path = eval_dir / "report.html"
    path.write_text(
        render_report(summary, results, load_eval_cases(eval_dir), comparison), encoding="utf-8"
    )
    return path


def render_blind_review(cases: list[EvalCase]) -> str:
    """Case context and drafts for human labelling, without any judge output."""
    blocks = []
    for case in cases:
        history = "".join(
            f"<li>[{m.date.isoformat()}] {ROLE_NAMES[m.role]}：{escape_text(m.text)}</li>"
            for m in case.input.conversation_history
        ) or "<li>无历史消息</li>"
        facts = case.facts
        fact_items = [
            f"{escape_text(p.name)}：{p.price_cny:,} 元；{escape_text('、'.join(p.features))}"
            for p in facts.products
        ]
        fact_items += [escape_text(f.text) for f in facts.event_facts + facts.service_facts]
        fact_items += [f"未提供：{escape_text(t)}" for t in facts.unavailable_information]
        facts_html = "".join(f"<li>{t}</li>" for t in fact_items) or "<li>无</li>"
        messages = "".join(
            f'<div class="msg">话术 {i}<div class="text">{escape_text(t)}</div></div>'
            for i, t in enumerate(case.messages, 1)
        )
        info = case.input.client_information
        blocks.append(
            f'<div class="case"><h3>{escape_text(case.case_id)} · {escape_text(case.scenario.value)}</h3>'
            f'<div class="sub">{escape_text(info.name)}（{escape_text(info.salutation or "")}）· '
            f"业务日期 {case.case_date.isoformat()}</div>"
            f'<div class="ctx"><b>对话历史</b><ul>{history}</ul><b>可用事实</b><ul>{facts_html}</ul></div>'
            f"{messages}</div>"
        )
    intro = (
        "<h1>人工标注材料</h1><p class='note'>按 data/evaluation/rubric.md 判断，在 human_labels.csv 中"
        "为每条话术填写六项“是 / 否”，每个 case 的 distinct_angles 只在第 1 条填写。"
        "本页不含任何 judge 结果。</p>"
    )
    return _page("LACAZE 人工标注", intro + "".join(blocks))
