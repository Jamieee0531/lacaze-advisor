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
    """Exercises real PydanticAI orchestration, not model quality. No network."""

    def __init__(self, *, use_tools=True, corrupt_evidence=False):
        self.use_tools = use_tools
        self.corrupt_evidence = corrupt_evidence
        self.seen = []
        self.model = FunctionModel(self.respond, model_name="offline-test-model")

    def respond(self, messages, info):
        prompts = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
        payload = json.loads(prompts[-1])
        schema = info.output_tools[0].parameters_json_schema["properties"]
        salutation = payload["client_information"]["salutation"]
        if "needs_and_preferences" in schema:
            stage = "extraction"
            original = payload["conversation_history"][0]
            output = {
                "needs_and_preferences": ["Preserve the current request."],
                "conversation_state": "Continue the existing conversation.",
                "relationship_and_style": ["Use the explicit salutation."],
                "relevant_product_names": [],
                "evidence": [
                    {
                        "message_id": original["message_id"],
                        "quote": "fabricated quotation"
                        if self.corrupt_evidence
                        else original["text"],
                    }
                ],
                "information_gaps": [],
                "conflicts": [],
            }
        elif "objective" in schema:
            stage = "decision"
            if self.use_tools and info.function_tools:
                self.seen.append((stage, payload, "tool"))
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "query_products",
                            {
                                "names": ["Odette"],
                                "requested_fields": ["compartments"],
                            },
                        )
                    ]
                )
            output = {
                "objective": "Continue the conversation without inventing facts.",
                "content_focus": ["Respond to the expressed need."],
                "personalization_basis": [{"detail": "Relevant history", "message_ids": ["m001"]}],
                "communication_strategy": {
                    "salutation": salutation,
                    "tone": "restrained",
                    "approach": "respectful",
                    "next_step": None,
                },
                "fact_boundaries": {
                    "product_ids": ["odette"] if self.use_tools else [],
                    "service_and_event_fact_ids": [],
                    "missing_information": ["compartments"],
                    "prohibited_claims": ["Do not invent compartments."],
                    "advisor_notes": [],
                },
            }
        else:
            stage = "generation"
            output = {
                "messages": [
                    f"{salutation}，这两款可以先了解一下。",
                    f"{salutation}，先接着您上次提到的需求聊聊。",
                    f"{salutation}，您可以按自己的节奏慢慢看。",
                ]
            }
        self.seen.append((stage, payload, "output"))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
