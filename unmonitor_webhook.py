#!/usr/bin/env python3
"""
unmonitor_webhook.py

Listens for Overseerr / Jellyseerr webhook notifications and immediately
sets the corresponding movie (Radarr) or series (Sonarr) to UNMONITORED
right after it gets added. Includes a small web settings page so you can
configure Radarr/Sonarr URLs and API keys without editing files or
restarting the container.

-----------------------------------------------------------------------
SETUP
-----------------------------------------------------------------------
1. Run it (locally or in Docker - see Dockerfile / docker-compose.yml).

2. Open http://<host>:5055/settings in a browser and fill in:
     - Radarr URL + API key
     - Sonarr URL + API key
     - (optional) a webhook secret
   Settings are saved to a JSON file (CONFIG_PATH) so they survive restarts.

3. In Overseerr/Jellyseerr:
     Settings -> Notifications -> Webhook
       - Enable Agent: ON
       - Webhook URL: http://<host-running-this-script>:5055/webhook
       - JSON Payload: leave as the DEFAULT template
       - Notification Types: enable "Request Approved" and
         "Request Automatically Approved"
       - (Optional) Add an "Authorization" header matching your webhook
         secret from the settings page.

4. Test it: make a request in Overseerr/Jellyseerr and check the logs -
   it should find the item in Radarr/Sonarr and unmonitor it within seconds.
-----------------------------------------------------------------------
"""

import os
import json
import time
import logging
import threading

import requests
from flask import Flask, request, jsonify, render_template_string, redirect, url_for

# -----------------------------------------------------------------------
# Config storage - a small JSON file so settings survive container restarts.
# Environment variables (if set) only seed the file the very first time it
# is created; after that, the settings page is the source of truth.
# -----------------------------------------------------------------------
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/data/config.json")

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

_config_lock = threading.Lock()


def load_config():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        merged = {**DEFAULT_CONFIG, **saved}
        return merged
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


CONFIG = load_config()
if not os.path.exists(CONFIG_PATH):
    save_config(CONFIG)


def get_config():
    with _config_lock:
        return dict(CONFIG)


def update_config(new_values):
    with _config_lock:
        CONFIG.update(new_values)
        save_config(CONFIG)


LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "5055"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seerr-unmonitor")

app = Flask(__name__)


# -----------------------------------------------------------------------
# Radarr
# -----------------------------------------------------------------------
def unmonitor_radarr_movie(tmdb_id):
    cfg = get_config()
    headers = {"X-Api-Key": cfg["radarr_api_key"]}

    for attempt in range(1, cfg["retry_attempts"] + 1):
        try:
            resp = requests.get(
                f"{cfg['radarr_url']}/api/v3/movie",
                params={"tmdbId": tmdb_id},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            movies = resp.json()
        except requests.RequestException as e:
            log.warning("Radarr lookup failed (attempt %s/%s): %s", attempt, cfg["retry_attempts"], e)
            time.sleep(cfg["retry_delay_seconds"])
            continue

        if movies:
            movie = movies[0]
            if not movie.get("monitored", False):
                log.info("Movie '%s' (tmdbId=%s) already unmonitored.", movie.get("title"), tmdb_id)
                return
            movie["monitored"] = False
            put_resp = requests.put(
                f"{cfg['radarr_url']}/api/v3/movie/{movie['id']}",
                json=movie, headers=headers, timeout=10,
            )
            if put_resp.ok:
                log.info("Unmonitored movie '%s' (tmdbId=%s) in Radarr.", movie.get("title"), tmdb_id)
            else:
                log.error("Failed to update movie %s in Radarr: %s %s",
                          movie.get("id"), put_resp.status_code, put_resp.text)
            return

        log.info("Movie tmdbId=%s not in Radarr yet (attempt %s/%s), retrying...",
                  tmdb_id, attempt, cfg["retry_attempts"])
        time.sleep(cfg["retry_delay_seconds"])

    log.error("Gave up waiting for tmdbId=%s to appear in Radarr.", tmdb_id)


# -----------------------------------------------------------------------
# Sonarr
# -----------------------------------------------------------------------
def unmonitor_sonarr_series(tvdb_id):
    cfg = get_config()
    headers = {"X-Api-Key": cfg["sonarr_api_key"]}

    for attempt in range(1, cfg["retry_attempts"] + 1):
        try:
            resp = requests.get(f"{cfg['sonarr_url']}/api/v3/series", headers=headers, timeout=15)
            resp.raise_for_status()
            all_series = resp.json()
        except requests.RequestException as e:
            log.warning("Sonarr lookup failed (attempt %s/%s): %s", attempt, cfg["retry_attempts"], e)
            time.sleep(cfg["retry_delay_seconds"])
            continue

        match = next((s for s in all_series if s.get("tvdbId") == tvdb_id), None)

        if match:
            already_done = not match.get("monitored", False) and not cfg["unmonitor_sonarr_seasons"]
            if already_done:
                log.info("Series '%s' (tvdbId=%s) already unmonitored.", match.get("title"), tvdb_id)
                return

            match["monitored"] = False
            if cfg["unmonitor_sonarr_seasons"]:
                for season in match.get("seasons", []):
                    season["monitored"] = False

            put_resp = requests.put(
                f"{cfg['sonarr_url']}/api/v3/series/{match['id']}",
                json=match, headers=headers, timeout=10,
            )
            if put_resp.ok:
                log.info("Unmonitored series '%s' (tvdbId=%s) in Sonarr.", match.get("title"), tvdb_id)
            else:
                log.error("Failed to update series %s in Sonarr: %s %s",
                          match.get("id"), put_resp.status_code, put_resp.text)
            return

        log.info("Series tvdbId=%s not in Sonarr yet (attempt %s/%s), retrying...",
                  tvdb_id, attempt, cfg["retry_attempts"])
        time.sleep(cfg["retry_delay_seconds"])

    log.error("Gave up waiting for tvdbId=%s to appear in Sonarr.", tvdb_id)


# -----------------------------------------------------------------------
# Webhook endpoint
# -----------------------------------------------------------------------
def extract_media_info(payload):
    media = payload.get("media") or {}
    media_type = media.get("media_type")
    tmdb_id, tvdb_id = media.get("tmdbId"), media.get("tvdbId")
    try:
        tmdb_id = int(tmdb_id) if tmdb_id not in (None, "") else None
    except (TypeError, ValueError):
        tmdb_id = None
    try:
        tvdb_id = int(tvdb_id) if tvdb_id not in (None, "") else None
    except (TypeError, ValueError):
        tvdb_id = None
    return media_type, tmdb_id, tvdb_id


@app.route("/webhook", methods=["POST"])
def webhook():
    cfg = get_config()
    if cfg["webhook_secret"]:
        if request.headers.get("Authorization") != cfg["webhook_secret"]:
            log.warning("Rejected webhook call with missing/invalid Authorization header.")
            return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    log.debug("Received payload: %s", payload)

    notification_type = payload.get("notification_type", "")
    if notification_type not in {"MEDIA_APPROVED", "MEDIA_AUTO_APPROVED"}:
        log.info("Ignoring notification_type=%s", notification_type)
        return jsonify({"status": "ignored"}), 200

    media_type, tmdb_id, tvdb_id = extract_media_info(payload)

    if media_type == "movie" and tmdb_id:
        threading.Thread(target=unmonitor_radarr_movie, args=(tmdb_id,), daemon=True).start()
    elif media_type == "tv" and tvdb_id:
        threading.Thread(target=unmonitor_sonarr_series, args=(tvdb_id,), daemon=True).start()
    else:
        log.warning("Could not determine media_type/id from payload: %s", payload)
        return jsonify({"status": "no-op", "reason": "missing media_type or id"}), 200

    return jsonify({"status": "processing"}), 200


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


# -----------------------------------------------------------------------
# Settings page
# -----------------------------------------------------------------------
SETTINGS_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seerr Unmonitor - Settings</title>
<style>
  :root {
    --bg: #12161c;
    --panel: #1a2029;
    --border: #262e3a;
    --text: #e6e9ef;
    --muted: #8b93a1;
    --accent: #4fb0a5;
    --accent-hover: #62c4b9;
    --danger: #d9705a;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    margin: 0;
    padding: 2.5rem 1.25rem;
    display: flex;
    justify-content: center;
  }
  .card {
    width: 100%;
    max-width: 560px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 2rem;
  }
  h1 {
    font-size: 1.25rem;
    margin: 0 0 0.25rem;
    letter-spacing: -0.01em;
  }
  p.sub {
    color: var(--muted);
    margin: 0 0 1.75rem;
    font-size: 0.9rem;
  }
  fieldset {
    border: none;
    padding: 0;
    margin: 0 0 1.5rem;
  }
  legend {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin-bottom: 0.75rem;
    padding: 0;
  }
  label {
    display: block;
    font-size: 0.85rem;
    margin: 0.9rem 0 0.35rem;
  }
  input[type=text], input[type=password], input[type=number] {
    width: 100%;
    background: #0e1217;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 0.55rem 0.65rem;
    border-radius: 6px;
    font-size: 0.9rem;
  }
  input:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
  .checkbox-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.9rem;
  }
  .checkbox-row input { width: auto; }
  .checkbox-row label { margin: 0; }
  button {
    width: 100%;
    background: var(--accent);
    color: #0e1217;
    border: none;
    padding: 0.7rem 1rem;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    margin-top: 0.5rem;
  }
  button:hover { background: var(--accent-hover); }
  .webhook-url {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    background: #0e1217;
    border: 1px solid var(--border);
    padding: 0.6rem 0.7rem;
    border-radius: 6px;
    font-size: 0.82rem;
    color: var(--accent);
    word-break: break-all;
    margin-bottom: 1.5rem;
  }
  .flash {
    background: rgba(79,176,165,0.12);
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 0.6rem 0.8rem;
    border-radius: 6px;
    font-size: 0.85rem;
    margin-bottom: 1.25rem;
  }
