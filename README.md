# HALUNG Clip Control V12

**Industrial harness clip test system.** Raspberry Pi 5 + Windows Dashboard + modifiable source code.

Test 1–23 connector points. Manage programs, production tracking, NAS backups, and live station monitoring.

---

## Features

- **Clip Test Engine** — State machine (READY → LOCK → CHECKING → VALIDATED → RELEASE)
- **Manual Programs** — Select 1–23 points per program; no recompile needed
- **Two Hardware Profiles** — 3-point bench (HALUNG_3IO_BENCH_V1) or 23-point production (HALUNG_23IO_V1)
- **LCD Display** — Real-time cycle state and diagnostics on Raspberry
- **Raspberry Manager** — Add stations, SSH install, health monitoring
- **Production Tracking** — OK/NOK counters, efficiency, cycle times, traceability
- **NAS Integration** — Automatic report generation and backup to network storage
- **Full Source Code** — 100% editable in VS Code; no compiled binaries or mocks

---

## Quick Start — Windows Dashboard

### 1. Clone Repository
```bash
git clone https://github.com/Skiivn/halung-clip-control.git
cd halung-clip-control
```

### 2. Create Environment
```powershell
# Windows PowerShell
py -3 -m venv .venv
.\.\ venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure
```bash
cp .env.example .env
# Edit .env with your admin password and secret
notepad .env
```

### 4. Initialize Database
```bash
python dashboard/app.py
# Database will auto-initialize on first run
```

### 5. Open Dashboard
- **PC:** `http://127.0.0.1:8080`
- **Another device on LAN:** `http://<PC_IP>:8080`
- **Login:** admin / admin123 (from `.env`)

---

## Project Structure

```
halung-clip-control/
├── dashboard/                   # Windows Flask application
│   ├── app.py                   # Main Flask app, routes, API
│   ├── config.py                # Configuration, paths, constants
│   ├── database.py              # SQLite schema, initialization
│   ├── routes/                  # Flask route modules
│   ├── services/                # Business logic
│   ├── templates/               # HTML (Jinja2)
│   ├── static/                  # CSS, JavaScript, assets
│   └── data/                    # SQLite, backups, reports (git-ignored)
│
├── raspberry/                   # Raspberry Pi 5 Edge Agent
│   ├── agent.py                 # Main loop, API client, heartbeat
│   ├── config.py                # Configuration loader
│   ├── hardware/                # Hardware abstraction
│   ├── engine/                  # Clip Test state machine
│   ├── network/                 # Communication
│   ├── config/                  # Configuration files (local)
│   ├── tests/                   # Unit tests
│   └── systemd/                 # Linux service file
│
├── scripts/
├── docs/
├── .gitignore
├── .env.example
├── requirements.txt
└── README.md
```

---

## Development in VS Code

1. **Open folder:** `File → Open Folder → halung-clip-control`
2. **Select Python interpreter:** `.venv` from the project
3. **Install extensions:** Python, Flask, SQLite (optional)
4. **Edit freely:** All source is `.py`, `.html`, `.js`, `.css` — no compilation needed
5. **Run:** Open terminal, `python dashboard/app.py`

---

## Testing

```bash
# Unit tests (state machine, config contract, I/O adapter)
pytest raspberry/tests/ -v

# Compile check (Python syntax)
python -m py_compile dashboard/app.py raspberry/agent.py
```

---

**Built from scratch — V12 — October 2026**
