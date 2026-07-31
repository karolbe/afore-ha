"""Config flow to configure the Afore integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow


from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlowWithConfigEntry

from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, LOGGER, CONF_REFRESH_TOKEN
from .afore import (
    AforeNoDataError,
    AforeAuthenticationError,
    AforeOutputAuthenticationError,
    AforeError,
    Afore,
)


async def validate_input(
    hass: HomeAssistant, *, access_token: str, refresh_token: str
) -> None:
    """Try using the given tokens against the Afore API."""
    session = async_get_clientsession(hass)

    # Minimal stand-in config entry for validation. It carries both tokens so the
    # client can authenticate; a fresh access token means no refresh is attempted.
    class DummyConfigEntryForValidation:
        def __init__(self, access: str, refresh: str):
            self.data = {
                CONF_ACCESS_TOKEN: access,
                CONF_REFRESH_TOKEN: refresh,
            }

    dummy_entry = DummyConfigEntryForValidation(access_token, refresh_token)

    afore_client = Afore(
        hass=hass,
        config_entry=dummy_entry,
        session=session,
    )
    await afore_client.system()


class AforeFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for Afore."""

    VERSION = 1

    imported_name: str | None = None
    reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            try:
                await validate_input(
                    self.hass,
                    access_token=user_input[CONF_ACCESS_TOKEN],
                    refresh_token=user_input[CONF_REFRESH_TOKEN],
                )
            except AforeOutputAuthenticationError:
                errors["base"] = "invalid_auth"
            except AforeAuthenticationError:
                errors["base"] = "invalid_auth"
            except AforeError:
                LOGGER.exception("Cannot connect to Afore")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(user_input[CONF_REFRESH_TOKEN]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Afore Inverter",
                    data={
                        CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                        CONF_REFRESH_TOKEN: user_input[CONF_REFRESH_TOKEN],
                    },
                )
        else:
            user_input = {}

        return self.async_show_form(
            step_id="user",
            description_placeholders={"account_url": "https://hom.aforenergy.com"},
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACCESS_TOKEN,
                        default=user_input.get(CONF_ACCESS_TOKEN, ""),
                    ): str,
                    vol.Required(
                        CONF_REFRESH_TOKEN,
                        default=user_input.get(CONF_REFRESH_TOKEN, ""),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle initiation of re-authentication with Afore."""
        self.reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for Afore."""
        return AforeOptionsFlowHandler(config_entry)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication with Afore.

        Only reached when the refresh token itself has expired (~every 6 months),
        so ask for a fresh access token AND refresh token from a new login.
        """
        errors = {}

        if user_input is not None and self.reauth_entry:
            try:
                await validate_input(
                    self.hass,
                    access_token=user_input[CONF_ACCESS_TOKEN],
                    refresh_token=user_input[CONF_REFRESH_TOKEN],
                )
            except AforeAuthenticationError:
                errors["base"] = "invalid_auth"
            except AforeError:
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    self.reauth_entry,
                    data={
                        **self.reauth_entry.data,
                        CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                        CONF_REFRESH_TOKEN: user_input[CONF_REFRESH_TOKEN],
                    },
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.reauth_entry.entry_id)
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"account_url": "https://hom.aforenergy.com"},
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): str,
                    vol.Required(CONF_REFRESH_TOKEN): str,
                }
            ),
            errors=errors,
        )


def _get_data_schema(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry | None = None
) -> vol.Schema:
    """Get a schema with default values."""
    defaults = config_entry.data if config_entry else {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ACCESS_TOKEN, default=defaults.get(CONF_ACCESS_TOKEN, "")
            ): str,
            vol.Required(
                CONF_REFRESH_TOKEN, default=defaults.get(CONF_REFRESH_TOKEN, "")
            ): str,
        }
    )


class AforeOptionsFlowHandler(OptionsFlowWithConfigEntry):
    """Options flow for Afore component."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure options for Afore."""

        if user_input is not None:
            # Update config entry with data from user input
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=user_input
            )
            return self.async_create_entry(
                title=self._config_entry.title, data=user_input
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_get_data_schema(self.hass, config_entry=self._config_entry),
        )
