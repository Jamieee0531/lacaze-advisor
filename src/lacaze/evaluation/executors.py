"""How judgments are produced is separate from what is judged.

Version 1 is file-based: `prepare` writes packets, Claude Code runs one independent
subagent per packet and writes `judgments/<case_id>.json`, `collect` validates them.

An API executor (e.g. PydanticAI with output_type=CaseJudgment) can later implement
JudgeExecutor and write the same judgment files; rubric, packets and labels stay unchanged.
"""

from pathlib import Path
from typing import Protocol

from lacaze.evaluation.models import CaseJudgment


class JudgeExecutor(Protocol):
    async def judge(self, case_id: str, packet: str, judge_model: str) -> CaseJudgment: ...


def read_judgment(path: Path) -> CaseJudgment:
    return CaseJudgment.model_validate_json(path.read_text(encoding="utf-8"))
