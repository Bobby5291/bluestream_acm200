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
    CONF_HOST,
    CONF_NUM_OUTPUTS,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    DEFAULT_NUM_OUTPUTS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


def _entry_device_key(entry: ConfigEntry) -> str:
    return entry.unique_id or entry.entry_id


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
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
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("clients", {})
    hass.data[DOMAIN].setdefault("coordinators", {})
    hass.data[DOMAIN].setdefault("service_registered", False)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    domain_data = hass.data[DOMAIN]
    domain_data.setdefault("clients", {})
    domain_data.setdefault("coordinators", {})
    domain_data.setdefault("service_registered", False)

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

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

    async def _handle_switch_route(call: ServiceCall) -> None:
        # Support both "output_id" (legacy) and "output" field names
        out_id = int(call.data.get("output_id") or call.data["output"])
        in_id = int(call.data.get("input_id") or call.data["input"])
        target_entry_id: str | None = call.data.get("entry_id")

        if target_entry_id:
            target_client = domain_data["clients"].get(target_entry_id)
            if not target_client:
                _LOGGER.error("ACM200: no client for entry_id %s", target_entry_id)
                return
        else:
            target_client = client  # default to this entry's client

        _LOGGER.info(
            "ACM200: service switch_route output=%s input=%s", out_id, in_id
        )
        await target_client.switch_route(out_id, in_id)

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
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    domain_data = hass.data.get(DOMAIN, {})
    clients = domain_data.get("clients", {})
    coordinators = domain_data.get("coordinators", {})

    clients.pop(entry.entry_id, None)
    coordinators.pop(entry.entry_id, None)

    if unload_ok and not clients and domain_data.get("service_registered"):
        hass.services.async_remove(DOMAIN, "switch_route")
        domain_data["service_registered"] = False

    if unload_ok and not clients:
        hass.data.pop(DOMAIN, None)

    return unload_ok
