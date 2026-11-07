# LACAZE Advisor

Private development project for the Artefact written challenge. LACAZE, all clients, products, services and events are fictional. The recruitment PDF and screenshots stay local.

The application takes a case and generates three Chinese WeChat drafts for a Client Advisor. It uses **PydanticAI 2.65**, **Pydantic 2**, the machine's **Python 3.13.13**, and **Claude Opus 4.8 through Hyperspace**. There is no database, external retrieval, automated message sending or model fallback.

## Run locally

Run these commands from the `lacaze-advisor/` directory. A transfer copy contains dependency declarations, not installed packages; `uv sync --locked` recreates the environment on the destination computer.

```sh
uv sync --locked
uv run lacaze validate-data
uv run lacaze generate --case-id C01
uv run lacaze generate --input /absolute/path/to/new-case.json
uv run python scripts/run_cases.py
```

The model connection reads existing `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` (or `ANTHROPIC_API_KEY`) from the shell. A local `.env` is also supported; use `.env.example` as a reference. Credentials are not copied into source or result files.

`LACAZE_MODEL` overrides `ANTHROPIC_MODEL`; the default is `claude-opus-4-8`. This machine's Hyperspace URL is `http://localhost:6655/anthropic`. The local Hyperspace process must be running.

Run selected cases, or choose an artifact directory:

```sh
uv run lacaze batch --case-ids C02 C07 C10 --output-dir artifacts/my-run
```

The default is sequential. Add `--concurrency 2` to run two independent cases at once; each still has its own context and tool budget.

Output directories must be new, preventing accidental replacement of earlier experiments. The default is a timestamped folder under `artifacts/`. Each case writes its result immediately; errors are recorded separately and remaining cases continue. This runner measures execution, not semantic quality.

## Structure

```text
src/lacaze/
  domain/models.py            Input, context, decision, facts and output contracts
  application/agents.py       Three PydanticAI agents; one read-only product tool
  application/workflow.py     Fixed order and run-local data flow
  application/batch.py        Batch execution and artifacts (sequential by default)
  infrastructure/            Configuration, JSON loading, catalog and Hyperspace
  interfaces/                CLI and thin HTTP entry point
data/
  policies/                  Brand rules and six scenario policies
  catalog/products.json       Six fictional products; unknown specs remain null
  prompts/                   Extraction, decision and generation instructions
  cases/development.jsonl     Ten executable input cases
scripts/run_cases.py          Batch convenience entry point
tests/                       Offline contract, tool-loop and integration checks
artifacts/                   Local run outputs, ignored by Git
docs/implementation.md       Implementation and verification record
```

The application runs from this source checkout. Set `LACAZE_DATA_DIR` when storing runtime data elsewhere; the wheel intentionally does not bundle confidential case data. Original Markdown notes remain human discussion/source material, not runtime prompts.

## Input contract

All JSON field names are English. Chinese text is preserved in names, history and message content. The authoritative contract is `src/lacaze/domain/models.py`; HTTP OpenAPI also exposes the schemas.

```json
{
  "case_id": "new_case",
  "scenario": "Birthday and festive greetings",
  "case_date": "2026-11-06",
  "client_information": {
    "name": "张宁",
    "salutation": "张女士",
    "birthday": "11-06"
  },
  "conversation_history": [],
  "product_information": {}
}
```

`scenario` is exactly one of the original PDF labels:

1. `Birthday and festive greetings`
2. `Product recommendation`
3. `Post-purchase care`
4. `Reactivation`
5. `Event invitation`
6. `Price objection`

`case_date` is required and is the simulated business date. The system never substitutes today's machine date. Actual API timestamps appear only in run metadata. History is chronological, with unique `message_id` values and no message after `case_date`.

Identity fields are optional except `name`; unknown is `null`. `annual_spend` records `amount_cny`, `as_of`, and whether the amount is `approximate`. It is annual spending, not lifetime spending.

`product_information` contains `products`, `event_facts`, `service_facts`, and `unavailable_information`. An event or service fact has `fact_id` and `text`. This preserves current confirmed arrangements without inventing a large event-management schema. A catalog lookup cannot book an appointment or confirm a service.

## Workflow and data ownership

```text
CaseInput
   ↓
Scenario enum → select scenario policy (Python)
   ↓
Extraction Agent: full case + policies
   ↓
CaseContext: needs, conversation state, quotes, gaps
   ↓
Decision Agent: context + identity + supplied facts + policies
   ↔ query_products (read-only, default maximum two calls)
   ↓
CommunicationDecision + supplied/queried facts
   ↓
Generation Agent: decision + selected quotes + identity + facts + policies
   ↓
Three independent Chinese drafts for the CA
```

The extraction agent preserves source quotations, current requests, outstanding promises and changes of preference. Its history quotations are checked against the input. It does not recreate a complete persistent client profile.

The decision agent produces five fields: `objective`, `content_focus`, `personalization_basis`, `communication_strategy`, `fact_boundaries`. It may query several products/fields together. Empty product names list the small catalog. Tool access is removed when its budget is exhausted. Unavailable facts remain unavailable; there is no repeated-query fallback.

The writer receives the decision's cited history excerpts, not the entire history or extraction output. Brand/scenario policies and original identity/fact records are reused directly. This avoids asking a model to rewrite a price or policy on every hop. Whether the selected evidence preserves enough nuance is a business-quality question for subsequent manual evaluation.

Case-supplied product snapshots take precedence over catalog entries with the same product ID. The catalog never fills a null field in a supplied snapshot by silently switching sources. Queried products and exact tool results are recorded.

PydanticAI has one structured-output correction attempt per agent and bounded model requests. The provider SDK has automatic network retries disabled. Failures remain failures; no canned message is substituted. Format checks do not prove factual or semantic correctness.

## Batch artifacts

- `C01.json` … `C10.json`: exact input and complete successful result, or an error type.
- `outputs.csv`: requested input/output columns plus case date and execution status.
- `summary.json`: model, configuration hash, counts and completion time.
- `configuration.json`: exact policy, catalog and prompt file contents used for that batch, so later edits do not erase the experimental setup.

Successful results include context, five-field decision, selected quotations, exact product facts/tool queries, three messages, application version, configuration hash, timestamps and per-stage request/token counts. There are no invented scores or ground-truth answers.

## HTTP interface

```sh
uv run uvicorn lacaze.interfaces.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the interactive schema and a new-input test. `GET /health` reports application readiness; it does not make a model request. `GET /scenarios` lists the six labels. `POST /generate` accepts a CaseInput and returns the same result as the CLI. Invalid inputs return 422; a failed generation returns 502 with an error type. The service is intended for local use.

## Checks

```sh
uv run pytest -q
uv run ruff check src scripts tests
```

Offline tests use PydanticAI's FunctionModel to exercise the actual agents and native tool loop. They check contracts, source quotations, lookup limits, facts shared with the writer, request isolation, HTTP validation and batch files. They do not test the real model's language quality.

## Evaluation

Evaluates existing run artifacts; it never re-generates messages. Rubric, judge prompt, judgment schema and code-check settings live in `data/evaluation/`. Each message gets a label computed by code from the judge's yes/no answers: Good, Needs edit or Not acceptable; each case also gets a distinct-angles verdict.

```sh
uv run lacaze evaluate prepare --run artifacts/review-v0.1.2 --out artifacts/eval-review-v0.1.2 --judge-model claude-opus-5-5
# one independent judge per packets/Cxx.md writes judgments/Cxx.json (version 1: Claude Code subagents)
uv run lacaze evaluate collect --eval-dir artifacts/eval-review-v0.1.2
uv run lacaze evaluate report --eval-dir artifacts/eval-review-v0.1.2 --compare artifacts/eval-development-v0.1.1
uv run lacaze evaluate calibration-template --eval-dir artifacts/eval-review-v0.1.2
uv run lacaze evaluate agreement --eval-dir artifacts/eval-review-v0.1.2 --human artifacts/eval-review-v0.1.2/calibration/human_labels.csv
```

Packets are blind: no app version, run name or code-check flags. They contain the rubric, brand and scenario policies, the case input and the facts the generator actually saw (supplied facts plus catalog query results). All versions are judged against the same current policies. Results record the judge model plus rubric, judge-prompt, schema, checks and policy hashes; `collect` refuses judgments if any of these files changed after `prepare`.

Code checks (banned phrases, exclamation marks, prices/dates/times not in facts, out-of-scope product names, salutation, length) are shown beside judge results as flags and never decide a label. The calibration template and its review page contain no judge output, so human labels stay blind. An API judge executor can later implement `JudgeExecutor` in `src/lacaze/evaluation/executors.py` without changing rubric, packets or labels.

## Current development results

Version **0.1.2** has actual results for all ten development cases. Open [the review CSV](artifacts/review-v0.1.2/outputs.csv) or the per-case JSON files in that directory. The review bundle preserves which source run produced each case; provider quota/unavailability/timeout failures remain in the original run folders. The complete 0.1.1 batch is retained for comparison.

Seventeen offline tests and lint passed. See [the implementation record](docs/implementation.md) for fixes and remaining language-quality limitations. Recommendations still need work on brevity, variation and unsupported offers to check missing specifications. These are development outputs for human review, not a completed semantic evaluation or the final 50-case submission.
