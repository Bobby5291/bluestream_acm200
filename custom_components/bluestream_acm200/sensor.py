from __future__ import annotations

from typing import Any, Dict

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ACM200Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ACM200Coordinator = data["coordinator"]
    num_outputs = int(data["num_outputs"])

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
        self._num_outputs = int(num_outputs)
        self._attr_unique_id = f"{entry_id}_routing_overview"
        self._attr_name = "Routing Overview"

    @property
    def native_value(self) -> str:
        routes = self.coordinator.data or {}
        if not routes:
            return "No data"
        # e.g. "OUT001→IN002, OUT002→IN002 ..."
        parts = []
        for out_id in range(1, self._num_outputs + 1):
            in_id = routes.get(out_id)
            if in_id:
                parts.append(f"OUT{out_id:03d}→IN{in_id:03d}")
        return ", ".join(parts) if parts else "No routes"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        routes = self.coordinator.data or {}
        attrs: Dict[str, Any] = {}
        for out_id, in_id in sorted(routes.items()):
            attrs[f"output_{out_id:03d}"] = f"input_{in_id:03d}"
        return attrs
