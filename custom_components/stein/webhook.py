"""Webhook handler for STEIN push updates."""
from __future__ import annotations

import logging
import hashlib
import hmac

from aiohttp import web
from homeassistant.components.webhook import async_register, async_unregister
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SteinCoordinator

_LOGGER = logging.getLogger(__name__)

WEBHOOK_ID = "stein_webhook"


async def async_setup_webhook(
    hass: HomeAssistant,
    coordinator: SteinCoordinator,
    webhook_secret: str | None = None,
) -> str:
    """Register webhook and return the webhook URL."""

    async def handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        # Validate secret if configured
        if webhook_secret:
            secret_header = request.headers.get("X-Secret", "")
            if secret_header != webhook_secret:
                _LOGGER.warning("STEIN webhook: invalid secret received")
                return web.Response(status=401)

        try:
            payload = await request.json()
        except Exception:
            _LOGGER.error("STEIN webhook: invalid JSON payload")
            return web.Response(status=400)

        _LOGGER.debug("STEIN webhook received: %s", payload)

        # Trigger a coordinator refresh so entities update immediately
        await coordinator.async_request_refresh()

        return web.Response(status=200, text="OK")

    async_register(
        hass,
        DOMAIN,
        "STEIN Webhook",
        WEBHOOK_ID,
        handle_webhook,
    )

    webhook_url = hass.components.webhook.async_generate_url(WEBHOOK_ID)
    _LOGGER.info("STEIN webhook registered at %s", webhook_url)
    return webhook_url


def async_teardown_webhook(hass: HomeAssistant) -> None:
    async_unregister(hass, WEBHOOK_ID)
