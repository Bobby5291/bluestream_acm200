from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, List, Optional, Tuple

_LOGGER = logging.getLogger(__name__)

# Timeout for individual commands (seconds)
_CMD_TIMEOUT = 5.0
# Quick probe timeout for online checks (seconds)
_PROBE_TIMEOUT = 2.0


class ACM200Client:
    """Async telnet-style client for the Blustream ACM200."""

    def __init__(self, host: str, port: int = 23) -> None:
        self._host = host
        self._port = port
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Low-level transport
    # ------------------------------------------------------------------

    async def _send_command(self, command: str, timeout: float = _CMD_TIMEOUT) -> str:
        """Open a connection, send *command*, and return the raw response text."""
        async with self._lock:
            reader: Optional[asyncio.StreamReader] = None
            writer: Optional[asyncio.StreamWriter] = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=timeout,
                )

                # Drain banner / prompt so we get a clean slate
                try:
                    await asyncio.wait_for(reader.read(4096), timeout=0.5)
                except asyncio.TimeoutError:
                    pass

                writer.write((command.strip() + "\r\n").encode("utf-8"))
                await writer.drain()

                data = b""
                try:
                    while True:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=0.7)
                        if not chunk:
                            break
                        data += chunk
                        if b"ACM200>" in data:
                            break
                except asyncio.TimeoutError:
                    pass

                return data.decode("utf-8", errors="ignore")

            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # Connectivity check
    # ------------------------------------------------------------------

    async def async_test_connection(self) -> bool:
        """Return True if the device is reachable and responds."""
        try:
            resp = await self._send_command("HELP", timeout=_PROBE_TIMEOUT)
            return bool(resp)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Routing control
    # ------------------------------------------------------------------

    async def switch_route(self, output_id: int, input_id: int) -> None:
        """Route *output_id* to *input_id* using: OUT ooo FR yyy."""
        cmd = f"OUT {output_id:03d} FR {input_id:03d}"
        resp = await self._send_command(cmd)
        if "[ERROR]" in resp:
            _LOGGER.error(
                "ACM200 rejected command %s — response: %s", cmd, resp.strip()
            )

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    async def get_output_status(self, output_id: int) -> str:
        """Query a single output: OUT ooo STATUS."""
        return await self._send_command(f"OUT {output_id:03d} STATUS")

    async def get_input_status(self, input_id: int) -> str:
        """Query a single input: IN iii STATUS."""
        return await self._send_command(f"IN {input_id:03d} STATUS")

    async def get_routing_status(self, num_outputs: int) -> Dict[int, int]:
        """
        Return {output_id: input_id} for every output by polling OUT ooo STATUS.
        Outputs that do not respond are omitted from the result so callers can
        detect them as unavailable.
        """
        result: Dict[int, int] = {}
        for out_id in range(1, num_outputs + 1):
            try:
                resp = await self.get_output_status(out_id)
                in_id = _parse_routed_input(resp)
                if in_id is not None:
                    result[out_id] = in_id
            except Exception as exc:
                _LOGGER.debug("ACM200: could not poll output %d: %s", out_id, exc)
        return result

    # ------------------------------------------------------------------
    # Auto-discovery helpers
    # ------------------------------------------------------------------

    async def discover_matrix_size(self) -> Tuple[int, int]:
        """
        Ask the device how many inputs and outputs it has.

        Tries the ``MATRIX STATUS`` command first (works on most firmware).
        Falls back to probing consecutive outputs / inputs until the device
        stops responding, up to a generous ceiling of 32 each.
        """
        try:
            resp = await self._send_command("MATRIX STATUS")
            num_in, num_out = _parse_matrix_size(resp)
            if num_in and num_out:
                _LOGGER.debug(
                    "ACM200: matrix size from MATRIX STATUS: %d×%d", num_in, num_out
                )
                return num_in, num_out
        except Exception:
            pass

        # Fallback: probe until silent
        num_in = await self._probe_count("IN", max_probe=32)
        num_out = await self._probe_count("OUT", max_probe=32)
        _LOGGER.debug(
            "ACM200: matrix size from probing: %d×%d", num_in, num_out
        )
        return num_in, num_out

    async def _probe_count(self, direction: str, max_probe: int = 32) -> int:
        """Probe STATUS for direction (IN/OUT) 1..max_probe until no useful reply."""
        count = 0
        for idx in range(1, max_probe + 1):
            try:
                resp = await self._send_command(
                    f"{direction} {idx:03d} STATUS", timeout=_PROBE_TIMEOUT
                )
                if "[ERROR]" in resp or not resp.strip():
                    break
                count = idx
            except Exception:
                break
        return count

    async def discover_input_names(self, num_inputs: int) -> Dict[int, str]:
        """
        Return {input_id: friendly_name} by querying IN iii STATUS for each input.
        Inputs that do not report a name are omitted so the caller can fall back
        to a generic label.
        """
        names: Dict[int, str] = {}
        for in_id in range(1, num_inputs + 1):
            try:
                resp = await self.get_input_status(in_id)
                name = _parse_name(resp)
                if name:
                    names[in_id] = name
            except Exception as exc:
                _LOGGER.debug("ACM200: could not query input %d name: %s", in_id, exc)
        return names

    async def discover_output_names(self, num_outputs: int) -> Dict[int, str]:
        """
        Return {output_id: friendly_name} by querying OUT ooo STATUS for each output.
        """
        names: Dict[int, str] = {}
        for out_id in range(1, num_outputs + 1):
            try:
                resp = await self.get_output_status(out_id)
                name = _parse_name(resp)
                if name:
                    names[out_id] = name
            except Exception as exc:
                _LOGGER.debug(
                    "ACM200: could not query output %d name: %s", out_id, exc
                )
        return names

    async def discover_online_outputs(self, num_outputs: int) -> List[int]:
        """
        Return a list of output IDs that appear to have an active/connected device.
        We look for an "online", "connected", or "active" flag in the STATUS reply.
        """
        online: List[int] = []
        for out_id in range(1, num_outputs + 1):
            try:
                resp = await self.get_output_status(out_id)
                if _parse_output_online(resp):
                    online.append(out_id)
            except Exception:
                pass
        return online


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def _parse_routed_input(resp: str) -> Optional[int]:
    """
    Parse routed input from an OUT ooo STATUS response.

    Handles several known firmware variants:
    - "From Input: 003"
    - "FR 003"
    - "Input 003" / "Input: 003"
    - "Routed to Input 2"
    """
    text = resp.replace("\r", "\n")
    patterns = [
        r"\bFrom\s+Input\s*[:=]\s*(\d{1,3})\b",
        r"\bRouted\s+(?:to\s+)?Input\s*[:=]?\s*(\d{1,3})\b",
        r"\bFR\s+(\d{1,3})\b",
        r"\bInput\s*[:=]\s*(\d{1,3})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _parse_name(resp: str) -> Optional[str]:
    """
    Extract a friendly name from an IN iii STATUS or OUT ooo STATUS response.

    Common firmware formats:
    - "Name: Living Room TV"
    - "Label: AppleTV"
    - "Input Name: Blu-ray"
    - "Output Name: Bedroom"
    """
    text = resp.replace("\r", "\n")
    patterns = [
        r"\b(?:Output\s+)?Name\s*[:=]\s*(.+)",
        r"\b(?:Input\s+)?Name\s*[:=]\s*(.+)",
        r"\bLabel\s*[:=]\s*(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            name = m.group(1).strip().strip('"').strip("'")
            # Reject placeholder / empty names the firmware sometimes returns
            if name and name.lower() not in {"", "n/a", "none", "unknown", "input", "output"}:
                return name
    return None


def _parse_matrix_size(resp: str) -> Tuple[int, int]:
    """
    Parse input/output count from a MATRIX STATUS response.

    Looks for lines like:
    - "Inputs: 4"  /  "Outputs: 9"
    - "4 Inputs"  /  "9 Outputs"
    """
    text = resp.replace("\r", "\n")
    num_in = num_out = 0

    m = re.search(r"\bInputs?\s*[:=]\s*(\d+)\b", text, flags=re.IGNORECASE)
    if m:
        num_in = int(m.group(1))

    m = re.search(r"\bOutputs?\s*[:=]\s*(\d+)\b", text, flags=re.IGNORECASE)
    if m:
        num_out = int(m.group(1))

    # Alternate: "4 x 9" or "4x9" matrix descriptor
    if not (num_in and num_out):
        m = re.search(r"\b(\d+)\s*[xX×]\s*(\d+)\b", text)
        if m:
            num_in, num_out = int(m.group(1)), int(m.group(2))

    return num_in, num_out


def _parse_output_online(resp: str) -> bool:
    """
    Return True if the STATUS response indicates the output has an active sink.

    Looks for positive keywords; absence of response or explicit offline
    keywords returns False.
    """
    if not resp.strip():
        return False
    text = resp.lower()
    online_markers = ["online", "connected", "active", "link up", "hdmi lock", "locked"]
    offline_markers = ["offline", "disconnected", "no device", "no sink", "no signal", "link down"]
    if any(m in text for m in offline_markers):
        return False
    return any(m in text for m in online_markers)
