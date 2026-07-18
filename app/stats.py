"""
Simple persistent counters + recent-activity log, shown on the dashboard.
Stored separately from config.py's settings so the two can't collide.
"""

import os
import json
import threading
import datetime

STATS_PATH = os.environ.get("STATS_PATH", "/app/data/stats.json")
MAX_RECENT_EVENTS = 20

DEFAULT_STATS = {
    "movies_unmonitored": 0,
    "series_unmonitored": 0,
    "last_events": [],
}

_lock = threading.Lock()
_stats = None


def _load_from_disk():
    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    if os.path.exists(STATS_PATH):
        with open(STATS_PATH, "r") as f:
            saved = json.load(f)
        return {**DEFAULT_STATS, **saved}
    return dict(DEFAULT_STATS)


def _save_to_disk(s):
    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    with open(STATS_PATH, "w") as f:
        json.dump(s, f, indent=2)


def init():
    global _stats
    with _lock:
        _stats = _load_from_disk()


def get():
    with _lock:
        return dict(_stats)


def record_unmonitor(kind, title):
    """kind should be 'movie' or 'series'."""
    with _lock:
        key = "movies_unmonitored" if kind == "movie" else "series_unmonitored"
        _stats[key] = _stats.get(key, 0) + 1

        event = {
            "kind": kind,
            "title": title,
            "at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        }
        events = _stats.get("last_events", [])
        events.insert(0, event)
        _stats["last_events"] = events[:MAX_RECENT_EVENTS]

        _save_to_disk(_stats)


init()