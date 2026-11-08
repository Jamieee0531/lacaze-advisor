# E. Defects and Next Steps

Every change below started from an evaluation result and was judged by the next one. All results use the same judge (claude-opus-5-5) and the same rubric (methodology section 3).

## Versions

| Version | What changed | Commit |
|---|---|---|
| v0.1.2 | Single generation step | `396c747` |
| v0.2.0 | Facts retrieved by code; Planner and Writer; code checks with one retry | `2a4846a` (development set), `2d99d83` (test set) |
| v0.2.1 | Polish: rewrite only sentences that match known problem patterns | `5c0db98` |
| v0.2.2 | Planner lists each point the client asked | `34d5dae` |
| v0.2.3 | One set of facts shared by all three messages | `bfd3571` |

## Round 1: Rebuild the architecture (v0.1.2 → v0.2.0)

TODO: defects found in v0.1.2, after it is re-judged with the current rubric.

**Development set, 10 cases, 30 messages**

| Result | v0.1.2 | v0.2.0 |
|---|---|---|
| Good | TBD | 17 |
| Needs edit | TBD | 10 |
| Not acceptable | TBD | 3 |
| Usable cases (at least one Good) | TBD | 10 / 10 |

| Messages failing each indicator | v0.1.2 | v0.2.0 |
|---|---|---|
| Fabricates facts | TBD | 2 |
| Crosses brand red line | TBD | 0 |
| Contradicts client wish | TBD | 1 |
| Personal | TBD | 4 |
| Natural and on-brand | TBD | 1 |
| Responds to the moment | TBD | 8 |

## Round 2: Polish and complete answers (v0.2.0 → v0.2.3)

Evaluating v0.2.0 on all 50 cases showed two main defects.

**Stock phrases.** Messages kept ending with reassurance the client never asked for ("您不用特意回复") or defensive lines ("这个我这边没有信息"), 56 sentences across 150 messages. Three prompt changes reduced them but lowered overall quality, so all three were reverted (table below). v0.2.1 instead finds these sentences with code and rewrites only them, leaving the rest of the message untouched. The count fell to 0.

**Incomplete answers.** "Responds to the moment" was the most failed indicator. The Planner split the client's questions across the three angles, so each message answered only part of them. v0.2.2 makes the Planner list every point the client asked, and each message must answer all of them. v0.2.3 gives all three messages the same facts, so no message is missing the facts it needs.

**All 50 cases, 150 messages**

| Result | v0.2.0 | v0.2.3 |
|---|---|---|
| Good | 64 | 75 |
| Needs edit | 66 | 54 |
| Not acceptable | 20 | 21 |
| Usable cases (at least one Good) | 41 / 50 | 43 / 50 |

| Messages failing each indicator | v0.2.0 | v0.2.3 |
|---|---|---|
| Fabricates facts | 17 | 16 |
| Crosses brand red line | 1 | 3 |
| Contradicts client wish | 2 | 2 |
| Personal | 27 | 24 |
| Natural and on-brand | 29 | 35 |
| Responds to the moment | 37 | 31 |

**Reverted prompt changes (development set, 10 cases)**

| Result | v0.2.0 | All three must answer | Do / don't examples | Examples with reasons |
|---|---|---|---|---|
| Good | 17 | 15 | 13 | 10 |
| Needs edit | 10 | 13 | 12 | 14 |
| Not acceptable | 3 | 2 | 5 | 6 |
| Usable cases (at least one Good) | 10 / 10 | 9 / 10 | 8 / 10 | 7 / 10 |

## What remains (v0.2.3)

| Defect | Indicator | Next step |
|---|---|---|
| Invented memories or feelings, e.g. "那天的情形我还记得" (7 messages) | Fabricates facts | Any reference to the past must quote a message from the history; add these phrasings to the polish patterns |
| Promises with no basis, e.g. "等我核实清楚后再告诉您" (C21) | Fabricates facts | Code check for promised follow-up actions that no service fact supports |
| Internal facts told to the client (C33, C40) | Crosses brand red line | Check each message against the text of internal facts before output |
| Still selling after the client said "先不考虑" (C35) | Contradicts client wish | Planner lists the client's stated wishes next to their questions; every message must respect them |
| More messages judged not natural (29 → 35) | Natural and on-brand | Find the new stiff phrasings and add them to the polish patterns |
| Fewer cases with three distinct angles (48 → 41) | Distinct angles | Make the angles differ in structure and opening while keeping the shared facts |
