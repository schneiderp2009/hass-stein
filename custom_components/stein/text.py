"""Text platform for STEIN."""
from __future__ import annotations
import logging
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import SteinCoordinator
from .sensor import _asset_device, _label_slug

_LOGGER = logging.getLogger(__name__)

_FIELDS = [
    ("label",     "label",     "Bezeichnung",  255,   "mdi:tag",          None),
    ("name",      "name",      "Name",         255,   "mdi:rename-box",   None),
    ("comment",   "comment",   "Kommentar",  25000,   "mdi:comment-text", None),
    ("category",  "category",  "Kategorie",     45,   "mdi:shape",        None),
    ("radioname", "radioName", "Funkrufname",  255,   "mdi:radio",        None),
    ("issi",      "issi",      "ISSI",         255,   "mdi:signal",       EntityCategory.CONFIG),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for aid in coordinator.assets:
        for suffix, api_field, fname, maxlen, icon, cat in _FIELDS:
            entities.append(SteinAssetTextField(coordinator, aid, suffix, api_field, fname, maxlen, icon, cat))
    async_add_entities(entities, True)
    known: set[int] = set(coordinator.assets.keys())

    @callback
    def _handle_update() -> None:
        nonlocal known
        new = set(coordinator.assets.keys()) - known
        if new:
            new_e = []
            for aid in new:
                for suffix, api_field, fname, maxlen, icon, cat in _FIELDS:
                    new_e.append(SteinAssetTextField(coordinator, aid, suffix, api_field, fname, maxlen, icon, cat))
            async_add_entities(new_e)
        known.update(new)
    coordinator.async_add_listener(_handle_update)


class SteinAssetTextField(CoordinatorEntity[SteinCoordinator], TextEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, asset_id, field_suffix, api_field, friendly_name, max_length, icon, entity_category):
        super().__init__(coordinator)
        self._asset_id = asset_id
        self._api_field = api_field
        self._friendly_name = friendly_name
        self._attr_native_max = max_length
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        self._field_suffix = field_suffix
        asset = coordinator.assets.get(asset_id, {})
        label = asset.get("label") or f"asset_{asset_id}"
        slug = _label_slug(label)
        self._attr_unique_id = f"stein_asset_{asset_id}_text_{field_suffix}"
        self.entity_id = f"text.stein_{slug}_{field_suffix}"

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def name(self) -> str:
        return self._friendly_name

    @property
    def native_value(self) -> str:
        return self._asset.get(self._api_field) or ""

    async def async_set_value(self, value: str) -> None:
        a = self._asset
        payload = {"buId": a.get("buId"), "groupId": a.get("groupId"), "label": a.get("label", ""), "status": a.get("status", "ready")}
        for f in ("name", "comment", "category", "radioName", "issi", "sortOrder", "operationReservation", "huValidUntil"):
            if a.get(f) is not None:
                payload[f] = a[f]
        payload[self._api_field] = value
        await self.coordinator.api.update_asset(self._asset_id, payload)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return _asset_device(self._asset, self.coordinator)

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets
