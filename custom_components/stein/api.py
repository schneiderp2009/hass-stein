"""STEIN API client."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import DEFAULT_API_BASE

_LOGGER = logging.getLogger(__name__)


class SteinApiError(Exception):
    """General STEIN API error."""


class SteinAuthError(SteinApiError):
    """Authentication failed."""


class SteinApi:
    """Async client for the STEIN REST API."""

    def __init__(
        self,
        token: str,
        session: aiohttp.ClientSession,
        base_url: str = DEFAULT_API_BASE,
    ) -> None:
        self._token = token
        self._session = session
        self._base = base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: Any = None) -> Any:
        url = f"{self._base}{path}"
        _LOGGER.debug("STEIN GET %s params=%s", url, params)
        try:
            async with self._session.get(
                url, headers=self._headers, params=params
            ) as resp:
                _LOGGER.debug("STEIN GET %s → HTTP %s", url, resp.status)
                if resp.status == 401:
                    raise SteinAuthError("Invalid API token")
                if resp.status == 404:
                    return None
                if resp.status >= 400:
                    raise SteinApiError(f"HTTP {resp.status}")
                return await resp.json(content_type=None)
        except (SteinAuthError, SteinApiError):
            raise
        except Exception as err:
            _LOGGER.error("STEIN GET %s failed: %s (%s)", url, err, type(err).__name__)
            raise SteinApiError(f"Error: {err}") from err

    async def _patch(self, path: str, data: dict, params: Any = None) -> Any:
        url = f"{self._base}{path}"
        _LOGGER.debug("STEIN PATCH %s", url)
        try:
            async with self._session.patch(
                url,
                headers={**self._headers, "Content-Type": "application/json"},
                json=data,
                params=params,
            ) as resp:
                _LOGGER.debug("STEIN PATCH %s → HTTP %s", url, resp.status)
                if resp.status == 401:
                    raise SteinAuthError("Invalid API token")
                if resp.status >= 400:
                    raise SteinApiError(f"HTTP {resp.status}")
                return await resp.json(content_type=None)
        except (SteinAuthError, SteinApiError):
            raise
        except Exception as err:
            _LOGGER.error("STEIN PATCH %s failed: %s (%s)", url, err, type(err).__name__)
            raise SteinApiError(f"Error: {err}") from err

    async def get_userinfo(self) -> dict:
        result = await self._get("/api/ext/userinfo")
        return result or {}

    async def get_assets(self, bu_ids: list[int]) -> list[dict]:
        params = [("buIds", bid) for bid in bu_ids]
        result = await self._get("/api/ext/assets/", params=params)
        return result or []

    async def get_asset(self, asset_id: int) -> dict | None:
        return await self._get(f"/api/ext/assets/{asset_id}")

    async def update_asset(self, asset_id: int, data: dict, notify_radio: bool = False) -> dict:
        params = {"notifyRadio": "true"} if notify_radio else None
        return await self._patch(f"/api/ext/assets/{asset_id}", data, params)

    async def get_bu(self, bu_id: int) -> dict | None:
        return await self._get(f"/api/ext/bu/{bu_id}")

    async def get_reports(self, updated_since: int) -> list[dict]:
        """Fetch all reports updated since the given timestamp.

        The API accepts an ISO 8601 datetime string (e.g. 2019-08-24T14:15:22Z).
        We convert the UNIX timestamp to that format.
        """
        from datetime import datetime, timezone
        iso = datetime.fromtimestamp(updated_since, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = await self._get(
            "/api/ext/reports/full",
            params={"updatedSince": iso},
        )
        return result or []

    async def test_connection(self) -> bool:
        _LOGGER.debug("STEIN testing connection to %s", self._base)
        info = await self.get_userinfo()
        _LOGGER.debug("STEIN userinfo: %s", info)
        return bool(info.get("name"))
