"""DataUpdateCoordinator for STEIN."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SteinApi, SteinApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_SLOW_FETCH_EVERY = 10
_RATE_LIMIT_DELAY = 70  # seconds to wait after 429


class SteinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch STEIN data with 429-aware spacing between requests."""

    def __init__(self, hass: HomeAssistant, api: SteinApi, bu_ids: list[int], scan_interval: int) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=scan_interval))
        self.api = api
        self.bu_ids = bu_ids
        self.assets: dict[int, dict] = {}
        self.bus: dict[int, dict] = {}
        self.userinfo: dict = {}
        self._refresh_count = 0

    async def _safe_get(self, coro, description: str):
        """Run a coroutine, wait and retry once on 429."""
        try:
            return await coro
        except SteinApiError as err:
            if "429" in str(err):
                _LOGGER.warning("STEIN 429 on %s – waiting %ss", description, _RATE_LIMIT_DELAY)
                await asyncio.sleep(_RATE_LIMIT_DELAY)
                try:
                    return await coro
                except SteinApiError as retry_err:
                    _LOGGER.warning("STEIN retry failed for %s: %s", description, retry_err)
                    return None
            _LOGGER.warning("STEIN error on %s: %s", description, err)
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        self._refresh_count += 1
        do_slow = (self._refresh_count == 1) or (self._refresh_count % _SLOW_FETCH_EVERY == 0)

        # Always fetch assets – with 1s spacing before to avoid burst
        if self._refresh_count > 1:
            await asyncio.sleep(1)

        try:
            raw_assets = await self.api.get_assets(self.bu_ids)
        except SteinApiError as err:
            if "429" in str(err):
                _LOGGER.warning("STEIN 429 on assets – waiting %ss", _RATE_LIMIT_DELAY)
                await asyncio.sleep(_RATE_LIMIT_DELAY)
                try:
                    raw_assets = await self.api.get_assets(self.bu_ids)
                except SteinApiError as retry_err:
                    raise UpdateFailed(f"STEIN API error after retry: {retry_err}") from retry_err
            else:
                raise UpdateFailed(f"STEIN API error: {err}") from err

        assets: dict[int, dict] = {}
        for asset in raw_assets:
            aid = asset.get("id")
            if aid is not None:
                assets[aid] = asset
        self.assets = assets

        if do_slow:
            # Space requests 2s apart to stay under rate limit
            await asyncio.sleep(2)
            for bu_id in self.bu_ids:
                result = await self._safe_get(self.api.get_bu(bu_id), f"BU {bu_id}")
                if result:
                    self.bus[bu_id] = result
                await asyncio.sleep(2)

            result = await self._safe_get(self.api.get_userinfo(), "userinfo")
            if result:
                self.userinfo = result

        return {"assets": self.assets, "bus": self.bus, "userinfo": self.userinfo}
