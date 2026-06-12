"""DataUpdateCoordinator for STEIN."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SteinApi, SteinApiError
from .const import DOMAIN, EVENT_STEIN_NEW_REPORT, EVENT_STEIN_UPDATED_REPORT, EVENT_STEIN_CLOSED_REPORT

_LOGGER = logging.getLogger(__name__)

_SLOW_FETCH_EVERY = 10
_RATE_LIMIT_DELAY = 70  # seconds to wait after 429

# How far back to look on first reports fetch (1 year covers all active reports)
_REPORTS_INITIAL_LOOKBACK = 365 * 24 * 3600


class SteinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch STEIN data with 429-aware spacing between requests."""

    def __init__(self, hass: HomeAssistant, api: SteinApi, bu_ids: list[int], scan_interval: int) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=scan_interval))
        self.api = api
        self.bu_ids = bu_ids
        self.assets: dict[int, dict] = {}
        self.bus: dict[int, dict] = {}
        self.userinfo: dict = {}

        # Reports: keyed by report id, value is full report dict
        self.reports: dict[int, dict] = {}
        # Timestamp of last successful reports fetch (UNIX)
        self._reports_last_fetched: int = 0
        # Set to True after a 403 – stops further report fetching until HA restart
        self.reports_permission_denied: bool = False

        self._refresh_count = 0

    async def _safe_get(self, coro_factory, description: str, raises: bool = False):
        """Run a coroutine factory, wait and retry once on 429.

        raises=True: non-recoverable errors become UpdateFailed instead of None.
        """
        try:
            return await coro_factory()
        except SteinApiError as err:
            if "429" in str(err):
                _LOGGER.warning("STEIN 429 on %s – waiting %ss", description, _RATE_LIMIT_DELAY)
                await asyncio.sleep(_RATE_LIMIT_DELAY)
                try:
                    return await coro_factory()
                except SteinApiError as retry_err:
                    if raises:
                        raise UpdateFailed(f"STEIN {description} failed after retry: {retry_err}") from retry_err
                    _LOGGER.warning("STEIN retry failed for %s: %s", description, retry_err)
                    return None
            if "403" in str(err):
                # 403 = fehlende Berechtigung (Headquarter-Level erforderlich)
                # Kein Warning-Spam – einmalig loggen, danach nicht mehr versuchen
                if description == "reports":
                    _LOGGER.info(
                        "STEIN: Reports-API nicht verfügbar (HTTP 403 – Headquarter-Berechtigung "
                        "erforderlich). Report-Funktionen deaktiviert."
                    )
                    self.reports_permission_denied = True
                return None
            if raises:
                raise UpdateFailed(f"STEIN {description} error: {err}") from err
            _LOGGER.warning("STEIN error on %s: %s", description, err)
            return None

    async def _fetch_reports(self) -> None:
        """Fetch reports, detect new/updated/closed ones and fire HA events."""
        if self.reports_permission_denied:
            return  # 403 bereits erhalten – kein weiterer Versuch
        now = int(time.time())

        # On first fetch, look back a full year to catch all active reports
        if self._reports_last_fetched == 0:
            updated_since = now - _REPORTS_INITIAL_LOOKBACK
        else:
            # Look back a little extra to avoid missing anything at boundary
            updated_since = self._reports_last_fetched - 60

        _LOGGER.debug("STEIN fetching reports updated since %s", updated_since)

        raw = await self._safe_get(
            lambda: self.api.get_reports(updated_since), "reports"
        )
        if raw is None:
            return

        self._reports_last_fetched = now

        new_report_map: dict[int, dict] = {}
        for r in raw:
            rid = r.get("id")
            if rid is not None:
                new_report_map[rid] = r

        # Detect changes and fire events
        for rid, report in new_report_map.items():
            if rid not in self.reports:
                # Brand new report – only fire if not finished
                if not report.get("finished", False):
                    _LOGGER.info("STEIN new report #%s: %s", rid, report.get("einsatzStichwort", ""))
                    self.hass.bus.async_fire(
                        EVENT_STEIN_NEW_REPORT,
                        _report_event_data(report),
                    )
                    await self._send_persistent_notification(report, new=True)
            else:
                old = self.reports[rid]
                if _report_changed(old, report):
                    if report.get("finished") and not old.get("finished"):
                        # Report just closed
                        _LOGGER.info("STEIN report #%s closed", rid)
                        self.hass.bus.async_fire(
                            EVENT_STEIN_CLOSED_REPORT,
                            _report_event_data(report),
                        )
                        await self._dismiss_persistent_notification(rid)
                    else:
                        _LOGGER.info("STEIN report #%s updated", rid)
                        self.hass.bus.async_fire(
                            EVENT_STEIN_UPDATED_REPORT,
                            _report_event_data(report),
                        )

        # Merge new data into self.reports, then drop finished ones to prevent unbounded growth.
        # Events are fired above before this point, so the transition is already captured.
        self.reports.update(new_report_map)
        for rid in [rid for rid, r in self.reports.items() if r.get("finished", False)]:
            del self.reports[rid]

    async def _send_persistent_notification(self, report: dict, new: bool) -> None:
        """Create or update a persistent notification for an active report."""
        rid = report.get("id")
        stichwort = report.get("einsatzStichwort") or "–"
        schadenort = report.get("schadenort") or "–"
        assets = report.get("assets", [])
        asset_names = ", ".join(a.get("name") or a.get("label") or str(a.get("id","")) for a in assets) or "–"
        ek_total = (
            report.get("anzahlEk1", 0) +
            report.get("anzahlEk2", 0) +
            report.get("anzahlEk3", 0)
        )
        prefix = "🚨 Neuer Einsatz" if new else "🔄 Einsatz aktualisiert"

        message = (
            f"**{stichwort}**\n\n"
            f"📍 Schadenort: {schadenort}\n"
            f"🚒 Fahrzeuge: {asset_names}\n"
            f"👥 EK-Kräfte: {ek_total}\n"
            f"📋 Einsatz-ID: #{rid}"
        )
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": f"{prefix} #{rid}",
                "message": message,
                "notification_id": f"stein_report_{rid}",
            },
        )

    async def _dismiss_persistent_notification(self, report_id: int) -> None:
        """Dismiss the persistent notification when a report is closed."""
        await self.hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": f"stein_report_{report_id}"},
        )

    async def _async_update_data(self) -> dict[str, Any]:
        self._refresh_count += 1
        do_slow = (self._refresh_count == 1) or (self._refresh_count % _SLOW_FETCH_EVERY == 0)

        # Always fetch assets – with 1s spacing before to avoid burst
        if self._refresh_count > 1:
            await asyncio.sleep(1)

        raw_assets = await self._safe_get(
            lambda: self.api.get_assets(self.bu_ids), "assets", raises=True
        )

        assets: dict[int, dict] = {}
        for asset in raw_assets:
            aid = asset.get("id")
            if aid is not None:
                assets[aid] = asset
        self.assets = assets

        if do_slow:
            await asyncio.sleep(2)
            for bu_id in self.bu_ids:
                result = await self._safe_get(lambda: self.api.get_bu(bu_id), f"BU {bu_id}")
                if result:
                    self.bus[bu_id] = result
                await asyncio.sleep(2)

            result = await self._safe_get(lambda: self.api.get_userinfo(), "userinfo")
            if result:
                self.userinfo = result

        # Fetch reports every cycle (they're cheap – only delta since last fetch)
        await asyncio.sleep(1)
        await self._fetch_reports()

        return {"assets": self.assets, "bus": self.bus, "userinfo": self.userinfo, "reports": self.reports}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _report_event_data(report: dict) -> dict:
    """Build the payload for HA event firing – only the most relevant fields."""
    assets = report.get("assets", [])
    return {
        "report_id":       report.get("id"),
        "einsatz_stichwort": report.get("einsatzStichwort"),
        "schadenort":      report.get("schadenort"),
        "einsatzbeginn":   report.get("einsatzbeginn"),
        "finished":        report.get("finished", False),
        "meldeschwellen":  report.get("meldeschwellen", []),
        "anzahl_ek":       (
            report.get("anzahlEk1", 0) +
            report.get("anzahlEk2", 0) +
            report.get("anzahlEk3", 0)
        ),
        "asset_ids":  [a.get("id")   for a in assets],
        "asset_names":[a.get("name") or a.get("label") for a in assets],
        "bu_id":      report.get("bu", {}).get("id") if report.get("bu") else None,
    }


def _report_changed(old: dict, new: dict) -> bool:
    """Return True if a report has meaningfully changed."""
    watch = (
        "finished", "einsatzStichwort", "schadenort", "schaden",
        "meldeschwellen", "assets", "anzahlEk1", "anzahlEk2", "anzahlEk3",
        "einsatzende", "lastModified",
    )
    for key in watch:
        if old.get(key) != new.get(key):
            return True
    return False
