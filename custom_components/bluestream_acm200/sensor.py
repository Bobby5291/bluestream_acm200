from __future__ import annotations

from typing import Any, Dict

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS, DOMAIN
from .coordinator import ACM200Coordinator, ACM200Data


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
    """Diagnostic sensor summarising live routing and online state."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:router-network"
    _attr_entity_category = "diagnostic"

    def __init__(
        self, coordinator: ACM200Coordinator, entry_id: str, num_outputs: int
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._num_outputs = num_outputs
        self._attr_name = "Routing Overview"
        self._attr_unique_id = f"{entry_id}_routing_overview"

    @property
    def native_value(self) -> str:
        data: ACM200Data | None = self.coordinator.data
        if data is None:
            return "unavailable"
        parts: list[str] = []
        for out_id in range(1, self._num_outputs + 1):
            in_id = data.input_for(out_id)
            online = "●" if data.is_output_online(out_id) else "○"
            parts.append(f"{online}{out_id:03d}→{in_id if in_id is not None else '??'}")
        return " ".join(parts)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        data: ACM200Data | None = self.coordinator.data
        if data is None:
            return {}
        attrs: Dict[str, Any] = {}
        for out_id in range(1, self._num_outputs + 1):
            attrs[f"output_{out_id:03d}_input"] = data.input_for(out_id)
            attrs[f"output_{out_id:03d}_online"] = data.is_output_online(out_id)
        return attrs
