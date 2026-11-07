"""Self-contained, blind review packets: no app version, run name or code-check flags."""

import json

from lacaze.evaluation.materials import EvaluationMaterials
from lacaze.evaluation.models import EvalCase

ROLE_NAMES = {"client": "客户", "advisor": "CA"}


def _json_block(value) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def render_history(case: EvalCase) -> str:
    if not case.input.conversation_history:
        return "（无历史消息）"
    return "\n".join(
        f"- [{m.date.isoformat()}] {ROLE_NAMES[m.role]}：{m.text}"
        for m in case.input.conversation_history
    )


def render_facts(case: EvalCase, internal: bool = False) -> str:
    facts = [f for f in case.facts if f.internal == internal]
    if not facts:
        return "（无）"
    return "\n".join(f"- `{f.fact_id}` {f.text}" for f in facts)


def render_packet(case: EvalCase, materials: EvaluationMaterials, judge_model: str) -> str:
    scenario_policy = materials.scenarios[case.scenario]
    messages = "\n\n".join(
        f"### 话术 {i}\n\n{text}" for i, text in enumerate(case.messages, 1)
    )
    sections = [
        f"# 评审材料 · Case {case.case_id}",
        materials.judge_prompt.strip(),
        "---\n\n" + materials.rubric.strip(),
        "---\n\n## 品牌规则\n\n" + _json_block(materials.brand.model_dump(mode="json")),
        "## 场景规则（本 case 场景）\n\n" + _json_block(scenario_policy.model_dump(mode="json")),
        "---\n\n## Case 输入\n\n"
        f"- Case ID：{case.case_id}\n"
        f"- 场景：{case.scenario.value}\n"
        f"- 业务日期（拟发送消息的日期）：{case.case_date.isoformat()}",
        "### 客户信息\n\n"
        + _json_block(case.client),
        "### 对话历史（按时间顺序）\n\n" + render_history(case),
        "## 可用事实\n\n"
        "生成话术时可以告诉客户的事实（含客户的购买记录）。"
        "客户卡片里的层级和累计消费是内部信息，不应出现在话术中。\n\n"
        + render_facts(case),
        "### 内部事实（只用于判断，不能告诉客户）\n\n" + render_facts(case, internal=True),
        "---\n\n## 三条候选话术\n\n" + messages,
        "---\n\n## 输出格式\n\n"
        f"- `case_id` 填写：`{case.case_id}`\n"
        f"- `judge_model` 填写：`{judge_model}`\n"
        "- 只输出一个符合下列 JSON schema 的 JSON 对象，不要输出标签或分数。\n\n"
        "```json\n" + materials.schema_json.strip() + "\n```",
    ]
    return "\n\n".join(sections) + "\n"
