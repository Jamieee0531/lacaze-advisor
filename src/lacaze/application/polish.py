"""Wording polish after the Writer: code finds the sentences, a model rewrites only those.

Two habits survived every prompt change (docs/experiments.zh-CN.md, experiments 1 and 3):
reassurance that tells the client how to respond ("不用特意回复", "不着急") and defensive
remarks about what the advisor lacks ("我这边没有可以给您的说法"). Rewriting whole messages
changed everything else too, so only the matched sentences go to the model and code splices
the answers back; every other character stays as the Writer wrote it.
"""

import re

from lacaze.application.guardrail import mentioned_products
from lacaze.domain.pack import CasePack, PolishConfig
from lacaze.domain.plan import Draft, Edit, Flag, Rewrite
from lacaze.domain.text import extract_dates, extract_prices, extract_times
from lacaze.infrastructure.data import RuntimeData

SENTENCE = re.compile(r"[^。！？!?]+[。！？!?]*")
EXTRACTORS = (extract_prices, extract_dates, extract_times)


def sentences(text: str) -> list[str]:
    return SENTENCE.findall(text)


def find_flags(drafts: list[Draft], config: PolishConfig) -> list[Flag]:
    flags = []
    for draft in drafts:
        for sentence in dict.fromkeys(sentences(draft.text)):
            kinds = [
                name
                for name, kind in config.kinds.items()
                if any(re.search(p, sentence) for p in kind.patterns)
            ]
            if kinds:
                flags.append(Flag(angle=draft.angle, sentence=sentence, kinds=kinds))
    return flags


def polish_payload(pack: CasePack, drafts: list[Draft], flags: list[Flag], data) -> dict:
    labels = {name: kind.label for name, kind in data.polish.kinds.items()}
    angles = {f.angle for f in flags}
    return {
        "salutation": pack.client.salutation,
        "messages": [{"angle": d.angle, "text": d.text} for d in drafts if d.angle in angles],
        "flagged": [
            {"angle": f.angle, "sentence": f.sentence, "problems": [labels[k] for k in f.kinds]}
            for f in flags
        ],
    }


def rewrite_problems(rewrite: Rewrite, flags: list[Flag], pack: CasePack, data: RuntimeData):
    """Why a rewrite cannot be spliced in, phrased for the polish model."""
    where = f"第 {rewrite.angle} 条「{rewrite.sentence}」"
    if not any(f.angle == rewrite.angle and f.sentence == rewrite.sentence for f in flags):
        return [f"{where}不是标出的句子，请逐字照抄标出的原句"]
    before, after = rewrite.sentence, rewrite.replacement
    if after == before:
        return []
    problems = []
    if len(after) > len(before):
        problems.append(f"{where}改后比原句长，只能删减或换成更短的说法")
    if any(extract(after) - extract(before) for extract in EXTRACTORS):
        problems.append(f"{where}改后出现了原句没有的价格、日期或时间")
    if mentioned_products(after, data) - mentioned_products(before, data):
        problems.append(f"{where}改后出现了原句没有的商品")
    salutation = pack.client.salutation
    if salutation and salutation in before and salutation not in after:
        problems.append(f"{where}删掉了称呼「{salutation}」")
    if find_flags([Draft(angle=rewrite.angle, text=after or "。", fact_ids=[])], data.polish):
        problems.append(f"{where}改后仍有同类说法")
    return problems


def apply_rewrites(
    drafts: list[Draft], rewrites: list[Rewrite], flags: list[Flag]
) -> tuple[list[Draft], list[Edit]]:
    """New drafts with each changed sentence replaced once; the rest is untouched."""
    kinds = {(f.angle, f.sentence): f.kinds for f in flags}
    changed = {
        (r.angle, r.sentence): r.replacement for r in rewrites if r.replacement != r.sentence
    }
    result, edits = [], []
    for draft in drafts:
        text = draft.text
        for (angle, before), after in changed.items():
            if angle == draft.angle and before in text:
                text = text.replace(before, after, 1)
                edits.append(
                    Edit(angle=angle, kinds=kinds[(angle, before)], before=before, after=after)
                )
        result.append(draft.model_copy(update={"text": text.strip()}))
    return result, edits
