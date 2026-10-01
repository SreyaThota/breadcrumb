"""Configuration settings for Breadcrumb.

All settings have safe local defaults. No network connections or API keys are required.
"""
from pathlib import Path
import json

# Paths
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "breadcrumb.db"
SETTINGS_PATH = BASE_DIR / "settings.json"

# Polling and Aggregation
POLL_INTERVAL_SECONDS = 2.0                 # How often the collector checks the active window
SESSION_INACTIVITY_THRESHOLD_MINUTES = 15   # Gap indicating a new work session (10-15m)
MAX_TIMELINE_DISPLAY_ITEMS = 60             # Maximum items to show in recent timeline
DEBOUNCE_MIN_DURATION_SECONDS = 2.0         # Ignore window switches shorter than this in aggregation

# Privacy Filter
# Window titles containing these substrings will be sanitized / masked
SENSITIVE_KEYWORDS = [
    "bitwarden", "1password", "keepass", "lastpass",
    "private browsing", "incognito", "inprivate",
    "password", "credit card", "bank", "banking", "pin number"
]

# Ignored Applications: Excluded from session analysis, durations, and inferences
DEFAULT_IGNORED_APPLICATIONS = ["Spotify", "WhatsApp", "Netflix"]

def get_ignored_applications():
    """Loads user-configured ignored applications, falling back to defaults."""
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ignored_applications", DEFAULT_IGNORED_APPLICATIONS)
        except Exception:
            pass
    return list(DEFAULT_IGNORED_APPLICATIONS)

def save_ignored_applications(app_list):
    """Saves user-configured ignored applications locally."""
    try:
        data = {}
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["ignored_applications"] = list(set(app_list))
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

# Optional Local LLM (Ollama) configuration
# Ollama is purely optional; Breadcrumb defaults to the deterministic rule engine.
OLLAMA_ENABLED = False
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3:8b"
OLLAMA_TIMEOUT_SECONDS = 5.0
