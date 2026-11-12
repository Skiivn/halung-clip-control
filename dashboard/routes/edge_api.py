"""Raspberry-facing API. Every call requires the Bearer token.

Flow: heartbeat -> (if assigned != active) GET config -> apply -> POST program-ack.
The dashboard only calls a program "active" after the Raspberry acknowledges
the exact program_id + version it was assigned.
"""
import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from dashboard.auth import edge_token_required
from dashboard.database import get_db
from dashboard.services import program_service as ps

bp = Blueprint("edge_api", __name__, url_prefix="/api/edge")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _station(con, code):
    return con.execute("SELECT * FROM stations WHERE code=? AND enabled=1", (code,)).fetchone()


@bp.post("/<code>/heartbeat")
@edge_token_required
def heartbeat(code):
    body = request.get_json(silent=True) or {}
    con = get_db()
    st = _station(con, code)
    if st is None:
        con.close()
        return jsonify(ok=False, error="unknown or disabled station"), 404
    con.execute(
        "UPDATE stations SET last_seen=?, ip_address=?, agent_version=?, state_json=?, status='ONLINE', "
        "last_error=? WHERE code=?",
        (_now(), request.remote_addr, body.get("agent_version"), json.dumps(body), body.get("last_error"), code))
    con.commit()
    con.close()
    return jsonify(ok=True, assigned_program_id=st["manual_program_id"],
                   assigned_version=st["assigned_version"],
                   config_update_needed=bool(st["manual_program_id"]) and (
                       st["active_program_id"] != st["manual_program_id"]
                       or st["active_version"] != st["assigned_version"]))


@bp.get("/<code>/config")
@edge_token_required
def config(code):
    con = get_db()
    st = _station(con, code)
    con.close()
    if st is None:
        return jsonify(ok=False, error="unknown or disabled station"), 404
    program = ps.get_program(st["manual_program_id"]) if st["manual_program_id"] else None
    if program:
        # Re-check at delivery time: the program may have been edited or the profile changed.
        compatible, msg = ps.check_compatibility(program, st["hardware_profile"])
        if not compatible or not program["active"]:
            return jsonify(ok=False, error=msg if not compatible else "program disabled"), 409
    return jsonify(ok=True, station=code, hardware_profile=st["hardware_profile"],
                   program=ps.edge_payload(program) if program else None)


@bp.post("/<code>/program-ack")
@edge_token_required
def program_ack(code):
    body = request.get_json(silent=True) or {}
    con = get_db()
    st = _station(con, code)
    if st is None:
        con.close()
        return jsonify(ok=False, error="unknown or disabled station"), 404
    pid, ver = body.get("program_id"), body.get("version")
    if (pid, ver) != (st["manual_program_id"], st["assigned_version"]):
        con.close()
        return jsonify(ok=False, error="ack does not match assigned program/version"), 409
    con.execute("UPDATE stations SET active_program_id=?, active_version=?, active_ack_at=? WHERE code=?",
                (pid, ver, _now(), code))
    con.execute("INSERT INTO station_events(created_at, station_code, event_type, payload_json) VALUES(?,?,?,?)",
                (_now(), code, "PROGRAM_ACTIVE", json.dumps({"program_id": pid, "version": ver})))
    con.commit()
    con.close()
    return jsonify(ok=True)


@bp.post("/<code>/cycles")
@edge_token_required
def cycles(code):
    """Accepts buffered cycles; client_uid makes re-sends after a network outage idempotent."""
    body = request.get_json(silent=True) or {}
    items = body.get("cycles")
    if not isinstance(items, list):
        return jsonify(ok=False, error="cycles must be a list"), 400
    con = get_db()
    st = _station(con, code)
    if st is None:
        con.close()
        return jsonify(ok=False, error="unknown or disabled station"), 404
    accepted = []
    for c in items:
        uid = c.get("client_uid")
        status = c.get("status", "OK")
        if not uid or status not in ("OK", "NOK", "INTERRUPTED"):
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO cycles(cycle_time, station_code, variant_code, variant_ref, "
            "cycle_time_seconds, status, failure_code, details_json, client_uid, swlock_time, butok_time) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (c.get("ended_at") or _now(), code, c.get("variant"), c.get("layout"),
             c.get("duration_s"), status, c.get("failure_code"), json.dumps(c), uid,
             c.get("swlock_time"), c.get("butok_time")))
        accepted.append(uid)  # duplicates are also acknowledged so the Pi can drop them
    con.commit()
    con.close()
    return jsonify(ok=True, accepted=accepted)
