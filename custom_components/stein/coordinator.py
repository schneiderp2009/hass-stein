"""DataUpdateCoordinator for STEIN."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SteinApi, SteinApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# BU and userinfo change rarely – only fetch every N asset refreshes
_SLOW_FETCH_EVERY = 10


class SteinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch all STEIN data and distribute to entities."""

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
        """Fetch data from STEIN API."""
        self._refresh_count += 1
        do_slow_fetch = (self._refresh_count == 1) or (self._refresh_count % _SLOW_FETCH_EVERY == 0)

        # Always fetch assets (primary data)
        try:
            raw_assets = await self.api.get_assets(self.bu_ids)
        except SteinApiError as err:
            raise UpdateFailed(f"STEIN API error: {err}") from err

        assets: dict[int, dict] = {}
        for asset in raw_assets:
            asset_id = asset.get("id")
            if asset_id is not None:
                assets[asset_id] = asset
        self.assets = assets

        # Fetch BU and userinfo only occasionally (rate-limit friendly)
        if do_slow_fetch:
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
        else:
            _LOGGER.debug(
                "STEIN skipping BU/userinfo fetch (cycle %s/%s)",
                self._refresh_count,
                _SLOW_FETCH_EVERY,
            )

        return {"assets": self.assets, "bus": self.bus, "userinfo": self.userinfo}
