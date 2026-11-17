"""Coordinator + entity tests for Einsätze (reports), with a mocked API."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stein.api import SteinApiError
from custom_components.stein.const import CONF_API_TOKEN, CONF_BU_IDS, DOMAIN
from custom_components.stein.coordinator import (
    SteinCoordinator,
    report_belongs_to_bu,
    report_ek_total,
)

from .conftest import make_report

# Testdaten liegen in 2026 – Zeit fixieren, damit "dieses Jahr" stabil bleibt
pytestmark = pytest.mark.freeze_time("2026-11-17 13:00:00+00:00")


def _api(reports=None):
    api = AsyncMock()
    api.get_assets.return_value = [
        {"id": 340, "buId": 19, "label": "GKW", "status": "ready"}
    ]
    api.get_bu.return_value = {"id": 19, "name": "OV Schwäbisch Gmünd"}
    api.get_userinfo.return_value = {"name": "HA"}
    api.get_reports.return_value = reports if reports is not None else []
    return api


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("custom_components.stein.coordinator.asyncio.sleep", new=AsyncMock()):
        yield


def test_helpers():
    r = make_report()
    assert report_ek_total(r) == 7
    assert report_belongs_to_bu(r, 19)
    assert not report_belongs_to_bu(r, 20)
    r2 = make_report(bu_id=99, beteiligteBus=[{"id": 19}])
    assert report_belongs_to_bu(r2, 19)


async def test_coordinator_filters_reports_to_configured_bus(hass: HomeAssistant):
    api = _api([
        make_report(1),
        make_report(2, bu_id=55),
        make_report(3, bu_id=55, beteiligteBus=[{"id": 19}]),
    ])
    coord = SteinCoordinator(hass, api, [19], 300)
    await coord._fetch_reports()

    (since,) = api.get_reports.await_args.args
    assert isinstance(since, int)
    assert set(coord.reports) == {1, 3}


async def test_coordinator_403_disables_reports(hass: HomeAssistant):
    api = _api()
    api.get_reports.side_effect = SteinApiError("HTTP 403: Forbidden", status=403)
    coord = SteinCoordinator(hass, api, [19], 300)
    await coord._fetch_reports()
    assert coord.reports_permission_denied
    await coord._fetch_reports()
    assert api.get_reports.await_count == 1


async def test_current_report_is_newest_active(hass: HomeAssistant):
    api = _api([
        make_report(1, einsatzbeginn="2026-11-17T08:00:00Z", einsatzStichwort="Alt"),
        make_report(2, einsatzbeginn="2026-11-17T12:00:00Z", einsatzStichwort="Neu"),
        make_report(3, finished=True, einsatzbeginn="2026-11-17T13:00:00Z"),
    ])
    coord = SteinCoordinator(hass, api, [19], 300)
    await coord._fetch_reports()
    assert [r["id"] for r in coord.active_reports(19)] == [2, 1]
    assert coord.current_report(19)["einsatzStichwort"] == "Neu"


async def _setup(hass, api):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_API_TOKEN: "API-test", CONF_BU_IDS: [19]}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.stein.SteinApi", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_entities_show_active_einsatz(hass: HomeAssistant):
    api = _api([make_report(42)])
    await _setup(hass, api)

    active = hass.states.get("binary_sensor.stein_bu_19_einsatz_aktiv")
    assert active.state == "on"
    assert active.attributes["aktueller_einsatz_stichwort"] == "THL Unwetter"

    current = hass.states.get("sensor.stein_bu_19_aktueller_einsatz")
    assert current.state == "THL Unwetter"
    assert current.attributes["schadenort"] == "Schwäbisch Gmünd, Remsstraße 1"
    assert current.attributes["schaden"] == "Baum auf Fahrbahn"
    assert current.attributes["einsatzbeginn"] == "2026-11-17T10:00:00Z"
    assert current.attributes["fahrzeuge"] == ["GKW", "MTW"]
    assert current.attributes["einsatzkraefte"] == 7

    assert hass.states.get("sensor.stein_bu_19_aktive_einsaetze").state == "1"
    assert hass.states.get("sensor.stein_report_42").state == "THL Unwetter"


async def test_entities_without_einsatz(hass: HomeAssistant):
    await _setup(hass, _api([]))

    assert hass.states.get("binary_sensor.stein_bu_19_einsatz_aktiv").state == "off"
    assert hass.states.get("sensor.stein_bu_19_aktueller_einsatz").state == "Kein Einsatz"


async def test_finished_reports_kept_for_this_year(hass: HomeAssistant):
    api = _api([
        make_report(1, finished=True, einsatzbeginn="2026-03-01T08:00:00Z",
                    einsatzende="2026-03-01T12:00:00Z", einsatzStichwort="Hochwasser"),
        make_report(2, finished=True, einsatzbeginn="2026-10-05T08:00:00Z",
                    einsatzende="2026-10-05T18:00:00Z", einsatzStichwort="Sturm"),
        make_report(3, finished=True, einsatzbeginn="2025-12-30T08:00:00Z",
                    einsatzende="2025-12-30T10:00:00Z"),
        make_report(4, einsatzbeginn="2026-11-17T10:00:00Z"),
    ])
    coord = SteinCoordinator(hass, api, [19], 300)
    await coord._fetch_reports()

    assert set(coord.finished_reports) == {1, 2}
    assert coord.last_finished_report(19)["einsatzStichwort"] == "Sturm"
    assert coord.reports_this_year(19) == 3  # 1, 2 und der laufende 4


async def test_active_report_moves_to_finished(hass: HomeAssistant):
    api = _api([make_report(5, einsatzbeginn="2026-11-17T10:00:00Z")])
    coord = SteinCoordinator(hass, api, [19], 300)
    await coord._fetch_reports()
    assert coord.current_report(19)["id"] == 5
    assert coord.last_finished_report(19) is None

    api.get_reports.return_value = [
        make_report(5, finished=True, einsatzbeginn="2026-11-17T10:00:00Z",
                    einsatzende="2026-11-17T14:00:00Z")
    ]
    await coord._fetch_reports()
    assert coord.current_report(19) is None
    assert coord.last_finished_report(19)["id"] == 5
    assert coord.reports_this_year(19) == 1


async def test_last_einsatz_and_year_counter_entities(hass: HomeAssistant):
    api = _api([
        make_report(7, finished=True, einsatzbeginn="2026-09-01T08:00:00Z",
                    einsatzende="2026-09-01T15:00:00Z", einsatzStichwort="Ölspur"),
        make_report(8, einsatzbeginn="2026-11-17T10:00:00Z"),
    ])
    await _setup(hass, api)

    last = hass.states.get("sensor.stein_bu_19_letzter_einsatz")
    assert last.state == "Ölspur"
    assert last.attributes["einsatzende"] == "2026-09-01T15:00:00Z"
    assert last.attributes["fahrzeuge"] == ["GKW", "MTW"]
    assert last.attributes["einsatzkraefte"] == 7

    assert hass.states.get("sensor.stein_bu_19_einsaetze_dieses_jahr").state == "2"
    assert hass.states.get("sensor.stein_bu_19_aktueller_einsatz").state == "THL Unwetter"
