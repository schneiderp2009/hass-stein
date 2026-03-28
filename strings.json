"""Sensor platform for STEIN: asset status & BU statistics."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STATUS_LABELS
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    entities.append(SteinUserinfoSensor(coordinator))

    for asset_id in coordinator.assets:
        entities.append(SteinAssetSensor(coordinator, asset_id))

    for bu_id in coordinator.bus:
        entities.append(SteinBuSensor(coordinator, bu_id))

    async_add_entities(entities, True)

    known_asset_ids: set[int] = set(coordinator.assets.keys())
    known_bu_ids: set[int] = set(coordinator.bus.keys())

    @callback
    def _handle_coordinator_update() -> None:
        nonlocal known_asset_ids, known_bu_ids
        new_entities: list[SensorEntity] = []

        new_assets = set(coordinator.assets.keys()) - known_asset_ids
        for asset_id in new_assets:
            new_entities.append(SteinAssetSensor(coordinator, asset_id))

        new_bus = set(coordinator.bus.keys()) - known_bu_ids
        for bu_id in new_bus:
            new_entities.append(SteinBuSensor(coordinator, bu_id))

        if new_entities:
            async_add_entities(new_entities)

        known_asset_ids.update(new_assets)
        known_bu_ids.update(new_bus)

    coordinator.async_add_listener(_handle_coordinator_update)


class SteinAssetSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Represents a single STEIN asset as a sensor – shows all available fields."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_asset_{self._asset_id}"

    @property
    def name(self) -> str:
        return self._asset.get("label") or f"Asset {self._asset_id}"

    @property
    def state(self) -> str:
        raw = self._asset.get("status", "unknown")
        return STATUS_LABELS.get(raw, raw)

    @property
    def icon(self) -> str:
        icons = {
            "ready": "mdi:check-circle",
            "notready": "mdi:close-circle",
            "semiready": "mdi:alert-circle",
            "inuse": "mdi:fire-truck",
            "maint": "mdi:wrench",
        }
        return icons.get(self._asset.get("status", ""), "mdi:help-circle")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        a = self._asset
        return {
            # Identifikation
            "id": a.get("id"),
            "bu_id": a.get("buId"),
            "group_id": a.get("groupId"),
            "label": a.get("label"),
            "name": a.get("name"),
            # Status
            "status": a.get("status"),
            "status_label": STATUS_LABELS.get(a.get("status", ""), a.get("status")),
            "operation_reservation": a.get("operationReservation"),
            # Funk / Digitalfunk
            "radio_name": a.get("radioName"),
            "issi": a.get("issi"),
            # Sonstiges
            "category": a.get("category"),
            "comment": a.get("comment"),
            "sort_order": a.get("sortOrder"),
            "hu_valid_until": a.get("huValidUntil"),
            # Metadaten (read-only)
            "deleted": a.get("deleted"),
            "created": a.get("created"),
            "last_modified": a.get("lastModified"),
            "last_modified_by": a.get("lastModifiedBy"),
        }

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


class SteinBuSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Summary sensor for a BU – shows all BU fields and asset counts."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SteinCoordinator, bu_id: int) -> None:
        super().__init__(coordinator)
        self._bu_id = bu_id

    @property
    def _bu(self) -> dict:
        return self.coordinator.bus.get(self._bu_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_bu_{self._bu_id}"

    @property
    def name(self) -> str:
        return f"{self._bu.get('name', f'BU {self._bu_id}')} – Übersicht"

    @property
    def state(self) -> int:
        return sum(1 for a in self.coordinator.assets.values() if a.get("buId") == self._bu_id)

    @property
    def unit_of_measurement(self) -> str:
        return "Fahrzeuge"

    @property
    def icon(self) -> str:
        return "mdi:garage"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bu = self._bu

        # Count assets per status
        counts: dict[str, int] = {}
        for a in self.coordinator.assets.values():
            if a.get("buId") == self._bu_id:
                s = a.get("status", "unknown")
                label = STATUS_LABELS.get(s, s)
                counts[label] = counts.get(label, 0) + 1

        return {
            # Identifikation
            "id": bu.get("id"),
            "name": bu.get("name"),
            "code": bu.get("code"),
            "region_id": bu.get("regionId"),
            # Metadaten
            "author": bu.get("author"),
            "last_modified": bu.get("lastModified"),
            "comment": bu.get("comment"),
            "fs_sort_order": bu.get("fsSortOrder"),
            # Einstellungen
            "email_status_change_enabled": bu.get("emailStatusChangeEnabled"),
            # Statistiken
            "stats_api": bu.get("stats", {}),
            "asset_counts": counts,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"bu_{self._bu_id}")},
            name=self._bu.get("name", f"BU {self._bu_id}"),
            manufacturer="STEIN",
            model="Bereitschaft",
        )


class SteinUserinfoSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Sensor showing info about the authenticated STEIN API user."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-circle"

    @property
    def unique_id(self) -> str:
        return "stein_userinfo"

    @property
    def name(self) -> str:
        return "STEIN Verbindung"

    @property
    def state(self) -> str:
        return self.coordinator.userinfo.get("name", "Unbekannt")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        u = self.coordinator.userinfo
        scope_role = u.get("scopeRole", {})
        return {
            "id": u.get("id"),
            "name": u.get("name"),
            "email": u.get("email"),
            "scope": u.get("scope"),
            "tech_user": u.get("techUser"),
            "active": u.get("active"),
            "scope_role_entity": scope_role.get("entity"),
            "scope_role_permission": scope_role.get("permission"),
            "scope_role_entity_id": scope_role.get("entityId"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "stein_connection")},
            name="STEIN API",
            manufacturer="STEIN",
            model="API Verbindung",
            entry_type="service",
        )
