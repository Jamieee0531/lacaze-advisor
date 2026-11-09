"""Replays of the v0.2.3 evaluation runs, so an unedited demo case shows the results that were scored.

A replay streams the same events as a live run, stage by stage with a short pause, and never calls
the model. Any change to the input, however small, makes it a new case that runs live.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from lacaze.domain.models import CaseInput
from lacaze.interfaces.demo import _encode

# Seconds per stage: long enough to follow the progress, short enough not to waste the viewer's time.
PACE = {"prepare": 0.4, "planner": 1.6, "writer": 1.8, "polish": 0.8}
MODEL_STAGES = ("planner", "writer", "polish")


def load_replays(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text()) if path.is_file() else {}


def find_replay(replays: dict[str, dict[str, Any]], case: CaseInput) -> dict[str, Any] | None:
    record = replays.get(case.case_id)
    if record and CaseInput.model_validate(record["input"]) == case:
        return record
    return None


def _stage_output(stage: str, record: dict[str, Any]) -> Any:
    result = record["result"]
    if stage == "planner":
        return result["plan"]  # the checked plan, not the model's first answer
    if stage == "polish":
        return {"drafts": result["drafts"], "edits": result["edits"]}
    return record["stages"][stage]["output"]


async def stream_replay(record: dict[str, Any]) -> AsyncGenerator[str]:
    pace, result = PACE, record["result"]
    usage = {u["stage"]: u for u in result["usage"]}
    yield _encode(
        {
            "type": "run_started",
            "version": result["app_version"],
            "model": result["model"],
            "configuration_hash": result["configuration_hash"],
            "replay": True,
        }
    )
    yield _encode({"type": "stage_started", "stage": "prepare", "input": record["input"]})
    await asyncio.sleep(pace["prepare"])
    yield _encode({"type": "stage_completed", "stage": "prepare", "output": result["pack"]})
    for stage in MODEL_STAGES:
        stored = record["stages"].get(stage)
        if stored is None:
            yield _encode({"type": "stage_skipped", "stage": stage, "reason": "未命中修整规则"})
            continue
        yield _encode({"type": "stage_started", "stage": stage, "input": stored["input"]})
        for _ in range(stored["retries"]):
            await asyncio.sleep(pace[stage] / 2)
            yield _encode({"type": "stage_retry", "stage": stage, "problems": []})
        await asyncio.sleep(pace[stage])
        yield _encode(
            {
                "type": "stage_completed",
                "stage": stage,
                "output": _stage_output(stage, record),
                "usage": usage.get(stage),
            }
        )
    yield _encode({"type": "result", "result": result, "replayed": True})
