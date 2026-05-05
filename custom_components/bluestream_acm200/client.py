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
        """Return list of output IDs whose Net column reports On (RX on the network)."""
        online: List[int] = []
        for out_id in range(1, num_outputs + 1):
            try:
                resp = await self.get_output_status(out_id)
                if _parse_output_online(resp):
                    online.append(out_id)
            except Exception:
                pass
        return online

    async def get_full_status(self, num_outputs: int) -> Tuple[Dict[int, int], List[int]]:
        """
        Single-pass poll: one OUT ooo STATUS call per output returns both
        the routing table and the online list — half the round-trips vs two separate calls.
        """
        routing: Dict[int, int] = {}
        online: List[int] = []
        for out_id in range(1, num_outputs + 1):
            try:
                resp = await self.get_output_status(out_id)
                in_id = _parse_routed_input(resp)
                if in_id is not None:
                    routing[out_id] = in_id
                if _parse_output_online(resp):
                    online.append(out_id)
            except Exception as exc:
                _LOGGER.debug("ACM200: could not poll output %d: %s", out_id, exc)
        return routing, online


# ---------------------------------------------------------------------------
# Response parsers — tuned for ACM200 FW 1.31 fixed-width table format
# ---------------------------------------------------------------------------
#
# OUT STATUS header line format (FW 1.31):
#   Out   Net    HPD   Ver     Mode   Res   Rotate  Name
#   001   Off    Off   A7.3.0  MX     00    0       RX 1 Lounge
#
# The data line immediately below has the routing info:
#   >>Fast   Fr    Vid/Aud/IR_/Ser/USB/CEC      HDR   MCast
#     On     001   000/000/000/000/000/000      On    On
#
# IN STATUS header line format (FW 1.31):
#   In    Net    Sig   Ver     EDID   Aud   MCast   Name
#   001   On     Off   A7.3.0  DF015  HDMI  On      TX 1 SKY
# ---------------------------------------------------------------------------

def _parse_routed_input(resp: str) -> Optional[int]:
    """
    Parse the currently routed input from an OUT ooo STATUS response.

    FW 1.31 puts this in the '>>Fast / Fr' data row:
        >>Fast   Fr    ...
          On     001   ...
    We find the '>>Fast' marker line, then read 'Fr' value from the next
    data line by column position.
    """
    lines = resp.replace("\r", "").splitlines()

    # Strategy 1: find the header ">>Fast  Fr" and read the value line below
    for i, line in enumerate(lines):
        if re.search(r">>\s*Fast", line, flags=re.IGNORECASE):
            # Find column position of "Fr" in this header line
            m_hdr = re.search(r"\bFr\b", line)
            if m_hdr and i + 1 < len(lines):
                col = m_hdr.start()
                val_line = lines[i + 1]
                # Extract the token at that column (allow ±4 chars slop)
                segment = val_line[max(0, col - 2): col + 8].strip()
                tok = segment.split()[0] if segment.split() else ""
                try:
                    return int(tok)
                except ValueError:
                    pass

    # Strategy 2: fallback — any bare 3-digit number after "Fr" anywhere
    m = re.search(r"\bFr\b\s+(\d{1,3})\b", resp, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    return None


def _parse_name(resp: str) -> Optional[str]:
    """
    Extract the friendly name from an IN iii STATUS or OUT ooo STATUS response.

    FW 1.31 puts the name as the last column on the device data row:
        Out   Net    HPD   Ver     Mode   Res   Rotate  Name
        001   Off    Off   A7.3.0  MX     00    0       RX 1 Lounge

        In    Net    Sig   Ver     EDID   Aud   MCast   Name
        001   On     Off   A7.3.0  DF015  HDMI  On      TX 1 SKY

    We find the 'Name' column header, note its character position, then
    read the same offset on the very next non-empty line.
    """
    lines = resp.replace("\r", "").splitlines()

    for i, line in enumerate(lines):
        # Look for the column-header line that contains "Name" as last header
        if re.search(r"\bName\s*$", line.rstrip()):
            col = line.rstrip().rfind("Name")
            # Find the next non-empty line — that's the data row
            for j in range(i + 1, len(lines)):
                data = lines[j]
                if data.strip() and not data.strip().startswith("="):
                    name = data[col:].strip() if len(data) > col else ""
                    name = name.strip('"').strip("'")
                    if name and name.lower() not in {
                        "", "n/a", "none", "unknown", "input", "output", "name"
                    }:
                        return name
                    break

    return None


def _parse_output_net(resp: str) -> Optional[str]:
    """
    Return the raw 'Net' column value for an output ('On' or 'Off').

    FW 1.31 output data row:
        Out   Net    HPD   ...
        001   Off    Off   ...
    """
    lines = resp.replace("\r", "").splitlines()

    for i, line in enumerate(lines):
        if re.search(r"\bOut\b.*\bNet\b", line, flags=re.IGNORECASE):
            # Find column position of "Net"
            m_hdr = re.search(r"\bNet\b", line)
            if m_hdr and i + 1 < len(lines):
                col = m_hdr.start()
                data_line = lines[i + 1]
                segment = data_line[max(0, col - 1): col + 6].strip()
                tok = segment.split()[0] if segment.split() else ""
                return tok  # "On" or "Off"
    return None


def _parse_input_net(resp: str) -> Optional[str]:
    """
    Return the raw 'Net' column value for an input ('On' or 'Off').

    FW 1.31 input data row:
        In    Net    Sig   ...
        001   On     Off   ...
    """
    lines = resp.replace("\r", "").splitlines()

    for i, line in enumerate(lines):
        if re.search(r"\bIn\b.*\bNet\b", line, flags=re.IGNORECASE):
            m_hdr = re.search(r"\bNet\b", line)
            if m_hdr and i + 1 < len(lines):
                col = m_hdr.start()
                data_line = lines[i + 1]
                segment = data_line[max(0, col - 1): col + 6].strip()
                tok = segment.split()[0] if segment.split() else ""
                return tok
    return None


def _parse_output_online(resp: str) -> bool:
    """
    Return True if the output's 'Net' column reports 'On' (RX is on the network).
    """
    net = _parse_output_net(resp)
    if net is not None:
        return net.lower() == "on"
    # Fallback: no parseable response → treat as offline
    return False


def _parse_matrix_size(resp: str) -> Tuple[int, int]:
    """Not used on FW 1.31 (MATRIX STATUS returns [ERROR]). Kept for future firmware."""
    text = resp.replace("\r", "\n")
    num_in = num_out = 0
    m = re.search(r"\bInputs?\s*[:=]\s*(\d+)\b", text, flags=re.IGNORECASE)
    if m:
        num_in = int(m.group(1))
    m = re.search(r"\bOutputs?\s*[:=]\s*(\d+)\b", text, flags=re.IGNORECASE)
    if m:
        num_out = int(m.group(1))
    if not (num_in and num_out):
        m = re.search(r"\b(\d+)\s*[xX×]\s*(\d+)\b", text)
        if m:
            num_in, num_out = int(m.group(1)), int(m.group(2))
    return num_in, num_out
