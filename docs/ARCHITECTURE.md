# HALUNG Clip Control V12 — Architecture

## System Overview

**Current implementation boundary:** the Raspberry agent currently provides
Dashboard networking and program synchronization only. GPIO/I²C drivers, LCD,
relay control, and the production Clip Test state machine are not implemented
yet. The hardware profiles and state-machine flow below describe the target,
not hardware functionality currently running on the Pi.

```
┌─────────────────────┐
│  Windows PC         │
│  Flask Dashboard    │  http://192.168.X.X:8080
│  - SQLite DB        │
│  - Program Manager  │
│  - Raspberry Mgr    │
│  - Reports/NAS      │
└──────────┬──────────┘
           │ REST API
           │ Authorization: Bearer <token>
           │
    ┌──────▼──────┐
    │  Raspberry Pi 5
    │  Edge Agent
    ├──────────────┤
    │ Network Agent│  Heartbeat, programs, durable result outbox
    └──────────────┘
```

## Database Schema

### `stations`
- `code` — Unique station ID (CT-01, CT-02, ...)
- `hardware_profile` — HALUNG_3IO_BENCH_V1 or HALUNG_23IO_V1
- `status` — READY, RUNNING, OFFLINE, ERROR
- `manual_program_id` — Active program (if manual mode)
- `layout_id` — Active layout (if layout mode, future)

### `manual_programs`
- `name` — Program name
- `required_switches` — JSON array [1, 3, 5, ...]
- `cycle_time_target` — Seconds, for KPI calculation

### `cycles`
- Production record per completed cycle
- `status` — OK or NOK
- `cycle_time_seconds` — Duration
- `efficiency` — Actual/Target * 100

## REST API Endpoints

### Heartbeat (Raspberry → Dashboard)
```
POST /api/edge/<station_code>/heartbeat
Header: Authorization: Bearer <api_token>

{
  "state": "READY",
  "cycle_time": 45.3,
  "actual_per_hour": 42.5,
  "swlock": false,
  "butok": false
}
```

### Get Configuration (Raspberry → Dashboard)
```
GET /api/edge/<station_code>/config
Header: Authorization: Bearer <api_token>

Response:
{
  "ok": true,
  "program": {
    "program_id": 1,
    "version": 1,
    "required_switches": [1, 3, 5]
  }
}
```

The Raspberry validates the program against its hardware profile, saves it
atomically, then calls `POST /api/edge/<station_code>/program-ack`. The
Dashboard marks that version active only after this acknowledgement.

### Report Cycles (Raspberry → Dashboard)
```
POST /api/edge/<station_code>/cycles
Header: Authorization: Bearer <api_token>

{
  "cycles": [{
    "client_uid": "stable-uuid",
    "status": "OK",
    "duration_s": 45.3
  }]
}
```

The Raspberry retains unacknowledged cycle records in a local SQLite outbox.
Resending a record with the same `client_uid` does not duplicate production.

## Planned Clip Test State Machine

### States
- **READY** — Waiting for SWLOCK press
- **SWLOCK** — Lock button pressed, start checking points
- **CHECKING** — All required points must match program
- **VALIDATED** — BUTOK pressed, cycle OK
- **WAIT_RELEASE** — All points must be released to complete
- **WRONG_CLIP** — Extra/missing point detected
- **ERROR** — Hardware or comms failure

### Transitions
```
READY
  ├─ SWLOCK pressed → SWLOCK
  └─ (timer) → READY (safety timeout)

SWLOCK
  ├─ All required points pressed → CHECKING
  ├─ Extra point detected → WRONG_CLIP
  └─ Timeout → ERROR

CHECKING
  ├─ BUTOK pressed → VALIDATED
  ├─ Point released early → WAIT_RELEASE
  └─ Timeout → ERROR

VALIDATED
  ├─ All points released → READY (save cycle)
  └─ Timeout → ERROR

WAIT_RELEASE
  ├─ All released → READY
  └─ Timeout → ERROR

WRONG_CLIP
  └─ All points released → READY (reject cycle)

ERROR
  └─ Manual reset needed
```

## Hardware Profiles

### HALUNG_3IO_BENCH_V1
- **MCP23017 @ 0x20**
  - Port B: SW1, SW2, SW3, BUTOK (GPB0-3), SWLOCK (GPB4)
  - Port A: LED1, LED2, LED3, LED_OK (GPA0-3), EVLOCK (GPA4)
- **Max channels:** 3 switches, 3 LEDs
- **Use case:** Validation bench

### HALUNG_23IO_V1
- **MCP23017 @ 0x20:** SW1-8 (Port B), SW9-16 (Port A)
- **MCP23017 @ 0x21:** SW17-23 (Port B), LED1-9 (Port A)
- **MCP23017 @ 0x22:** LED10-23 (Port A/B)
- **GPIO Direct:** SWLOCK (BCM16), BUTOK (BCM21)
- **Max channels:** 23 switches, 23 LEDs
- **Use case:** Production

## Communication Protocol

1. **Dashboard starts up:**
   - Initializes SQLite
   - Loads settings, programs, stations

2. **Raspberry agent starts:**
   - Loads local config (station_code, dashboard_url, api_token)
   - Starts Dashboard synchronization (hardware is not initialized in this phase)

3. **Heartbeat (configurable; default 5 seconds):**
   - Raspberry sends agent and hardware configuration status
   - Dashboard records health
   - Raspberry checks for commands

4. **Program delivery:**
   - Dashboard signals that an assigned version differs from the acknowledged one
   - Raspberry validates profile compatibility, atomically saves, then acknowledges

5. **Cycle completion:**
   - The future local engine queues a cycle report in SQLite
   - Raspberry sends buffered reports and retains any not acknowledged
   - Dashboard records OK/NOK, calculates KPIs
   - Updates production counters

## Error Handling

- **I²C failure:** Log error, set state to ERROR, freeze I/O
- **Network timeout:** Keep cycle records in the local SQLite outbox and sync on reconnect
- **Invalid config:** Revert to last known good, alert Dashboard
- **Unexpected button:** Set WRONG_CLIP, wait for release
- **LED/relay stuck:** Log hardware error, continue (graceful degrade)
