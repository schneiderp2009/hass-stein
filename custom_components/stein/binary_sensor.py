"""Binary sensor platform for STEIN – Einsatz aktiv."""
from __future__ import annotations

import logging
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
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

    # One global "Einsatz aktiv" sensor per BU
    entities = []
    for bu_id in coordinator.bu_ids:
        entities.append(SteinEinsatzActiveSensor(coordinator, bu_id))

    async_add_entities(entities, True)


class SteinEinsatzActiveSensor(CoordinatorEntity[SteinCoordinator], BinarySensorEntity):
    """True when at least one non-finished report exists for this BU."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:alarm-light"

    def __init__(self, coordinator: SteinCoordinator, bu_id: int) -> None:
        super().__init__(coordinator)
        self._bu_id = bu_id
        self._attr_unique_id = f"stein_bu_{bu_id}_einsatz_aktiv"
        self.entity_id = f"binary_sensor.stein_bu_{bu_id}_einsatz_aktiv"

    @property
    def name(self) -> str:
        bu = self.coordinator.bus.get(self._bu_id, {})
        bu_name = bu.get("name") or f"BU {self._bu_id}"
        return f"{bu_name} Einsatz aktiv"

    @property
    def _active_reports(self) -> list[dict]:
        return [
            r for r in self.coordinator.reports.values()
            if not r.get("finished", False)
            and (r.get("bu") or {}).get("id") == self._bu_id
        ]

    @property
    def is_on(self) -> bool:
        return len(self._active_reports) > 0

    @property
    def icon(self) -> str:
        return "mdi:alarm-light" if self.is_on else "mdi:alarm-light-off"

    @property
    def extra_state_attributes(self) -> dict:
        active = self._active_reports
        return {
            "anzahl_aktive_einsaetze": len(active),
            "einsatz_ids": [r.get("id") for r in active],
            "stichwörter": [r.get("einsatzStichwort") for r in active if r.get("einsatzStichwort")],
            "schadenorte": [r.get("schadenort") for r in active if r.get("schadenort")],
        }

    @property
    def device_info(self) -> DeviceInfo:
        bu = self.coordinator.bus.get(self._bu_id, {})
        return DeviceInfo(
            identifiers={(DOMAIN, f"bu_{self._bu_id}")},
            name=f"STEIN BU {bu.get('name', self._bu_id)}",
            manufacturer="STEIN",
            model="Ortsverband",
        )
