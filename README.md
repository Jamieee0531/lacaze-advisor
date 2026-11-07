# LACAZE Advisor

Private development project for the Artefact written challenge. LACAZE, all clients, products, services and events are fictional. The recruitment PDF and screenshots stay local.

The application takes a case and generates three Chinese WeChat drafts for a Client Advisor. It uses **PydanticAI 2.65**, **Pydantic 2**, **Python 3.13.13** and the Anthropic API (default model `claude-opus-5-5`). There is no database, vector retrieval, automated message sending or model fallback.

## Run locally

Run these commands from the `lacaze-advisor/` directory. A transfer copy contains dependency declarations, not installed packages; `uv sync --locked` recreates the environment on the destination computer.

```sh
uv sync --locked
uv run lacaze validate-data
uv run lacaze generate --case-id C01
uv run lacaze generate --input /absolute/path/to/new-case.json
uv run python scripts/run_cases.py
```

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` (created in Claude Console, platform.claude.com) and optionally `LACAZE_MODEL`. Without `ANTHROPIC_BASE_URL` the official Anthropic API is used; set it, with `ANTHROPIC_AUTH_TOKEN`, only for a proxy. Credentials are not copied into source or result files.

Run selected cases, or choose an artifact directory:

```sh
uv run lacaze batch --case-ids C02 C07 C10 --output-dir artifacts/my-run
```

The default is sequential. Add `--concurrency 2` to run two independent cases at once; each still has its own run-local state.

Output directories must be new, preventing accidental replacement of earlier experiments. The default is a timestamped folder under `artifacts/`. Each case writes its result immediately; errors are recorded separately and remaining cases continue. This runner measures execution, not semantic quality.

## Structure

```text
src/lacaze/
  domain/                    Contracts: input, case pack, plan, drafts, result; shared text checks
  application/preparation.py Preparation node: loading table → per-case fact pack (no model call)
  application/agents.py      Planner and Writer, with layered instructions
  application/plan_checks.py Code checks on the plan
  application/guardrail.py   Code checks on the drafts
  application/workflow.py    Fixed order and the Planner / Writer inputs
  application/batch.py       Batch execution and artifacts (sequential by default)
  infrastructure/            Data loading, foundation lookups, settings, model client
  interfaces/                CLI and thin HTTP entry point
  evaluation/                Judge packets, code checks, summaries and reports
data/
  foundation/                Brand, scenario rules, products, services, policies, events,
                             calendar, clients and itemized purchases (see its README)
  context/loading.json       Scenario × data loading table
  context/guardrail.json     Draft checks (length, internal terms)
  prompts/                   Planner and Writer instructions; one invented style example per scenario
  cases/development.jsonl    Ten development cases
  evaluation/                Rubric, judge prompt, schema, phrase lists
scripts/run_cases.py         Batch convenience entry point
tests/                       Offline tests with a scripted model
artifacts/                   Local run outputs, ignored by Git
```

The application runs from this source checkout. Set `LACAZE_DATA_DIR` when storing runtime data elsewhere. Original Markdown notes remain human discussion/source material, not runtime prompts.

## Input contract

All JSON field names are English. Chinese text is preserved in names, history and message content. The authoritative contract is `src/lacaze/domain/models.py`; HTTP OpenAPI also exposes the schemas.

```json
{
  "case_id": "new_case",
  "scenario": "Birthday and festive greetings",
  "case_date": "2026-11-06",
  "client_information": {"client_id": "cl004"},
  "conversation_history": [],
  "product_information": {"product_ids": [], "event_id": null}
}
```

A new client without store records is written inline instead, e.g. `{"name": "周敏", "salutation": "周女士"}`; the tool then treats purchases as unknown.

`scenario` is exactly one of the original PDF labels:

1. `Birthday and festive greetings`
2. `Product recommendation`
3. `Post-purchase care`
4. `Reactivation`
5. `Event invitation`
6. `Price objection`

`case_date` is required and is the simulated business date. The system never substitutes today's machine date. Actual API timestamps appear only in run metadata. History is chronological, with unique `message_id` values and no message after `case_date`.

A known client is given by `client_id` alone. Name, salutation, birthday, cumulative spend, tier and purchases come from `data/foundation/`; spend and tier are computed from purchases up to `case_date`, never written by hand.

`product_information` names what the case is about: `product_ids` and an optional `event_id`. `lacaze validate-data` fails on unknown IDs in our own cases; generation is lenient and passes an unknown ID to the Planner as a note, so a live input with a typo still runs.

## Workflow and data ownership

```text
CaseInput
   ↓
