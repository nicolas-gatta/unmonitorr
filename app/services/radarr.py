import time
import logging

import requests

log = logging.getLogger("unmonitorr.radarr")


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


def unmonitor_movie(cfg, tmdb_id, on_success):
    """
    Looks up a movie by tmdbId (retrying, since the webhook can fire before
    Radarr has actually added it) and flips it to unmonitored.
    on_success(kind, title) is called once the change is confirmed.
    """
    headers = {"X-Api-Key": cfg["radarr_api_key"]}
    base_url = cfg["radarr_url"].rstrip("/")

    for attempt in range(1, cfg["retry_attempts"] + 1):
        try:
            resp = requests.get(
                f"{base_url}/api/v3/movie",
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
                f"{base_url}/api/v3/movie/{movie['id']}",
                json=movie,
                headers=headers,
                timeout=10,
            )
            if put_resp.ok:
                title = movie.get("title", f"tmdb:{tmdb_id}")
                log.info("Unmonitored movie '%s' (tmdbId=%s) in Radarr.", title, tmdb_id)
                on_success("movie", title)
            else:
                log.error("Failed to update movie %s in Radarr: %s %s",
                          movie.get("id"), put_resp.status_code, put_resp.text)
            return

        log.info("Movie tmdbId=%s not in Radarr yet (attempt %s/%s), retrying...",
                  tmdb_id, attempt, cfg["retry_attempts"])
        time.sleep(cfg["retry_delay_seconds"])

    log.error("Gave up waiting for tmdbId=%s to appear in Radarr.", tmdb_id)