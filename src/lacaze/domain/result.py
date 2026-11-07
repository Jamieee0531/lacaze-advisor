from datetime import date, datetime

from pydantic import Field

from lacaze.domain.models import CandidateMessages, Contract, Scenario, StageUsage
from lacaze.domain.pack import CasePack
from lacaze.domain.plan import Draft, Plan


class GenerationResult(Contract):
    """Three drafts plus the trace that produced them: the pack, the plan and any warnings."""

    case_id: str
    scenario: Scenario
    case_date: date
    app_version: str
    model: str
    configuration_hash: str
    started_at: datetime
    finished_at: datetime
    pack: CasePack
    plan: Plan
    drafts: list[Draft]
    candidates: CandidateMessages
    warnings: list[str]
    usage: list[StageUsage]
    trace: dict[str, list] = Field(
        default_factory=dict, description="Per stage, the exact messages exchanged with the model."
    )
