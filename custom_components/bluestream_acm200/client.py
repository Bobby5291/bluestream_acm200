ffrom __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

_LOGGER = logging.getLogger(__name__)


class ACM200Client:
    """Very small async client to talk to ACM200 (telnet-like)."""

    def __init__(self, host: str, port: int = 23) -> None:
        self._host = host
        self._port = port
        self._lock = asyncio.Lock()

    async def _send_command(self, command: str, expect_response: bool = True, timeout: float = 5.0) -> str:
        """Send a command and optionally read response."""
        async with self._lock:
            reader: Optional[asyncio.StreamReader] = None
            writer: Optional[asyncio.StreamWriter] = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=timeout,
                )
                msg = command.strip() + "\r\n"
                writer.write(msg.encode("utf-8"))
                await writer.drain()

                if not expect_response:
                    return ""

                data = await asyncio.wait_for(reader.read(4096), timeout=timeout)
                return data.decode("utf-8", errors="ignore")
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass

    async def switch_route(self, output_id: int, input_id: int) -> None:
        """Route output_id to input_id."""
        # Command may differ per device; adjust as needed.
        # Format used here: "CIxxxOyyy" is placeholder for your working command.
        cmd = f"SW {output_id} {input_id}"
        await self._send_command(cmd, expect_response=False)

    async def get_routing_status(self, num_outputs: int) -> Dict[int, int]:
        """
        Poll routing status for outputs 1..num_outputs.
        This assumes the device supports a query per output.
        """
        result: Dict[int, int] = {}
        for out_id in range(1, num_outputs + 1):
            cmd = f"GET {out_id}"
            resp = await self._send_command(cmd, expect_response=True)
            # VERY device-specific parsing:
            # Expect something like "OUT 001 IN 3"
            in_id = _parse_input_id(resp)
            if in_id is not None:
                result[out_id] = in_id
        return result


def _parse_input_id(resp: str) -> Optional[int]:
    # Basic parsing helper; tailor to your actual ACM200 response.
    for token in resp.replace("\r", " ").replace("\n", " ").split():
        if token.isdigit():
            return int(token)
    return None
