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

_SLOW_FETCH_EVERY = 10  # BU + userinfo only every 10th refresh
_RETRY_DELAY = 65       # seconds to wait after 429


class SteinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch STEIN data with 429-aware retry logic."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SteinApi,
        bu_ids: list[int],
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.bu_ids = bu_ids
        self.assets: dict[int, dict] = {}
        self.bus: dict[int, dict] = {}
        self.userinfo: dict = {}
        self._refresh_count = 0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data – retry once after 429."""
        self._refresh_count += 1
        do_slow = (self._refresh_count == 1) or (self._refresh_count % _SLOW_FETCH_EVERY == 0)

        # Assets – retry once on 429
        for attempt in range(2):
            try:
                raw_assets = await self.api.get_assets(self.bu_ids)
                break
            except SteinApiError as err:
                if "429" in str(err) and attempt == 0:
                    _LOGGER.warning("STEIN 429 – waiting %ss before retry", _RETRY_DELAY)
                    await asyncio.sleep(_RETRY_DELAY)
                else:
                    raise UpdateFailed(f"STEIN API error: {err}") from err

        assets: dict[int, dict] = {}
        for asset in raw_assets:
            aid = asset.get("id")
            if aid is not None:
                assets[aid] = asset
        self.assets = assets

        if do_slow:
            for bu_id in self.bu_ids:
                try:
                    bu = await self.api.get_bu(bu_id)
                    if bu:
                        self.bus[bu_id] = bu
                except SteinApiError as err:
                    _LOGGER.warning("Could not fetch BU %s: %s", bu_id, err)
            try:
                self.userinfo = await self.api.get_userinfo() or self.userinfo
            except SteinApiError as err:
                _LOGGER.warning("Could not fetch userinfo: %s", err)

        return {"assets": self.assets, "bus": self.bus, "userinfo": self.userinfo}
