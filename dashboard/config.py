"""Configuration and constants."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

# Paths
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / os.getenv("HALUNG_DB_PATH", "halung.db")
BACKUP_DIR = DATA_DIR / "backups"
REPORT_DIR = DATA_DIR / "reports"
LAYOUT_DIR = DATA_DIR / "layouts"

# Flask
FLASK_SECRET = os.getenv("HALUNG_SECRET", "change-me-in-production")
FLASK_HOST = os.getenv("HALUNG_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("HALUNG_PORT", 8080))

# Admin
ADMIN_USER = os.getenv("HALUNG_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("HALUNG_ADMIN_PASSWORD", "admin123")

# Edge API
EDGE_API_TOKEN = os.getenv("HALUNG_EDGE_API_TOKEN", "change-me")

# NAS
NAS_ENABLED = os.getenv("HALUNG_NAS_ENABLED", "0") == "1"
NAS_PATH = os.getenv("HALUNG_NAS_PATH", "")
NAS_RETRY_MINUTES = int(os.getenv("HALUNG_NAS_RETRY_MINUTES", 5))

# Backup
BACKUP_ENABLED = os.getenv("HALUNG_BACKUP_ENABLED", "1") == "1"
BACKUP_INTERVAL_MINUTES = int(os.getenv("HALUNG_BACKUP_INTERVAL_MINUTES", 60))
BACKUP_RETENTION_DAYS = int(os.getenv("HALUNG_BACKUP_RETENTION_DAYS", 30))

# Station health
STATION_OFFLINE_SECONDS = int(os.getenv("HALUNG_STATION_OFFLINE_SECONDS", 15))

# App
APP_VERSION = "12.0.0"
APP_NAME = "HALUNG Clip Control"

# Constants
HARDWARE_PROFILES = {
    "HALUNG_3IO_BENCH_V1": {"channels": 3, "description": "Validation bench (3 points)"},
    "HALUNG_23IO_V1": {"channels": 23, "description": "Production (23 points)"},
}

STATION_STATES = [
    "READY",
    "READY_OK",
    "WRONG_CLIP",
    "WAIT_RELEASE",
    "RUNNING",
    "OFFLINE",
    "ERROR",
    "DISABLED",
]
