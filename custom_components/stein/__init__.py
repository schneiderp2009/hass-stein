"""STEIN – Status Einsatz Meldung – Home Assistant Integration."""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import SteinApi
from .const import (
    DOMAIN,
    CONF_API_TOKEN,
    CONF_BU_IDS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "select"]

SERVICE_UPDATE_ASSET_STATUS = "update_asset_status"
SERVICE_UPDATE_ASSET_STATUS_SCHEMA = vol.Schema(
    {
        vol.Required("asset_id"): cv.positive_int,
        vol.Required("status"): vol.In(["ready", "notready", "semiready", "inuse", "maint"]),
        vol.Optional("comment"): cv.string,
        vol.Optional("notify_radio"): cv.boolean,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up STEIN from a config entry."""
    token = entry.data[CONF_API_TOKEN]
    bu_ids = entry.data[CONF_BU_IDS]
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    session = async_get_clientsession(hass)
    api = SteinApi(token, session)

    coordinator = SteinCoordinator(hass, api, bu_ids, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- Service: update_asset_status ---
    async def handle_update_asset_status(call: ServiceCall) -> None:
        asset_id = call.data["asset_id"]
        status = call.data["status"]
        comment = call.data.get("comment")
        notify_radio = call.data.get("notify_radio", False)

        payload: dict = {"status": status}
        if comment is not None:
            payload["comment"] = comment

        # Fill required fields from cached data
        cached = coordinator.assets.get(asset_id, {})
        for required in ("buId", "label", "groupId"):
            if required not in payload and required in cached:
                payload[required] = cached[required]

        await api.update_asset(asset_id, payload, notify_radio=notify_radio)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_ASSET_STATUS,
        handle_update_asset_status,
        schema=SERVICE_UPDATE_ASSET_STATUS_SCHEMA,
    )

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
