import json

from fastapi.testclient import TestClient

from lacaze.application.batch import run_batch
from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import ClientInformation
from lacaze.interfaces.api import create_app
from tests.conftest import ScriptedModel


def test_http_validates_case_and_returns_same_workflow(data, cases):
    workflow = AdvisorWorkflow(ScriptedModel().model, data)
    with TestClient(create_app(workflow), base_url="http://127.0.0.1") as client:
        assert len(client.get("/scenarios").json()) == 6
        payload = cases[0].model_dump(mode="json")
        response = client.post("/generate", json=payload)
        assert response.status_code == 200
        assert len(response.json()["candidates"]["messages"]) == 3
        del payload["case_date"]
        assert client.post("/generate", json=payload).status_code == 422


async def test_batch_preserves_inputs_and_outputs_without_quality_scores(data, cases, tmp_path):
    workflow = AdvisorWorkflow(ScriptedModel().model, data)
    directory = tmp_path / "run"
    summary = await run_batch(workflow, cases[:2], directory, concurrency=2)
    assert summary["success"] == 2
    result = json.loads((directory / "C01.json").read_text())
    assert result["input"] == cases[0].model_dump(mode="json")
    assert len(result["result"]["candidates"]["messages"]) == 3
    assert (directory / "outputs.csv").is_file()
    snapshot = json.loads((directory / "configuration.json").read_text())
    assert snapshot == data.source_files
    assert "score" not in result


async def test_repolish_run_writes_a_new_run_the_evaluator_can_read(data, cases, tmp_path):
    from lacaze.application.batch import repolish_run
    from lacaze.evaluation.loader import load_run

    workflow = AdvisorWorkflow(ScriptedModel().model, data)
    await run_batch(workflow, cases[:2], tmp_path / "run")
    summary = await repolish_run(workflow, tmp_path / "run", tmp_path / "polished")
    assert summary["total"] == 2 and summary["error"] == 0 and summary["edits"] == 0
    assert [c.case_id for c in load_run(tmp_path / "polished").cases] == ["C01", "C02"]


async def test_batch_records_failure_without_fabricating_candidates(data, cases, tmp_path):
    workflow = AdvisorWorkflow(ScriptedModel().model, data)
    directory = tmp_path / "failed-run"
    unknown = ClientInformation(client_id="cl999")  # no record and nothing inline
    broken = [c.model_copy(update={"client_information": unknown}) for c in cases[:2]]
    summary = await run_batch(workflow, broken, directory)
    assert summary["error"] == 2
    for cid in ["C01", "C02"]:
        record = json.loads((directory / f"{cid}.json").read_text())
        assert record["status"] == "error"
        assert "result" not in record
