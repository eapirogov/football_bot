import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import httpx

from bot.config import settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"
CACHE_TTL_SECONDS = 300


class FootballAPI:
    def __init__(self, api_key: str = settings.FOOTBALL_DATA_KEY) -> None:
        self._headers = {"X-Auth-Token": api_key}
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        cache_key = f"{path}?{sorted((params or {}).items())}"
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                return cached[1]

        async with httpx.AsyncClient(timeout=20.0) as client:
            for attempt in range(3):
                res = await client.get(f"{BASE_URL}{path}", params=params, headers=self._headers)
                if res.status_code == 429:
                    retry_after = int(res.headers.get("X-RequestCounter-Reset", "60"))
                    log.warning("football-data.org 429, sleeping %ss (attempt %s)", retry_after, attempt + 1)
                    await asyncio.sleep(retry_after)
                    continue
                res.raise_for_status()
                data = res.json()
                break
            else:
                res.raise_for_status()

        async with self._lock:
            self._cache[cache_key] = (time.monotonic(), data)
        return data

    async def get_competition(self, code: str) -> dict[str, Any] | None:
        """Данные лиги по коду (PL, CL и т.д.)."""
        try:
            return await self._get(f"/competitions/{code}")
        except httpx.HTTPStatusError:
            return None

    async def get_teams(self, code: str, season: int) -> list[dict[str, Any]]:
        """Команды лиги за сезон."""
        try:
            data = await self._get(f"/competitions/{code}/teams", {"season": season})
            return data.get("teams") or []
        except httpx.HTTPStatusError:
            return []

    async def get_matches(
        self,
        code: str,
        date_from: str,
        date_to: str,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        """Матчи лиги в диапазоне дат."""
        params: dict[str, Any] = {"dateFrom": date_from, "dateTo": date_to}
        if season is not None:
            params["season"] = season
        try:
            data = await self._get(f"/competitions/{code}/matches", params)
            return data.get("matches") or []
        except httpx.HTTPStatusError:
            return []

    async def get_match(self, match_id: int) -> dict[str, Any] | None:
        """Данные одного матча по ID."""
        try:
            return await self._get(f"/matches/{match_id}")
        except httpx.HTTPStatusError:
            return None

    async def get_standings(self, code: str, season: int | None = None) -> list[dict[str, Any]]:
        """Турнирная таблица лиги."""
        params: dict[str, Any] = {}
        if season is not None:
            params["season"] = season
        try:
            data = await self._get(f"/competitions/{code}/standings", params)
            standings = data.get("standings") or []
            # берём TOTAL (есть ещё HOME/AWAY)
            total = next((s for s in standings if s.get("type") == "TOTAL"), None)
            return (total or {}).get("table") or []
        except httpx.HTTPStatusError:
            return []

    async def check_api_key(self) -> bool:
        """Проверка ключа — один дешёвый запрос к /competitions."""
        try:
            await self._get("/competitions/PL")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                return False
            raise


def current_season() -> int:
    now = datetime.utcnow()
    return now.year if now.month >= 7 else now.year - 1


football_api = FootballAPI()
