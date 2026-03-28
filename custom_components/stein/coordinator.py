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
        # Keyed by asset id (int)
        self.assets: dict[int, dict] = {}
        # Keyed by bu id (int)
        self.bus: dict[int, dict] = {}
        # Authenticated user info
        self.userinfo: dict = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from STEIN API."""
        try:
            raw_assets = await self.api.get_assets(self.bu_ids)
        except SteinApiError as err:
            raise UpdateFailed(f"STEIN API error: {err}") from err

        assets: dict[int, dict] = {}
        for asset in raw_assets:
            asset_id = asset.get("id")
            if asset_id is not None:
                assets[asset_id] = asset

        # Fetch BU data (only on first run or if list changed)
        bus: dict[int, dict] = {}
        for bu_id in self.bu_ids:
            try:
                bu = await self.api.get_bu(bu_id)
                if bu:
                    bus[bu_id] = bu
            except SteinApiError as err:
                _LOGGER.warning("Could not fetch BU %s: %s", bu_id, err)

        # Fetch userinfo
        try:
            userinfo = await self.api.get_userinfo()
        except SteinApiError as err:
            _LOGGER.warning("Could not fetch userinfo: %s", err)
            userinfo = self.userinfo  # keep last known

        self.assets = assets
        self.bus = bus
        self.userinfo = userinfo
        return {"assets": assets, "bus": bus, "userinfo": userinfo}
