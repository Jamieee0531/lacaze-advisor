"""Deterministic message checks. They raise flags beside the judge; they never decide a label.

The extractors are shared with the runtime guardrail (lacaze.domain.text).
"""

import re

from lacaze.domain.text import (
    extract_dates,
    extract_prices,
    extract_times,
)
from lacaze.domain.text import (
    mentioned as _mentioned_products,
)
from lacaze.evaluation.materials import EvaluationMaterials
from lacaze.evaluation.models import EvalCase, Flag

__all__ = ["extract_dates", "extract_prices", "extract_times", "run_checks"]

EXCLAMATION = re.compile(r"[!！]")
SCOPE_KINDS = {"product", "purchase", "event"}


def _source_texts(case: EvalCase) -> list[str]:
    """Texts a message may legitimately draw numbers and dates from."""
    return [m.text for m in case.input.conversation_history] + [f.text for f in case.facts]


def run_checks(message: str, case: EvalCase, materials: EvaluationMaterials) -> list[Flag]:
    config = materials.checks
    sources = _source_texts(case)
    joined = "\n".join(sources)
    flags: list[Flag] = []

    banned = [p for p in config.banned_phrases if p in message]
    if banned:
        flags.append(Flag(code="banned_phrase", severity="warning", detail="、".join(banned)))

    discount = [t for t in config.discount_terms if t in message]
    if discount:
        normal = case.scenario in config.discount_normal_scenarios
        note = "，该场景下可能属正常表达" if normal else "，该场景不应出现"
        flags.append(
            Flag(
                code="discount_term",
                severity="info" if normal else "warning",
                detail=f"{'、'.join(discount)}（场景：{case.scenario.value}{note}）",
            )
        )

    if EXCLAMATION.search(message):
        flags.append(Flag(code="exclamation", severity="warning", detail="出现感叹号"))

    allowed_prices = extract_prices(joined)
    unknown_prices = sorted(extract_prices(message) - allowed_prices)
    if unknown_prices:
        detail = "、".join(f"{p:,} 元" for p in unknown_prices) + " 不在本例事实中"
        flags.append(Flag(code="unsupported_price", severity="warning", detail=detail))

    allowed_dates = extract_dates(joined) | {(case.case_date.month, case.case_date.day)}
    allowed_dates |= {(m.date.month, m.date.day) for m in case.input.conversation_history}
    birthday = case.client.get("birthday")
    if birthday:
        month, day = birthday.split("-")
        allowed_dates.add((int(month), int(day)))
    unknown_dates = sorted(extract_dates(message) - allowed_dates)
    if unknown_dates:
        detail = "、".join(f"{m}月{d}日" for m, d in unknown_dates) + " 不在本例事实中"
        flags.append(Flag(code="unsupported_date", severity="warning", detail=detail))

    unknown_times = sorted(extract_times(message) - extract_times(joined))
    if unknown_times:
        detail = "、".join(unknown_times) + " 不在本例事实中"
        flags.append(Flag(code="unsupported_time", severity="warning", detail=detail))

    # Policies name every restricted product, so they do not widen the scope.
    scope_texts = [m.text for m in case.input.conversation_history]
    scope_texts += [f.text for f in case.facts if f.kind in SCOPE_KINDS]
    in_scope = _mentioned_products("\n".join(scope_texts), materials.product_names)
    out_of_scope = sorted(_mentioned_products(message, materials.product_names) - in_scope)
    if out_of_scope:
        detail = "、".join(out_of_scope) + " 不在本例产品范围内"
        flags.append(Flag(code="product_out_of_scope", severity="warning", detail=detail))

    salutation = case.client.get("salutation")
    if salutation and salutation not in message:
        flags.append(
            Flag(code="missing_salutation", severity="warning", detail=f"未使用称呼「{salutation}」")
        )

    length = len(re.sub(r"\s", "", message))
    if length > config.max_chars:
        flags.append(
            Flag(code="too_long", severity="warning", detail=f"{length} 字，超过 {config.max_chars} 字")
        )
    return flags
