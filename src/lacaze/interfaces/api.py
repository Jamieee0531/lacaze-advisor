from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from lacaze import __version__
from lacaze.application.preparation import prepare
from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import CaseInput, Scenario
from lacaze.domain.result import GenerationResult
from lacaze.infrastructure.data import RuntimeData, load_cases
from lacaze.infrastructure.provider import create_model
from lacaze.infrastructure.settings import Settings
from lacaze.interfaces.demo import foundation_payload, require_same_origin, stream_generation

WEB_DIR = Path(__file__).with_name("web")


def create_app(workflow: AdvisorWorkflow | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = None
        settings = Settings()
        if workflow is None:
            data = RuntimeData.load(settings.data_dir)
            model, client = create_model(settings)
            app.state.workflow = AdvisorWorkflow(model, data)
        else:
            app.state.workflow = workflow
        app.state.demo_cases = [
            case.model_dump(mode="json")
            for name in ("development.jsonl", "test.jsonl")
            for case in load_cases(settings.data_dir / "cases" / name)
        ]
        try:
            yield
        finally:
            if client:
                await client.close()

    app = FastAPI(title="LACAZE Advisor", version=__version__, lifespan=lifespan)
    app.mount("/web", StaticFiles(directory=WEB_DIR, check_dir=False), name="web")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/demo/bootstrap")
    async def bootstrap() -> dict:
        flow = app.state.workflow
        return {
            "version": __version__,
            "model": flow.model_name,
            "configuration_hash": flow.data.configuration_hash,
            "cases": app.state.demo_cases,
            "foundation": foundation_payload(flow.data),
        }

    @app.post("/demo/prepare", dependencies=[Depends(require_same_origin)])
    async def preview(case: CaseInput) -> dict:
        try:
            return prepare(case, app.state.workflow.data).model_dump(mode="json")
        except ValueError:
            raise HTTPException(
                status_code=422, detail="无法找到客户。请选择已有客户，或填写新客户姓名。"
            ) from None

    @app.post("/generate/stream", dependencies=[Depends(require_same_origin)])
    async def generate_stream(case: CaseInput) -> StreamingResponse:
        return StreamingResponse(
            stream_generation(app.state.workflow, case),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "model": app.state.workflow.model_name}

    @app.get("/scenarios")
    async def scenarios() -> list[str]:
        return [s.value for s in Scenario]

    @app.post(
        "/generate", response_model=GenerationResult, dependencies=[Depends(require_same_origin)]
    )
    async def generate(case: CaseInput) -> GenerationResult:
        try:
            return await app.state.workflow.generate(case)
        except Exception as exc:
            # A failed generation is not replaced with canned text.
            raise HTTPException(
                status_code=502, detail={"error_type": type(exc).__name__}
            ) from None

    return app


app = create_app()
