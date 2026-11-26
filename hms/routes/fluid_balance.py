import secrets
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import func

from ..extensions import db
from ..models import FluidBalanceEntry, now
from ..permissions import can_access
from ..utils import parse_int, roles_required
from .patients import get_patient_or_404

bp = Blueprint("fluid_balance", __name__, url_prefix="/fluid-balance")


@bp.route("/<path:hospital_id>", methods=["GET", "POST"])
@roles_required("nurse", "doctor", "visiting_doctor")
def sheet(hospital_id):
    patient = get_patient_or_404(hospital_id)
    if "fluid_balance_token" not in session:
        session["fluid_balance_token"] = secrets.token_hex(32)
    if request.method == "POST":
        if not can_access(current_user, "fluid_balance", "manage"):
            abort(403)
        if not secrets.compare_digest(request.form.get("csrf_token", ""), session["fluid_balance_token"]):
            abort(400)
        try:
            entry_at = datetime.strptime(request.form.get("entry_at", ""), "%Y-%m-%dT%H:%M")
        except ValueError:
            entry_at = None
        fluid = (request.form.get("fluid") or "").strip()
        remarks = (request.form.get("remarks") or "").strip()
        amounts = {key: parse_int(request.form.get(key), -1)
                   if (request.form.get(key) or "").strip() else 0
                   for key, _label in FluidBalanceEntry.ALL_FIELDS}
        if entry_at is None or entry_at > now():
            flash("Enter a valid date and time (not in the future).", "danger")
        elif len(fluid) > 160:
            flash("Fluid description allows up to 160 characters.", "danger")
        elif len(remarks) > 5000:
            flash("Remarks allow up to 5,000 characters.", "danger")
        elif any(qty < 0 or qty > 99999 for qty in amounts.values()):
            flash("Each amount must be a number from 0 to 99999 ml.", "danger")
        elif not any(amounts.values()):
            flash("Enter an amount for at least one intake or output.", "danger")
        else:
            db.session.add(FluidBalanceEntry(patient=patient, recorded_by=current_user,
                                           entry_at=entry_at, fluid=fluid or None,
                                           remarks=remarks or None, **amounts))
            db.session.commit()
            flash("Fluid balance entry recorded.", "success")
            return redirect(url_for("fluid_balance.sheet", hospital_id=patient.hospital_id))
    page = max(1, request.args.get("page", 1, type=int))
    entries = FluidBalanceEntry.query.filter_by(patient_id=patient.id).order_by(
        FluidBalanceEntry.entry_at.desc(), FluidBalanceEntry.id.desc()).paginate(page=page, per_page=50)
    base = [func.coalesce(func.sum(getattr(FluidBalanceEntry, key)), 0)
            for key, _l in FluidBalanceEntry.ALL_FIELDS]
    row = db.session.query(*base).filter_by(patient_id=patient.id).one()
    totals = dict(zip((key for key, _l in FluidBalanceEntry.ALL_FIELDS), row))
    intake_total = sum(totals[k] for k, _l in FluidBalanceEntry.INTAKE_FIELDS)
    output_total = sum(totals[k] for k, _l in FluidBalanceEntry.OUTPUT_FIELDS)
    return render_template("nurse/fluid_balance.html", p=patient, entries=entries, totals=totals,
                           intake_total=intake_total, output_total=output_total,
                           cumulative=intake_total - output_total,
                           intake_fields=FluidBalanceEntry.INTAKE_FIELDS,
                           output_fields=FluidBalanceEntry.OUTPUT_FIELDS,
                           current_time=now().strftime("%Y-%m-%dT%H:%M"),
                           csrf_token=session["fluid_balance_token"])
