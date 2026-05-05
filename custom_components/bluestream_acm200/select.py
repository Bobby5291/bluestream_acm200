from __future__ import annotations

import logging
from typing import Dict, List, Optional

from homeassistant.components.select import SelectEntity
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

    entities: List[ACM200OutputSelect] = [
        ACM200OutputSelect(
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


class ACM200OutputSelect(
    CoordinatorEntity[ACM200Coordinator], SelectEntity, RestoreEntity
):
    """Select entity for choosing the source routed to one ACM200 output.

    Reflects the coordinator's live routing data.  An optimistic current_option
    is applied immediately after a user action so the UI feels responsive, and
    is cleared once the coordinator confirms the change.
    """

    _attr_should_poll = False
    _attr_icon = "mdi:video-input-hdmi"

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

        # Disabled by default; enabled automatically if output is online at first poll
        data = coordinator.data
        self._attr_entity_registry_enabled_default = (
            data.is_output_online(output_id) if data is not None else False
        )

        dev_key = entry.unique_id or entry.entry_id
        self._attr_device_info = get_device_info(entry)

        out_friendly = (output_names.get(str(output_id)) or "").strip()
        self._attr_name = (
            f"{out_friendly} Source" if out_friendly else f"ACM200 Output {output_id:03d} Source"
        )
        self._attr_unique_id = f"{dev_key}_output_{output_id:03d}_source"

        raw_labels: List[str] = []
        for in_id in range(1, num_inputs + 1):
            friendly = (input_names.get(str(in_id)) or "").strip()
            raw_labels.append(friendly or f"Input {in_id}")

        labels = _make_unique_labels(raw_labels)
        self._label_to_input: Dict[str, int] = {
            label: idx for idx, label in enumerate(labels, start=1)
        }
        self._input_to_label: Dict[int, str] = {
            idx: label for label, idx in self._label_to_input.items()
        }
        self._attr_options = labels

        self._optimistic_option: Optional[str] = None

    # ------------------------------------------------------------------
    # Coordinator updates
    # ------------------------------------------------------------------

    @callback
    def _handle_coordinator_update(self) -> None:
        data: ACM200Data = self.coordinator.data
        if data and self._optimistic_option:
            confirmed = data.input_for(self._output_id)
            if confirmed == self._label_to_input.get(self._optimistic_option):
                self._optimistic_option = None
        self.async_write_ha_state()

    @property
    def current_option(self) -> Optional[str]:
        if self._optimistic_option:
            return self._optimistic_option
        data: ACM200Data | None = self.coordinator.data
        if data is None:
            return None
        in_id = data.input_for(self._output_id)
        return self._input_to_label.get(in_id) if in_id is not None else None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and self.coordinator.data is None:
            if last_state.state in self._attr_options:
                self._optimistic_option = last_state.state

    # ------------------------------------------------------------------
    # User action
    # ------------------------------------------------------------------

    async def async_select_option(self, option: str) -> None:
        if option not in self._label_to_input:
            _LOGGER.error(
                "ACM200: unknown option %s for %s", option, self._attr_unique_id
            )
            return

        in_id = self._label_to_input[option]
        _LOGGER.info(
            "ACM200: routing output %03d → input %d (%s)",
            self._output_id,
            in_id,
            option,
        )
        await self._client.switch_route(self._output_id, in_id)

        self._optimistic_option = option
        self.async_write_ha_state()
