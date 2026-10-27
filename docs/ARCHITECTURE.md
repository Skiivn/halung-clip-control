# HALUNG Clip Control V12 — Architecture

## System Overview

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
           │ (X-Halung-Token)
           │
    ┌──────▼──────┐
    │  Raspberry Pi 5
    │  Edge Agent
    ├──────────────┤
    │ State Machine│  Cycle: READY → LOCK → CHECKING → VALIDATED
    │ I²C + GPIO   │
    │ LCD Display  │
    │ Heartbeat    │
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
POST /api/edge/stations/<station_code>/heartbeat
Header: X-Halung-Token: <api_token>

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
GET /api/edge/stations/<station_code>/config
Header: X-Halung-Token: <api_token>

Response:
{
  "ok": true,
  "config": {
    "hardware": { /* MCP/GPIO mapping */ },
    "points": [ /* SW/LED channels */ ]
  }
}
```

### Report Cycle (Raspberry → Dashboard)
```
POST /api/edge/stations/<station_code>/cycles
Header: X-Halung-Token: <api_token>

{
  "status": "OK",
  "cycle_time_seconds": 45.3,
  "swlock_time": "2026-10-27T14:30:15Z",
  "butok_time": "2026-10-27T14:31:00Z",
  "actual_per_hour": 79.3,
  "efficiency": 88.1,
  "operator": "Oussama"
}
```

## State Machine

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
   - Initializes hardware (MCP, GPIO, LCD)
   - Enters main loop

3. **Heartbeat (every 1 second):**
   - Raspberry sends state + I/O status
   - Dashboard records health
   - Raspberry checks for commands

4. **Config refresh (every 5 seconds):**
   - Raspberry fetches active program if changed
   - Loads new hardware mapping
   - Resets state machine

5. **Cycle completion:**
   - Raspberry sends cycle report
   - Dashboard records OK/NOK, calculates KPIs
   - Updates production counters

## Error Handling

- **I²C failure:** Log error, set state to ERROR, freeze I/O
- **Network timeout:** Buffer cycles locally, sync on reconnect
- **Invalid config:** Revert to last known good, alert Dashboard
- **Unexpected button:** Set WRONG_CLIP, wait for release
- **LED/relay stuck:** Log hardware error, continue (graceful degrade)
