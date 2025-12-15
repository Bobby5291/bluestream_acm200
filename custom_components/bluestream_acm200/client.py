from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, Optional

_LOGGER = logging.getLogger(__name__)


class ACM200Client:
    """Async telnet-style client for ACM200."""

    def __init__(self, host: str, port: int = 23) -> None:
        self._host = host
        self._port = port
        self._lock = asyncio.Lock()

    async def _send_command(self, command: str, timeout: float = 5.0) -> str:
        """Send a command and read the response (best-effort)."""
        async with self._lock:
            reader: Optional[asyncio.StreamReader] = None
            writer: Optional[asyncio.StreamWriter] = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=timeout,
                )

                # Read banner/prompt quickly (don’t hang if nothing)
                try:
                    await asyncio.wait_for(reader.read(2048), timeout=0.5)
                except asyncio.TimeoutError:
                    pass

                msg = command.strip() + "\r\n"
                writer.write(msg.encode("utf-8"))
                await writer.drain()

                # Read response
                data = b""
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(2048), timeout=0.7)
                        if not chunk:
                            break
                        data += chunk
                        # Stop early if we see a prompt
                        if b"ACM200>" in data:
                            break
                except asyncio.TimeoutError:
                    # If device is slow/quiet, return what we got
                    pass

                return data.decode("utf-8", errors="ignore")

            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass

    async def switch_route(self, output_id: int, input_id: int) -> None:
        """Route output to input using: OUT ooo FR yyy."""
        cmd = f"OUT {output_id:03d} FR {input_id:03d}"
        resp = await self._send_command(cmd)

        # Helpful diagnostics in logs if command rejected
        if "[ERROR]" in resp:
            _LOGGER.error("ACM200 rejected command %s. Response: %s", cmd, resp.strip())

    async def get_output_status(self, output_id: int) -> str:
        """Query a single output status: OUT ooo STATUS."""
        cmd = f"OUT {output_id:03d} STATUS"
        return await self._send_command(cmd)

    async def get_routing_status(self, num_outputs: int) -> Dict[int, int]:
        """
        Best-effort routing fetch by calling OUT ooo STATUS for each output and parsing input number.
        This is slower but reliable with FW 1.31 since HELP documents it.
        """
        result: Dict[int, int] = {}
        for out_id in range(1, num_outputs + 1):
            resp = await self.get_output_status(out_id)
            in_id = _parse_routed_input(resp)
            if in_id is not None:
                result[out_id] = in_id
        return result


def _parse_routed_input(resp: str) -> Optional[int]:
    """
    Parse routed input from OUT ooo STATUS response.
    Different firmware prints different wording, so we use tolerant patterns.
    """
    text = resp.replace("\r", "\n")

    # Common patterns we try (tolerant):
    # "From Input: 003"
    # "FR 003"
    # "Input 003"
    patterns = [
        r"\bFrom\s+Input\s*[:=]\s*(\d{1,3})\b",
        r"\bFR\s+(\d{1,3})\b",
        r"\bInput\s+(\d{1,3})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None
