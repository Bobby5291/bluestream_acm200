from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Tuple

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_HOST, CONF_PORT

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

# Hard cap for discovery probing so the UI never hangs more than ~15 s
_MAX_PROBE = 16
# Total timeout for the entire discovery probe
_DISCOVER_TIMEOUT = 20.0


async def _probe_device(
    host: str, port: int
) -> Tuple[int, int, Dict[str, str], Dict[str, str]]:
    """
    Connect once, probe inputs/outputs in a single efficient pass.

    Returns (num_inputs, num_outputs, input_names, output_names).
    Falls back to defaults if anything fails — never raises.
    """
    client = ACM200Client(host=host, port=port)

    # ---- Step 1: discover how many inputs / outputs exist ----
    # Probe IN and OUT concurrently up to _MAX_PROBE each
    async def probe_direction(direction: str) -> int:
        count = 0
        for idx in range(1, _MAX_PROBE + 1):
            try:
                resp = await client._send_command(
                    f"{direction} {idx:03d} STATUS", timeout=2.0
                )
                if "[ERROR]" in resp or not resp.strip():
                    break
                count = idx
            except Exception:
                break
        return count

    try:
        num_in, num_out = await asyncio.wait_for(
            asyncio.gather(probe_direction("IN"), probe_direction("OUT")),
            timeout=_DISCOVER_TIMEOUT,
        )
    except Exception:
        num_in, num_out = 0, 0

    if not num_in:
        num_in = DEFAULT_NUM_INPUTS
    if not num_out:
        num_out = DEFAULT_NUM_OUTPUTS

    # ---- Step 2: fetch names for discovered inputs/outputs ----
    # Re-use the status responses we already need to fetch anyway
    from .client import _parse_name  # local import avoids circular at module level

    async def fetch_names(direction: str, count: int) -> Dict[str, str]:
        names: Dict[str, str] = {}
        for idx in range(1, count + 1):
            try:
                cmd = f"{direction} {idx:03d} STATUS"
                resp = await client._send_command(cmd, timeout=2.0)
                name = _parse_name(resp)
                if name:
                    names[str(idx)] = name
            except Exception:
                pass
        return names

    try:
        input_names, output_names = await asyncio.wait_for(
            asyncio.gather(
                fetch_names("IN", num_in),
                fetch_names("OUT", num_out),
            ),
            timeout=_DISCOVER_TIMEOUT,
        )
    except Exception:
        input_names, output_names = {}, {}

    return num_in, num_out, input_names, output_names


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Blustream ACM200 config flow — supports both manual entry and mDNS discovery."""

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
        host = str(discovery_info.host)
        port = discovery_info.port or DEFAULT_PORT
        name = discovery_info.name or ""

        if MDNS_NAME_FRAGMENT not in name.lower():
            return self.async_abort(reason="not_acm200")

        await self.async_set_unique_id(f"{host}:{port}")
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        self._discovered_host = host
        self._discovered_port = port
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return await self._probe_and_advance(
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

            # Quick reachability check before committing to a long probe
            client = ACM200Client(host=host, port=port)
            reachable = await client.async_test_connection()
            if not reachable:
                errors["base"] = "cannot_connect"
            else:
                return await self._probe_and_advance(host, port)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Probe then show names step
    # ------------------------------------------------------------------

    async def _probe_and_advance(self, host: str, port: int) -> config_entries.FlowResult:
        num_in, num_out, in_names, out_names = await _probe_device(host, port)

        self._config = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_NUM_INPUTS: num_in,
            CONF_NUM_OUTPUTS: num_out,
            CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
        }
        self._auto_input_names = in_names
        self._auto_output_names = out_names

        _LOGGER.debug(
            "ACM200 probe: %d inputs, %d outputs — in_names=%s out_names=%s",
            num_in, num_out, in_names, out_names,
        )
        return await self.async_step_names()

    # ------------------------------------------------------------------
    # Names confirmation step
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
            fields[vol.Optional(f"in_{i}", default=self._auto_input_names.get(str(i), ""))] = str
        for o in range(1, num_outputs + 1):
            fields[vol.Optional(f"out_{o}", default=self._auto_output_names.get(str(o), ""))] = str

        return self.async_show_form(step_id="names", data_schema=vol.Schema(fields))

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow — rename inputs/outputs."""

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
                data={CONF_INPUT_NAMES: input_names, CONF_OUTPUT_NAMES: output_names},
            )

        fields: Dict[Any, Any] = {}
        for i in range(1, num_inputs + 1):
            fields[vol.Optional(f"in_{i}", default=existing_inputs.get(str(i), ""))] = str
        for o in range(1, num_outputs + 1):
            fields[vol.Optional(f"out_{o}", default=existing_outputs.get(str(o), ""))] = str

        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
