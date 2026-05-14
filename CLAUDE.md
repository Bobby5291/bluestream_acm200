# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration for the **Blustream ACM200/ACM210 video matrix switcher**. It communicates exclusively over the local network via raw TCP (telnet port 23). There is no cloud dependency. It is distributed via HACS and validated by Home Assistant's `hassfest` tool.

- **Domain**: `bluestream_acm200`
- **Minimum HA version**: 2026.4.0 (per `hacs.json`)
- **IoT class**: `local_polling`

## Architecture

### Data flow

```
ACM200 device (TCP/23)
    ↕  raw text commands
ACM200Client (client.py)
    ↕  Python dicts / lists
ACM200Coordinator (coordinator.py)   ← DataUpdateCoordinator, polls every N seconds
    ↕  ACM200Data dataclass
Entity classes (media_player, select, sensor)
    ↕  HA state machine
Home Assistant
```

### Component responsibilities

**`client.py` — `ACM200Client`**  
Pure async telnet client. Opens a new TCP connection per command (no persistent socket), drains the banner, sends one command, reads until `ACM200>` prompt or timeout, then closes. A single `asyncio.Lock` serialises all commands. Module-level `_parse_*` functions handle all firmware-specific response parsing — they use column-position heuristics because the ACM200 FW 1.31 returns fixed-width tables.

Key commands issued to the device:
- `OUT 001 STATUS` — returns routing (the `Fr` column) and online state (`Net` column)
- `IN 001 STATUS` — returns input metadata and name
- `OUT 001 FR 002` — routes output 001 from input 002
- `MATRIX STATUS` — queries matrix size (returns `[ERROR]` on FW 1.31; probing fallback used instead)

**`coordinator.py` — `ACM200Coordinator` / `ACM200Data`**  
Standard HA `DataUpdateCoordinator`. On each tick it calls `client.get_full_status()` which does a single `OUT ooo STATUS` per output, extracting both routing and online state in one pass. The result is an `ACM200Data` dataclass: `routing: Dict[int, int]` (output→input) and `online_outputs: List[int]`.

**`__init__.py`**  
Entry setup and teardown. Stores clients and coordinators in `hass.data[DOMAIN]["clients"]` and `hass.data[DOMAIN]["coordinators"]` keyed by `entry_id`. Registers the `switch_route` service once (guarded by `service_registered` flag to survive multiple entries). Unregisters the service only when the last entry is removed.

**`config_flow.py` — `ConfigFlow` / `OptionsFlowHandler`**  
Two entry points: `async_step_user` (manual IP entry) and `async_step_zeroconf` (mDNS auto-discovery via `_telnet._tcp.local.` records). Both funnel into `_probe_and_advance()` → `async_step_names()`. The probe concurrently queries IN and OUT counts then fetches names. Names are stored in `entry.options` (not `entry.data`) so they can be updated without re-setup.

**`media_player.py`** and **`select.py`**  
Both create one entity per output. They are `CoordinatorEntity + RestoreEntity`. Key pattern: optimistic updates — when a user selects a source, `_optimistic_source` / `_optimistic_option` is set immediately so the UI responds without waiting for the next poll. It is cleared once the coordinator confirms the change. Both entity types are **disabled by default** and only auto-enable if the output was online at the time of the first coordinator refresh.

**`sensor.py`**  
Single diagnostic sensor per entry. Its `native_value` is a compact routing summary (e.g., `●001→2 ○002→1`). Per-output detail is in `extra_state_attributes`.

### Data storage split

| What | Where |
|---|---|
| Host, port, matrix size, poll interval | `entry.data` (immutable after setup) |
| Input/output friendly names | `entry.options` (editable via Options flow) |

### Numbers are always 1-based

All input and output IDs throughout the codebase are 1-based integers matching the device's own numbering.

## Validation / CI

No local test suite or linter is configured. The two CI workflows are:

- **hassfest** (`.github/workflows/hassfest.yaml`) — Home Assistant's official integration validator. Checks `manifest.json`, `strings.json`, `services.yaml`, and general HA integration conventions.
- **HACS validation** (`.github/workflows/validate.yml`) — checks the repository is a valid HACS integration.

Both run on push, pull request, and daily schedule. To test locally you need a real HA instance or the `hassfest` Docker image:

```bash
# Run hassfest locally (requires Docker)
docker run --rm -v $(pwd):/github/workspace homeassistant/hassfest
```

## Key conventions

- All async I/O uses `asyncio`; there are no blocking calls.
- Parser functions (`_parse_*`) at module level in `client.py` are pure functions — keep them that way to make them testable without an HA environment.
- When adding a new entity platform, add it to `PLATFORMS` in `const.py` and add `async_setup_entry` in the new module — `__init__.py` forwards to all platforms automatically.
- The `switch_route` service supports both `output`/`input` (current field names) and `output_id`/`input_id` (legacy aliases) — preserve both when touching the service handler.
- `en.json` is the translations file (used by `hassfest`). Field keys in config/options flows must match the schema field names defined in `config_flow.py`.
