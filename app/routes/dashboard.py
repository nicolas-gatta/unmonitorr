from flask import Blueprint, render_template

from .. import stats as stats_module

bp = Blueprint("dashboard", __name__)


@bp.route("/", methods=["GET"])
def dashboard():
    return render_template("dashboard.html", stats=stats_module.get())