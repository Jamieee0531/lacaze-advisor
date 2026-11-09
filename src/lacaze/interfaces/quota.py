"""Daily cap on billable generations, so a public demo link cannot run up the API bill."""

from collections.abc import Callable
from datetime import UTC, date, datetime

from fastapi import HTTPException


def _utc_today() -> date:
    return datetime.now(UTC).date()


class DailyQuota:
    """Counts generations per UTC day in memory; a restart starts the count again."""

    def __init__(self, limit: int | None, today: Callable[[], date] = _utc_today):
        self.limit = limit
        self._today = today
        self._day: date | None = None
        self._used = 0

    def __call__(self) -> None:
        if self.limit is None:
            return
        day = self._today()
        if day != self._day:
            self._day, self._used = day, 0
        if self._used >= self.limit:
            raise HTTPException(status_code=429, detail="今日演示次数已用完，请明天再试。")
        self._used += 1
