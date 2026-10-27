"""HALUNG Raspberry Edge Agent — Main loop."""
import time
import json
import logging
from datetime import datetime

from raspberry.config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('halung-agent')


class Agent:
    """Main HALUNG agent."""

    def __init__(self, config_path="config/config.json"):
        self.config = Config(config_path)
        self.station_code = self.config.get('station_code', 'CT-00')
        self.dashboard_url = self.config.get('dashboard_url', 'http://localhost:8080')
        self.api_token = self.config.get('api_token', '')
        self.heartbeat_interval = self.config.get('heartbeat_seconds', 1)
        self.state = 'READY'
        logger.info(f"Agent initialized for station {self.station_code}")

    def send_heartbeat(self):
        """Send heartbeat to dashboard."""
        payload = {
            'state': self.state,
            'cycle_time': 0.0,
            'actual_per_hour': 0,
            'swlock': False,
            'butok': False,
            'agent_version': '12.0.0'
        }
        logger.info(f"Heartbeat: {json.dumps(payload)}")
        # TODO: Implement actual HTTP call

    def main_loop(self):
        """Main agent loop."""
        logger.info(f"Starting main loop (heartbeat every {self.heartbeat_interval}s)")
        try:
            while True:
                self.send_heartbeat()
                time.sleep(self.heartbeat_interval)
        except KeyboardInterrupt:
            logger.info("Shutdown requested")


if __name__ == '__main__':
    agent = Agent()
    agent.main_loop()
