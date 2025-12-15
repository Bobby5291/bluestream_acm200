from __future__ import annotations

import logging
from typing import Dict, List, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .client import ACM200Client
from .const import (
    DOMAIN,
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    DEFAULT_NUM_INPUTS,
    DEFAULT_NUM_OUTPUTS,
    CONF_INPUT_NAMES,
    CONF_OUTPUT_NAMES,
)
from . import get_device_info

_LOGGER = logging.getLogger(__name__)


def _make_unique_labels(labels: List[str]) -> List[str]:
    """Ensure options are unique strings (HA Select requires unique options)."""
    seen: Dict[str, int] = {}
    out: List[str] = []
    for label in labels:
        if label not in seen:
            seen[label] = 1
            out.append(label)
        else:
            seen[label] += 1
            out.append(f"{label} ({seen[label]})")
    return out


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    domain_data = hass.data[DOMAIN]
    client: ACM200Client = domain_data["clients"][entry.entry_id]

    num_inputs: int = int(entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS))
    num_outputs: int = int(entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))

    input_names: Dict[str, str] = dict(entry.options.get(CONF_INPUT_NAMES, {}))
    output_names: Dict[str, str] = dict(entry.options.get(CONF_OUTPUT_NAMES, {}))

    entities: List[ACM200OutputSelect] = []
    for out_id in range(1, num_outputs + 1):
        entities.append(
            ACM200OutputSelect(
                client=client,
                entry=entry,
                output_id=out_id,
                num_inputs=num_inputs,
                input_names=input_names,
                output_names=output_names,
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
        input_names: Dict[str, str],
        output_names: Dict[str, str],
    ) -> None:
        self._client = client
        self._entry = entry
        self._output_id = output_id
        self._num_inputs = num_inputs

        dev_key = entry.unique_id or entry.entry_id
        self._attr_device_info = get_device_info(entry)

        out_friendly = (output_names.get(str(output_id)) or "").strip()
        if out_friendly:
            self._attr_name = f"{out_friendly} Source"
        else:
            self._attr_name = f"ACM200 Output {output_id:03d} Source"

        self._attr_unique_id = f"{dev_key}_output_{output_id:03d}_source"
        self._attr_icon = "mdi:video-input-hdmi"

        # Build options labels from input names
        raw_labels: List[str] = []
        self._inputs: Dict[str, int] = {}

        for in_id in range(1, num_inputs + 1):
            friendly = (input_names.get(str(in_id)) or "").strip()
            label = friendly if friendly else f"Input {in_id}"
            raw_labels.append(label)

        # Ensure uniqueness (in case two inputs were given the same friendly name)
        labels = _make_unique_labels(raw_labels)

        # Map label -> input id (preserving order)
        for idx, label in enumerate(labels, start=1):
            self._inputs[label] = idx

        self._attr_options = labels
        self._attr_current_option: Optional[str] = None

    async def async_added_to_hass(self) -> None:
        last_state = await self.async_get_last_state()
        if last_state is not None:
            if last_state.state in self._attr_options:
                self._attr_current_option = last_state.state
                _LOGGER.debug(
                    "ACM200: restored %s to option %s",
                    self._attr_unique_id,
                    self._attr_current_option,
                )

    @property
    def current_option(self) -> Optional[str]:
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
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
