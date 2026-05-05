from __future__ import annotations

import asyncio
import logging
from ipaddress import ip_address
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .client import ACM200Client
from .const import (
    CONF_INPUT_NAMES,
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    CONF_OUTPUT_NAMES,
    CONF_POLL_INTERVAL,
    DEFAULT_NUM_INPUTS,
    DEFAULT_NUM_OUTPUTS,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    MDNS_NAME_FRAGMENT,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Blustream ACM200 config flow — supports both manual and mDNS discovery."""

    VERSION = 1

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._auto_input_names: Dict[str, str] = {}
        self._auto_output_names: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # mDNS / zeroconf discovery entry-point
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> config_entries.FlowResult:
        """Handle a device discovered via mDNS."""
        host = str(discovery_info.host)
        port = discovery_info.port or DEFAULT_PORT
        name = discovery_info.name or ""

        # Only accept entries that look like an ACM200
        if MDNS_NAME_FRAGMENT not in name.lower():
            return self.async_abort(reason="not_acm200")

        _LOGGER.debug("ACM200: mDNS discovery → host=%s port=%d name=%s", host, port, name)

        await self.async_set_unique_id(f"{host}:{port}")
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        self._discovered_host = host
        self._discovered_port = port
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Ask the user to confirm a discovered device before querying it."""
        if user_input is not None:
            return await self._async_probe_and_advance(
                self._discovered_host,  # type: ignore[arg-type]
                self._discovered_port,
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "host": self._discovered_host,
                "port": str(self._discovered_port),
            },
        )

    # ------------------------------------------------------------------
    # Manual entry-point
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            client = ACM200Client(host=host, port=port)
            reachable = await client.async_test_connection()
            if not reachable:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_probe_and_advance(host, port)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_NUM_INPUTS, default=DEFAULT_NUM_INPUTS): int,
                vol.Optional(CONF_NUM_OUTPUTS, default=DEFAULT_NUM_OUTPUTS): int,
                vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ------------------------------------------------------------------
    # Internal: probe device then go to names step
    # ------------------------------------------------------------------

    async def _async_probe_and_advance(
        self, host: str, port: int
    ) -> config_entries.FlowResult:
        """Connect to the device, auto-discover its matrix size and names."""
        client = ACM200Client(host=host, port=port)

        # Try to discover real matrix dimensions
        try:
            num_inputs, num_outputs = await asyncio.wait_for(
                client.discover_matrix_size(), timeout=30
            )
            if not num_inputs:
                num_inputs = DEFAULT_NUM_INPUTS
            if not num_outputs:
                num_outputs = DEFAULT_NUM_OUTPUTS
        except Exception:
            num_inputs, num_outputs = DEFAULT_NUM_INPUTS, DEFAULT_NUM_OUTPUTS

        # Try to pull friendly names from the device
        try:
            raw_in = await asyncio.wait_for(
                client.discover_input_names(num_inputs), timeout=30
            )
            self._auto_input_names = {str(k): v for k, v in raw_in.items()}
        except Exception:
            self._auto_input_names = {}

        try:
            raw_out = await asyncio.wait_for(
                client.discover_output_names(num_outputs), timeout=30
            )
            self._auto_output_names = {str(k): v for k, v in raw_out.items()}
        except Exception:
            self._auto_output_names = {}

        self._config = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_NUM_INPUTS: num_inputs,
            CONF_NUM_OUTPUTS: num_outputs,
            CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
        }
        return await self.async_step_names()

    # ------------------------------------------------------------------
    # Names step — pre-populated with auto-discovered names
    # ------------------------------------------------------------------

    async def async_step_names(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        num_inputs = int(self._config.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS))
        num_outputs = int(self._config.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))

        if user_input is not None:
            input_names: Dict[str, str] = {}
            output_names: Dict[str, str] = {}

            for i in range(1, num_inputs + 1):
                v = (user_input.get(f"in_{i}") or "").strip()
                if v:
                    input_names[str(i)] = v

            for o in range(1, num_outputs + 1):
                v = (user_input.get(f"out_{o}") or "").strip()
                if v:
                    output_names[str(o)] = v

            return self.async_create_entry(
                title=f"ACM200 ({self._config[CONF_HOST]})",
                data=self._config,
                options={
                    CONF_INPUT_NAMES: input_names,
                    CONF_OUTPUT_NAMES: output_names,
                },
            )

        fields: Dict[Any, Any] = {}
        for i in range(1, num_inputs + 1):
            default = self._auto_input_names.get(str(i), "")
            fields[vol.Optional(f"in_{i}", default=default)] = str
        for o in range(1, num_outputs + 1):
            default = self._auto_output_names.get(str(o), "")
            fields[vol.Optional(f"out_{o}", default=default)] = str

        return self.async_show_form(step_id="names", data_schema=vol.Schema(fields))

    # ------------------------------------------------------------------
    # Options flow
    # ------------------------------------------------------------------

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow — rename inputs/outputs and adjust poll interval."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        num_inputs = int(self._entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS))
        num_outputs = int(self._entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))

        existing_inputs = dict(self._entry.options.get(CONF_INPUT_NAMES, {}))
        existing_outputs = dict(self._entry.options.get(CONF_OUTPUT_NAMES, {}))

        if user_input is not None:
            input_names: Dict[str, str] = {}
            output_names: Dict[str, str] = {}

            for i in range(1, num_inputs + 1):
                v = (user_input.get(f"in_{i}") or "").strip()
                if v:
                    input_names[str(i)] = v

            for o in range(1, num_outputs + 1):
                v = (user_input.get(f"out_{o}") or "").strip()
                if v:
                    output_names[str(o)] = v

            return self.async_create_entry(
                title="",
                data={
                    CONF_INPUT_NAMES: input_names,
                    CONF_OUTPUT_NAMES: output_names,
                },
            )

        fields: Dict[Any, Any] = {}
        for i in range(1, num_inputs + 1):
            fields[vol.Optional(f"in_{i}", default=existing_inputs.get(str(i), ""))] = str
        for o in range(1, num_outputs + 1):
            fields[vol.Optional(f"out_{o}", default=existing_outputs.get(str(o), ""))] = str

        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
