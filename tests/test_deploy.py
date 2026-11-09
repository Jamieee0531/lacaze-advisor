import pytest
from fastapi.testclient import TestClient

from lacaze.application.workflow import AdvisorWorkflow
from lacaze.interfaces.api import create_app
from tests.conftest import ScriptedModel, live

HOST = "https://lacaze-demo.onrender.com"


def client_for(data, base_url="http://127.0.0.1", **kwargs):
    app = create_app(AdvisorWorkflow(ScriptedModel().model, data))
    return TestClient(app, base_url=base_url, **kwargs)


def test_unknown_host_is_rejected_by_default(data):
    with client_for(data, base_url=HOST) as client:
        assert client.get("/").status_code == 400
        assert client.get("/scenarios").status_code == 400


def test_health_check_answers_any_host(data):
    """The host's health checker may use an internal address; /health carries no data."""
    with client_for(data, base_url="http://10.0.0.7:10000") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 400


def test_render_hostname_is_allowed(data, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "lacaze-demo.onrender.com")
    with client_for(data, base_url=HOST) as client:
        assert client.get("/health").status_code == 200


def test_extra_hosts_come_from_settings(data, monkeypatch):
    monkeypatch.setenv("LACAZE_ALLOWED_HOSTS", "lacaze-demo.onrender.com, example.test")
    with client_for(data, base_url=HOST) as client:
        assert client.get("/health").status_code == 200


def test_no_access_code_means_open_locally(data, monkeypatch):
    monkeypatch.delenv("LACAZE_ACCESS_CODE", raising=False)
    with client_for(data) as client:
        assert client.get("/scenarios").status_code == 200


def test_access_code_guards_every_page_but_health(data, monkeypatch):
    monkeypatch.setenv("LACAZE_ACCESS_CODE", "s3cret")
    with client_for(data) as client:
        denied = client.get("/")
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"].startswith("Basic")
        assert client.get("/scenarios", auth=("advisor", "wrong")).status_code == 401
        assert client.get("/scenarios", auth=("advisor", "s3cret")).status_code == 200
        assert client.get("/health").status_code == 200


def test_daily_limit_caps_billable_generations(data, cases, monkeypatch):
    monkeypatch.setenv("LACAZE_DAILY_GENERATION_LIMIT", "2")
    payload = live(cases[0])
    with client_for(data) as client:
        assert client.post("/generate", json=payload).status_code == 200
        assert client.post("/generate/stream", json=payload).status_code == 200
        refused = client.post("/generate", json=payload)
        assert refused.status_code == 429
        assert "今日" in refused.json()["detail"]
        assert client.post("/demo/prepare", json=payload).status_code == 200


def test_daily_limit_resets_on_a_new_day():
    from datetime import date

    from fastapi import HTTPException

    from lacaze.interfaces.quota import DailyQuota

    day = [date(2026, 11, 9)]
    quota = DailyQuota(1, today=lambda: day[0])
    quota()
    with pytest.raises(HTTPException) as refused:
        quota()
    assert refused.value.status_code == 429
    day[0] = date(2026, 11, 10)
    quota()


def test_no_daily_limit_by_default(data, cases, monkeypatch):
    monkeypatch.delenv("LACAZE_DAILY_GENERATION_LIMIT", raising=False)
    payload = cases[0].model_dump(mode="json")
    with client_for(data) as client:
        for _ in range(3):
            assert client.post("/generate", json=payload).status_code == 200


def test_unedited_case_replays_without_model_or_quota(data, cases, monkeypatch):
    monkeypatch.setenv("LACAZE_DAILY_GENERATION_LIMIT", "1")
    monkeypatch.setattr(
        "lacaze.interfaces.replay.PACE",
        dict.fromkeys(["prepare", "planner", "writer", "polish"], 0),
    )
    model = ScriptedModel()
    app = create_app(AdvisorWorkflow(model.model, data))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for _ in range(2):
            body = client.post("/generate/stream", json=cases[1].model_dump(mode="json")).text
            assert '"replayed": true' in body
        assert model.seen == [], "a replay never calls the model"
        assert client.post("/generate/stream", json=live(cases[1])).status_code == 200
        assert client.post("/generate/stream", json=live(cases[1])).status_code == 429
