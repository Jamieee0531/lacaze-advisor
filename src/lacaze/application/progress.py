"""Optional, per-run observation of public workflow stages, never model reasoning."""

from collections.abc import Awaitable, Callable
from typing import Any

type ProgressObserver = Callable[[dict[str, Any]], Awaitable[None]]


async def report(observer: ProgressObserver | None, event: dict[str, Any]) -> None:
    if observer is not None:
        await observer(event)
