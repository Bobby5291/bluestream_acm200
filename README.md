# Blustream ACM

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![hassfest](https://github.com/Bobby5291/blustream_acm/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/Bobby5291/blustream_acm/actions/workflows/hassfest.yaml)
[![HACS validation](https://github.com/Bobby5291/blustream_acm/actions/workflows/validate.yml/badge.svg)](https://github.com/Bobby5291/blustream_acm/actions/workflows/validate.yml)
[![GitHub Stars](https://img.shields.io/github/stars/Bobby5291/blustream_acm?style=flat&logo=github&color=yellow&label=Stars)](https://github.com/Bobby5291/blustream_acm/stargazers)
[![GitHub Downloads](https://img.shields.io/github/downloads/Bobby5291/blustream_acm/total?style=flat&logo=github&label=Downloads)](https://github.com/Bobby5291/blustream_acm/releases)

A Home Assistant custom integration for the **Blustream ACM200 video matrix**.

Connects directly over the local network — no cloud, no relay.

---

## Features

| Feature | Detail |
|---|---|
| **Auto-discovery** | Finds ACM200 / ACM210 devices on your network via mDNS (zeroconf) |
| **Auto-detects matrix size** | Queries the device to find how many inputs and outputs it has |
| **Auto-imports names** | Reads input/output labels stored on the device — no manual entry needed |
| **Online/offline detection** | Each output shows ON/OFF state based on whether a sink is connected |
| **Live routing state** | Polls the device and reflects the current routing in HA in real time |
| **Media Player entities** | One per output — supports source selection |
| **Select entities** | Lightweight drop-down alternative to Media Player |
| **Routing overview sensor** | Single diagnostic sensor summarising all routes at a glance |
| **`switch_route` service** | Call from automations or scripts to change routing programmatically |
| **No cloud dependency** | Communicates entirely over the local network |

---

## Installation

### HACS (recommended)

1. Open **HACS → Integrations**
2. Click the three-dot menu → **Custom repositories**
3. Add `https://github.com/Bobby5291/blustream_acm` — category **Integration**
4. Install **Blustream ACM200**
5. Restart Home Assistant

### Manual

Copy `custom_components/bluestream_acm200/` into your HA `config/custom_components/` folder and restart.

---

## Configuration

### Auto-discovery (recommended)

If your ACM200 advertises itself via mDNS on your network, Home Assistant will show a discovery notification automatically. Click it, confirm, and the integration queries the device to fill in the matrix size and names — you only need to review and optionally edit them.

### Manual setup

1. **Settings → Devices & Services → Add Integration**
2. Search for **Blustream ACM200**
3. Enter the device IP/hostname and port (default `23`)
4. The integration will connect and attempt to auto-detect the matrix size and names
5. Review the pre-filled names on the next screen, edit if needed, and click Submit

---

## Entities

### Media Player  (`media_player.*`)
One entity per output. Supports source selection. State:
- **ON** — output has an active/connected display
- **OFF** — output routing is known but no sink detected
- **Unavailable** — device not responding

### Select  (`select.*`)
Lightweight drop-down alternative to Media Player for each output.

### Sensor  (`sensor.*_routing_overview`)
Diagnostic sensor. `native_value` is a compact routing summary, e.g.:
```
●001→2 ○002→1 ●003→3
```
`●` = online, `○` = offline.  Full per-output routing and online state are also in `extra_state_attributes`.

---

## Service: `bluestream_acm200.switch_route`

```yaml
service: bluestream_acm200.switch_route
data:
  output: 3       # Output number (1-based)
  input: 2        # Input number (1-based)
  entry_id: ""    # Optional — only needed with multiple ACM200 devices
```

---

## Options

After setup, go to **Settings → Devices & Services → Blustream ACM200 → Configure** to rename any input or output.

---

## Requirements

- Blustream ACM200 accessible on the local network (telnet port 23 open)
- Home Assistant 2025.12.0 or newer

---

## Disclaimer

Independent community integration. Not affiliated with or endorsed by Blustream.
