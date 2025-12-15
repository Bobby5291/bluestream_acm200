from __future__ import annotations

import logging
from typing import Dict, List, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    DEFAULT_NUM_INPUTS,
    DEFAULT_NUM_OUTPUTS,
)
from . import ACM200Client, get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for each output (RX) of the ACM200."""

    domain_data = hass.data[DOMAIN]
    clients: Dict[str, ACM200Client] = domain_data.get("clients", {})
    client = clients.get(entry.entry_id)

    if client is None:
        _LOGGER.error("ACM200: no client found for entry %s", entry.entry_id)
        return

    num_inputs: int = entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS)
    num_outputs: int = entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS)

    entities: List[ACM200OutputSelect] = []
    for out_id in range(1, num_outputs + 1):
        entities.append(
            ACM200OutputSelect(
                client=client,
                entry=entry,
                output_id=out_id,
                num_inputs=num_inputs,
            )
        )

    async_add_entities(entities)


class ACM200OutputSelect(SelectEntity, RestoreEntity):
    """Select entity representing the source for a given output (RX)."""

    _attr_should_poll = False

    def __init__(
        self,
        client: ACM200Client,
        entry: ConfigEntry,
        output_id: int,
        num_inputs: int,
    ) -> None:
        self._client = client
        self._entry = entry
        self._output_id = output_id
        self._num_inputs = num_inputs

        dev_key = entry.unique_id or entry.entry_id

        self._attr_device_info = get_device_info(entry)
        self._attr_name = f"ACM200 Output {output_id:03d} Source"
        self._attr_unique_id = f"{dev_key}_output_{output_id:03d}_source"

        self._inputs: Dict[str, int] = {}
        options: List[str] = []
        for in_id in range(1, num_inputs + 1):
            label = f"Input {in_id}"
            options.append(label)
            self._inputs[label] = in_id

        self._attr_options = options
        self._attr_current_option: Optional[str] = None

    async def async_added_to_hass(self) -> None:
        """Restore previous state if available."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state in self._attr_options:
                self._attr_current_option = last_state.state
                _LOGGER.debug(
                    "ACM200: restored %s to %s",
                    self._attr_unique_id,
                    self._attr_current_option,
                )

    @property
    def current_option(self) -> Optional[str]:
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        """Handle selection of a new input for this output."""

        if option not in self._inputs:
            _LOGGER.error("ACM200: unknown option %s for %s", option, self._attr_unique_id)
            return

        in_id = self._inputs[option]
        out_id = self._output_id

        _LOGGER.info(
            "ACM200: routing output %03d from %s (input %d)",
            out_id,
            option,
            in_id,
        )

        await self._client.switch_route(out_id, in_id)

        self._attr_current_option = option
        self.async_write_ha_state()
