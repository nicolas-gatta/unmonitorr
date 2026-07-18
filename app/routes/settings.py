from flask import Blueprint, request, render_template, jsonify

from .. import config as config_module
from ..services import radarr, sonarr

bp = Blueprint("settings", __name__)


@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    saved = False
    if request.method == "POST":
        form = request.form
        config_module.update({
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

    return render_template(
        "settings.html", cfg=config_module.get(), saved=saved,
        webhook_url=f"{request.scheme}://{request.host}/webhook",
    )


@bp.route("/settings/test-radarr", methods=["POST"])
def test_radarr():
    data = request.get_json(silent=True) or {}
    result = radarr.test_connection(data.get("url", ""), data.get("api_key", ""))
    return jsonify(result)


@bp.route("/settings/test-sonarr", methods=["POST"])
def test_sonarr():
    data = request.get_json(silent=True) or {}
    result = sonarr.test_connection(data.get("url", ""), data.get("api_key", ""))
    return jsonify(result)