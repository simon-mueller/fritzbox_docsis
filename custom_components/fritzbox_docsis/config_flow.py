"""Config flow for the FRITZ!Box DOCSIS integration."""

from __future__ import annotations

from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DEFAULT_URL, DOMAIN
from .coordinator import FritzBoxApi, FritzBoxApiError, FritzBoxAuthError


class FritzBoxDocsisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration through the Home Assistant UI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Validate and store FRITZ!Box connection details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            try:
                parsed_url = urlsplit(url)
                parsed_url.port
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                invalid_url = (
                    parsed_url.scheme not in ("http", "https")
                    or not parsed_url.hostname
                    or parsed_url.username is not None
                    or parsed_url.password is not None
                    or bool(parsed_url.query or parsed_url.fragment)
                )
                if invalid_url:
                    errors["base"] = "invalid_url"
                else:
                    user_input[CONF_URL] = url
                    await self.async_set_unique_id(url.casefold())
                    self._abort_if_unique_id_configured()
                    api = FritzBoxApi(
                        async_get_clientsession(self.hass),
                        url,
                        user_input[CONF_USERNAME],
                        user_input[CONF_PASSWORD],
                    )
                    try:
                        await api.async_get_channels()
                    except FritzBoxAuthError:
                        errors["base"] = "invalid_auth"
                    except FritzBoxApiError:
                        errors["base"] = "cannot_connect"
                    else:
                        return self.async_create_entry(
                            title=parsed_url.hostname,
                            data=user_input,
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=DEFAULT_URL): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )