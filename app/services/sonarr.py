import time
import logging

import requests

log = logging.getLogger("unmonitorr.sonarr")


def test_connection(url, api_key):
    """Used by the 'Test connection' button on the settings page."""
    if not url or not api_key:
        return {"ok": False, "error": "URL and API key are both required."}
    try:
        resp = requests.get(
            f"{url.rstrip('/')}/api/v3/system/status",
            headers={"X-Api-Key": api_key},
            timeout=8,
        )
        if resp.status_code == 401:
            return {"ok": False, "error": "Unauthorized - check the API key."}
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "version": data.get("version", "unknown")}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def unmonitor_series(cfg, tvdb_id, on_success):
    """
    Looks up a series by tvdbId (retrying, since the webhook can fire before
    Sonarr has actually added it) and flips it (and optionally its seasons)
    to unmonitored. on_success(kind, title) is called once confirmed.
    """
    headers = {"X-Api-Key": cfg["sonarr_api_key"]}
    base_url = cfg["sonarr_url"].rstrip("/")

    for attempt in range(1, cfg["retry_attempts"] + 1):
        try:
            resp = requests.get(f"{base_url}/api/v3/series", headers=headers, timeout=15)
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
                f"{base_url}/api/v3/series/{match['id']}",
                json=match,
                headers=headers,
                timeout=10,
            )
            if put_resp.ok:
                title = match.get("title", f"tvdb:{tvdb_id}")
                log.info("Unmonitored series '%s' (tvdbId=%s) in Sonarr.", title, tvdb_id)
                on_success("series", title)
            else:
                log.error("Failed to update series %s in Sonarr: %s %s",
                          match.get("id"), put_resp.status_code, put_resp.text)
            return

        log.info("Series tvdbId=%s not in Sonarr yet (attempt %s/%s), retrying...",
                  tvdb_id, attempt, cfg["retry_attempts"])
        time.sleep(cfg["retry_delay_seconds"])

    log.error("Gave up waiting for tvdbId=%s to appear in Sonarr.", tvdb_id)