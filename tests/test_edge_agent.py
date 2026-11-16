"""Edge agent networking, program persistence, and durable cycle outbox tests."""
import json

import pytest

from raspberry.agent import Agent
from raspberry.network.dashboard_client import (
    CycleOutbox,
    DashboardError,
    validate_program,
    write_active_program,
)


def test_program_validation_respects_station_hardware():
    program = {"program_id": 1, "version": 1, "name": "P", "required_switches": [1, 3]}
    assert validate_program(program, "HALUNG_3IO_BENCH_V1") == program
    with pytest.raises(ValueError, match="supports only"):
        validate_program({**program, "required_switches": [1, 4]}, "HALUNG_3IO_BENCH_V1")
    with pytest.raises(ValueError, match="integers"):
        validate_program({**program, "required_switches": [True]}, "HALUNG_23IO_V1")


def test_outbox_survives_restart_and_removes_only_acknowledged(tmp_path):
    db = tmp_path / "outbox.sqlite3"
    first = CycleOutbox(db)
    uid1 = first.enqueue({"status": "OK", "duration_s": 12.5})
    uid2 = first.enqueue({"status": "NOK", "failure_code": "WRONG_CLIP"})
    assert first.enqueue({"client_uid": uid1, "status": "OK"}) == uid1
    assert len(first) == 2

    restarted = CycleOutbox(db)
    assert [r["client_uid"] for r in restarted.pending()] == [uid1, uid2]
    restarted.acknowledge([uid1])
    assert [r["client_uid"] for r in restarted.pending()] == [uid2]


def test_active_program_file_is_complete_json(tmp_path):
    path = tmp_path / "config" / "active.json"
    program = {"program_id": 8, "version": 2, "required_switches": [1, 2, 3]}
    write_active_program(path, program)
    assert json.loads(path.read_text(encoding="utf-8")) == program
    assert not path.with_name("active.json.tmp").exists()


class FakeDashboard:
    def __init__(self):
        self.acked = []
        self.uploaded = []

    def heartbeat(self, payload):
        self.heartbeat_payload = payload
        return {"config_update_needed": not bool(self.acked)}

    def get_config(self):
        return {
            "hardware_profile": "HALUNG_3IO_BENCH_V1",
            "program": {
                "program_id": 7,
                "version": 3,
                "name": "PROGRAM_03",
                "layout": "LAYOUT",
                "variant": "VARIANT",
                "required_switches": [1, 3],
            },
        }

    def acknowledge_program(self, program_id, version):
        self.acked.append((program_id, version))
        return {"ok": True}

    def upload_cycles(self, records):
        self.uploaded.extend(records)
        return {"accepted": [r["client_uid"] for r in records]}


def make_agent(tmp_path):
    config = tmp_path / "station.json"
    config.write_text(json.dumps({
        "station_code": "CT-06",
        "hardware_profile": "HALUNG_3IO_BENCH_V1",
        "dashboard_url": "http://dashboard",
        "api_token": "test-token",
        "active_program_path": str(tmp_path / "active.json"),
        "outbox_path": str(tmp_path / "outbox.sqlite3"),
    }), encoding="utf-8")
    return Agent(config)


def test_agent_persists_program_before_ack_and_syncs_results(tmp_path):
    agent = make_agent(tmp_path)
    fake = FakeDashboard()
    agent.client = fake
    agent.sync_program_if_needed({"config_update_needed": True})
    uid = agent.queue_cycle_report({
        "status": "OK",
        "cycle_time_seconds": 12.5,
        "swlock_time": "2026-11-16T07:00:00",
        "butok_time": "2026-11-16T07:00:12.5",
    })

    agent.run_once()

    saved = json.loads(agent.active_program_path.read_text(encoding="utf-8"))
    assert saved["program_id"] == 7
    assert fake.acked == [(7, 3)]
    assert fake.uploaded[0]["client_uid"] == uid
    assert fake.uploaded[0]["duration_s"] == 12.5
    assert fake.uploaded[0]["layout"] == "LAYOUT"
    assert len(agent.outbox) == 0


def test_failed_program_validation_is_not_acknowledged(tmp_path):
    agent = make_agent(tmp_path)
    fake = FakeDashboard()
    fake.get_config = lambda: {
        "hardware_profile": "HALUNG_3IO_BENCH_V1",
        "program": {
            "program_id": 7, "version": 3, "name": "INVALID",
            "required_switches": [4],
        },
    }
    agent.client = fake
    with pytest.raises(ValueError, match="supports only"):
        agent.sync_program_if_needed({"config_update_needed": True})
    assert fake.acked == []
    assert not agent.active_program_path.exists()


def test_outbox_requires_object_records(tmp_path):
    with pytest.raises(ValueError, match="object"):
        CycleOutbox(tmp_path / "outbox.sqlite3").enqueue(["not", "an", "object"])


def test_failed_cycle_upload_keeps_results_for_retry(tmp_path):
    agent = make_agent(tmp_path)
    agent.queue_cycle_report({"status": "OK", "duration_s": 9})

    def offline(_records):
        raise DashboardError("offline")

    agent.client.upload_cycles = offline
    with pytest.raises(DashboardError, match="offline"):
        agent.sync_pending_cycles()
    assert len(agent.outbox) == 1
