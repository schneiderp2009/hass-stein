"""Webhook receiver for STEIN push notifications.

STEIN can call a URL per Ortsverband (BU fields ``webhookUrl`` /
``webhookSecret``). Which events and which payload STEIN sends is not
documented, so this receiver accepts any JSON, keeps the last payload for
inspection, fires the HA event ``stein_webhook`` and refreshes the data.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_STEIN_WEBHOOK
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)

_MAX_BODY = 64 * 1024


def webhook_url(hass: HomeAssistant, webhook_id: str) -> str | None:
    """External URL STEIN should call (None if HA has no URL configured)."""
    try:
        return webhook.async_generate_url(hass, webhook_id, prefer_external=True)
    except Exception:  # noqa: BLE001 – no external/internal URL configured
        return None


def async_setup_webhook(
    hass: HomeAssistant, coordinator: SteinCoordinator, webhook_id: str
) -> None:
    """Register the STEIN webhook for this config entry."""

    async def handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        raw = await request.content.read(_MAX_BODY)
        text = raw.decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(text) if text else None
        except ValueError:
            payload = text

        header_names = sorted(
            h for h in request.headers if h.lower() not in ("authorization", "cookie")
        )
        _LOGGER.info(
            "STEIN webhook empfangen (Header: %s): %s", ", ".join(header_names), text[:2000]
        )

        coordinator.last_webhook = {
            "received": dt_util.utcnow().isoformat(),
            "headers": header_names,
            # Keep state attributes small (recorder limit ~16 KB)
            "payload": payload if len(text) <= 8000 else text[:8000] + " …",
        }
        coordinator.async_update_listeners()
        hass.bus.async_fire(
            EVENT_STEIN_WEBHOOK, {"payload": payload, "headers": header_names}
        )
        await coordinator.async_request_refresh()
        return web.Response(status=200, text="OK")

    webhook.async_register(
        hass,
        DOMAIN,
        "STEIN",
        webhook_id,
        handle_webhook,
        local_only=False,
        allowed_methods=["POST", "PUT"],
    )
    _LOGGER.info("STEIN webhook registriert: %s", webhook_url(hass, webhook_id) or webhook_id)


def async_teardown_webhook(hass: HomeAssistant, webhook_id: str) -> None:
    webhook.async_unregister(hass, webhook_id)
