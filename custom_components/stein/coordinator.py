"""DataUpdateCoordinator for STEIN."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SteinApi, SteinApiError, SteinAuthError
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
        # Finished reports of the current year, keyed by report id
        self.finished_reports: dict[int, dict] = {}
        # Timestamp of last successful reports fetch (UNIX)
        self._reports_last_fetched: int = 0
        # Set to True after a 403 – stops further report fetching until HA restart
        self.reports_permission_denied: bool = False

        self._refresh_count = 0
        # Last payload received via STEIN webhook (for inspection)
        self.last_webhook: dict | None = None
        self.webhook_url: str | None = None

    async def _safe_get(
        self,
        coro_factory,
        description: str,
        raises: bool = False,
    ):
        """Run a coroutine factory, wait and retry once on 429.

        raises=True: non-recoverable errors become UpdateFailed instead of None.
        """
        try:
            return await coro_factory()
        except SteinAuthError as err:
            # Token ungültig/abgelaufen – HA startet automatisch den Reauth-Flow
            # (via async_step_reauth in config_flow.py), Integration muss dafür
            # NICHT gelöscht werden.
            raise ConfigEntryAuthFailed(f"STEIN {description} error: Invalid API token") from err
        except SteinApiError as err:
            if err.status == 429:
                _LOGGER.warning("STEIN 429 on %s – waiting %ss", description, _RATE_LIMIT_DELAY)
                await asyncio.sleep(_RATE_LIMIT_DELAY)
                try:
                    return await coro_factory()
                except SteinApiError as retry_err:
                    if raises:
                        raise UpdateFailed(f"STEIN {description} failed after retry: {retry_err}") from retry_err
                    _LOGGER.warning("STEIN retry failed for %s: %s", description, retry_err)
                    return None
            if err.status == 403:
                # Laut STEIN-API-Doku ist /reports/full nur mit
                # Headquarter-Berechtigung nutzbar. Einmalig loggen, danach
                # nicht mehr anfragen (bis Neustart/Neu-Laden der Integration).
                if description == "reports":
                    scope = self.userinfo.get("scope") or "unbekannt"
                    _LOGGER.info(
                        "STEIN: Einsätze nicht abrufbar – der API-Key (Scope %s) hat keine "
                        "Headquarter-Berechtigung, die STEIN für /reports/full verlangt. "
                        "Einsatz-Sensoren bleiben leer.",
                        scope,
                    )
                    self.reports_permission_denied = True
                return None
            if raises:
                raise UpdateFailed(f"STEIN {description} error: {err}") from err
            _LOGGER.warning("STEIN error on %s: %s", description, err)
            return None

    # ── Report helpers used by the entities ───────────────────────────────────

    def active_reports(self, bu_id: int) -> list[dict]:
        """All unfinished reports of a BU, newest Einsatzbeginn first."""
        active = [
            r for r in self.reports.values()
            if not r.get("finished", False) and report_belongs_to_bu(r, bu_id)
        ]
        active.sort(key=_report_sort_key, reverse=True)
        return active

    def last_finished_report(self, bu_id: int) -> dict | None:
        """The most recently ended report of a BU in the current year."""
        done = [r for r in self.finished_reports.values() if report_belongs_to_bu(r, bu_id)]
        if not done:
            return None
        return max(done, key=_finished_sort_key)

    def reports_this_year(self, bu_id: int) -> int:
        """Number of reports (active + finished) of a BU started this year."""
        year = _current_year()
        return sum(
            1
            for r in (*self.reports.values(), *self.finished_reports.values())
            if report_belongs_to_bu(r, bu_id) and report_year(r) == year
        )

    def current_report(self, bu_id: int) -> dict | None:
        """The most recent unfinished report of a BU, or None."""
        active = self.active_reports(bu_id)
        return active[0] if active else None

    async def _fetch_reports(self) -> None:
        """Fetch reports, detect new/updated/closed ones and fire HA events."""
        if self.reports_permission_denied:
            return  # 403 bereits erhalten – kein weiterer Versuch
        now = int(time.time())

        # On first fetch, look back a full year (at least to Jahresbeginn) to
        # catch all active reports and all of this year's finished ones
        if self._reports_last_fetched == 0:
            updated_since = min(now - _REPORTS_INITIAL_LOOKBACK, _start_of_year_ts())
        else:
            # Look back a little extra to avoid missing anything at boundary
            updated_since = self._reports_last_fetched - 60

        _LOGGER.debug("STEIN fetching reports for BUs %s updated since %s", self.bu_ids, updated_since)

        raw = await self._safe_get(
            lambda: self.api.get_reports(updated_since), "reports"
        )
        if raw is None:
            return

        self._reports_last_fetched = now

        # The endpoint has no BU filter – keep only reports of configured BUs
        new_report_map: dict[int, dict] = {}
        for r in raw:
            rid = r.get("id")
            if rid is None:
                continue
            if any(report_belongs_to_bu(r, bid) for bid in self.bu_ids):
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
        # Finished ones of the current year are kept in self.finished_reports
        # (für "Letzter Einsatz" und "Einsätze dieses Jahr").
        self.reports.update(new_report_map)
        for rid in [rid for rid, r in self.reports.items() if r.get("finished", False)]:
            report = self.reports.pop(rid)
            self.finished_reports[rid] = report
        year = _current_year()
        for rid in [rid for rid, r in self.finished_reports.items() if report_year(r) != year]:
            del self.finished_reports[rid]

    async def _send_persistent_notification(self, report: dict, new: bool) -> None:
        """Create or update a persistent notification for an active report."""
        rid = report.get("id")
        stichwort = report.get("einsatzStichwort") or "–"
        schadenort = report.get("schadenort") or "–"
        assets = report.get("assets") or []
        asset_names = ", ".join(a.get("name") or a.get("label") or str(a.get("id","")) for a in assets) or "–"
        ek_total = report_ek_total(report)
        prefix = "🚨 Neuer Einsatz" if new else "🔄 Einsatz aktualisiert"

        message = (
            f"**{stichwort}**\n\n"
            f"📍 Schadenort: {schadenort}\n"
            f"🚒 Fahrzeuge: {asset_names}\n"
            f"👥 EK-Kräfte: {ek_total}\n"
            f"📋 Einsatz-ID: #{rid}"
        )
        try:
            persistent_notification.async_create(
                self.hass,
                message,
                title=f"{prefix} #{rid}",
                notification_id=f"stein_report_{rid}",
            )
        except Exception as err:  # noqa: BLE001 – Benachrichtigung darf Update nicht abbrechen
            _LOGGER.warning("STEIN: Benachrichtigung für Einsatz #%s fehlgeschlagen: %s", rid, err)

    async def _dismiss_persistent_notification(self, report_id: int) -> None:
        """Dismiss the persistent notification when a report is closed."""
        try:
            persistent_notification.async_dismiss(self.hass, f"stein_report_{report_id}")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("STEIN: Benachrichtigung #%s nicht entfernt: %s", report_id, err)

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

        return {
            "assets": self.assets,
            "bus": self.bus,
            "userinfo": self.userinfo,
            "reports": self.reports,
            "finished_reports": self.finished_reports,
        }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _report_event_data(report: dict) -> dict:
    """Build the payload for HA event firing – only the most relevant fields."""
    assets = report.get("assets") or []
    return {
        "report_id":       report.get("id"),
        "einsatz_stichwort": report.get("einsatzStichwort"),
        "schadenort":      report.get("schadenort"),
        "einsatzbeginn":   report.get("einsatzbeginn"),
        "finished":        report.get("finished", False),
        "meldeschwellen":  report.get("meldeschwellen", []),
        "anzahl_ek":       report_ek_total(report),
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


def report_ek_total(report: dict) -> int:
    """Sum of Einsatzkräfte (EK1–EK3); tolerates null values."""
    return sum(int(report.get(k) or 0) for k in ("anzahlEk1", "anzahlEk2", "anzahlEk3"))


def report_belongs_to_bu(report: dict, bu_id: int) -> bool:
    """True if the BU leads the report or is listed as beteiligte BU."""
    if (report.get("bu") or {}).get("id") == bu_id:
        return True
    return any((b or {}).get("id") == bu_id for b in report.get("beteiligteBus") or [])


def _report_sort_key(report: dict) -> tuple[str, int]:
    return (
        str(report.get("einsatzbeginn") or report.get("created") or ""),
        int(report.get("id") or 0),
    )


def _current_year() -> int:
    return dt_util.now().year


def _start_of_year_ts() -> int:
    now = dt_util.now()
    return int(now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


def report_year(report: dict) -> int | None:
    """Year of Einsatzbeginn (fallback: created) in HA local time."""
    raw = report.get("einsatzbeginn") or report.get("created")
    if not raw:
        return None
    parsed = dt_util.parse_datetime(str(raw))
    if parsed is None:
        try:
            return datetime.fromisoformat(str(raw)[:10]).year
        except ValueError:
            return None
    return dt_util.as_local(parsed).year


def _finished_sort_key(report: dict) -> tuple[str, str, int]:
    return (
        str(report.get("einsatzende") or ""),
        str(report.get("lastModified") or ""),
        int(report.get("id") or 0),
    )
