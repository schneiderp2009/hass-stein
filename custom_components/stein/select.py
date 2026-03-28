"""Select platform for STEIN: change asset status directly from HA."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STATUS_LABELS
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)

_LABEL_TO_STATUS = {v: k for k, v in STATUS_LABELS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SteinAssetStatusSelect(coordinator, asset_id)
        for asset_id in coordinator.assets
    ]
    async_add_entities(entities, True)

    known_ids: set[int] = set(coordinator.assets.keys())

    @callback
    def _handle_update() -> None:
        nonlocal known_ids
        new_ids = set(coordinator.assets.keys()) - known_ids
        if new_ids:
            async_add_entities([SteinAssetStatusSelect(coordinator, aid) for aid in new_ids])
        known_ids.update(new_ids)

    coordinator.async_add_listener(_handle_update)


class SteinAssetStatusSelect(CoordinatorEntity[SteinCoordinator], SelectEntity):
    """Select entity to change an asset's status."""

    _attr_has_entity_name = True
    _attr_options = list(STATUS_LABELS.values())
    _attr_icon = "mdi:list-status"

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_asset_status_{self._asset_id}"

    @property
    def name(self) -> str:
        label = self._asset.get("label") or f"Asset {self._asset_id}"
        return f"{label} – Status"

    @property
    def current_option(self) -> str | None:
        return STATUS_LABELS.get(self._asset.get("status", ""))

    async def async_select_option(self, option: str) -> None:
        status = _LABEL_TO_STATUS.get(option)
        if not status:
            _LOGGER.error("Unknown status option: %s", option)
            return
        await self._update_asset({"status": status})

    async def _update_asset(self, changes: dict) -> None:
        """Merge changes with current asset data and send PATCH."""
        asset = self._asset
        payload = {
            "buId": asset.get("buId"),
            "groupId": asset.get("groupId"),
            "label": asset.get("label", ""),
            "status": asset.get("status", "ready"),
        }
        # Include all existing optional fields
        for field in ("name", "comment", "category", "radioName", "issi",
                      "sortOrder", "operationReservation", "huValidUntil"):
            if asset.get(field) is not None:
                payload[field] = asset[field]
        payload.update(changes)
        await self.coordinator.api.update_asset(self._asset_id, payload)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        bu_id = self._asset.get("buId", "?")
        bu = self.coordinator.bus.get(bu_id, {})
        return DeviceInfo(
            identifiers={(DOMAIN, f"bu_{bu_id}")},
            name=bu.get("name", f"BU {bu_id}"),
            manufacturer="STEIN",
            model="Bereitschaft",
        )

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets
