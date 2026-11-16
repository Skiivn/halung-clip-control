"""Raspberry agent configuration loader."""
import json
from pathlib import Path


class Config:
    """Load agent configuration from a JSON file."""

    def __init__(self, config_path="raspberry/config/station.json"):
        self.config_path = Path(config_path)
        self.data = {}
        self.load()

    def load(self):
        """Load configuration, rejecting malformed or missing configuration."""
        try:
            with self.config_path.open(encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError as exc:
            raise RuntimeError(f"agent configuration not found: {self.config_path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSON in agent configuration: {self.config_path}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("agent configuration must be a JSON object")
        self.data = data

    def get(self, key, default=None):
        """Get configuration value."""
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data[key]

    def require(self, key):
        """Get a non-empty required setting or raise a clear configuration error."""
        value = self.data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"required agent setting is missing: {key}")
        return value.strip()
