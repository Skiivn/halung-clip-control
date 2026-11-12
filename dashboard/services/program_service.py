"""Program Manager business logic (1-23 point programs, versioned, auditable).

A program is pure data: the Raspberry engine never changes when a program does.
"""
import json
from datetime import datetime

from dashboard.config import HARDWARE_PROFILES
from dashboard.database import get_db

MAX_POINTS = 23


class ProgramError(ValueError):
    """Invalid program data or operation."""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def parse_switches(raw):
    """Return a sorted, de-duplicated list of ints in 1..23, or raise ProgramError."""
    if not isinstance(raw, (list, tuple)):
        raise ProgramError("required_switches must be a list")
    out = set()
    for v in raw:
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ProgramError(f"invalid switch: {v!r}")
        if not 1 <= n <= MAX_POINTS:
            raise ProgramError(f"switch {n} out of range 1..{MAX_POINTS}")
        out.add(n)
    if not out:
        raise ProgramError("at least one switch is required")
    return sorted(out)


def row_to_dict(row):
    d = dict(row)
    d["required_switches"] = json.loads(d["required_switches"])
    return d


def edge_payload(program):
    """Exact JSON the Raspberry stores as active_program.json."""
    return {
        "program_id": program["id"],
        "version": program["version"],
        "name": program["name"],
        "layout": program.get("layout"),
        "variant": program.get("variant"),
        "required_switches": program["required_switches"],
        "swlock_required": bool(program["swlock_required"]),
        "butok_required": bool(program["butok_required"]),
        "cycle_time_target": program["cycle_time_target"],
    }


def check_compatibility(program, hardware_profile):
    """Return (ok, message). A program may not use points the station lacks."""
    profile = HARDWARE_PROFILES.get(hardware_profile)
    if profile is None:
        return False, f"unknown hardware profile {hardware_profile}"
    too_high = [n for n in program["required_switches"] if n > profile["channels"]]
    if too_high:
        return False, (f"{hardware_profile} has {profile['channels']} points; "
                       f"program uses SW{too_high}")
    return True, "compatible"


def _get_row(con, pid):
    return row_to_dict(con.execute("SELECT * FROM manual_programs WHERE id=?", (pid,)).fetchone())


def _history(con, program, action, user):
    con.execute(
        "INSERT INTO program_history(program_id, version, changed_at, changed_by, action, snapshot_json) "
        "VALUES(?,?,?,?,?,?)",
        (program["id"], program["version"], _now(), user, action, json.dumps(program)),
    )


def _clean(data):
    name = (data.get("name") or "").strip()
    if not name:
        raise ProgramError("name is required")
    try:
        target = float(data.get("cycle_time_target", 30))
    except (TypeError, ValueError):
        raise ProgramError("cycle_time_target must be a number")
    if target <= 0:
        raise ProgramError("cycle_time_target must be > 0")
    return {
        "name": name,
        "required_switches": parse_switches(data.get("required_switches")),
        "layout": (data.get("layout") or "").strip() or None,
        "variant": (data.get("variant") or "").strip() or None,
        "swlock_required": 1 if data.get("swlock_required", True) else 0,
        "butok_required": 1 if data.get("butok_required", True) else 0,
        "cycle_time_target": target,
    }


def list_programs(include_inactive=True):
    con = get_db()
    sql = "SELECT * FROM manual_programs"
    if not include_inactive:
        sql += " WHERE active=1"
    rows = con.execute(sql + " ORDER BY name").fetchall()
    con.close()
    return [row_to_dict(r) for r in rows]


def get_program(program_id):
    con = get_db()
    row = con.execute("SELECT * FROM manual_programs WHERE id=?", (program_id,)).fetchone()
    con.close()
    return row_to_dict(row) if row else None


