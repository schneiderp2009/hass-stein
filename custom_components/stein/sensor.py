"""Sensor platform for STEIN – Assets, BU, Userinfo, and Reports."""
from __future__ import annotations
import logging
import re
from typing import Any
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, STATUS_LABELS, ART_LABELS, VORENDE_LABELS
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)


def _label_slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _asset_device(asset: dict, coordinator: SteinCoordinator) -> DeviceInfo:
    bu_id = asset.get("buId", "?")
    bu = coordinator.bus.get(bu_id, {})
    label = asset.get("label") or f"Asset {asset.get('id', '?')}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"asset_{asset.get('id')}")},
        name=f"STEIN {label}",
        manufacturer="STEIN",
        model=asset.get("category") or "Asset",
        suggested_area=bu.get("name"),
    )


def _bu_device(bu: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"bu_{bu.get('id')}")},
        name=f"STEIN BU {bu.get('name', bu.get('id', '?'))}",
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

    # Asset sensors
    for asset_id in coordinator.assets:
        entities.append(SteinAssetSensor(coordinator, asset_id))
        entities.append(SteinAssetReadinessSensor(coordinator, asset_id))

    # BU sensors
    for bu_id in coordinator.bus:
        entities.append(SteinBuSensor(coordinator, bu_id))

    # Report sensors – summary + one per active report
    for bu_id in coordinator.bu_ids:
        entities.append(SteinActiveReportsSummarySensor(coordinator, bu_id))
    for report_id, report in coordinator.reports.items():
        if not report.get("finished", False):
            entities.append(SteinReportSensor(coordinator, report_id))

    async_add_entities(entities, True)

    known_asset_ids: set[int] = set(coordinator.assets.keys())
    known_bu_ids: set[int] = set(coordinator.bus.keys())
    known_report_ids: set[int] = {
        rid for rid, r in coordinator.reports.items() if not r.get("finished", False)
    }

    @callback
    def _handle_update() -> None:
        nonlocal known_asset_ids, known_bu_ids, known_report_ids
        new_entities: list = []

        for aid in set(coordinator.assets.keys()) - known_asset_ids:
            new_entities.append(SteinAssetSensor(coordinator, aid))
            new_entities.append(SteinAssetReadinessSensor(coordinator, aid))
        for bid in set(coordinator.bus.keys()) - known_bu_ids:
            new_entities.append(SteinBuSensor(coordinator, bid))

        current_active_reports = {
            rid for rid, r in coordinator.reports.items() if not r.get("finished", False)
        }
        for rid in current_active_reports - known_report_ids:
            new_entities.append(SteinReportSensor(coordinator, rid))

        if new_entities:
            async_add_entities(new_entities)

        known_asset_ids.update(coordinator.assets.keys())
        known_bu_ids.update(coordinator.bus.keys())
        known_report_ids = current_active_reports

    coordinator.async_add_listener(_handle_update)


# ── Asset Sensors ──────────────────────────────────────────────────────────────

class SteinAssetSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:fire-truck"

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id
        self._attr_unique_id = f"stein_asset_{asset_id}_status"
        self.entity_id = f"sensor.stein_{asset_id}_status"

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

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
            "id":                    a.get("id"),
            "bu_id":                 a.get("buId"),
            "group_id":              a.get("groupId"),
            "label":                 a.get("label"),
            "name":                  a.get("name"),
            "status_raw":            a.get("status"),
            "status_label":          STATUS_LABELS.get(a.get("status", ""), a.get("status")),
            "category":              a.get("category"),
            "radio_name":            a.get("radioName"),
            "issi":                  a.get("issi"),
            "comment":               a.get("comment"),
            "sort_order":            a.get("sortOrder"),
            "operation_reservation": a.get("operationReservation"),
            "hu_valid_until":        a.get("huValidUntil"),
            "deleted":               a.get("deleted"),
            "created":               a.get("created"),
            "last_modified":         a.get("lastModified"),
            "last_modified_by":      a.get("lastModifiedBy"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _asset_device(self._asset, self.coordinator)

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets


class SteinAssetReadinessSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SteinCoordinator, asset_id: int) -> None:
        super().__init__(coordinator)
        self._asset_id = asset_id
        self._attr_unique_id = f"stein_asset_{asset_id}_readiness"
        self.entity_id = f"sensor.stein_{asset_id}_einsatzbereitschaft"

    @property
    def _asset(self) -> dict:
        return self.coordinator.assets.get(self._asset_id, {})

    @property
    def name(self) -> str:
        return "Einsatzbereitschaft"

    @property
    def state(self) -> str:
        s = self._asset.get("status", "")
        if s == "ready":     return "Voll"
        if s == "semiready": return "Bedingt"
        return "Nicht bereit"

    @property
    def icon(self) -> str:
        s = self._asset.get("status", "")
        if s == "ready":     return "mdi:shield-check"
        if s == "semiready": return "mdi:shield-half-full"
        return "mdi:shield-off"

    @property
    def device_info(self) -> DeviceInfo:
        return _asset_device(self._asset, self.coordinator)

    @property
    def available(self) -> bool:
        return self._asset_id in self.coordinator.assets