</style>
</head>
<body>
  <div class="card">
    <h1>Unmonitor webhook settings</h1>
    <p class="sub">These values are saved to disk and take effect immediately - no restart needed.</p>

    {% if saved %}
    <div class="flash">Settings saved.</div>
    {% endif %}

    <div class="webhook-url">POST http://&lt;this-host&gt;:{{ port }}/webhook</div>

    <form method="post" action="{{ url_for('settings_page') }}">
      <fieldset>
        <legend>Radarr</legend>
        <label for="radarr_url">URL</label>
        <input type="text" id="radarr_url" name="radarr_url" value="{{ cfg.radarr_url }}" placeholder="http://radarr:7878">
        <label for="radarr_api_key">API key</label>
        <input type="password" id="radarr_api_key" name="radarr_api_key" value="{{ cfg.radarr_api_key }}">
      </fieldset>

      <fieldset>
        <legend>Sonarr</legend>
        <label for="sonarr_url">URL</label>
        <input type="text" id="sonarr_url" name="sonarr_url" value="{{ cfg.sonarr_url }}" placeholder="http://sonarr:8989">
        <label for="sonarr_api_key">API key</label>
        <input type="password" id="sonarr_api_key" name="sonarr_api_key" value="{{ cfg.sonarr_api_key }}">
        <div class="checkbox-row">
          <input type="checkbox" id="unmonitor_sonarr_seasons" name="unmonitor_sonarr_seasons" {% if cfg.unmonitor_sonarr_seasons %}checked{% endif %}>
          <label for="unmonitor_sonarr_seasons">Also unmonitor individual seasons</label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Webhook</legend>
        <label for="webhook_secret">Shared secret (optional)</label>
        <input type="password" id="webhook_secret" name="webhook_secret" value="{{ cfg.webhook_secret }}" placeholder="leave blank to disable">
      </fieldset>

      <fieldset>
        <legend>Retry behavior</legend>
        <label for="retry_attempts">Attempts to find newly-added media</label>
        <input type="number" id="retry_attempts" name="retry_attempts" value="{{ cfg.retry_attempts }}" min="1" max="30">
        <label for="retry_delay_seconds">Delay between attempts (seconds)</label>
        <input type="number" id="retry_delay_seconds" name="retry_delay_seconds" value="{{ cfg.retry_delay_seconds }}" min="1" max="30" step="0.5">
      </fieldset>

      <button type="submit">Save changes</button>
    </form>
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("settings_page"))


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    saved = False
    if request.method == "POST":
        form = request.form
        update_config({
            "radarr_url": form.get("radarr_url", "").strip(),
            "radarr_api_key": form.get("radarr_api_key", "").strip(),
            "sonarr_url": form.get("sonarr_url", "").strip(),
            "sonarr_api_key": form.get("sonarr_api_key", "").strip(),
            "webhook_secret": form.get("webhook_secret", "").strip(),
            "unmonitor_sonarr_seasons": "unmonitor_sonarr_seasons" in form,
            "retry_attempts": int(form.get("retry_attempts", 8)),
            "retry_delay_seconds": float(form.get("retry_delay_seconds", 3)),
        })
        saved = True

    return render_template_string(
        SETTINGS_TEMPLATE, cfg=get_config(), saved=saved, port=LISTEN_PORT
    )


cfg = get_config()
missing = [k for k in ("radarr_api_key", "sonarr_api_key") if not cfg.get(k)]
if missing:
    log.warning("Not yet configured: %s - visit /settings to set these up.", ", ".join(missing))

if __name__ == "__main__":
    log.info("Starting on %s:%s (settings at /settings)", LISTEN_HOST, LISTEN_PORT)
    app.run(host=LISTEN_HOST, port=LISTEN_PORT)