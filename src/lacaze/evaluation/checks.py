"""Deterministic message checks. They raise flags beside the judge; they never decide a label.

Kept free of evaluation-run state so the same functions can later guard runtime generation.
"""

import re
import unicodedata

from lacaze.evaluation.materials import EvaluationMaterials
from lacaze.evaluation.models import EvalCase, Flag

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
ARABIC_WAN = re.compile(r"(\d+(?:\.\d+)?)\s*万")
YUAN_SIGN = re.compile(r"[¥￥]\s*(\d[\d,]*)")
ARABIC_YUAN = re.compile(r"(?<![\d.])(\d[\d,]{2,})\s*元")
CHINESE_WAN = re.compile(r"([一二两三四五六七八九十]+)万(?:([一二两三四五六七八九])(?:千)?)?")
DATE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
TIME = re.compile(r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)")
EXCLAMATION = re.compile(r"[!！]")


def _chinese_number(text: str) -> int:
    """Chinese numerals up to 99, e.g. 五, 十五, 二十, 二十五."""
    if "十" not in text:
        return CN_DIGITS[text]
    tens, _, ones = text.partition("十")
    return (CN_DIGITS[tens] if tens else 1) * 10 + (CN_DIGITS[ones] if ones else 0)


def extract_prices(text: str) -> set[int]:
    prices = {round(float(m) * 10000) for m in ARABIC_WAN.findall(text)}
    prices |= {int(m.replace(",", "")) for m in YUAN_SIGN.findall(text)}
    prices |= {int(m.replace(",", "")) for m in ARABIC_YUAN.findall(text)}
    for wan, thousands in CHINESE_WAN.findall(text):
        prices.add(_chinese_number(wan) * 10000 + (CN_DIGITS[thousands] * 1000 if thousands else 0))
    return prices


def extract_dates(text: str) -> set[tuple[int, int]]:
    return {(int(m), int(d)) for m, d in DATE.findall(text)}


def extract_times(text: str) -> set[str]:
    return {f"{int(h)}:{m}" for h, m in TIME.findall(text)}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _source_texts(case: EvalCase) -> list[str]:
    """Texts a message may legitimately draw numbers and dates from."""
    facts = case.facts
    texts = [m.text for m in case.input.conversation_history]
    texts += [f.text for f in facts.event_facts + facts.service_facts]
    return texts


def _mentioned_products(text: str, names: tuple[str, ...]) -> set[str]:
    folded = normalize(text)
    return {name for name in names if normalize(name) in folded}


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

    allowed_prices = {p.price_cny for p in case.facts.products} | extract_prices(joined)
    unknown_prices = sorted(extract_prices(message) - allowed_prices)
    if unknown_prices:
        detail = "、".join(f"{p:,} 元" for p in unknown_prices) + " 不在本例事实中"
        flags.append(Flag(code="unsupported_price", severity="warning", detail=detail))

    allowed_dates = extract_dates(joined) | {(case.case_date.month, case.case_date.day)}
    allowed_dates |= {(m.date.month, m.date.day) for m in case.input.conversation_history}
    birthday = case.input.client_information.birthday
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

    in_scope = {p.name.split()[0] for p in case.facts.products}
    in_scope |= _mentioned_products(joined, materials.product_names)
    out_of_scope = sorted(_mentioned_products(message, materials.product_names) - in_scope)
    if out_of_scope:
        detail = "、".join(out_of_scope) + " 不在本例产品范围内"
        flags.append(Flag(code="product_out_of_scope", severity="warning", detail=detail))

    salutation = case.input.client_information.salutation
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
