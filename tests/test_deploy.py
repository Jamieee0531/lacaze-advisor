from fastapi.testclient import TestClient

from lacaze.application.workflow import AdvisorWorkflow
from lacaze.interfaces.api import create_app
from tests.conftest import ScriptedModel

HOST = "https://lacaze-demo.onrender.com"


def client_for(data, base_url="http://127.0.0.1", **kwargs):
    app = create_app(AdvisorWorkflow(ScriptedModel().model, data))
    return TestClient(app, base_url=base_url, **kwargs)


def test_unknown_host_is_rejected_by_default(data):
    with client_for(data, base_url=HOST) as client:
        assert client.get("/health").status_code == 400


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