# ── BU Sensor ─────────────────────────────────────────────────────────────────

class SteinBuSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-group"

    def __init__(self, coordinator: SteinCoordinator, bu_id: int) -> None:
        super().__init__(coordinator)
        self._bu_id = bu_id
        self._attr_unique_id = f"stein_bu_{bu_id}_total"
        self.entity_id = f"sensor.stein_bu_{bu_id}"

    @property
    def _bu(self) -> dict:
        return self.coordinator.bus.get(self._bu_id, {})

    @property
    def name(self) -> str:
        return "Ortsverband"

    @property
    def state(self) -> int:
        return sum(1 for a in self.coordinator.assets.values() if a.get("buId") == self._bu_id)

    @property
    def unit_of_measurement(self) -> str:
        return "Assets"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        bu = self._bu
        counts: dict[str, int] = {}
        total = 0
        ready = 0
        for a in self.coordinator.assets.values():
            if a.get("buId") != self._bu_id:
                continue
            total += 1
            s = a.get("status", "unknown")
            if s == "ready":
                ready += 1
            label = STATUS_LABELS.get(s, s)
            counts[label] = counts.get(label, 0) + 1
        stats = bu.get("stats", {})
        return {
            "id":           bu.get("id"),
            "name":         bu.get("name"),
            "code":         bu.get("code"),
            "region_id":    bu.get("regionId"),
            "comment":      bu.get("comment"),
            "author":       bu.get("author"),
            "last_modified": bu.get("lastModified"),
            "email_status_change_enabled": bu.get("emailStatusChangeEnabled"),
            "fs_sort_order": bu.get("fsSortOrder"),
            "stats_ready":    stats.get("ready", 0),
            "stats_notready": stats.get("notready", 0),
            "stats_semiready": stats.get("semiready", 0),
            "stats_inuse":    stats.get("inuse", 0),
            "stats_maint":    stats.get("maint", 0),
            "asset_counts":  counts,
            "readiness_pct": round(ready / total * 100) if total else 0,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return _bu_device(self._bu)


# ── Userinfo Sensor ────────────────────────────────────────────────────────────

class SteinUserinfoSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:account-circle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SteinCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "stein_userinfo"
        self.entity_id = "sensor.stein_api_stein_verbindung"

    @property
    def name(self) -> str:
        return "Verbindung"

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
        )


# ── Report Sensors ─────────────────────────────────────────────────────────────

class SteinActiveReportsSummarySensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """Counts active (non-finished) reports for a BU."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:clipboard-alert"
    _attr_native_unit_of_measurement = "Einsätze"

    def __init__(self, coordinator: SteinCoordinator, bu_id: int) -> None:
        super().__init__(coordinator)
        self._bu_id = bu_id
        self._attr_unique_id = f"stein_bu_{bu_id}_aktive_einsaetze"
        self.entity_id = f"sensor.stein_bu_{bu_id}_aktive_einsaetze"

    @property
    def name(self) -> str:
        return "Aktive Einsätze"

    @property
    def _active_reports(self) -> list[dict]:
        return [
            r for r in self.coordinator.reports.values()
            if not r.get("finished", False)
            and (r.get("bu") or {}).get("id") == self._bu_id
        ]

    @property
    def native_value(self) -> int:
        return len(self._active_reports)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        active = self._active_reports
        return {
            "einsatz_ids": [r.get("id") for r in active],
            "stichwörter": [r.get("einsatzStichwort") for r in active],
            "schadenorte":  [r.get("schadenort") for r in active],
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


class SteinReportSensor(CoordinatorEntity[SteinCoordinator], SensorEntity):
    """One sensor per report – state = Einsatzstichwort, all API fields as attributes."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clipboard-text-clock"

    def __init__(self, coordinator: SteinCoordinator, report_id: int) -> None:
        super().__init__(coordinator)
        self._report_id = report_id
        self._attr_unique_id = f"stein_report_{report_id}"
        self.entity_id = f"sensor.stein_report_{report_id}"

    @property
    def _report(self) -> dict:
        return self.coordinator.reports.get(self._report_id, {})

    @property
    def name(self) -> str:
        stichwort = self._report.get("einsatzStichwort") or f"Einsatz #{self._report_id}"
        return f"Einsatz {stichwort}"

    @property
    def state(self) -> str:
        r = self._report
        if r.get("finished"):
            return "Abgeschlossen"
        return r.get("einsatzStichwort") or "Aktiv"

    @property
    def icon(self) -> str:
        return "mdi:clipboard-check" if self._report.get("finished") else "mdi:clipboard-alert"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._report
        bu = r.get("bu") or {}
        assets = r.get("assets", [])
        incidents = r.get("incidents", [])
        tasks = r.get("tasks", [])
        categories = r.get("categories", [])
        beteiligte = r.get("beteiligteBus", [])
        project = r.get("project") or {}
        requester = r.get("requester") or {}
        zip_code = r.get("zipCode") or {}
        ek_total = (
            r.get("anzahlEk1", 0) +
            r.get("anzahlEk2", 0) +
            r.get("anzahlEk3", 0)
        )
        return {
            "id":               r.get("id"),
            "schema_version":   r.get("schemaVersion"),
            "created":          r.get("created"),
            "last_modified":    r.get("lastModified"),
            "last_modified_by": r.get("lastModifiedBy"),
            "finished":         r.get("finished", False),
            "meldeschwellen":   r.get("meldeschwellen", []),
            "einsatz_stichwort": r.get("einsatzStichwort"),
            "art_tech_unterstuetzung": ART_LABELS.get(
                r.get("artTechUnterstuetzung", ""), r.get("artTechUnterstuetzung")
            ),
            "schadenort":       r.get("schadenort"),
            "schaden":          r.get("schaden"),
            "einsatzbeginn":    r.get("einsatzbeginn"),
            "einsatzende":      r.get("einsatzende"),
            "auftragsnummer":   r.get("auftragsnummer"),
            "dienststelle":     r.get("dienststelle"),
            "fachberater":      r.get("fachberater"),
            "besonderheiten":   r.get("besonderheiten"),
            "zip_code":         zip_code.get("zipCode"),
            "zip_ausland":      r.get("zipCodeAusland", False),
            "zip_ausland_wert": r.get("zipCodeAuslandValue"),
            "author":           r.get("author"),
            "author_phone":     r.get("authorPhone"),
            "betroffene_unverletzte": r.get("betroffeneUnverletzte", 0),
            "betroffene_verletzte":   r.get("betroffeneVerletzte", 0),
            "betroffene_tote":        r.get("betroffeneTote", 0),
            "betroffene_vermisste":   r.get("betroffeneVermisste", 0),
            "betroffene_unbekannt":   r.get("betroffeneUnbekannt", False),
            "anzahl_ek1":       r.get("anzahlEk1", 0),
            "anzahl_ek2":       r.get("anzahlEk2", 0),
            "anzahl_ek3":       r.get("anzahlEk3", 0),
            "anzahl_ek_max":    r.get("anzahlEkMax", 0),
            "anzahl_ek_gesamt": ek_total,
            "keine_helfer":     r.get("anzahlEkNone", False),
            "medien_vor_ort":           r.get("medienVorOrt"),
            "oeffentlichkeitsarbeit":   r.get("oeffentlichkeitsarbeitMoeglich"),
            "vor_einsatzende_hours": VORENDE_LABELS.get(
                r.get("vorEinsatzendeHours", ""), r.get("vorEinsatzendeHours")
            ),
            "vor_einsatzende_days": r.get("vorEinsatzendeDays"),
            "bu_id":   bu.get("id"),
            "bu_name": bu.get("name"),
            "bu_code": bu.get("code"),
            "assets": [
                {"id": a.get("id"), "name": a.get("name") or a.get("label")}
                for a in assets
            ],
            "asset_names": [a.get("name") or a.get("label") for a in assets],
            "incidents": [
                {"id": i.get("id"), "code": i.get("code"), "name": i.get("name")}
                for i in incidents
            ],
            "tasks":       [t.get("name") for t in tasks],
            "categories":  [{"name": c.get("name"), "value": c.get("value")} for c in categories],
            "beteiligte_ovs": [
                {"id": b.get("id"), "name": b.get("name"), "code": b.get("code")}
                for b in beteiligte
            ],
            "project_name":   project.get("name"),
            "requester_name": requester.get("name"),
        }

    @property
    def available(self) -> bool:
        return self._report_id in self.coordinator.reports

    @property
    def device_info(self) -> DeviceInfo:
        r = self._report
        bu = r.get("bu") or {}
        bu_id = bu.get("id")
        if bu_id and bu_id in self.coordinator.bus:
            bu_data = self.coordinator.bus[bu_id]
            return DeviceInfo(
                identifiers={(DOMAIN, f"bu_{bu_id}")},
                name=f"STEIN BU {bu_data.get('name', bu_id)}",
                manufacturer="STEIN",
                model="Ortsverband",
            )
        return DeviceInfo(
            identifiers={(DOMAIN, "stein_connection")},
            name="STEIN API",
            manufacturer="STEIN",
            model="API Verbindung",
        )
