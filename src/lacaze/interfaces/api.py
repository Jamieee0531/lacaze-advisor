from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from lacaze import __version__
from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import CaseInput, Scenario
from lacaze.domain.result import GenerationResult
from lacaze.infrastructure.data import RuntimeData
from lacaze.infrastructure.provider import create_model
from lacaze.infrastructure.settings import Settings


def create_app(workflow: AdvisorWorkflow | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = None
        if workflow is None:
            settings = Settings()
            data = RuntimeData.load(settings.data_dir)
            model, client = create_model(settings)
            app.state.workflow = AdvisorWorkflow(model, data)
        else:
            app.state.workflow = workflow
        try:
            yield
        finally:
            if client:
                await client.close()

    app = FastAPI(title="LACAZE Advisor", version=__version__, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "model": app.state.workflow.model_name}

    @app.get("/scenarios")
    async def scenarios() -> list[str]:
        return [s.value for s in Scenario]

    @app.post("/generate", response_model=GenerationResult)
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
