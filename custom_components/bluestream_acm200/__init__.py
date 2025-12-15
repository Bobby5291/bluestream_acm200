from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)


def _entry_device_key(entry: ConfigEntry) -> str:
    """Return a stable-ish key for this device."""
    # Prefer unique_id (set in config_flow). Fall back to entry_id.
    return entry.unique_id or entry.entry_id


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
    """DeviceInfo used by entities so they appear under the integration."""
    dev_key = _entry_device_key(entry)
    return DeviceInfo(
        identifiers={(DOMAIN, dev_key)},
        name=f"Blustream ACM200 ({dev_key})",
        manufacturer="Blustream",
        model="ACM200",
        configuration_url="https://www.blustream.co.uk/",
    )


@dataclass
class ACM200Connection:
    host: str
    port: int = DEFAULT_PORT


class ACM200Client:
    """Simple TCP client for Blustream ACM200 ASCII command interface."""

    def __init__(self, conn: ACM200Connection) -> None:
        self._conn = conn

    async def _send_command(self, command: str) -> None:
        """Send a single command and (optionally) read a single response line."""
        host = self._conn.host
        port = self._conn.port

        _LOGGER.debug("ACM200: connecting to %s:%s", host, port)
        reader: asyncio.StreamReader
        writer: asyncio.StreamWriter

        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError as err:
            _LOGGER.error("ACM200: connection to %s:%s failed: %s", host, port, err)
            raise

        try:
            payload = (command + "\r\n").encode("ascii")
            writer.write(payload)
            await writer.drain()
            _LOGGER.debug("ACM200: sent: %s", command)

            # Optional: read one line back (device may or may not reply).
            try:
                reply = await asyncio.wait_for(reader.readline(), timeout=0.5)
                if reply:
                    _LOGGER.debug("ACM200: reply: %r", reply)
            except asyncio.TimeoutError:
                _LOGGER.debug("ACM200: no reply received (timeout)")
        finally:
            writer.close()
            await writer.wait_closed()
            _LOGGER.debug("ACM200: connection closed")

    async def switch_route(self, output: int, input_: int) -> None:
        """Switch output receiver (RX) to take signal from input transmitter (TX)."""
        if output < 1 or input_ < 1:
            raise ValueError("Input and output IDs must be >= 1")

        # Command syntax: OUT ooo FR yyy  -> here without spaces
        command = f"OUT{output:03d}FR{input_:03d}"
        await self._send_command(command)

    async def get_output_status(self, output: int) -> dict | None:
        """Placeholder for future status parsing."""
        _LOGGER.debug("ACM200: get_output_status not implemented for output %s", output)
        return None


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the integration (YAML not used, but required entrypoint)."""
    hass.data.setdefault(DOMAIN, {"clients": {}, "service_registered": False})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Blustream ACM200 from a config entry."""
    hass.data.setdefault(DOMAIN, {"clients": {}, "service_registered": False})
    domain_data = hass.data[DOMAIN]

    host = entry.data.get(CONF_HOST)
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    if not host:
        _LOGGER.error("ACM200: missing host in config entry %s", entry.entry_id)
        return False

    # 1) Register a device for the config entry (so entities attach under Integrations).
    dev_reg = dr.async_get(hass)
    dev_key = _entry_device_key(entry)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, dev_key)},
        name=f"Blustream ACM200 ({host})",
        manufacturer="Blustream",
        model="ACM200",
        configuration_url="https://www.blustream.co.uk/",
    )

    # 2) Create and store client
    conn = ACM200Connection(host=str(host), port=int(port))
    client = ACM200Client(conn)

    clients: Dict[str, ACM200Client] = domain_data.setdefault("clients", {})
    clients[entry.entry_id] = client
    _LOGGER.info("ACM200: created client for %s:%s (entry %s)", host, port, entry.entry_id)

    # 3) Register service once
    if not domain_data.get("service_registered", False):

        async def handle_switch_route(call: ServiceCall) -> None:
            """Service: bluestream_acm200.switch_route"""
            output = int(call.data["output"])
            input_ = int(call.data["input"])

            # If service called without specifying entry_id, pick the first configured client.
            entry_id = call.data.get("entry_id")
            if entry_id:
                svc_client = clients.get(str(entry_id))
            else:
                svc_client = next(iter(clients.values()), None)

            if svc_client is None:
                _LOGGER.error("ACM200: no clients available to service switch_route")
                return

            await svc_client.switch_route(output, input_)

        hass.services.async_register(DOMAIN, "switch_route", handle_switch_route)
        domain_data["service_registered"] = True
        _LOGGER.info("ACM200: registered service %s.switch_route", DOMAIN)

    # 4) Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["select", "media_player"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["select", "media_player"])

    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return unload_ok

    clients: Dict[str, ACM200Client] = domain_data.get("clients", {})
    clients.pop(entry.entry_id, None)

    _LOGGER.info("ACM200: removed client for entry %s", entry.entry_id)

    if not clients and domain_data.get("service_registered"):
        hass.services.async_remove(DOMAIN, "switch_route")
        domain_data["service_registered"] = False
        _LOGGER.info("ACM200: removed service %s.switch_route", DOMAIN)

    return unload_ok
