from __future__ import annotations

import logging
from typing import Dict, List, Optional

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
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
    """Ensure sources are unique strings (HA expects a unique source list)."""
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

    entities: List[ACM200OutputMediaPlayer] = []
    for out_id in range(1, num_outputs + 1):
        entities.append(
            ACM200OutputMediaPlayer(
                client=client,
                entry=entry,
                output_id=out_id,
                num_inputs=num_inputs,
                input_names=input_names,
                output_names=output_names,
            )
        )

    async_add_entities(entities)


class ACM200OutputMediaPlayer(MediaPlayerEntity, RestoreEntity):
    """MediaPlayer entity representing an output (RX) with source selection."""

    _attr_should_poll = False
    _attr_supported_features = MediaPlayerEntityFeature.SELECT_SOURCE

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
        self._attr_name = out_friendly if out_friendly else f"ACM200 Output {output_id:03d}"
        self._attr_unique_id = f"{dev_key}_output_{output_id:03d}"
        self._attr_icon = "mdi:television"

        raw_labels: List[str] = []
        for in_id in range(1, num_inputs + 1):
            friendly = (input_names.get(str(in_id)) or "").strip()
            raw_labels.append(friendly if friendly else f"Input {in_id}")

        self._sources = _make_unique_labels(raw_labels)

        # map source label -> input id
        self._source_to_input: Dict[str, int] = {label: idx for idx, label in enumerate(self._sources, start=1)}

        self._current_source: Optional[str] = None

    async def async_added_to_hass(self) -> None:
        last_state = await self.async_get_last_state()
        if last_state is not None:
            src = last_state.attributes.get("source")
            if src in self._sources:
                self._current_source = src

    @property
    def source(self) -> Optional[str]:
        return self._current_source

    @property
    def source_list(self) -> List[str]:
        return self._sources

    async def async_select_source(self, source: str) -> None:
        if source not in self._source_to_input:
            _LOGGER.error("ACM200: unknown source %s for %s", source, self.entity_id)
            return

        in_id = self._source_to_input[source]
        out_id = self._output_id

        _LOGGER.info("ACM200: media_player routing output %03d to input %d (%s)", out_id, in_id, source)
        await self._client.switch_route(out_id, in_id)

        self._current_source = source
        self.async_write_ha_state()

