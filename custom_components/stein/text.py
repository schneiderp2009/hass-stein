"""Text platform for STEIN: edit asset text fields directly from HA."""
from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)


# Field definitions: (unique_suffix, api_field, friendly_name, max_length, icon)
_TEXT_FIELDS = [
    ("label",     "label",     "Bezeichnung",  255, "mdi:tag"),
    ("name",      "name",      "Name",         255, "mdi:rename-box"),
    ("comment",   "comment",   "Kommentar",  25000, "mdi:comment-text"),
    ("category",  "category",  "Kategorie",     45, "mdi:shape"),
    ("radioname", "radioName", "Funkrufname",  255, "mdi:radio"),
    ("issi",      "issi",      "ISSI",         255, "mdi:signal"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for asset_id in coordinator.assets:
        for suffix, api_field, fname, maxlen, icon in _TEXT_FIELDS:
            entities.append(
                SteinAssetTextField(coordinator, asset_id, suffix, api_field, fname, maxlen, icon)
            )

    async_add_entities(entities, True)

    known_ids: set[int] = set(coordinator.assets.keys())

    @callback
    def _handle_update() -> None:
        nonlocal known_ids
        new_ids = set(coordinator.assets.keys()) - known_ids
        if new_ids:
            new_entities = []
            for asset_id in new_ids:
                for suffix, api_field, fname, maxlen, icon in _TEXT_FIELDS:
                    new_entities.append(
                        SteinAssetTextField(coordinator, asset_id, suffix, api_field, fname, maxlen, icon)
                    )
            async_add_entities(new_entities)
        known_ids.update(new_ids)

    coordinator.async_add_listener(_handle_update)


class SteinAssetTextField(CoordinatorEntity[SteinCoordinator], TextEntity):
    """Text entity for a single editable field of a STEIN asset."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SteinCoordinator,
        asset_id: int,
        field_suffix: str,
        api_field: str,
        friendly_name: str,
        max_length: int,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id
        self._api_field = api_field
        self._friendly_name = friendly_name
        self._attr_native_max = max_length
        self._attr_icon = icon
        self._field_suffix = field_suffix

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_asset_{self._field_suffix}_{self._asset_id}"

    @property
    def name(self) -> str:
        label = self._asset.get("label") or f"Asset {self._asset_id}"
        return f"{label} – {self._friendly_name}"

    @property
    def native_value(self) -> str:
        return self._asset.get(self._api_field) or ""

    async def async_set_value(self, value: str) -> None:
        asset = self._asset
        payload = {
            "buId": asset.get("buId"),
            "groupId": asset.get("groupId"),
            "label": asset.get("label", ""),
            "status": asset.get("status", "ready"),
        }
        for field in ("name", "comment", "category", "radioName", "issi",
                      "sortOrder", "operationReservation", "huValidUntil"):
            if asset.get(field) is not None:
                payload[field] = asset[field]
        payload[self._api_field] = value
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
