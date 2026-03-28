"""STEIN – Status Einsatz Meldung – Home Assistant Integration."""
from __future__ import annotations

import logging

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

PLATFORMS = ["sensor", "select", "text", "switch"]

SERVICE_UPDATE_ASSET = "update_asset"
SERVICE_UPDATE_ASSET_SCHEMA = vol.Schema(
    {
        vol.Required("asset_id"): cv.positive_int,
        vol.Optional("status"): vol.In(["ready", "notready", "semiready", "inuse", "maint"]),
        vol.Optional("label"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("comment"): cv.string,
        vol.Optional("category"): cv.string,
        vol.Optional("radio_name"): cv.string,
        vol.Optional("issi"): cv.string,
        vol.Optional("sort_order"): cv.positive_int,
        vol.Optional("operation_reservation"): cv.boolean,
        vol.Optional("hu_valid_until"): cv.string,
        vol.Optional("notify_radio"): cv.boolean,
    }
)

# Mapping: Service-Feldname → API-Feldname
_FIELD_MAP = {
    "status": "status",
    "label": "label",
    "name": "name",
    "comment": "comment",
    "category": "category",
    "radio_name": "radioName",
    "issi": "issi",
    "sort_order": "sortOrder",
    "operation_reservation": "operationReservation",
    "hu_valid_until": "huValidUntil",
}


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

    # --- Service: update_asset ---
    async def handle_update_asset(call: ServiceCall) -> None:
        asset_id = call.data["asset_id"]
        notify_radio = call.data.get("notify_radio", False)

        # Start with all current values from cache (API requires buId, label, groupId)
        cached = coordinator.assets.get(asset_id, {})
        payload: dict = {
            "buId": cached.get("buId"),
            "groupId": cached.get("groupId"),
            "label": cached.get("label", ""),
            "status": cached.get("status", "ready"),
        }

        # Optionally copy other existing fields
        for api_field in ("name", "comment", "category", "radioName", "issi",
                          "sortOrder", "operationReservation", "huValidUntil"):
            if api_field in cached:
                payload[api_field] = cached[api_field]

        # Override with values from the service call
        for svc_field, api_field in _FIELD_MAP.items():
            if svc_field in call.data:
                payload[api_field] = call.data[svc_field]

        _LOGGER.debug("STEIN update_asset %s payload: %s", asset_id, payload)
        await api.update_asset(asset_id, payload, notify_radio=notify_radio)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_ASSET,
        handle_update_asset,
        schema=SERVICE_UPDATE_ASSET_SCHEMA,
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
