"""
Persistent configuration for the app.

Settings entered on the /settings page are saved to CONFIG_PATH (a JSON
file on the mounted data volume) and take effect immediately - no restart
needed. Environment variables only seed the very first run, before that
file exists.
"""

import os
import json
import threading

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/data/config.json")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

DEFAULT_CONFIG = {
    "radarr_url": os.environ.get("RADARR_URL", "http://localhost:7878"),
    "radarr_api_key": os.environ.get("RADARR_API_KEY", ""),
    "sonarr_url": os.environ.get("SONARR_URL", "http://localhost:8989"),
    "sonarr_api_key": os.environ.get("SONARR_API_KEY", ""),
    "webhook_secret": os.environ.get("WEBHOOK_SECRET", ""),
    "retry_attempts": int(os.environ.get("RETRY_ATTEMPTS", "8")),
    "retry_delay_seconds": float(os.environ.get("RETRY_DELAY_SECONDS", "3")),
    "unmonitor_sonarr_seasons": os.environ.get("UNMONITOR_SONARR_SEASONS", "true").lower() == "true",
}

_lock = threading.Lock()
_config = None


def _load_from_disk():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        return {**DEFAULT_CONFIG, **saved}
    return dict(DEFAULT_CONFIG)


def _save_to_disk(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def init():
    global _config
    with _lock:
        first_run = not os.path.exists(CONFIG_PATH)
        _config = _load_from_disk()
        if first_run:
            _save_to_disk(_config)


def get():
    """Returns a copy of the current config dict."""
    with _lock:
        return dict(_config)


def update(new_values):
    """Merge new_values into the config and persist it immediately."""
    with _lock:
        _config.update(new_values)
        _save_to_disk(_config)


init()