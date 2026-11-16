"""Program Manager + Edge API tests (isolated temp database)."""
import importlib
import sys

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HALUNG_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("HALUNG_EDGE_API_TOKEN", "tok")
    monkeypatch.setenv("HALUNG_ADMIN_PASSWORD", "pw")
    for m in [m for m in sys.modules if m.startswith("dashboard")]:
        del sys.modules[m]
    app_mod = importlib.import_module("dashboard.app")
    c = app_mod.app.test_client()
    c.post("/", data={"username": "admin", "password": "pw"})
    return c


EDGE = {"Authorization": "Bearer tok"}


def mk_station(c, code="CT-06", profile="HALUNG_3IO_BENCH_V1"):
    assert c.post("/api/stations", json={"code": code, "hardware_profile": profile}).status_code == 201


def mk_prog(c, name="P", sw=(1, 2, 3)):
    r = c.post("/api/programs", json={"name": name, "required_switches": list(sw),
                                      "layout": "L1", "variant": "V1"})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["program"]


def test_validation(client):
    for bad in ([], [0], [24], ["x"]):
        assert client.post("/api/programs", json={"name": "B", "required_switches": bad}).status_code == 400
    assert client.post("/api/programs", json={"name": "", "required_switches": [1]}).status_code == 400


def test_any_subset_and_versioning(client):
    p = mk_prog(client, "A", [2, 5, 8, 14, 19])
    assert p["required_switches"] == [2, 5, 8, 14, 19] and p["version"] == 1
    r = client.put(f"/api/programs/{p['id']}", json={**p, "required_switches": list(range(1, 24))})
    assert r.get_json()["program"]["version"] == 2
    hist = client.get(f"/api/programs/{p['id']}/history").get_json()["history"]
    assert [h["action"] for h in hist] == ["UPDATE", "CREATE"]


def test_duplicate_and_disable(client):
    p = mk_prog(client, "A", [1])
    d = client.post(f"/api/programs/{p['id']}/duplicate", json={}).get_json()["program"]
    assert d["name"] == "A_COPY" and d["id"] != p["id"]
    assert client.post(f"/api/programs/{p['id']}/active", json={"active": False}).get_json()["program"]["active"] == 0


def test_bench_rejects_23_point_program(client):
    mk_station(client)
    p = mk_prog(client, "FULL", range(1, 24))
    r = client.post("/api/stations/CT-06/assign-program", json={"program_id": p["id"]})
    assert r.status_code == 400 and "3 points" in r.get_json()["error"]


def test_edge_flow_assign_fetch_ack_verify(client):
    mk_station(client)
    p = mk_prog(client)
    assert client.post("/api/stations/CT-06/assign-program", json={"program_id": p["id"]}).status_code == 200
    assert client.get("/api/stations/CT-06/program-status").get_json()["verified"] is False

    assert client.post("/api/edge/CT-06/heartbeat", json={"state": "READY"}).status_code == 401
    hb = client.post("/api/edge/CT-06/heartbeat",
                     json={"state": "NOT_CONFIGURED", "hardware_status": "NOT_CONFIGURED"},
                     headers=EDGE).get_json()
    assert hb["config_update_needed"] is True
    cfg = client.get("/api/edge/CT-06/config", headers=EDGE).get_json()
    assert cfg["program"]["required_switches"] == [1, 2, 3]

    # wrong version ack is refused, right one is accepted
    assert client.post("/api/edge/CT-06/program-ack", json={"program_id": p["id"], "version": 99},
                       headers=EDGE).status_code == 409
    assert client.post("/api/edge/CT-06/program-ack", json={"program_id": p["id"], "version": 1},
                       headers=EDGE).status_code == 200
    st = client.get("/api/stations/CT-06/program-status").get_json()
    assert st["verified"] is True and st["status"] == "ONLINE"
    station = client.get("/api/stations").get_json()["stations"][0]
    assert station["status"] == "ONLINE"
    assert station["hardware_status"] == "NOT_CONFIGURED"

    # editing the program bumps the version -> must be re-sent
    client.put(f"/api/programs/{p['id']}", json={**p, "required_switches": [1]})
    client.post("/api/stations/CT-06/assign-program", json={"program_id": p["id"]})
    assert client.get("/api/stations/CT-06/program-status").get_json()["verified"] is False


def test_cycle_upload_is_idempotent(client):
    mk_station(client)
    body = {"cycles": [{"client_uid": "u1", "status": "OK", "duration_s": 12.5},
                       {"client_uid": "u1", "status": "OK", "duration_s": 12.5}]}
    for _ in range(2):
        r = client.post("/api/edge/CT-06/cycles", json=body, headers=EDGE).get_json()
        assert r["accepted"] == ["u1", "u1"]
    invalid = client.post("/api/edge/CT-06/cycles", json={"cycles": [{"status": "OK"}]},
                          headers=EDGE)
    assert invalid.status_code == 400
    from dashboard.database import get_db
    con = get_db()
    assert con.execute("SELECT COUNT(*) FROM cycles").fetchone()[0] == 1
    con.close()


def test_api_requires_login(client):
    client.get("/logout")
    assert client.get("/api/programs").status_code == 401
