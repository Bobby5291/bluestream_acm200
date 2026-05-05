from __future__ import annotations

import logging
from typing import Dict, List, Optional

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import ACM200Client
from .const import (
    CONF_INPUT_NAMES,
    CONF_NUM_INPUTS,
    CONF_NUM_OUTPUTS,
    CONF_OUTPUT_NAMES,
    DEFAULT_NUM_INPUTS,
    DEFAULT_NUM_OUTPUTS,
    DOMAIN,
)
from .coordinator import ACM200Coordinator, ACM200Data
from . import get_device_info

_LOGGER = logging.getLogger(__name__)


def _make_unique_labels(labels: List[str]) -> List[str]:
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
    coordinator: ACM200Coordinator = domain_data["coordinators"][entry.entry_id]

    num_inputs: int = int(entry.data.get(CONF_NUM_INPUTS, DEFAULT_NUM_INPUTS))
    num_outputs: int = int(entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))

    input_names: Dict[str, str] = dict(entry.options.get(CONF_INPUT_NAMES, {}))
    output_names: Dict[str, str] = dict(entry.options.get(CONF_OUTPUT_NAMES, {}))

    entities: List[ACM200OutputMediaPlayer] = [
        ACM200OutputMediaPlayer(
            coordinator=coordinator,
            client=client,
            entry=entry,
            output_id=out_id,
            num_inputs=num_inputs,
            input_names=input_names,
            output_names=output_names,
        )
        for out_id in range(1, num_outputs + 1)
    ]

    async_add_entities(entities)


class ACM200OutputMediaPlayer(
    CoordinatorEntity[ACM200Coordinator], MediaPlayerEntity, RestoreEntity
):
    """MediaPlayer entity for one ACM200 output zone.

    State reflects what the coordinator last saw:
    - ON  → output is actively routing and the sink reports online
    - OFF → routing is known but sink is offline / not connected
    - UNAVAILABLE → coordinator hasn't received data for this output yet
    """

    _attr_should_poll = False
    _attr_supported_features = MediaPlayerEntityFeature.SELECT_SOURCE
    _attr_icon = "mdi:television"

    def __init__(
        self,
        coordinator: ACM200Coordinator,
        client: ACM200Client,
        entry: ConfigEntry,
        output_id: int,
        num_inputs: int,
        input_names: Dict[str, str],
        output_names: Dict[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._output_id = output_id
        self._num_inputs = num_inputs

        dev_key = entry.unique_id or entry.entry_id
        self._attr_device_info = get_device_info(entry)

        out_friendly = (output_names.get(str(output_id)) or "").strip()
        self._attr_name = out_friendly or f"ACM200 Output {output_id:03d}"
        self._attr_unique_id = f"{dev_key}_output_{output_id:03d}"

        raw_labels: List[str] = []
        for in_id in range(1, num_inputs + 1):
            friendly = (input_names.get(str(in_id)) or "").strip()
            raw_labels.append(friendly or f"Input {in_id}")

        self._sources = _make_unique_labels(raw_labels)
        self._source_to_input: Dict[str, int] = {
            label: idx for idx, label in enumerate(self._sources, start=1)
        }
        self._input_to_source: Dict[int, str] = {
            idx: label for label, idx in self._source_to_input.items()
        }

        # Optimistic source used between poll cycles after a user action
        self._optimistic_source: Optional[str] = None

    # ------------------------------------------------------------------
    # Coordinator-driven state
    # ------------------------------------------------------------------

    @callback
    def _handle_coordinator_update(self) -> None:
        # Clear the optimistic override once the coordinator confirms the change
        data: ACM200Data = self.coordinator.data
        if data and self._optimistic_source:
            confirmed_in = data.input_for(self._output_id)
            if confirmed_in == self._source_to_input.get(self._optimistic_source):
                self._optimistic_source = None
        self.async_write_ha_state()

    @property
    def state(self) -> MediaPlayerState | None:
        data: ACM200Data | None = self.coordinator.data
        if data is None:
            return None
        if data.is_output_online(self._output_id):
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def source(self) -> Optional[str]:
        if self._optimistic_source:
            return self._optimistic_source
        data: ACM200Data | None = self.coordinator.data
        if data is None:
            return None
        in_id = data.input_for(self._output_id)
        return self._input_to_source.get(in_id) if in_id is not None else None

    @property
    def source_list(self) -> List[str]:
        return self._sources

    # ------------------------------------------------------------------
    # Restore last state on HA restart (before first coordinator cycle)
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and self.coordinator.data is None:
            src = last_state.attributes.get("source")
            if src in self._sources:
                self._optimistic_source = src

    # ------------------------------------------------------------------
    # User action
    # ------------------------------------------------------------------

    async def async_select_source(self, source: str) -> None:
        if source not in self._source_to_input:
            _LOGGER.error(
                "ACM200: unknown source %s for %s", source, self.entity_id
            )
            return

        in_id = self._source_to_input[source]
        _LOGGER.info(
            "ACM200: routing output %03d → input %d (%s)",
            self._output_id,
            in_id,
            source,
        )
        await self._client.switch_route(self._output_id, in_id)

        # Optimistic update so the UI responds immediately
        self._optimistic_source = source
        self.async_write_ha_state()
