"""Read-only demo materials and cancellable live progress transport."""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

from anyio import CancelScope
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from lacaze import __version__
from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.models import CaseInput
from lacaze.infrastructure.data import RuntimeData


def foundation_payload(data: RuntimeData) -> dict[str, Any]:
    """Only explicit fictional business data; never settings, credentials or artifacts."""
    f = data.foundation
    return {
        "brand": data.brand.model_dump(mode="json"),
        "scenarios": [s.model_dump(mode="json") for s in data.scenarios.values()],
        "clients": [c.model_dump(mode="json") for c in f.clients.values()],
        "purchases": [p.model_dump(mode="json") for p in f.purchases],
        "products": [p.model_dump(mode="json") for p in data.catalog.products.values()],
        "services": [s.model_dump(mode="json") for s in f.services],
        "events": [e.model_dump(mode="json") for e in f.events.values()],
        "stores": [s.model_dump(mode="json") for s in f.stores.values()],
        "policies": f.policies.model_dump(mode="json"),
        "calendar": [c.model_dump(mode="json") for c in f.calendar],
    }


def require_same_origin(request: Request) -> None:
    """Stop another website from initiating billable requests to the local demo."""
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="请从当前演示页面发起请求。")


def _encode(event: dict[str, Any]) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


class GenerationStreamResponse(StreamingResponse):
    """Close the producer even when a disconnect interrupts transport send()."""

    def __init__(self, stream: AsyncGenerator[str]):
        self.stream = stream
        super().__init__(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await self.stream.aclose()


async def stream_generation(workflow: AdvisorWorkflow, case: CaseInput) -> AsyncGenerator[str]:
    """Disconnecting the browser cancels the producer and its pending model request."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=16)
    current_stage = "prepare"

    async def observe(event: dict[str, Any]) -> None:
        nonlocal current_stage
        if event.get("stage"):
            current_stage = event["stage"]
        await queue.put(event)

    async def produce() -> None:
        try:
            result = await workflow.generate(case, observer=observe)
            await queue.put(
                {"type": "result", "result": result.model_dump(mode="json", exclude={"trace"})}
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Provider exception bodies can contain credentials or raw response content.
            await queue.put(
                {
                    "type": "error",
                    "stage": current_stage,
                    "error_type": type(exc).__name__,
                    "message": "本次生成未完成。请检查输入或模型连接后重新生成；已完成的阶段保留在页面中。",
                }
            )

    yield _encode(
        {
            "type": "run_started",
            "version": __version__,
            "model": workflow.model_name,
            "configuration_hash": workflow.data.configuration_hash,
        }
    )
    task = asyncio.create_task(produce())
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield _encode(event)
            if event["type"] in {"result", "error"}:
                break
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
