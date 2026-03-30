"""Sensor platform for STEIN."""
from __future__ import annotations
import logging
from typing import Any
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, STATUS_LABELS
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)


def _asset_device(asset: dict, coordinator: SteinCoordinator) -> DeviceInfo:
    bu_id = asset.get("buId", "?")
    bu = coordinator.bus.get(bu_id, {})
    label = asset.get("label") or f"Asset {asset['id']}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"asset_{asset['id']}")},
        name=f"STEIN {label}",
        manufacturer="STEIN",
        model=asset.get("category") or "Asset",
        via_device=(DOMAIN, f"bu_{bu_id}"),
        suggested_area=bu.get("name"),
    )


def _bu_device(bu: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"bu_{bu['id']}") },
        name=f"STEIN BU {bu.get('name', bu['id'])}",
        manufacturer="STEIN",
        model="Ortsverband",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SteinCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [SteinUserinfoSensor(coordinator)]

    for asset_id in coordinator.assets:
        entities.append(SteinAssetSensor(coordinator, asset_id))
        entities.append(SteinAssetReadinessSensor(coordinator, asset_id))

    for bu_id in coordinator.bus:
        entities.append(SteinBuSensor(coordinator, bu_id))
        for status_key in ("ready", "notready", "semiready", "inuse", "maint"):
            entities.append(SteinBuStatusCountSensor(coordinator, bu_id, status_key))

    async_add_entities(entities, True)

    known_asset_ids: set[int] = set(coordinator.assets.keys())
    known_bu_ids: set[int] = set(coordinator.bus.keys())

    @callback
    def _handle_update() -> None:
        nonlocal known_asset_ids, known_bu_ids
        new_entities: list = []
        for aid in set(coordinator.assets.keys()) - known_asset_ids:
            new_entities.append(SteinAssetSensor(coordinator, aid))
            new_entities.append(SteinAssetReadinessSensor(coordinator, aid))
        for bid in set(coordinator.bus.keys()) - known_bu_ids:
            new_entities.append(SteinBuSensor(coordinator, bid))
            for sk in ("ready", "notready", "semiready", "inuse", "maint"):
                new_entities.append(SteinBuStatusCountSensor(coordinator, bid, sk))
        if new_entities:
            async_add_entities(new_entities)
        known_asset_ids.update(set(coordinator.assets.keys()) - known_asset_ids)
        known_bu_ids.update(set(coordinator.bus.keys()) - known_bu_ids)

    coordinator.async_add_listener(_handle_update)


class SteinAssetSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Main status sensor per asset – state is the German status label."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:fire-truck"

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id
        asset = coordinator.assets.get(asset_id, {})
        label = asset.get("label", f"asset_{asset_id}")
        import re
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        self._attr_unique_id = f"stein_asset_{asset_id}_status"
        self.entity_id = f"sensor.stein_{slug}_status"

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_asset_{self._asset_id}_status"

    @property
    def name(self) -> str:
        return "Status"

    @property
    def state(self) -> str:
        return STATUS_LABELS.get(self._asset.get("status", ""), self._asset.get("status", "unbekannt"))

    @property
    def icon(self) -> str:
        return {
            "ready":     "mdi:check-circle",
            "notready":  "mdi:close-circle",
            "semiready": "mdi:alert-circle",
            "inuse":     "mdi:fire-truck",
            "maint":     "mdi:wrench",
        }.get(self._asset.get("status", ""), "mdi:help-circle")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        a = self._asset
        return {
            "id":                   a.get("id"),
            "bu_id":                a.get("buId"),
            "group_id":             a.get("groupId"),
            "label":                a.get("label"),
            "name":                 a.get("name"),
            "status_raw":           a.get("status"),
            "status_label":         STATUS_LABELS.get(a.get("status", ""), a.get("status")),
            "category":             a.get("category"),
            "radio_name":           a.get("radioName"),
            "issi":                 a.get("issi"),
            "comment":              a.get("comment"),
            "sort_order":           a.get("sortOrder"),
            "operation_reservation": a.get("operationReservation"),
            "hu_valid_until":       a.get("huValidUntil"),
            "deleted":              a.get("deleted"),
            "created":              a.get("created"),
            "last_modified":        a.get("lastModified"),
            "last_modified_by":     a.get("lastModifiedBy"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _asset_device(self._asset, self.coordinator)

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets


class SteinAssetReadinessSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Binary-style sensor: is the asset operationally ready?"""
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_asset_{self._asset_id}_readiness"

    @property
    def name(self) -> str:
        return "Einsatzbereitschaft"

    @property
    def state(self) -> str:
        s = self._asset.get("status", "")
        if s == "ready":    return "Voll"
        if s == "semiready": return "Bedingt"
        return "Nicht bereit"

    @property
    def icon(self) -> str:
        s = self._asset.get("status", "")
        if s == "ready":    return "mdi:shield-check"
        if s == "semiready": return "mdi:shield-half-full"
        return "mdi:shield-off"

    @property
    def device_info(self) -> DeviceInfo:
        return _asset_device(self._asset, self.coordinator)

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets


class SteinBuSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Total asset count for a BU."""
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:garage"

    def __init__(self, coordinator: SteinCoordinator, bu_id: int) -> None:
        super().__init__(coordinator)
        self._bu_id = bu_id

    @property
    def _bu(self) -> dict:
        return self.coordinator.bus.get(self._bu_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_bu_{self._bu_id}_total"

    @property
    def name(self) -> str:
        return "Fahrzeuge gesamt"

    @property
    def state(self) -> int:
        return sum(1 for a in self.coordinator.assets.values() if a.get("buId") == self._bu_id)

    @property
    def unit_of_measurement(self) -> str:
        return "Fahrzeuge"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bu = self._bu
        counts: dict[str, int] = {}
        for a in self.coordinator.assets.values():
            if a.get("buId") == self._bu_id:
                s = a.get("status", "unknown")
                counts[STATUS_LABELS.get(s, s)] = counts.get(STATUS_LABELS.get(s, s), 0) + 1
        ready = sum(1 for a in self.coordinator.assets.values()
                    if a.get("buId") == self._bu_id and a.get("status") == "ready")
        total = self.state
        return {
            "bu_id":   bu.get("id"),
            "bu_name": bu.get("name"),
            "bu_code": bu.get("code"),
            "region_id": bu.get("regionId"),
            "comment": bu.get("comment"),
            "author":  bu.get("author"),
            "last_modified": bu.get("lastModified"),
            "email_status_change_enabled": bu.get("emailStatusChangeEnabled"),
            "fs_sort_order": bu.get("fsSortOrder"),
            "stats_api": bu.get("stats", {}),
            "asset_counts": counts,
            "readiness_pct": round(ready / total * 100) if total else 0,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _bu_device(self._bu)


class SteinBuStatusCountSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Count of assets in a specific status for a BU – great for dashboards."""
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SteinCoordinator, bu_id: int, status_key: str) -> None:
        super().__init__(coordinator)
        self._bu_id = bu_id
        self._status_key = status_key

    @property
    def _bu(self) -> dict:
        return self.coordinator.bus.get(self._bu_id, {})

    @property
    def unique_id(self) -> str:
        return f"stein_bu_{self._bu_id}_count_{self._status_key}"

    @property
    def name(self) -> str:
        return f"Anzahl {STATUS_LABELS.get(self._status_key, self._status_key)}"

    @property
    def state(self) -> int:
        return sum(
            1 for a in self.coordinator.assets.values()
            if a.get("buId") == self._bu_id and a.get("status") == self._status_key
        )

    @property
    def unit_of_measurement(self) -> str:
        return "Fahrzeuge"

    @property
    def icon(self) -> str:
        return {
            "ready":     "mdi:check-circle",
            "notready":  "mdi:close-circle",
            "semiready": "mdi:alert-circle",
            "inuse":     "mdi:fire-truck",
            "maint":     "mdi:wrench",
        }.get(self._status_key, "mdi:help-circle")

    @property
    def device_info(self) -> DeviceInfo:
        return _bu_device(self._bu)


class SteinUserinfoSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """API connection info sensor."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:account-circle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return "stein_userinfo"

    @property
    def name(self) -> str:
        return "API Verbindung"

    @property
    def state(self) -> str:
        return self.coordinator.userinfo.get("name", "Unbekannt")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        u = self.coordinator.userinfo
        sr = u.get("scopeRole", {})
        return {
            "id":    u.get("id"),
            "name":  u.get("name"),
            "email": u.get("email"),
            "scope": u.get("scope"),
            "tech_user": u.get("techUser"),
            "active":    u.get("active"),
            "scope_role_entity":     sr.get("entity"),
            "scope_role_permission": sr.get("permission"),
            "scope_role_entity_id":  sr.get("entityId"),
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
