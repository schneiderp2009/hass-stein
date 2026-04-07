"""Select platform for STEIN."""
from __future__ import annotations
import logging
import re
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, STATUS_LABELS
from .coordinator import SteinCoordinator
from .sensor import _asset_device, _label_slug

_LOGGER = logging.getLogger(__name__)
_LABEL_TO_STATUS = {v: k for k, v in STATUS_LABELS.items()}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SteinAssetStatusSelect(coordinator, aid) for aid in coordinator.assets], True)
    known: set[int] = set(coordinator.assets.keys())

    @callback
    def _handle_update() -> None:
        nonlocal known
        new = set(coordinator.assets.keys()) - known
        if new:
            async_add_entities([SteinAssetStatusSelect(coordinator, aid) for aid in new])
        known.update(new)
    coordinator.async_add_listener(_handle_update)


class SteinAssetStatusSelect(CoordinatorEntity[SteinCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_options = list(STATUS_LABELS.values())
    _attr_icon = "mdi:list-status"

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id
        asset = coordinator.assets.get(asset_id, {})
        label = asset.get("label") or f"asset_{asset_id}"
        slug = _label_slug(label)
        self._attr_unique_id = f"stein_asset_{asset_id}_select_status"
        self.entity_id = f"select.stein_{asset_id}_status_setzen"

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def name(self) -> str:
        return "Status setzen"

    @property
    def current_option(self) -> str | None:
        return STATUS_LABELS.get(self._asset.get("status", ""))

    async def async_select_option(self, option: str) -> None:
        status = _LABEL_TO_STATUS.get(option)
        if not status:
            return
        a = self._asset
        payload = {"buId": a.get("buId"), "groupId": a.get("groupId"), "label": a.get("label", ""), "status": status}
        for f in ("name", "comment", "category", "radioName", "issi", "sortOrder", "operationReservation", "huValidUntil"):
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
