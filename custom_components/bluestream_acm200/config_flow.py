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
    CONF_INPUT_NAMES,
)


class ACM200ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Blustream ACM200."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial step where the user enters host/port/counts."""
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))

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

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow handler."""
        return ACM200OptionsFlowHandler(config_entry)


class ACM200OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for ACM200 (e.g. friendly input names)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        """Manage the options."""
        num_inputs: int = self._entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS)

        # Existing saved names: {"1": "Apple TV", "2": "Sky Q", ...}
        existing: dict = dict(self._entry.options.get(CONF_INPUT_NAMES, {}))

        if user_input is not None:
            new_names: dict[str, str] = {}

            for in_id in range(1, num_inputs + 1):
                key = f"input_{in_id}_name"
                raw = str(user_input.get(key, "")).strip()
                if raw:
                    new_names[str(in_id)] = raw

            return self.async_create_entry(
                title="",
                data={CONF_INPUT_NAMES: new_names},
            )

        # Build a dynamic form with one field per input
        schema_fields = {}
        for in_id in range(1, num_inputs + 1):
            default = existing.get(str(in_id), "")
            schema_fields[vol.Optional(f"input_{in_id}_name", default=default)] = str

        data_schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )
