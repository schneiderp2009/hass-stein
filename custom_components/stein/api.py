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
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        try:
            async with self._session.get(url, headers=self._headers, params=params) as resp:
                if resp.status == 401:
                    raise SteinAuthError("Invalid API token")
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            raise SteinApiError(f"Connection error: {err}") from err

    async def _patch(self, path: str, data: dict, params: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        try:
            async with self._session.patch(url, headers=self._headers, json=data, params=params) as resp:
                if resp.status == 401:
                    raise SteinAuthError("Invalid API token")
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            raise SteinApiError(f"Connection error: {err}") from err

    async def get_userinfo(self) -> dict:
        """Fetch info about the authenticated user."""
        result = await self._get("/ext/userinfo")
        return result or {}

    async def get_assets(self, bu_ids: list[int]) -> list[dict]:
        """Fetch all assets for the given BU IDs."""
        params = [("buIds", bid) for bid in bu_ids]
        # aiohttp supports list of tuples for repeated query params
        url = f"{self._base}/ext/assets/"
        try:
            async with self._session.get(url, headers=self._headers, params=params) as resp:
                if resp.status == 401:
                    raise SteinAuthError("Invalid API token")
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            raise SteinApiError(f"Connection error: {err}") from err

    async def get_asset(self, asset_id: int) -> dict | None:
        """Fetch a single asset by ID."""
        return await self._get(f"/ext/assets/{asset_id}")

    async def update_asset(
        self,
        asset_id: int,
        data: dict,
        notify_radio: bool = False,
    ) -> dict:
        """Update an asset."""
        params = {"notifyRadio": str(notify_radio).lower()} if notify_radio else None
        return await self._patch(f"/ext/assets/{asset_id}", data, params)

    async def get_bu(self, bu_id: int) -> dict | None:
        """Fetch a BU by ID."""
        return await self._get(f"/ext/bu/{bu_id}")

    async def test_connection(self) -> bool:
        """Validate credentials by calling userinfo."""
        try:
            info = await self.get_userinfo()
            return bool(info.get("name"))
        except SteinAuthError:
            raise
        except SteinApiError:
            return False
