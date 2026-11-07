"""Text helpers shared by the runtime guardrail and the evaluation checks."""

import re
import unicodedata
from collections.abc import Iterable


def normalize(text: str) -> str:
    """Casefold and strip accents, so Sable matches Sablé."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def mentioned(text: str, names: Iterable[str]) -> set[str]:
    folded = normalize(text)
    return {name for name in names if normalize(name) in folded}


CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
ARABIC_WAN = re.compile(r"(\d+(?:\.\d+)?)\s*万")
YUAN_SIGN = re.compile(r"[¥￥]\s*(\d[\d,]*)")
ARABIC_YUAN = re.compile(r"(?<![\d.])(\d[\d,]{2,})\s*元")
CHINESE_WAN = re.compile(r"([一二两三四五六七八九十]+)万(?:([一二两三四五六七八九])(?:千)?)?")
DATE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
TIME = re.compile(r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)")


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
