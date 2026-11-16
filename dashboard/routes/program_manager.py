"""Program Manager + station administration (browser side, login required)."""
import json
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, session

from dashboard.auth import login_required
from dashboard.config import HARDWARE_PROFILES, STATION_OFFLINE_SECONDS
from dashboard.database import get_db
from dashboard.services import program_service as ps

bp = Blueprint("program_manager", __name__)


def _user():
    return session.get("user", "admin")


def _err(exc, code=400):
    return jsonify(ok=False, error=str(exc)), code


def station_view(row):
    """Station dict with computed live status and program verification."""
    d = dict(row)
    seen = d.get("last_seen")
    online = False
    if seen:
        online = (datetime.now() - datetime.fromisoformat(seen)).total_seconds() <= STATION_OFFLINE_SECONDS
    d["status"] = "DISABLED" if not d["enabled"] else ("ONLINE" if online else "OFFLINE")
    d["program_verified"] = bool(
        d.get("manual_program_id") and d.get("active_program_id") == d["manual_program_id"]
        and d.get("active_version") == d.get("assigned_version"))
    d["state"] = json.loads(d["state_json"]) if d.get("state_json") else None
    d["hardware_status"] = (d["state"] or {}).get("hardware_status", "UNKNOWN")
    return d


@bp.route("/programs")
@login_required
def page():
    return render_template("program_manager.html", profiles=HARDWARE_PROFILES)


# ---- programs -------------------------------------------------------------
@bp.get("/api/programs")
@login_required
def api_list():
    return jsonify(ok=True, programs=ps.list_programs())


@bp.post("/api/programs")
@login_required
def api_create():
    try:
        return jsonify(ok=True, program=ps.create_program(request.get_json(force=True), _user())), 201
    except ps.ProgramError as e:
        return _err(e)


@bp.put("/api/programs/<int:pid>")
@login_required
def api_update(pid):
    try:
        return jsonify(ok=True, program=ps.update_program(pid, request.get_json(force=True), _user()))
    except ps.ProgramError as e:
        return _err(e, 404 if "not found" in str(e) else 400)


@bp.post("/api/programs/<int:pid>/duplicate")
@login_required
def api_duplicate(pid):
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(ok=True, program=ps.duplicate_program(pid, body.get("name"), _user())), 201
    except ps.ProgramError as e:
        return _err(e, 404)


@bp.post("/api/programs/<int:pid>/active")
@login_required
def api_active(pid):
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(ok=True, program=ps.set_active(pid, bool(body.get("active")), _user()))
    except ps.ProgramError as e:
        return _err(e, 404)


@bp.get("/api/programs/<int:pid>/history")
@login_required
def api_history(pid):
    return jsonify(ok=True, history=ps.program_history(pid))


# ---- stations -------------------------------------------------------------
@bp.get("/api/stations")
@login_required
def api_stations():
    con = get_db()
    rows = con.execute("SELECT * FROM stations ORDER BY code").fetchall()
    con.close()
    return jsonify(ok=True, stations=[station_view(r) for r in rows])


@bp.post("/api/stations")
@login_required
def api_station_add():
    b = request.get_json(force=True)
    code = (b.get("code") or "").strip().upper()
    profile = b.get("hardware_profile", "HALUNG_3IO_BENCH_V1")
    if not code:
        return _err("code is required")
    if profile not in HARDWARE_PROFILES:
        return _err(f"unknown hardware profile {profile}")
    con = get_db()
    try:
        con.execute(
            "INSERT INTO stations(code, display_name, hardware_profile, source, expected_ip, registered_at) "
            "VALUES(?,?,?,?,?,?)",
            (code, b.get("display_name") or code, profile, "RASPBERRY",
             b.get("expected_ip") or None, datetime.now().isoformat(timespec="seconds")))
        con.commit()
    except Exception as exc:
        return _err("station already exists" if "UNIQUE" in str(exc) else exc)
    finally:
        con.close()
    return jsonify(ok=True), 201


@bp.put("/api/stations/<code>")
@login_required
def api_station_update(code):
    b = request.get_json(force=True)
    if "hardware_profile" in b and b["hardware_profile"] not in HARDWARE_PROFILES:
        return _err("unknown hardware profile")
    allowed = ("display_name", "hardware_profile", "expected_ip", "enabled", "notes")
    sets = {k: b[k] for k in allowed if k in b}
    if not sets:
        return _err("nothing to update")
    con = get_db()
    cur = con.execute(
        f"UPDATE stations SET {', '.join(k + '=?' for k in sets)} WHERE code=?",
        (*sets.values(), code))
    con.commit()
    con.close()
    return (jsonify(ok=True) if cur.rowcount else _err("station not found", 404))


@bp.post("/api/stations/<code>/assign-program")
@login_required
def api_assign(code):
    b = request.get_json(force=True)
    try:
        prog = ps.assign_to_station(int(b.get("program_id", 0)), code, _user())
    except ps.ProgramError as e:
        return _err(e, 404 if "not found" in str(e) else 400)
    return jsonify(ok=True, program_id=prog["id"], version=prog["version"],
                   message="queued; the Raspberry must acknowledge it")


@bp.get("/api/stations/<code>/program-status")
@login_required
def api_program_status(code):
    con = get_db()
    row = con.execute("SELECT * FROM stations WHERE code=?", (code,)).fetchone()
    con.close()
    if row is None:
        return _err("station not found", 404)
    v = station_view(row)
    return jsonify(ok=True, assigned_program_id=v["manual_program_id"], assigned_version=v["assigned_version"],
                   active_program_id=v["active_program_id"], active_version=v["active_version"],
                   active_ack_at=v["active_ack_at"], verified=v["program_verified"], status=v["status"])
