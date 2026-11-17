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


async def test_coordinator_passes_bu_ids(hass: HomeAssistant):
    api = _api([make_report()])
    coord = SteinCoordinator(hass, api, [19], 300)
    await coord._fetch_reports()

    args = api.get_reports.await_args.args
    assert args[0] == [19]
    assert isinstance(args[1], int)
    assert coord.current_report(19)["id"] == 1


async def test_coordinator_falls_back_without_updated_since(hass: HomeAssistant):
    api = _api()
    api.get_reports.side_effect = [
        SteinApiError("HTTP 400: bad updatedSince", status=400),
        [make_report()],
        [make_report()],
    ]
    coord = SteinCoordinator(hass, api, [19], 300)
    await coord._fetch_reports()
    assert api.get_reports.await_args_list[1].args == ([19], None)
    assert 1 in coord.reports

    await coord._fetch_reports()
    assert api.get_reports.await_args_list[2].args == ([19], None)


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
