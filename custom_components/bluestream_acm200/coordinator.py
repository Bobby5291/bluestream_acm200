from __future__ import annotations

from datetime import timedelta
import logging
from typing import Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ACM200Client

_LOGGER = logging.getLogger(__name__)


class ACM200Coordinator(DataUpdateCoordinator[Dict[int, int]]):
    """Fetch and store Output->Input routes."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: ACM200Client,
        num_outputs: int,
        poll_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ACM200 Routing",
            update_interval=timedelta(seconds=max(2, int(poll_interval))),
        )
        self.client = client
        self.num_outputs = int(num_outputs)

    async def _async_update_data(self) -> Dict[int, int]:
        try:
            routes = await self.client.get_routes_bulk()

            # Fill missing outputs (only when needed) with per-output queries
            if self.num_outputs > 0 and len(routes) < self.num_outputs:
                for out_id in range(1, self.num_outputs + 1):
                    if out_id in routes:
                        continue
                    value = await self.client.get_route_for_output(out_id)
                    if value is not None:
                        routes[out_id] = value

            return routes
        except Exception as exc:
            raise UpdateFailed(str(exc)) from exc
