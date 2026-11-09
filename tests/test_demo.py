"""Demo boundaries use the real workflow with an offline model; no provider calls."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from lacaze.application.workflow import AdvisorWorkflow
from lacaze.interfaces.api import create_app
from tests.conftest import ScriptedModel, live


def events(response):
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


def test_bootstrap_imports_inputs_only_and_preview_matches_preparation(data, cases):
    model = ScriptedModel()
    with TestClient(
        create_app(AdvisorWorkflow(model.model, data)), base_url="http://127.0.0.1"
    ) as client:
        response = client.get("/demo/bootstrap")
        assert response.status_code == 200
        bootstrap = response.json()
        assert len(bootstrap["cases"]) == 50
        assert (
            bootstrap["cases"][1]["conversation_history"]
            == cases[1].model_dump(mode="json")["conversation_history"]
        )
        assert not any("result" in c or "candidates" in c for c in bootstrap["cases"])
        assert len(bootstrap["foundation"]["products"]) == 6
        preview = client.post("/demo/prepare", json=bootstrap["cases"][1])
        assert preview.status_code == 200
        assert preview.json()["client"]["salutation"] == "林女士"
        assert any(f["fact_id"] == "odette.interior" for f in preview.json()["facts"])
    assert not model.seen


def test_stream_delivers_actual_stages_retries_and_final_output(data, cases):
    model = ScriptedModel(plan_fault="unknown_fact")
    with TestClient(
        create_app(AdvisorWorkflow(model.model, data)), base_url="http://127.0.0.1"
    ) as client:
        response = client.post("/generate/stream", json=live(cases[1]))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    log = events(response)
    started = [e["stage"] for e in log if e["type"] == "stage_started"]
    assert started == ["prepare", "planner", "writer", "polish"]
    assert any(e["type"] == "stage_retry" and e["stage"] == "planner" for e in log)
    plan = next(
        e["output"] for e in log if e["type"] == "stage_completed" and e["stage"] == "planner"
    )
    writer = next(e for e in log if e["type"] == "stage_started" and e["stage"] == "writer")
    assert [f["fact_id"] for f in writer["input"]["facts"]] == plan["fact_ids"]
    final = log[-1]
    assert final["type"] == "result"
    assert len(final["result"]["candidates"]["messages"]) == 3
    assert "trace" not in final["result"]  # no model thinking/provider metadata sent to the UI
    assert final["result"]["edits"]
    assert (
        next(e for e in log if e["type"] == "stage_completed" and e["stage"] == "planner")["usage"][
            "requests"
        ]
        == 2
    )


def test_stream_rejects_bad_input_and_cross_origin_before_model(data, cases):
    model = ScriptedModel()
    with TestClient(
        create_app(AdvisorWorkflow(model.model, data)), base_url="http://127.0.0.1"
    ) as client:
        payload = cases[1].model_dump(mode="json")
        assert (
            client.post(
                "/generate/stream", json=payload, headers={"Origin": "https://unrelated.example"}
            ).status_code
            == 403
        )
        del payload["case_date"]
        assert client.post("/generate/stream", json=payload).status_code == 422
    assert not model.seen


def test_stream_reports_failure_without_leaking_exception_body(data, cases):
    flow = AdvisorWorkflow(ScriptedModel().model, data)

    async def fail(case, *, observer=None):
        raise RuntimeError("provider secret sentinel")

    flow.generate = fail
    with TestClient(create_app(flow), base_url="http://127.0.0.1") as client:
        response = client.post("/generate/stream", json=live(cases[0]))
    assert events(response)[-1]["type"] == "error"
    assert "provider secret sentinel" not in response.text


async def test_closing_stream_cancels_pending_generation(data, cases):
    from lacaze.interfaces.demo import stream_generation

    cancelled = asyncio.Event()
    flow = AdvisorWorkflow(ScriptedModel().model, data)

    async def block(case, *, observer=None):
        try:
            await observer({"type": "stage_started", "stage": "planner", "input": {}})
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    flow.generate = block
    stream = stream_generation(flow, cases[0])
    await anext(stream)
    await anext(stream)
    await stream.aclose()
    await asyncio.wait_for(cancelled.wait(), timeout=1)


async def test_observing_workflow_does_not_change_plan_or_messages(data, cases):
    flow = AdvisorWorkflow(ScriptedModel().model, data)
    baseline = await flow.generate(cases[1])
    log = []

    async def observe(event):
        log.append(event)

    observed = await flow.generate(cases[1], observer=observe)
    assert observed.plan == baseline.plan
    assert observed.drafts == baseline.drafts
    assert observed.edits == baseline.edits
    assert log[0]["type"] == "stage_started" and log[0]["stage"] == "prepare"
    assert log[-1]["stage"] == "polish"


async def test_unneeded_polish_is_reported_as_skipped(data, cases):
    log = []

    async def observe(event):
        log.append(event)

    # No patterns means the optional model stage must not be advertised as running.
    from dataclasses import replace

    flow = AdvisorWorkflow(
        ScriptedModel().model, replace(data, polish=data.polish.model_copy(update={"kinds": {}}))
    )
    result = await flow.generate(cases[1], observer=observe)
    assert [u.stage for u in result.usage] == ["planner", "writer"]
    assert log[-1]["type"] == "stage_skipped"


def test_demo_rejects_untrusted_host_even_with_matching_origin(data, cases):
    model = ScriptedModel()
    with TestClient(
        create_app(AdvisorWorkflow(model.model, data)), base_url="http://127.0.0.1"
    ) as client:
        response = client.post(
            "/generate/stream",
            json=live(cases[0]),
            headers={
                "Host": "unrelated.example",
                "Origin": "http://unrelated.example",
                "Sec-Fetch-Site": "same-origin",
            },
        )
    assert response.status_code == 400
    assert not model.seen


def test_api_can_start_without_optional_demo_fixtures(data, monkeypatch, tmp_path):
    monkeypatch.setenv("LACAZE_DATA_DIR", str(tmp_path))
    with TestClient(
        create_app(AdvisorWorkflow(ScriptedModel().model, data)), base_url="http://127.0.0.1"
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/demo/bootstrap").json()["cases"] == []


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_disconnect_during_transport_send_cancels_model(data, cases, spec_version):
    from starlette.requests import ClientDisconnect

    from lacaze.interfaces.demo import GenerationStreamResponse, stream_generation

    cancelled, sending = asyncio.Event(), asyncio.Event()
    flow = AdvisorWorkflow(ScriptedModel().model, data)

    async def block(case, *, observer=None):
        try:
            await observer({"type": "stage_started", "stage": "planner", "input": {}})
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    flow.generate = block
    stream = stream_generation(flow, cases[0])
    response = GenerationStreamResponse(stream)
    chunks = 0

    async def send(message):
        nonlocal chunks
        if message["type"] == "http.response.body":
            chunks += 1
            if chunks == 2:
                sending.set()
                if spec_version == "2.4":
                    raise OSError("client disconnected")
                await asyncio.Event().wait()

    async def receive():
        await sending.wait()
        return {"type": "http.disconnect"}

    try:
        try:
            await asyncio.wait_for(
                response({"type": "http", "asgi": {"spec_version": spec_version}}, receive, send),
                timeout=2,
            )
        except ClientDisconnect:
            pass
        assert cancelled.is_set()
    finally:
        await stream.aclose()
