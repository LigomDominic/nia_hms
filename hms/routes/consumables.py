import secrets
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import func

from ..extensions import db
from ..models import PatientConsumable
from ..permissions import can_access
from ..utils import parse_date, parse_int, roles_required
from .patients import get_patient_or_404

bp = Blueprint("consumables", __name__, url_prefix="/consumables")


@bp.route("/<path:hospital_id>", methods=["GET", "POST"])
@roles_required("nurse", "doctor", "visiting_doctor")
def record(hospital_id):
    patient = get_patient_or_404(hospital_id)
    if "consumables_token" not in session:
        session["consumables_token"] = secrets.token_hex(32)
    if request.method == "POST":
        if not can_access(current_user, "consumables", "manage"):
            abort(403)
        token = request.form.get("csrf_token", "")
        if not secrets.compare_digest(token, session["consumables_token"]):
            abort(400)
        record_date = parse_date(request.form.get("record_date"))
        name = (request.form.get("name") or "").strip()
        quantities = {key: parse_int(request.form.get(key), -1)
                      if (request.form.get(key) or "").strip() else 0
                      for key, _label in PatientConsumable.ITEM_FIELDS}
        if record_date is None or record_date > date.today():
            flash("Enter a valid date (not in the future).", "danger")
        elif len(name) > 160:
            flash("Name allows up to 160 characters.", "danger")
        elif any(qty < 0 or qty > 9999 for qty in quantities.values()):
            flash("Each item quantity must be a number from 0 to 9999.", "danger")
        elif not any(quantities.values()):
            flash("Enter a quantity for at least one item.", "danger")
        else:
            db.session.add(PatientConsumable(patient=patient, recorded_by=current_user,
                                           record_date=record_date, name=name or None, **quantities))
            db.session.commit()
            flash("Consumables recorded.", "success")
            return redirect(url_for("consumables.record", hospital_id=patient.hospital_id))
    page = max(1, request.args.get("page", 1, type=int))
    entries = PatientConsumable.query.filter_by(patient_id=patient.id).order_by(
        PatientConsumable.record_date.desc(), PatientConsumable.id.desc()).paginate(page=page, per_page=50)
    totals = {}
    for key, _label in PatientConsumable.ITEM_FIELDS:
        totals[key] = db.session.query(func.coalesce(func.sum(getattr(PatientConsumable, key)), 0)) \
            .filter_by(patient_id=patient.id).scalar()
    return render_template("nurse/consumables.html", p=patient, entries=entries, totals=totals,
                           item_fields=PatientConsumable.ITEM_FIELDS, today=date.today().isoformat(),
                           csrf_token=session["consumables_token"])
