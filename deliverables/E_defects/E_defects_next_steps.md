# E. Defects and Next Steps

Every change below started from an evaluation result and was checked by the next one. All results use the same judge (claude-opus-5-5) and the same rubric (Methodology, section 3).

## Versions

| Version | What changed | Commit |
|---|---|---|
| v0.1.2 | One model call writes all three messages | [`396c747`](https://github.com/Jamieee0531/lacaze-advisor/commit/396c747) |
| v0.2.0 | Facts retrieved by code; Planner and Writer split; code checks with one retry | [`780a244`](https://github.com/Jamieee0531/lacaze-advisor/commit/780a244) |
| v0.2.1 | Polish: rewrite only the sentences that match known problem patterns | [`5c0db98`](https://github.com/Jamieee0531/lacaze-advisor/commit/5c0db98) |
| v0.2.2 | Planner lists each point the client asked | [`34d5dae`](https://github.com/Jamieee0531/lacaze-advisor/commit/34d5dae) |
| v0.2.3 | All three messages share one set of facts | [`d0af521`](https://github.com/Jamieee0531/lacaze-advisor/commit/d0af521) |

## Round 1: Rebuild the architecture (v0.1.2 → v0.2.0)

- **Problem**: v0.1.2 wrote all three messages in one model call. The three were rewordings of the same message: in none of the 10 cases were the angles distinct. With no product data to look up, messages said "我手上还没有尺寸资料" and promised to check later. Client words were exaggerated, e.g. something said once became "反复提到".
- **Change**: facts are retrieved by code; the Planner sets three different angles, and the Writer writes one message per angle (v0.2.0).

**Development set, 10 cases**

| Result | v0.1.2 | v0.2.0 |
|---|---|---|
| Good | 15 | 17 |
| Needs edit | 10 | 10 |
| Not acceptable | 5 | 3 |
| Usable cases (at least one Good) | 6 / 10 | 10 / 10 |

| Messages failing each indicator | v0.1.2 | v0.2.0 |
|---|---|---|
| Fabricates facts | 5 | 2 |
| Crosses brand red line | 0 | 0 |
| Contradicts client wish | 0 | 1 |
| Personal | 5 | 4 |
| Natural and on-brand | 12 | 1 |
| Responds to the moment | 3 | 8 |
| Distinct angles (cases) | 0 / 10 | 10 / 10 |

## Round 2: Prompt changes (tried on v0.2.0, all reverted)

- **Problem**: messages kept adding reassurance the client never asked for, e.g. "您不用特意回复". The third message often drifted to a topic the client had not raised, just to differ from the first two.
- **Change**: three prompt changes: require all three messages to answer the client, then add paired "don't / do" examples, then add the reasons behind them. Stock phrases dropped, but overall quality fell, so all three were reverted.

**Development set, 10 cases**

| Result | v0.2.0 | All three must answer | "Don't / do" examples | Examples with reasons |
|---|---|---|---|---|
| Good | 17 | 15 | 13 | 10 |
| Needs edit | 10 | 13 | 12 | 14 |
| Not acceptable | 3 | 2 | 5 | 6 |
| Usable cases (at least one Good) | 10 / 10 | 9 / 10 | 8 / 10 | 7 / 10 |

| Messages failing each indicator | v0.2.0 | All three must answer | "Don't / do" examples | Examples with reasons |
|---|---|---|---|---|
| Fabricates facts | 2 | 2 | 5 | 5 |
| Crosses brand red line | 0 | 0 | 0 | 1 |
| Contradicts client wish | 1 | 0 | 0 | 0 |
| Personal | 4 | 7 | 6 | 7 |
| Natural and on-brand | 1 | 7 | 5 | 3 |
| Responds to the moment | 8 | 8 | 9 | 11 |
| Distinct angles (cases) | 10 / 10 | 9 / 10 | 9 / 10 | 10 / 10 |

## Round 3: Local polish (v0.2.0 → v0.2.1)

- **Problem**: reassurance and defensive lines (e.g. "这个我这边没有信息") kept appearing, and prompt changes affected the whole message.
- **Change**: code finds these sentences, and only those sentences go to the model to be rewritten or deleted; the rest of the message stays as written (v0.2.1). Across the 40 test cases, these lines fell from 42 sentences to 1. The tables cover the 25 cases where a sentence was changed.

**Test set, 25 changed cases**

| Result | v0.2.0 | v0.2.1 |
|---|---|---|
| Good | 31 | 35 |
| Needs edit | 33 | 28 |
| Not acceptable | 11 | 12 |
| Usable cases (at least one Good) | 21 / 25 | 21 / 25 |

| Messages failing each indicator | v0.2.0 | v0.2.1 |
|---|---|---|
| Fabricates facts | 10 | 11 |
| Crosses brand red line | 1 | 1 |
| Contradicts client wish | 0 | 0 |
| Personal | 9 | 11 |
| Natural and on-brand | 20 | 15 |
| Responds to the moment | 18 | 18 |
| Distinct angles (cases) | 23 / 25 | 23 / 25 |

## Round 4: Answer everything the client asked (v0.2.1 → v0.2.2 → v0.2.3)

- **Problem**: "Responds to the moment" was the most failed indicator. The Planner split the client's questions across the three angles, so each message answered only part of them.
- **Change**: the Planner first lists every point the client asked, and each message must answer all of them (v0.2.2). All three messages share one set of facts, so each has what it needs (v0.2.3). v0.2.3 was checked by hand here; its effect shows in the final comparison.

**7 targeted cases**

| Result | v0.2.1 | v0.2.2 |
|---|---|---|
| Good | 5 | 7 |
| Needs edit | 13 | 14 |
| Not acceptable | 3 | 0 |
| Usable cases (at least one Good) | 3 / 7 | 5 / 7 |

| Messages failing each indicator | v0.2.1 | v0.2.2 |
|---|---|---|
| Fabricates facts | 2 | 0 |
| Crosses brand red line | 0 | 0 |
| Contradicts client wish | 1 | 0 |
| Personal | 4 | 2 |
| Natural and on-brand | 3 | 6 |
| Responds to the moment | 12 | 9 |
| Distinct angles (cases) | 6 / 7 | 6 / 7 |

## Final comparison (v0.2.0 → v0.2.3)

**All 50 cases**

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
| Distinct angles (cases) | 48 / 50 | 41 / 50 |

## What remains (v0.2.3)

| Defect | Indicator | Next step |
|---|---|---|
| Invented memories or feelings, e.g. "那天的情形我还记得" (7 messages) | Fabricates facts | Any reference to the past must quote the conversation; add these phrasings to the polish patterns |
| Promises with no basis, e.g. "等我核实清楚后再告诉您" (C21) | Fabricates facts | Code check for promised follow-up actions; block any that no service fact supports |
| Internal facts told to the client (C33, C40) | Crosses brand red line | Compare each message against the text of internal facts before output |
| Still selling after the client said "先不考虑" (C35) | Contradicts client wish | The Planner lists the client's stated wishes next to their questions; every message must respect them |
| More messages judged not natural (29 → 35) | Natural and on-brand | Find the new stiff phrasings and add them to the polish patterns |
| Fewer cases with distinct angles (48 → 41) | Distinct angles | Keep the shared facts, but make the three messages differ in structure and opening |
