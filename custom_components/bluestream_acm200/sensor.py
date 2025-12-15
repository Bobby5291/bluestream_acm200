from __future__ import annotations

from typing import Any, Dict

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS
from .coordinator import ACM200Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ACM200Coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    num_outputs = int(entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS))

    async_add_entities(
        [ACM200RoutingOverviewSensor(coordinator, entry.entry_id, num_outputs)],
        update_before_add=True,
    )


class ACM200RoutingOverviewSensor(CoordinatorEntity[ACM200Coordinator], SensorEntity):
    """One sensor that summarises Output->Input routing for dashboards/diagnostics."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:router-network"
    _attr_entity_category = "diagnostic"

    def __init__(self, coordinator: ACM200Coordinator, entry_id: str, num_outputs: int) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._num_outputs = num_outputs

        self._attr_name = "Routing Overview"
        self._attr_unique_id = f"{entry_id}_routing_overview"

    @property
    def native_value(self) -> str:
        # Human readable summary
        data: Dict[int, int] = self.coordinator.data or {}
        parts = []
        for out_id in range(1, self._num_outputs + 1):
            in_id = data.get(out_id)
            parts.append(f"{out_id:03d}->{(in_id if in_id is not None else '??')}")
        return ", ".join(parts)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        # Useful structured attributes for dashboards/templating
        data: Dict[int, int] = self.coordinator.data or {}
        return {f"output_{out_id:03d}": data.get(out_id) for out_id in range(1, self._num_outputs + 1)}

