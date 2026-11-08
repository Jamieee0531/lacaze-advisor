# LACAZE Advisor

Drafts three WeChat messages for a luxury Client Advisor, grounded in what the store actually knows about the client and the product.

Given a client, the conversation so far and a scenario, it returns three candidate messages in Chinese, each taking a different angle. The advisor picks one, edits it and sends it. Nothing is sent automatically.

> LACAZE is a fictional brand. All clients, products, services and events in this repository are invented.

## Example

Scenario: *Birthday and festive greetings*. The client registered recently and has talked to the advisor once. There is little to personalise, and the messages must not sell.

| Angle | Message |
|---|---|
| 简短生日祝福 | 许小姐，生日快乐。愿您今天过得轻松愉快，新的一岁一切顺心。 |
| 初见的记忆 | 许小姐，生日快乐。十月在澄园店见到您，到现在还有印象。今天是您的生日，想在这里送上一句祝福，愿您新的一岁顺心舒展。 |
| 她随口说的喜欢 | 许小姐，生日快乐。还记得您那天逛店时随口说喜欢象牙白，那份轻松随意的眼光让我印象很深。愿您今天也过得自在愉快。 |

## How it works

![LACAZE Advisor architecture](assets/architecture.png)

1. **Prepare** (code, no model). A loading table decides, per scenario, which facts the case needs: products, services, policies, events, calendar, purchases. Every fact gets an ID. Client tier, eligibility and dates are computed, not asked of a model.
2. **Planner** (one call). Reads the client, the history and the facts. Lists what the client asked, which facts apply, what to avoid, and three different angles. Code checks that every cited ID exists.
3. **Writer** (one call). Writes one message per angle, seeing only the facts the plan chose. Code checks prices, dates, product scope, internal terms, salutation and length; a hard failure gets one rewrite with feedback.
4. **Polish.** Code flags sentences that match known problem patterns (reassurance nobody asked for, defensive non-answers). Only those sentences are rewritten.

It is a fixed workflow, not an autonomous agent: no tools, no database, no retrieval beyond the loading table.

## Quick start

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
cp .env.example .env        # set ANTHROPIC_API_KEY
uv run lacaze validate-data
uv run lacaze generate --case-id C12
```

`LACAZE_MODEL` selects the model (default `claude-sonnet-5-5`). Set `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` only when going through a proxy.

### Your own case

```sh
uv run lacaze generate --input new-case.json
```

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

- `scenario` is one of six: `Birthday and festive greetings`, `Product recommendation`, `Post-purchase care`, `Reactivation`, `Event invitation`, `Price objection`.
- `case_date` is required. It is the business date of the case; the machine's date is never used.
- A known client is given by `client_id` alone. Name, birthday, purchases, tier and spend come from `data/foundation/`.
- A new client is written inline: `{"name": "周敏", "salutation": "周女士"}`. Purchases are then treated as unknown.
- `product_information` holds `product_ids` and an optional `event_id`.
- History is chronological, with unique `message_id` values, none after `case_date`.

The full contract is `src/lacaze/domain/models.py`.

### Batches

```sh
uv run lacaze batch --case-ids C02 C07 C10 --output-dir artifacts/my-run
uv run lacaze batch --concurrency 2
```

Output directories must be new. Each case writes `Cxx.json` (input, plan, drafts, warnings, token usage) as soon as it finishes; `outputs.csv` and `summary.json` are written at the end, with `configuration.json` recording the exact data and prompts used.

### HTTP

```sh
uv run uvicorn lacaze.interfaces.api:app --host 127.0.0.1 --port 8000
```

`POST /generate` takes a case and returns the same result as the CLI. `GET /scenarios` lists the six scenarios, `GET /health` reports readiness, and `/docs` has the interactive schema. Intended for local use.

## Evaluation

`lacaze evaluate` scores existing runs against a rubric; it never regenerates messages.

| Level | Meaning |
|---|---|
| Not acceptable | Fabricates facts, crosses a brand red line, or contradicts what the client said |
| Needs edit | Safe, but not yet personal, natural and on-brand, or not responding to the moment |
| Good | Passes all six indicators |

```sh
uv run lacaze evaluate prepare --run artifacts/my-run --out artifacts/eval --judge-model claude-opus-5-5
# one independent judge per packets/Cxx.md writes judgments/Cxx.json
uv run lacaze evaluate collect --eval-dir artifacts/eval
```

Packets are blind: no app version, run name or code flags. Labels are computed by code from the judge's yes/no answers. The rubric, judge prompt and schema are in `data/evaluation/`; `collect` refuses judgments if any of them changed after `prepare`.

On the 50 test cases in `data/cases/`, v0.2.3 produced 75 Good, 54 Needs edit and 21 Not acceptable messages out of 150, and at least one Good message in 43 of 50 cases.

## Project layout

```text
src/lacaze/
  domain/          Contracts: input, case pack, plan, drafts, result
  application/     Preparation, Planner and Writer, code checks, polish, workflow, batch
  infrastructure/  Data loading, settings, model client
  interfaces/      CLI and HTTP
  evaluation/      Judge packets, code checks, labels, reports
data/
  foundation/      Brand, products, services, policies, events, calendar, clients, purchases
  context/         Loading table, draft checks, polish patterns
  prompts/         Planner, Writer and polish instructions
  cases/           Development (10) and test (40) cases
  evaluation/      Rubric, judge prompt, schema, phrase lists
tests/             Offline tests with a scripted model
```

`LACAZE_DATA_DIR` points the app at data stored elsewhere.

## Development

```sh
uv run pytest -q
uv run ruff check src scripts tests
```

The tests drive the real workflow with PydanticAI's `FunctionModel`: preparation, what each stage sees, plan and draft checks, retries, polish, HTTP validation and batch files. They do not judge the model's language quality; that is what `lacaze evaluate` is for.

Built with PydanticAI, Pydantic 2 and the Anthropic API.
