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
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    CONF_INPUT_NAMES,
    CONF_OUTPUT_NAMES,
)


class ACM200ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Blustream ACM200."""

    VERSION = 1

    def __init__(self) -> None:
        self._config: dict = {}

    async def async_step_user(self, user_input: dict | None = None):
        """Initial setup step: connection + matrix size."""
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            num_inputs = int(user_input.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS))
            num_outputs = int(user_input.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))
            poll_interval = int(user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            self._config = {
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_NUM_INPUTS: num_inputs,
                CONF_NUM_OUTPUTS: num_outputs,
                CONF_POLL_INTERVAL: poll_interval,
            }

            return await self.async_step_names()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_NUM_INPUTS, default=DEFAULT_NUM_INPUTS): int,
                vol.Optional(CONF_NUM_OUTPUTS, default=DEFAULT_NUM_OUTPUTS): int,
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_names(self, user_input: dict | None = None):
        """Allow the user to name each input and output (optional)."""
        num_inputs = int(self._config.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS))
        num_outputs = int(self._config.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))

        if user_input is not None:
            input_names: dict[str, str] = {}
            output_names: dict[str, str] = {}

            for in_id in range(1, num_inputs + 1):
                key = f"in_{in_id}"
                val = (user_input.get(key) or "").strip()
                if val:
                    input_names[str(in_id)] = val

            for out_id in range(1, num_outputs + 1):
                key = f"out_{out_id}"
                val = (user_input.get(key) or "").strip()
                if val:
                    output_names[str(out_id)] = val

            # Store friendly names in options so they can be edited later via Options
            return self.async_create_entry(
                title=f"ACM200 ({self._config[CONF_HOST]})",
                data=self._config,
                options={
                    CONF_INPUT_NAMES: input_names,
                    CONF_OUTPUT_NAMES: output_names,
                },
            )

        schema_dict: dict = {}

        # Inputs
        for in_id in range(1, num_inputs + 1):
            schema_dict[vol.Optional(f"in_{in_id}", default="")] = str

        # Outputs
        for out_id in range(1, num_outputs + 1):
            schema_dict[vol.Optional(f"out_{out_id}", default="")] = str

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="names",
            data_schema=data_schema,
            description_placeholders={
                "inputs": str(num_inputs),
                "outputs": str(num_outputs),
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return ACM200OptionsFlowHandler(config_entry)


class ACM200OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Blustream ACM200 (renaming inputs/outputs)."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict | None = None):
        num_inputs = int(self._entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS))
        num_outputs = int(self._entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))

        existing_inputs: dict[str, str] = dict(self._entry.options.get(CONF_INPUT_NAMES, {}))
        existing_outputs: dict[str, str] = dict(self._entry.options.get(CONF_OUTPUT_NAMES, {}))

        if user_input is not None:
            input_names: dict[str, str] = {}
            output_names: dict[str, str] = {}

            for in_id in range(1, num_inputs + 1):
                key = f"in_{in_id}"
                val = (user_input.get(key) or "").strip()
                if val:
                    input_names[str(in_id)] = val

            for out_id in range(1, num_outputs + 1):
                key = f"out_{out_id}"
                val = (user_input.get(key) or "").strip()
                if val:
                    output_names[str(out_id)] = val

            return self.async_create_entry(
                title="",
                data={
                    CONF_INPUT_NAMES: input_names,
                    CONF_OUTPUT_NAMES: output_names,
                },
            )

        schema_dict: dict = {}

        for in_id in range(1, num_inputs + 1):
            schema_dict[
                vol.Optional(f"in_{in_id}", default=existing_inputs.get(str(in_id), ""))
            ] = str

        for out_id in range(1, num_outputs + 1):
            schema_dict[
                vol.Optional(f"out_{out_id}", default=existing_outputs.get(str(out_id), ""))
            ] = str

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(step_id="init", data_schema=data_schema)

