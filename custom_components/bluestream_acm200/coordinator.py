from __future__ import annotations

import logging
from datetime import timedelta
from typing import Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ACM200Client

_LOGGER = logging.getLogger(__name__)


class ACM200Coordinator(DataUpdateCoordinator[Dict[int, int]]):
    """Coordinator to poll routing status."""

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
            name="ACM200 Routing Coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self._client = client
        self._num_outputs = num_outputs

    async def _async_update_data(self) -> Dict[int, int]:
        try:
            routing = await self._client.get_routing_status(self._num_outputs)
            return routing
        except Exception as err:
            raise UpdateFailed(f"Error updating ACM200 routing: {err}") from err