def create_program(data, user="system"):
    c = _clean(data)
    con = get_db()
    try:
        cur = con.execute(
            "INSERT INTO manual_programs(name, required_switches, swlock_required, butok_required, "
            "cycle_time_target, layout, variant, version, active, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,1,1,?,?)",
            (c["name"], json.dumps(c["required_switches"]), c["swlock_required"],
             c["butok_required"], c["cycle_time_target"], c["layout"], c["variant"], _now(), _now()),
        )
        pid = cur.lastrowid
        _history(con, _get_row(con, pid), "CREATE", user)
        con.commit()
    except Exception as exc:
        con.rollback()
        if "UNIQUE" in str(exc):
            raise ProgramError(f"program name '{c['name']}' already exists")
        raise
    finally:
        con.close()
    return get_program(pid)


def update_program(program_id, data, user="system"):
    if get_program(program_id) is None:
        raise ProgramError("program not found")
    c = _clean(data)
    con = get_db()
    try:
        con.execute(
            "UPDATE manual_programs SET name=?, required_switches=?, swlock_required=?, butok_required=?, "
            "cycle_time_target=?, layout=?, variant=?, version=version+1, updated_at=? WHERE id=?",
            (c["name"], json.dumps(c["required_switches"]), c["swlock_required"], c["butok_required"],
             c["cycle_time_target"], c["layout"], c["variant"], _now(), program_id),
        )
        _history(con, _get_row(con, program_id), "UPDATE", user)
        con.commit()
    except Exception as exc:
        con.rollback()
        if "UNIQUE" in str(exc):
            raise ProgramError(f"program name '{c['name']}' already exists")
        raise
    finally:
        con.close()
    return get_program(program_id)


def duplicate_program(program_id, new_name=None, user="system"):
    src = get_program(program_id)
    if src is None:
        raise ProgramError("program not found")
    existing = {p["name"] for p in list_programs()}
    base = (new_name or "").strip() or f"{src['name']}_COPY"
    name, i = base, 2
    while name in existing:
        name, i = f"{base}_{i}", i + 1
    src["name"] = name
    return create_program(src, user)


def set_active(program_id, active, user="system"):
    """Disable/enable (soft delete; history and past cycles are preserved)."""
    if get_program(program_id) is None:
        raise ProgramError("program not found")
    con = get_db()
    con.execute("UPDATE manual_programs SET active=?, version=version+1, updated_at=? WHERE id=?",
                (1 if active else 0, _now(), program_id))
    _history(con, _get_row(con, program_id), "ENABLE" if active else "DISABLE", user)
    con.commit()
    con.close()
    return get_program(program_id)


def program_history(program_id):
    con = get_db()
    rows = con.execute(
        "SELECT version, changed_at, changed_by, action FROM program_history "
        "WHERE program_id=? ORDER BY id DESC", (program_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def assign_to_station(program_id, station_code, user="system"):
    """Mark a program version as wanted on a station; the Raspberry fetches it
    on its next config poll and acknowledges it (see edge_api)."""
    program = get_program(program_id)
    if program is None:
        raise ProgramError("program not found")
    if not program["active"]:
        raise ProgramError("program is disabled")
    con = get_db()
    st = con.execute("SELECT * FROM stations WHERE code=?", (station_code,)).fetchone()
    if st is None:
        con.close()
        raise ProgramError("station not found")
    ok, msg = check_compatibility(program, st["hardware_profile"])
    if not ok:
        con.close()
        raise ProgramError(msg)
    con.execute(
        "UPDATE stations SET manual_program_id=?, assigned_version=?, variant_code=?, variant_ref=? WHERE code=?",
        (program_id, program["version"], program.get("variant"), program.get("layout"), station_code),
    )
    con.execute("INSERT INTO station_events(created_at, station_code, event_type, payload_json) VALUES(?,?,?,?)",
                (_now(), station_code, "PROGRAM_ASSIGNED",
                 json.dumps({"program_id": program_id, "version": program["version"], "by": user})))
    con.commit()
    con.close()
    return program
