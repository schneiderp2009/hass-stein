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

from .const import (
    DOMAIN,
    STATUS_LABELS,
    ATTR_LABEL,
    ATTR_NAME,
    ATTR_COMMENT,
    ATTR_CATEGORY,
    ATTR_RADIO_NAME,
    ATTR_ISSI,
    ATTR_OPERATION_RESERVATION,
    ATTR_HU_VALID_UNTIL,
    ATTR_LAST_MODIFIED,
    ATTR_LAST_MODIFIED_BY,
    ATTR_BU_ID,
    ATTR_GROUP_ID,
)
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    # Userinfo sensor
    entities.append(SteinUserinfoSensor(coordinator))

    # Asset sensors
    for asset_id, asset in coordinator.assets.items():
        entities.append(SteinAssetSensor(coordinator, asset_id))

    # BU summary sensors
    for bu_id, bu in coordinator.bus.items():
        entities.append(SteinBuSensor(coordinator, bu_id))

    async_add_entities(entities, True)

    # Track newly added assets between refreshes
    known_asset_ids: set[int] = set(coordinator.assets.keys())
    known_bu_ids: set[int] = set(coordinator.bus.keys())

    @callback
    def _handle_coordinator_update() -> None:
        nonlocal known_asset_ids, known_bu_ids
        new_assets = set(coordinator.assets.keys()) - known_asset_ids
        new_bus = set(coordinator.bus.keys()) - known_bu_ids

        new_entities: list[SensorEntity] = []
        for asset_id in new_assets:
            new_entities.append(SteinAssetSensor(coordinator, asset_id))
        for bu_id in new_bus:
            new_entities.append(SteinBuSensor(coordinator, bu_id))

        if new_entities:
            async_add_entities(new_entities)

        known_asset_ids.update(new_assets)
        known_bu_ids.update(new_bus)

    coordinator.async_add_listener(_handle_coordinator_update)


class SteinAssetSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Represents a single STEIN asset as a sensor."""

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
        status = self._asset.get("status", "")
        icons = {
            "ready": "mdi:check-circle",
            "notready": "mdi:close-circle",
            "semiready": "mdi:alert-circle",
            "inuse": "mdi:fire-truck",
            "maint": "mdi:wrench",
        }
        return icons.get(status, "mdi:help-circle")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        a = self._asset
        return {
            ATTR_LABEL: a.get("label"),
            ATTR_NAME: a.get("name"),
            "status_raw": a.get("status"),
            ATTR_COMMENT: a.get("comment"),
            ATTR_CATEGORY: a.get("category"),
            ATTR_RADIO_NAME: a.get("radioName"),
            ATTR_ISSI: a.get("issi"),
            ATTR_OPERATION_RESERVATION: a.get("operationReservation"),
            ATTR_HU_VALID_UNTIL: a.get("huValidUntil"),
            ATTR_LAST_MODIFIED: a.get("lastModified"),
            ATTR_LAST_MODIFIED_BY: a.get("lastModifiedBy"),
            ATTR_BU_ID: a.get("buId"),
            ATTR_GROUP_ID: a.get("groupId"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        bu_id = self._asset.get("buId", "?")
        bu = self.coordinator.bus.get(bu_id, {})
        bu_name = bu.get("name", f"BU {bu_id}")
        return DeviceInfo(
            identifiers={(DOMAIN, f"bu_{bu_id}")},
            name=bu_name,
            manufacturer="STEIN",
            model="Bereitschaft",
        )

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets


class SteinBuSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Summary sensor for a BU (shows count of assets per status)."""

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
        """Total assets in this BU."""
        return sum(
            1
            for a in self.coordinator.assets.values()
            if a.get("buId") == self._bu_id
        )

    @property
    def unit_of_measurement(self) -> str:
        return "Fahrzeuge"

    @property
    def icon(self) -> str:
        return "mdi:garage"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for a in self.coordinator.assets.values():
            if a.get("buId") == self._bu_id:
                s = a.get("status", "unknown")
                counts[STATUS_LABELS.get(s, s)] = counts.get(STATUS_LABELS.get(s, s), 0) + 1

        bu = self._bu
        return {
            "bu_name": bu.get("name"),
            "bu_code": bu.get("code"),
            "region_id": bu.get("regionId"),
            "comment": bu.get("comment"),
            "author": bu.get("author"),
            "last_modified": bu.get("lastModified"),
            "email_status_change_enabled": bu.get("emailStatusChangeEnabled"),
            "fs_sort_order": bu.get("fsSortOrder"),
            "stats": bu.get("stats", {}),
            "local_counts": counts,
        }

    @property
    def device_info(self) -> DeviceInfo:
        bu_name = self._bu.get("name", f"BU {self._bu_id}")
        return DeviceInfo(
            identifiers={(DOMAIN, f"bu_{self._bu_id}")},
            name=bu_name,
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
