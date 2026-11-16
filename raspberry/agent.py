"""HALUNG Raspberry Edge Agent network service.

This agent currently handles Dashboard communication and durable cycle syncing.
It does not claim to read or control hardware; hardware adapters and the local
Clip Test engine are separate work still required before production operation.
"""
import argparse
import json
import logging
import time
from pathlib import Path

from raspberry.config import Config
from raspberry.network.dashboard_client import (
    CycleOutbox,
    DashboardClient,
    DashboardError,
    validate_program,
    write_active_program,
)

APP_VERSION = "12.0.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("halung-agent")


class Agent:
    """Run network synchronization for one registered station."""

    def __init__(self, config_path="raspberry/config/station.json"):
        self.config = Config(config_path)
        self.station_code = self.config.require("station_code")
        self.dashboard_url = self.config.require("dashboard_url")
        self.api_token = self.config.require("api_token")
        self.hardware_profile = self.config.require("hardware_profile")
        self.heartbeat_interval = max(1.0, float(self.config.get("heartbeat_seconds", 5)))
        self.active_program_path = Path(
            self.config.get("active_program_path", "raspberry/data/active_program.json")
        )
        self.client = DashboardClient(
            self.dashboard_url,
            self.station_code,
            self.api_token,
            timeout=self.config.get("request_timeout_seconds", 3),
        )
        self.outbox = CycleOutbox(
            self.config.get("outbox_path", "raspberry/data/agent.sqlite3")
        )
        self.state = "NOT_CONFIGURED"
        logger.info("Agent initialized for station %s", self.station_code)

    def _active_program(self):
        try:
            with self.active_program_path.open(encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def _heartbeat_payload(self):
        program = self._active_program()
        return {
            "state": self.state,
            "hardware_status": "NOT_CONFIGURED",
            "cycle_time": 0.0,
            "actual_per_hour": 0,
            "swlock": None,
            "butok": None,
            "active_program_id": program.get("program_id") if program else None,
            "active_program_version": program.get("version") if program else None,
            "pending_cycles": len(self.outbox),
            "agent_version": APP_VERSION,
        }

    def sync_program_if_needed(self, heartbeat):
        """Validate, persist, then acknowledge the exact assigned program."""
        if not heartbeat.get("config_update_needed"):
            return False
        response = self.client.get_config()
        program = response.get("program")
        if program is None:
            logger.warning("No program assigned to station %s", self.station_code)
            return False
        validate_program(program, response.get("hardware_profile"))
        write_active_program(self.active_program_path, program)
        # Acknowledge only after durable local storage.
        self.client.acknowledge_program(program["program_id"], program["version"])
        logger.info(
            "Program %s v%s received and acknowledged",
            program["name"],
            program["version"],
        )
        return True

    def sync_pending_cycles(self):
        """Upload batches and remove only results confirmed by the Dashboard."""
        records = self.outbox.pending(limit=100)
        if not records:
            return 0
        response = self.client.upload_cycles(records)
        accepted = response.get("accepted")
        if not isinstance(accepted, list):
            raise DashboardError("Dashboard cycle response is missing accepted IDs")
        sent_ids = {record["client_uid"] for record in records}
        unexpected = set(accepted) - sent_ids
        if unexpected:
            raise DashboardError("Dashboard acknowledged unknown cycle IDs")
        self.outbox.acknowledge(accepted)
        logger.info("Synchronized %s buffered cycle(s)", len(accepted))
        return len(accepted)

    def queue_cycle_report(self, report):
        """Persist a Clip Test engine report for later upload.

        Accepts the existing state-machine report shape and converts its field
        names to the stable Dashboard cycle API contract.
        """
        if not isinstance(report, dict) or report.get("status") not in ("OK", "NOK", "INTERRUPTED"):
            raise ValueError("cycle report must have status OK, NOK, or INTERRUPTED")
        program = self._active_program() or {}
        record = {
            "status": report["status"],
            "ended_at": report.get("ended_at") or report.get("butok_time"),
            "duration_s": report.get("duration_s", report.get("cycle_time_seconds")),
            "swlock_time": report.get("swlock_time"),
            "butok_time": report.get("butok_time"),
            "layout": report.get("layout") or program.get("layout"),
            "variant": report.get("variant") or program.get("variant"),
            "failure_code": report.get("failure_code"),
        }
        return self.outbox.enqueue(record)

    def run_once(self):
        """Perform one heartbeat, any pending program sync, and cycle upload."""
        heartbeat = self.client.heartbeat(self._heartbeat_payload())
        try:
            self.sync_program_if_needed(heartbeat)
        except (DashboardError, ValueError) as exc:
            # A bad/new program must not block synchronization of completed cycles.
            logger.error("Program synchronization failed; keeping the last active program: %s", exc)
        self.sync_pending_cycles()

    def main_loop(self):
        logger.info(
            "Starting Dashboard sync for %s (every %ss)",
            self.station_code,
            self.heartbeat_interval,
        )
        while True:
            started = time.monotonic()
            try:
                self.run_once()
            except (DashboardError, ValueError) as exc:
                logger.warning("Dashboard sync unavailable; local outbox retained: %s", exc)
            delay = max(0, self.heartbeat_interval - (time.monotonic() - started))
            time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description="HALUNG Raspberry Dashboard sync agent")
    parser.add_argument(
        "--config",
        default="raspberry/config/station.json",
        help="path to station JSON configuration",
    )
    args = parser.parse_args()
    Agent(args.config).main_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
