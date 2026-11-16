"""HTTP client for Dashboard heartbeat, program delivery, and cycle sync.

Uses the Python standard library so the edge agent has no extra HTTP dependency.
"""
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request
import uuid
from pathlib import Path

logger = logging.getLogger("halung-agent.network")


class DashboardError(RuntimeError):
    """Dashboard returned an unsuccessful response."""


class DashboardClient:
    """Communicate with one registered station's Dashboard endpoints."""

    def __init__(self, base_url, station_code, token, timeout=3):
        if not base_url or not station_code or not token:
            raise ValueError("dashboard_url, station_code, and api_token are required")
        self.base_url = base_url.rstrip("/")
        self.station_code = station_code
        self.token = token
        self.timeout = float(timeout)

    def _request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DashboardError(f"Dashboard returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DashboardError(f"Dashboard unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DashboardError("Dashboard returned invalid JSON") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise DashboardError(result.get("error", "Dashboard request failed"))
        return result

    def heartbeat(self, payload):
        return self._request("POST", f"/api/edge/{self.station_code}/heartbeat", payload)

    def get_config(self):
        return self._request("GET", f"/api/edge/{self.station_code}/config")

    def acknowledge_program(self, program_id, version):
        return self._request(
            "POST",
            f"/api/edge/{self.station_code}/program-ack",
            {"program_id": program_id, "version": version},
        )

    def upload_cycles(self, records):
        return self._request(
            "POST", f"/api/edge/{self.station_code}/cycles", {"cycles": records}
        )


class CycleOutbox:
    """Durable SQLite queue for results awaiting Dashboard synchronization."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS cycle_outbox (
                    client_uid TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def _connect(self):
        con = sqlite3.connect(self.db_path, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    def enqueue(self, record):
        """Persist a result before attempting network delivery; return its stable ID."""
        if not isinstance(record, dict):
            raise ValueError("cycle record must be an object")
        payload = dict(record)
        uid = str(payload.get("client_uid") or uuid.uuid4())
        payload["client_uid"] = uid
        with self._connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO cycle_outbox(client_uid, payload_json) VALUES(?, ?)",
                (uid, json.dumps(payload, separators=(",", ":"))),
            )
        return uid

    def pending(self, limit=100):
        with self._connect() as con:
            rows = con.execute(
                "SELECT client_uid, payload_json FROM cycle_outbox ORDER BY rowid LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [{"client_uid": row["client_uid"], **json.loads(row["payload_json"])}
                for row in rows]

    def acknowledge(self, client_uids):
        """Remove only records explicitly accepted by the Dashboard."""
        if not client_uids:
            return
        with self._connect() as con:
            con.executemany(
                "DELETE FROM cycle_outbox WHERE client_uid=?",
                [(str(uid),) for uid in client_uids],
            )

    def __len__(self):
        with self._connect() as con:
            return con.execute("SELECT COUNT(*) FROM cycle_outbox").fetchone()[0]


def validate_program(program, hardware_profile):
    """Reject malformed or physically incompatible configs before acknowledging."""
    if not isinstance(program, dict):
        raise ValueError("program config must be an object")
    points = program.get("required_switches")
    if not isinstance(points, list) or not points:
        raise ValueError("program must contain at least one required switch")
    if any(type(point) is not int or not 1 <= point <= 23 for point in points):
        raise ValueError("required_switches must contain integers from 1 through 23")
    if len(set(points)) != len(points):
        raise ValueError("required_switches must not contain duplicates")
    capacities = {"HALUNG_3IO_BENCH_V1": 3, "HALUNG_23IO_V1": 23}
    capacity = capacities.get(hardware_profile)
    if capacity is None:
        raise ValueError(f"unsupported hardware profile: {hardware_profile}")
    if max(points) > capacity:
        raise ValueError(f"{hardware_profile} supports only SW1..SW{capacity}")
    for key in ("program_id", "version", "name"):
        if key not in program:
            raise ValueError(f"program is missing {key}")
    if type(program["program_id"]) is not int or type(program["version"]) is not int:
        raise ValueError("program_id and version must be integers")
    return program


def write_active_program(path, program):
    """Atomically persist config so power loss cannot leave a partial JSON file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(program, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(target)
