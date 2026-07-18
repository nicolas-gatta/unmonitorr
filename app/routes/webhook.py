import logging
import threading

from flask import Blueprint, request, jsonify

from .. import config as config_module
from .. import stats as stats_module
from ..services import radarr, sonarr

log = logging.getLogger("unmonitorr.webhook")

bp = Blueprint("webhook", __name__)


def _extract_media_info(payload):
    """Parses Overseerr/Jellyseerr's default webhook JSON payload shape."""
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


@bp.route("/webhook", methods=["POST"])
def webhook():
    cfg = config_module.get()

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

    media_type, tmdb_id, tvdb_id = _extract_media_info(payload)

    if media_type == "movie" and tmdb_id:
        threading.Thread(
            target=radarr.unmonitor_movie,
            args=(cfg, tmdb_id, stats_module.record_unmonitor),
            daemon=True,
        ).start()
    elif media_type == "tv" and tvdb_id:
        threading.Thread(
            target=sonarr.unmonitor_series,
            args=(cfg, tvdb_id, stats_module.record_unmonitor),
            daemon=True,
        ).start()
    else:
        log.warning("Could not determine media_type/id from payload: %s", payload)
        return jsonify({"status": "no-op", "reason": "missing media_type or id"}), 200

    return jsonify({"status": "processing"}), 200


@bp.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200