from __future__ import annotations

import logging
from typing import Dict, List, Optional

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.components.media_player.const import MediaPlayerState
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
    """Set up media_player entities for each output (RX) of the ACM200."""

    domain_data = hass.data[DOMAIN]
    clients: Dict[str, ACM200Client] = domain_data.get("clients", {})
    client = clients.get(entry.entry_id)

    if client is None:
        _LOGGER.error("ACM200: no client found for entry %s", entry.entry_id)
        return

    num_inputs: int = entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS)
    num_outputs: int = entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS)

    entities: List[ACM200OutputMediaPlayer] = []
    for out_id in range(1, num_outputs + 1):
        entities.append(
            ACM200OutputMediaPlayer(
                client=client,
                entry=entry,
                output_id=out_id,
                num_inputs=num_inputs,
            )
        )

    async_add_entities(entities)


class ACM200OutputMediaPlayer(MediaPlayerEntity, RestoreEntity):
    """Media player-like entity representing a matrix output (RX)."""

    _attr_should_poll = False
    _attr_supported_features = MediaPlayerEntityFeature.SELECT_SOURCE

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
        self._attr_name = f"ACM200 Output {output_id:03d}"
        self._attr_unique_id = f"{dev_key}_output_{output_id:03d}_media_player"

        self._source_map: Dict[str, int] = {}
        self._source_list: List[str] = []
        for in_id in range(1, num_inputs + 1):
            label = f"Input {in_id}"
            self._source_list.append(label)
            self._source_map[label] = in_id

        self._current_source: Optional[str] = None
        self._attr_state = MediaPlayerState.ON  # treat outputs as always on

    async def async_added_to_hass(self) -> None:
        """Restore previous state if available."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            last_source = last_state.attributes.get("source")
            if isinstance(last_source, str) and last_source in self._source_map:
                self._current_source = last_source
                self._attr_state = MediaPlayerState.ON
                _LOGGER.debug(
                    "ACM200: restored media_player %s to %s",
                    self._attr_unique_id,
                    self._current_source,
                )

    @property
    def source(self) -> Optional[str]:
        return self._current_source

    @property
    def source_list(self) -> List[str]:
        return self._source_list

    async def async_select_source(self, source: str) -> None:
        """Switch this output to the given input."""

        if source not in self._source_map:
            _LOGGER.error("ACM200: unknown source %s for %s", source, self._attr_unique_id)
            return

        in_id = self._source_map[source]
        out_id = self._output_id

        _LOGGER.info(
            "ACM200: media_player routing output %03d from %s (input %d)",
            out_id,
            source,
            in_id,
        )

        await self._client.switch_route(out_id, in_id)

        self._current_source = source
        self._attr_state = MediaPlayerState.ON
        self.async_write_ha_state()
