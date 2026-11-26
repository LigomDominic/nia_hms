import secrets
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..permissions import explicit_level
from ..models import Prescription, PrescriptionItem, TreatmentAdministration, TreatmentOrder, now
from ..utils import parse_int, roles_required
from .nurse import ROUTES
from .patients import get_patient_or_404

bp = Blueprint("treatment", __name__, url_prefix="/treatment")


@bp.route("/<path:hospital_id>", methods=["GET", "POST"])
@roles_required("nurse", "doctor", "visiting_doctor")
def chart(hospital_id):
    patient = get_patient_or_404(hospital_id)
    token = session.setdefault("treatment_token", secrets.token_hex(32))
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf_token", ""), token):
            abort(400)
        action = request.form.get("action")
        try:
            if action == "order":
                _create_order(patient)
            elif action in ("administer", "stop"):
                order = db.get_or_404(TreatmentOrder, parse_int(request.form.get("order_id")))
                if order.prescription_item.prescription.patient_id != patient.id:
                    abort(404)
                if action == "stop":
                    reason = (request.form.get("stop_reason") or "").strip()
                    if order.status != "active" or not reason or len(reason) > 500:
                        raise ValueError("Provide a reason (up to 500 characters) for stopping an active treatment.")
                    order.status = "stopped"
                    order.stopped_at = now()
                    order.stopped_by = current_user
                    order.stop_reason = reason
                else:
                    if current_user.role not in ("admin", "nurse") \
                            and explicit_level(current_user, "treatment") != "manage":
                        abort(403)
                    _administer(order)
            else:
                abort(400)
            db.session.commit()
            flash("Treatment chart updated.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash("This administration was already recorded. Refresh before recording another dose.", "warning")
        return redirect(url_for("treatment.chart", hospital_id=patient.hospital_id))
    items = PrescriptionItem.query.join(Prescription).filter(
        Prescription.patient_id == patient.id, Prescription.status != "cancelled").order_by(
        Prescription.created_at.desc(), PrescriptionItem.id).all()
    orders = TreatmentOrder.query.join(PrescriptionItem).join(Prescription).filter(
        Prescription.patient_id == patient.id).order_by(TreatmentOrder.created_at.desc(), TreatmentOrder.id.desc()).all()
    history = TreatmentAdministration.query.join(TreatmentOrder).join(PrescriptionItem).join(Prescription).filter(
        Prescription.patient_id == patient.id).order_by(
        TreatmentAdministration.administered_at.desc(), TreatmentAdministration.id.desc()).paginate(
        page=max(1, request.args.get("page", 1, type=int)), per_page=50)
    return render_template("nurse/treatments.html", p=patient, items=items, orders=orders, history=history,
                           routes=ROUTES, csrf_token=token, submission_token=secrets.token_hex(32),
                           current_time=now().strftime("%Y-%m-%dT%H:%M"))


def _create_order(patient):
    item = db.get_or_404(PrescriptionItem, parse_int(request.form.get("prescription_item_id")))
    if item.prescription.patient_id != patient.id:
        abort(404)
    if item.prescription.status == "cancelled":
        raise ValueError("Cancelled prescriptions cannot be added to the treatment chart.")
    if TreatmentOrder.query.filter_by(prescription_item_id=item.id, status="active").first():
        raise ValueError("This prescription item already has an active treatment order.")
    fields = {key: (request.form.get(key) or "").strip() for key in ("dose", "route", "frequency", "duration")}
    if any(not value or len(value) > 80 for value in fields.values()) or fields["route"] not in ROUTES:
        raise ValueError("Provide dose, frequency, duration (up to 80 characters each) and a valid route.")
    instructions = (request.form.get("instructions") or "").strip()
    if len(instructions) > 5000:
        raise ValueError("Treatment instructions allow up to 5,000 characters.")
    db.session.add(TreatmentOrder(prescription_item=item, created_by=current_user,
                                  instructions=instructions or None, **fields))


def _administer(order):
    if order.status != "active" or order.prescription_item.prescription.status == "cancelled":
        raise ValueError("Cannot record administration for a stopped treatment or cancelled prescription.")
    if order.prescription_item.prescription.status != "dispensed":
        raise ValueError("The prescription must be dispensed by Pharmacy before administration is recorded.")
    outcome = request.form.get("outcome")
    dose = (request.form.get("dose") or "").strip()
    route = (request.form.get("route") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    signature = (request.form.get("signature") or "").strip()
    submission = request.form.get("submission_token", "")
    try:
        administered_at = datetime.strptime(request.form.get("administered_at", ""), "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("Provide a valid administration date and time.") from None
    if administered_at > now() or administered_at < order.created_at.replace(second=0, microsecond=0):
        raise ValueError("Administration time must be after the treatment order and not in the future.")
    if outcome not in ("given", "withheld", "refused") or not signature or len(signature) > 120:
        raise ValueError("Select an outcome and enter a typed signature (up to 120 characters).")
    if len(notes) > 5000 or len(dose) > 80 or (route and route not in ROUTES):
        raise ValueError("Check the dose, route and notes lengths.")
    if outcome == "given" and (not dose or route not in ROUTES):
        raise ValueError("Record the actual dose and route for medication given.")
    if outcome != "given" and not notes:
        raise ValueError("Give a reason when medication is withheld or refused.")
    if len(submission) != 64 or any(char not in "0123456789abcdef" for char in submission):
        abort(400)
    db.session.add(TreatmentAdministration(order=order, recorded_by=current_user,
                                           administered_at=administered_at, outcome=outcome,
                                           dose=dose or None, route=route or None, notes=notes or None,
                                           signature=signature, submission_token=submission))
