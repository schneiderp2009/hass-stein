"""Config flow for STEIN integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SteinApi, SteinAuthError, SteinApiError
from .const import DOMAIN, CONF_API_TOKEN, CONF_BU_IDS, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


def _parse_bu_ids(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


class SteinConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for STEIN."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            bu_ids_raw = user_input[CONF_BU_IDS].strip()

            try:
                bu_ids = _parse_bu_ids(bu_ids_raw)
                if not bu_ids:
                    raise ValueError("No valid BU IDs")
            except ValueError:
                errors[CONF_BU_IDS] = "invalid_bu_ids"
            else:
                session = async_get_clientsession(self.hass)
                api = SteinApi(token, session)
                try:
                    valid = await api.test_connection()
                    if not valid:
                        errors["base"] = "cannot_connect"
                except SteinAuthError:
                    errors["base"] = "invalid_auth"
                except SteinApiError as err:
                    _LOGGER.error("STEIN setup connection error: %s", err)
                    errors["base"] = "cannot_connect"
                except Exception as err:
                    _LOGGER.exception("Unexpected error during STEIN setup: %s", err)
                    errors["base"] = "unknown"

                if not errors:
                    await self.async_set_unique_id(f"stein_{token[:8]}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="STEIN",
                        data={
                            CONF_API_TOKEN: token,
                            CONF_BU_IDS: bu_ids,
                            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_TOKEN): str,
                vol.Required(CONF_BU_IDS): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return SteinOptionsFlow(config_entry)


class SteinOptionsFlow(config_entries.OptionsFlow):
    """Options flow – only scan interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL,
                        self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ),
                ): vol.All(int, vol.Range(min=120)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
