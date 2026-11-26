from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Drug, LabTest

bp = Blueprint("main", __name__)

ROLE_MODULE = {
    "admin": "administration",
    "cashier": "billing",
    "doctor": "consultation",
    "visiting_doctor": "consultation",
    "nurse": "nursing",
    "lab": "laboratory",
    "pharmacist": "pharmacy",
    "store_keeper": "store",
    "cleaner": "cleaning",
}
ROLE_HOME = {
    "admin": "admin.dashboard",
    "cashier": "cashier.dashboard",
    "doctor": "doctor.dashboard",
    "visiting_doctor": "doctor.dashboard",
    "nurse": "nurse.dashboard",
    "lab": "lab.dashboard",
    "pharmacist": "pharmacy.dashboard",
    "store_keeper": "store.dashboard",
    "cleaner": "cleaner.dashboard",
}
# Fallback order when a user's role home is blocked or they have extra grants.
MODULE_HOME = [
    ("administration", "admin.dashboard"),
    ("billing", "cashier.dashboard"),
    ("consultation", "doctor.dashboard"),
    ("nursing", "nurse.dashboard"),
    ("anc", "anc.dashboard"),
    ("laboratory", "lab.dashboard"),
    ("pharmacy", "pharmacy.dashboard"),
    ("store", "store.dashboard"),
    ("cleaning", "cleaner.dashboard"),
    ("patients", "patients.index"),
    ("treatment", "patients.index"),
]


@bp.route("/")
def landing():
    return render_template(
        "landing.html", test_count=LabTest.query.filter_by(is_active=True).count(), drug_count=Drug.query.count()
    )


@bp.route("/environment", methods=["GET", "POST"])
@login_required
def environment():
    """Pick which copy of the app to use: the live system or the training demo."""
    demo_available = "demo" in db.engines
    if request.method == "POST":
        env = request.form.get("env")
        if env == "demo" and not demo_available:
            env = "live"
        if env in ("live", "demo"):
            session["env"] = env
            nxt = request.form.get("next", "")
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("main.dashboard"))
        flash("Choose which app to use.", "danger")
    return render_template("choose_environment.html", demo_available=demo_available,
                           nxt=request.args.get("next", ""))


@bp.route("/dashboard")
@login_required
def dashboard():
    from ..permissions import can_access

    module = ROLE_MODULE.get(current_user.role)
    endpoint = ROLE_HOME.get(current_user.role)
    if endpoint and module and can_access(current_user, module):
        return redirect(url_for(endpoint))
    for mod, ep in MODULE_HOME:
        if can_access(current_user, mod):
            return redirect(url_for(ep))
    return redirect(url_for("main.landing"))
