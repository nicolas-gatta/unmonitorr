import logging

from flask import Flask
from . import config as config_module
from .routes.webhook import bp as webhook_bp
from .routes.settings import bp as settings_bp
from .routes.dashboard import bp as dashboard_bp


logging.basicConfig(
    level=config_module.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("unmonitorr")


def create_app():
    flask_app = Flask(__name__)
    flask_app.register_blueprint(webhook_bp)
    flask_app.register_blueprint(settings_bp)
    flask_app.register_blueprint(dashboard_bp)

    cfg = config_module.get()
    missing = [k for k in ("radarr_api_key", "sonarr_api_key") if not cfg.get(k)]
    if missing:
        log.warning("Not yet configured: %s - visit /settings to set these up.", ", ".join(missing))

    return flask_app


app = create_app()