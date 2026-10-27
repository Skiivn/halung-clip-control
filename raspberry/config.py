"""Raspberry agent configuration loader."""
import json
from pathlib import Path


class Config:
    """Load and manage agent configuration."""

    def __init__(self, config_path="config/config.json"):
        self.config_path = Path(config_path)
        self.data = {}
        self.load()

    def load(self):
        """Load configuration from JSON file."""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self.data = json.load(f)

    def get(self, key, default=None):
        """Get configuration value."""
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data[key]
