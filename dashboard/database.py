"""SQLite database schema and initialization."""
import sqlite3
from pathlib import Path
from datetime import datetime
from dashboard.config import DB_PATH


def get_db() -> sqlite3.Connection:
    """Get database connection with Row factory."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _add_columns(con, table, columns):
    """Add missing columns (non-destructive migration; existing data is kept)."""
    have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _migrate(con):
    """Program Manager / Edge API schema additions."""
    _add_columns(con, "manual_programs", {
        "layout": "TEXT",
        "variant": "TEXT",
        "version": "INTEGER NOT NULL DEFAULT 1",
    })
    _add_columns(con, "stations", {
        "assigned_version": "INTEGER",      # version the dashboard wants active
        "active_program_id": "INTEGER",     # program acknowledged by the Raspberry
        "active_version": "INTEGER",
        "active_ack_at": "TEXT",
    })
    _add_columns(con, "cycles", {"client_uid": "TEXT"})
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cycles_uid ON cycles(client_uid) "
                "WHERE client_uid IS NOT NULL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS program_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            changed_at TEXT NOT NULL,
            changed_by TEXT,
            action TEXT NOT NULL,
            snapshot_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_program_history ON program_history(program_id, version);
        """
    )


def init_db():
    """Initialize database schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = get_db()

    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            display_name TEXT,
            hardware_profile TEXT NOT NULL DEFAULT 'HALUNG_23IO_V1',
            source TEXT NOT NULL DEFAULT 'SIMULATOR',
            status TEXT DEFAULT 'OFFLINE',
            state_json TEXT,
            ip_address TEXT,
            expected_ip TEXT,
            agent_version TEXT,
            last_seen TEXT,
            last_error TEXT,
            sync_status TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            registered_at TEXT,
            notes TEXT,
            manual_program_id INTEGER,
            layout_id INTEGER,
            variant_ref TEXT,
            variant_code TEXT
        );

        CREATE TABLE IF NOT EXISTS manual_programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            required_switches TEXT NOT NULL,
            swlock_required INTEGER NOT NULL DEFAULT 1,
            butok_required INTEGER NOT NULL DEFAULT 1,
            cycle_time_target REAL NOT NULL DEFAULT 30.0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_time TEXT NOT NULL,
            station_code TEXT NOT NULL,
            operator_name TEXT,
            variant_code TEXT,
            variant_ref TEXT,
            target_per_hour REAL,
            actual_per_hour REAL,
            efficiency REAL,
            swlock_time TEXT,
            butok_time TEXT,
            cycle_time_seconds REAL,
            status TEXT DEFAULT 'OK',
            serial_number TEXT,
            failure_code TEXT,
            details_json TEXT
        );

        CREATE TABLE IF NOT EXISTS station_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            station_code TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT
        );

        CREATE TABLE IF NOT EXISTS station_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sampled_at TEXT NOT NULL,
            station_code TEXT NOT NULL,
            health_status TEXT NOT NULL,
            last_error TEXT,
            ip_address TEXT,
            agent_version TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_station_health_time ON station_health(sampled_at);
        CREATE INDEX IF NOT EXISTS idx_station_health_station ON station_health(station_code, sampled_at);
        CREATE INDEX IF NOT EXISTS idx_cycles_station ON cycles(station_code);
        CREATE INDEX IF NOT EXISTS idx_cycles_time ON cycles(cycle_time);
        CREATE INDEX IF NOT EXISTS idx_events_station ON station_events(station_code);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            filename TEXT NOT NULL,
            size_bytes INTEGER DEFAULT 0,
            kind TEXT DEFAULT 'AUTO',
            status TEXT DEFAULT 'OK'
        );

        CREATE TABLE IF NOT EXISTS nas_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            job_key TEXT UNIQUE,
            job_type TEXT NOT NULL,
            period_start TEXT,
            period_end TEXT,
            local_file TEXT NOT NULL,
            remote_file TEXT,
            status TEXT DEFAULT 'PENDING',
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            sent_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_nas_jobs_status ON nas_jobs(status, created_at);
    """
    )

    _migrate(con)

    # Insert default settings if empty
    if con.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        defaults = {
            "buzzer_enabled": "1",
            "bell_enabled": "1",
            "missing_component_alarm": "1",
            "wrong_clip_alarm": "1",
        }
        for key, value in defaults.items():
            con.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?)",
                (key, value),
            )

    con.commit()
    con.close()
