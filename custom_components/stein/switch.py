"""Switch platform for STEIN: toggle operationReservation."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SteinOperationReservationSwitch(coordinator, asset_id)
        for asset_id in coordinator.assets
    ]
    async_add_entities(entities, True)

    known_ids: set[int] = set(coordinator.assets.keys())

    @callback
    def _handle_update() -> None:
        nonlocal known_ids
        new_ids = set(coordinator.assets.keys()) - known_ids
        if new_ids:
            async_add_entities([SteinOperationReservationSwitch(coordinator, aid) for aid in new_ids])
        known_ids.update(new_ids)

    coordinator.async_add_listener(_handle_update)


class SteinOperationReservationSwitch(CoordinatorEntity[SteinCoordinator], SwitchEntity):
    """Switch to toggle operationReservation on a STEIN asset."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bookmark-check"

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_asset_opreservation_{self._asset_id}"

    @property
    def name(self) -> str:
        label = self._asset.get("label") or f"Asset {self._asset_id}"
        return f"{label} – Einsatzreservierung"

    @property
    def is_on(self) -> bool:
        return bool(self._asset.get("operationReservation", False))

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_reservation(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_reservation(False)

    async def _set_reservation(self, value: bool) -> None:
        asset = self._asset
        payload = {
            "buId": asset.get("buId"),
            "groupId": asset.get("groupId"),
            "label": asset.get("label", ""),
            "status": asset.get("status", "ready"),
            "operationReservation": value,
        }
        for field in ("name", "comment", "category", "radioName", "issi",
                      "sortOrder", "huValidUntil"):
            if asset.get(field) is not None:
                payload[field] = asset[field]
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
