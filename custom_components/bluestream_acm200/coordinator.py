from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ACM200Client

_LOGGER = logging.getLogger(__name__)


@dataclass
class ACM200Data:
    """All live data fetched from the matrix in a single poll cycle."""

    # output_id -> input_id  (routing table)
    routing: Dict[int, int] = field(default_factory=dict)

    # Set of output IDs that reported a connected sink this cycle
    online_outputs: List[int] = field(default_factory=list)

    def input_for(self, output_id: int) -> Optional[int]:
        return self.routing.get(output_id)

    def is_output_online(self, output_id: int) -> bool:
        return output_id in self.online_outputs


class ACM200Coordinator(DataUpdateCoordinator[ACM200Data]):
    """Coordinator that polls routing status and output online state."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ACM200Client,
        num_outputs: int,
        poll_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ACM200 Coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self._client = client
        self._num_outputs = num_outputs

    async def _async_update_data(self) -> ACM200Data:
        try:
            routing = await self._client.get_routing_status(self._num_outputs)
            online = await self._client.discover_online_outputs(self._num_outputs)
            return ACM200Data(routing=routing, online_outputs=online)
        except Exception as err:
            raise UpdateFailed(f"ACM200 poll failed: {err}") from err
