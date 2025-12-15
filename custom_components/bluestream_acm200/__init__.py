from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .client import ACM200Client
from .coordinator import ACM200Coordinator
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_NUM_OUTPUTS,
    CONF_POLL_INTERVAL,
    DEFAULT_NUM_OUTPUTS,
    DEFAULT_POLL_INTERVAL,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


def _entry_device_key(entry: ConfigEntry) -> str:
    """Stable-ish device key for registry identifiers."""
    return entry.unique_id or entry.entry_id


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return DeviceInfo for this config entry."""
    host = entry.data.get(CONF_HOST, "unknown")
    dev_key = _entry_device_key(entry)
    return DeviceInfo(
        identifiers={(DOMAIN, dev_key)},
        name=f"Blustream ACM200 ({host})",
        manufacturer="Blustream",
        model="ACM200",
        configuration_url="https://www.blustream.co.uk/",
    )


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the integration (YAML not used, but keep for completeness)."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("clients", {})
    hass.data[DOMAIN].setdefault("coordinators", {})
    hass.data[DOMAIN].setdefault("service_registered", False)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    domain_data = hass.data[DOMAIN]
    domain_data.setdefault("clients", {})
    domain_data.setdefault("coordinators", {})
    domain_data.setdefault("service_registered", False)

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    # Register device
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, _entry_device_key(entry))},
        name=f"Blustream ACM200 ({host})",
        manufacturer="Blustream",
        model="ACM200",
        configuration_url="https://www.blustream.co.uk/",
    )

    client = ACM200Client(host=host, port=port)
    domain_data["clients"][entry.entry_id] = client

    # Coordinator (used by sensor platform)
    num_outputs = int(entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))
    poll_interval = int(entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
    coordinator = ACM200Coordinator(
        hass,
        client=client,
        num_outputs=num_outputs,
        poll_interval=poll_interval,
    )
    domain_data["coordinators"][entry.entry_id] = coordinator
    await coordinator.async_config_entry_first_refresh()

    # Service to switch a route
    async def _handle_switch_route(call: ServiceCall) -> None:
        out_id = int(call.data["output_id"])
        in_id = int(call.data["input_id"])
        _LOGGER.info("ACM200: service switch_route output=%s input=%s", out_id, in_id)
        await client.switch_route(out_id, in_id)

    if not domain_data.get("service_registered"):
        hass.services.async_register(
            DOMAIN,
            "switch_route",
            _handle_switch_route,
            schema=None,
        )
        domain_data["service_registered"] = True
        _LOGGER.info("ACM200: registered service %s.switch_route", DOMAIN)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    domain_data = hass.data.get(DOMAIN, {})
    clients = domain_data.get("clients", {})
    coordinators = domain_data.get("coordinators", {})

    clients.pop(entry.entry_id, None)
    coordinators.pop(entry.entry_id, None)

    if unload_ok and not clients and domain_data.get("service_registered"):
        hass.services.async_remove(DOMAIN, "switch_route")
        domain_data["service_registered"] = False
        _LOGGER.info("ACM200: removed service %s.switch_route", DOMAIN)

    if unload_ok and not clients:
        hass.data.pop(DOMAIN, None)

    return unload_ok
