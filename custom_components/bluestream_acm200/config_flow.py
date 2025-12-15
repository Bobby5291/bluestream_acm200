from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    DEFAULT_NUM_INPUTS,
    DEFAULT_NUM_OUTPUTS,
)


class ACM200ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Blustream ACM200."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial step where the user enters host/port/counts."""
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))

            # Make the config entry uniquely identifiable in HA, so device registry works properly.
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            title = f"ACM200 ({host})"
            return self.async_create_entry(
                title=title,
                data={**user_input, CONF_HOST: host, CONF_PORT: port},
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                vol.Optional(CONF_NUM_INPUTS, default=DEFAULT_NUM_INPUTS): vol.Coerce(int),
                vol.Optional(CONF_NUM_OUTPUTS, default=DEFAULT_NUM_OUTPUTS): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors={},
        )