Preparation (Python): loading table for this scenario → CasePack
   client card (internal tier/spend), full history, facts with IDs, notes
   ↓
Planner (one call): situation, sub-type, avoid, three angles citing message IDs
   and fact IDs, missing information
   ↓ code checks: IDs exist, sub-type allowed, angles differ (one retry with feedback)
Writer (one call): salutation, full history, the plan, only the facts each angle cites
   ↓ code checks: prices/dates/times in facts, products in scope, no internal terms,
     salutation, length (one retry with feedback)
Three drafts + angle names for the CA + pack, plan and warnings
```

This is a fixed workflow, not an autonomous agent: routing is by the input scenario and no tools are called. Instructions come in three layers: brand rules (both stages; tone only for the Writer), scenario rules split into judgement (Planner) and wording (Writer), and the case payload.

Preparation picks rows and columns: products under discussion (case, event or mentioned in history) with only the fields this scenario needs; owned products appear as purchase facts; services and policies per scenario, allocation rules only when a restricted product is involved. It computes tier, eligibility for events, days since purchases, birthdays and festivals near the business date, and the last contact.

History quotations are copied by code from the cited message IDs, so a model never retypes them. If a problem persists after the retry, unverifiable plan citations are dropped and drafts are returned with warnings; a person reviews every draft before sending. The provider SDK has automatic network retries disabled; no canned message is substituted.

## Batch artifacts

- `C01.json` … `C10.json`: exact input and complete successful result, or an error type.
- `outputs.csv`: requested input/output columns plus case date and execution status.
- `summary.json`: model, configuration hash, counts and completion time.
- `configuration.json`: exact data, loading table, rules and prompt file contents used for that batch, so later edits do not erase the experimental setup.

Successful results include the case pack, the plan, three drafts with the fact IDs they used, warnings, application version, configuration hash, timestamps and per-stage request/token counts. `outputs.csv` also has the resolved client card and the three angle names. There are no invented scores or ground-truth answers.

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

Offline tests use PydanticAI's FunctionModel to exercise the real workflow, retries and checks. They cover the preparation node, layered instructions, what each stage sees, plan and draft checks, warnings after a failed retry, request isolation, HTTP validation and batch files. They do not test the real model's language quality.

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

Packets are blind: no app version, run name or code-check flags. They contain the rubric, brand and scenario policies, the case input, the client card and the facts the generator actually saw (including purchases). All versions are judged against the same current policies. Results record the judge model plus rubric, judge-prompt, schema, checks and policy hashes; `collect` refuses judgments if any of these files changed after `prepare`.

Code checks (banned phrases, exclamation marks, prices/dates/times not in facts, out-of-scope product names, salutation, length) are shown beside judge results as flags and never decide a label. The calibration template and its review page contain no judge output, so human labels stay blind. An API judge executor can later implement `JudgeExecutor` in `src/lacaze/evaluation/executors.py` without changing rubric, packets or labels.

## Current development results

Version **0.1.2** has actual results for all ten development cases in `artifacts/review-v0.1.2/`, evaluated with rubric v2 in `artifacts/eval-review-v0.1.2-rubric2/` (Good 15 / Needs edit 10 / Not acceptable 5; distinct angles 0/10).

Version **0.2.0** (preparation node, Planner + Writer, guardrail) passes 52 offline tests and lint. It has not been run against a real model yet; the next step is to regenerate the ten cases once an API key is available and evaluate them with the same rubric.
