from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional

_LOGGER = logging.getLogger(__name__)

PROMPT_RE = re.compile(r"\bACM200>\s*$", re.IGNORECASE)

# Common patterns seen across similar firmwares for routing info
ROUTE_RE_LIST = [
    # e.g. "OUT 001 ... FROM IN 002"
    re.compile(
        r"\bOUT(?:PUT)?\s*0*([0-9]{1,3}).*?\b(?:FROM|FR)\b.*?\bIN(?:PUT)?\s*0*([0-9]{1,3}|AUTO)\b",
        re.IGNORECASE,
    ),
    # e.g. "Output 001 From Input 002"
    re.compile(
        r"\bOUTPUT\s*0*([0-9]{1,3}).*?\bFROM\b.*?\bINPUT\s*0*([0-9]{1,3}|AUTO)\b",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class ACM200ConnectionInfo:
    host: str
    port: int


class ACM200Client:
    """Telnet-style client for ACM200 Terminal Control."""

    def __init__(self, host: str, port: int) -> None:
        self._conn = ACM200ConnectionInfo(host=host, port=port)
        self._lock = asyncio.Lock()

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection(self._conn.host, self._conn.port)
        return reader, writer

    async def _read_until_prompt(
        self,
        reader: asyncio.StreamReader,
        *,
        timeout: float = 2.0,
        max_bytes: int = 64_000,
    ) -> str:
        """Read until ACM200 prompt appears or timeout; returns collected text."""
        buf = bytearray()
        try:
            while len(buf) < max_bytes:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=timeout)
                if not chunk:
                    break
                buf.extend(chunk)
                try:
                    text = buf.decode(errors="ignore")
                except Exception:
                    text = ""
                if PROMPT_RE.search(text):
                    break
        except asyncio.TimeoutError:
            # Normal if device returns partial output; we still return what we got.
            pass

        return buf.decode(errors="ignore")

    async def _send_and_read(
        self,
        command: str,
        *,
        read_timeout: float = 2.0,
    ) -> str:
        """Send a command and read response until prompt."""
        async with self._lock:
            reader, writer = await self._open()
            try:
                # Consume banner (if any)
                await self._read_until_prompt(reader, timeout=0.8)

                writer.write((command.strip() + "\r\n").encode())
                await writer.drain()

                text = await self._read_until_prompt(reader, timeout=read_timeout)
                return text
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

    async def switch_route(self, output: int, input_: int) -> None:
        """Route Output -> Input."""
        if output <= 0:
            raise ValueError("output must be >= 1")
        if input_ <= 0:
            raise ValueError("input must be >= 1")
        cmd = f"OUT {output:03d} FR {input_:03d}"
        _LOGGER.debug("ACM200 send: %s", cmd)
        await self._send_and_read(cmd, read_timeout=1.5)

    def _parse_routes(self, text: str) -> Dict[int, int]:
        routes: Dict[int, int] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            for rx in ROUTE_RE_LIST:
                m = rx.search(line)
                if not m:
                    continue
                out_s, in_s = m.group(1), m.group(2)
                try:
                    out_id = int(out_s)
                except ValueError:
                    continue
                # Ignore AUTO as a stable route value (we keep last numeric if present)
                if in_s.upper() == "AUTO":
                    continue
                try:
                    in_id = int(in_s)
                except ValueError:
                    continue
                if out_id > 0 and in_id > 0:
                    routes[out_id] = in_id
        return routes

    async def get_routes_bulk(self) -> Dict[int, int]:
        """Try to fetch all routes in one go."""
        # Try the most likely forms first.
        for cmd in ("OUT 000 STATUS", "STATUS", "OUT000STATUS", "OUT000 STATUS"):
            try:
                text = await self._send_and_read(cmd, read_timeout=2.5)
                routes = self._parse_routes(text)
                if routes:
                    _LOGGER.debug("ACM200 bulk routes via %s: %s", cmd, routes)
                    return routes
            except Exception as exc:
                _LOGGER.debug("ACM200 bulk status failed (%s): %s", cmd, exc)

        return {}

    async def get_route_for_output(self, output: int) -> Optional[int]:
        """Fetch a single output route; returns input id or None."""
        if output <= 0:
            return None
        for cmd in (f"OUT {output:03d} STATUS", f"OUT{output:03d}STATUS"):
            try:
                text = await self._send_and_read(cmd, read_timeout=2.0)
                routes = self._parse_routes(text)
                if output in routes:
                    return routes[output]
            except Exception as exc:
                _LOGGER.debug("ACM200 out status failed (%s): %s", cmd, exc)
        return None


# stdlib contextlib used above
import contextlib  # noqa: E402
