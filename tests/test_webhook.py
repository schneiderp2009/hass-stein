"""Webhook receiver test (mocked STEIN API, real HA webhook component)."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.stein.const import (
    CONF_API_TOKEN,
    CONF_BU_IDS,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_STEIN_WEBHOOK,
)


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("custom_components.stein.coordinator.asyncio.sleep", new=AsyncMock()):
        yield


async def test_webhook_receives_payload(hass: HomeAssistant, hass_client_no_auth):
    await async_setup_component(hass, "http", {})
    api = AsyncMock()
    api.get_assets.return_value = []
    api.get_bu.return_value = {"id": 19, "name": "OV"}
    api.get_userinfo.return_value = {"name": "HA", "scope": "bu_a_19"}
    api.get_reports.return_value = []

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_TOKEN: "t", CONF_BU_IDS: [19]})
    entry.add_to_hass(hass)
    with patch("custom_components.stein.SteinApi", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    webhook_id = entry.data[CONF_WEBHOOK_ID]
    assert len(webhook_id) == 32
    assert hass.states.get("sensor.stein_webhook").state == "Noch keiner"

    events = async_capture_events(hass, EVENT_STEIN_WEBHOOK)
    client = await hass_client_no_auth()
    resp = await client.post(
        f"/api/webhook/{webhook_id}",
        json={"type": "asset", "id": 340, "status": "inuse"},
        headers={"X-Secret": "abc"},
    )
    assert resp.status == 200
    await hass.async_block_till_done()

    state = hass.states.get("sensor.stein_webhook")
    assert state.state != "Noch keiner"
    assert state.attributes["payload"] == {"type": "asset", "id": 340, "status": "inuse"}
    assert "X-Secret" in state.attributes["header"]
    assert events and events[0].data["payload"]["status"] == "inuse"

    # Webhook-ID bleibt nach Neuladen gleich
    with patch("custom_components.stein.SteinApi", return_value=api):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.data[CONF_WEBHOOK_ID] == webhook_id
