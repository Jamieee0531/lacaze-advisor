import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from lacaze.infrastructure.data import RuntimeData, load_cases


@pytest.fixture
def data():
    return RuntimeData.load(Path(__file__).resolve().parents[1] / "data")


@pytest.fixture
def cases():
    return load_cases(Path(__file__).resolve().parents[1] / "data/cases/development.jsonl")


class ScriptedModel:
    """Exercises real PydanticAI orchestration, not model quality. No network.

    `plan_fault` / `draft_fault` make the first answer of that stage break a code check,
    or every answer when `persistent=True`, to exercise retry and warnings.
    """

    def __init__(self, *, plan_fault=None, draft_fault=None, persistent=False):
        self.plan_fault = plan_fault
        self.draft_fault = draft_fault
        self.persistent = persistent
        self.seen = []  # (stage, payload, instructions)
        self.model = FunctionModel(self.respond, model_name="offline-test-model")

    def respond(self, messages, info):
        prompts = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
        payload = json.loads(prompts[0])
        instructions = info.instructions or ""
        is_retry = len(messages) > 1
        fault_now = self.persistent or not is_retry
        schema = info.output_tools[0].parameters_json_schema["properties"]
        if "angles" in schema:
            stage, output = "planner", self._plan(payload, fault_now)
        else:
            stage, output = "writer", self._drafts(payload, fault_now)
        self.seen.append((stage, payload, instructions))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    def _plan(self, payload, fault_now):
        history = [m["message_id"] for m in payload["conversation_history"]]
        facts = [f["fact_id"] for f in payload["facts"]]
        sub_type = "超预算" if payload["scenario"] == "Price objection" else None
        cited = [history[-1:], history[-2:-1] or history[-1:], []]
        angles = [
            {
                "name": name,
                "purpose": "回应客户最近的话",
                "message_ids": cited[i],
                "fact_ids": facts[i : i + 1],
                "next_step": None,
            }
            for i, name in enumerate(["回应近况", "接着上次", "留出余地"])
        ]
        if fault_now and self.plan_fault == "unknown_fact":
            angles[0]["fact_ids"] = ["made_up_fact"]
        return {
            "situation": "客户在等顾问回复",
            "sub_type": sub_type or self.sub_type_for(payload["scenario"]),
            "avoid": ["不催促"],
            "angles": angles,
            "missing": [],
        }

    @staticmethod
    def sub_type_for(scenario):
        return {
            "Birthday and festive greetings": "生日",
            "Product recommendation": "比较候选",
            "Post-purchase care": "使用请求",
            "Reactivation": "单纯问候",
            "Event invitation": "首次邀请",
        }[scenario]

    def _drafts(self, payload, fault_now):
        salutation = payload["salutation"]
        texts = ["这两款可以先了解一下。", "先接着您上次提到的需求聊聊。", "您可以按自己的节奏慢慢看。"]
        drafts = [
            {"angle": a["angle"], "text": f"{salutation}，{text}", "fact_ids": []}
            for a, text in zip(payload["angles"], texts, strict=True)
        ]
        if fault_now and self.draft_fault == "foreign_fact":
            drafts[0]["fact_ids"] = ["not_in_this_angle"]
        if fault_now and self.draft_fault == "made_up_price":
            drafts[1]["text"] = f"{salutation}，这只现在是七万五。"
        return {"drafts": drafts}
