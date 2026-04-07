"""Switch platform for STEIN."""
from __future__ import annotations
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import SteinCoordinator
from .sensor import _asset_device, _label_slug

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SteinOperationReservationSwitch(coordinator, aid) for aid in coordinator.assets], True)
    known: set[int] = set(coordinator.assets.keys())

    @callback
    def _handle_update() -> None:
        nonlocal known
        new = set(coordinator.assets.keys()) - known
        if new:
            async_add_entities([SteinOperationReservationSwitch(coordinator, aid) for aid in new])
        known.update(new)
    coordinator.async_add_listener(_handle_update)


class SteinOperationReservationSwitch(CoordinatorEntity[SteinCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:bookmark-check"

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id
        asset = coordinator.assets.get(asset_id, {})
        label = asset.get("label") or f"asset_{asset_id}"
        slug = _label_slug(label)
        self._attr_unique_id = f"stein_asset_{asset_id}_switch_opreservation"
        self.entity_id = f"switch.stein_{asset_id}_einsatzreservierung"

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def name(self) -> str:
        return "Einsatzreservierung"

    @property
    def is_on(self) -> bool:
        return bool(self._asset.get("operationReservation", False))

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)

    async def _set(self, value: bool) -> None:
        a = self._asset
        payload = {"buId": a.get("buId"), "groupId": a.get("groupId"), "label": a.get("label", ""), "status": a.get("status", "ready"), "operationReservation": value}
        for f in ("name", "comment", "category", "radioName", "issi", "sortOrder", "huValidUntil"):
            if a.get(f) is not None:
                payload[f] = a[f]
        await self.coordinator.api.update_asset(self._asset_id, payload)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return _asset_device(self._asset, self.coordinator)

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets
