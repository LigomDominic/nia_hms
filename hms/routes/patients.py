from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import CLINICAL_ROLES, Patient
from ..utils import parse_date, roles_required

bp = Blueprint("patients", __name__, url_prefix="/patients")

PATIENT_FIELDS = (
    "first_name", "last_name", "other_names", "gender", "phone", "email", "address",
    "blood_group", "genotype", "allergies", "next_of_kin_name", "next_of_kin_phone",
)


def fill_patient(patient, form):
    for field in PATIENT_FIELDS:
        setattr(patient, field, (form.get(field) or "").strip() or None)
    patient.date_of_birth = parse_date(form.get("date_of_birth"))


def get_patient_or_404(hospital_id):
    patient = Patient.query.filter(Patient.hospital_id == hospital_id.strip().upper()).first()
    if patient is None:
        abort(404)
    return patient


@bp.route("/lookup")
@roles_required(*CLINICAL_ROLES)
def lookup():
    q = (request.args.get("q") or "").strip()
    results = []
    if q:
        exact = Patient.query.filter(Patient.hospital_id == q.upper()).first()
        if exact:
            return redirect(url_for("patients.profile", hospital_id=exact.hospital_id))
        if q.isdigit():
            tail = f"%{q}"
            results = (
                Patient.query.filter(
                    or_(
                        Patient.hospital_id.ilike(tail),
                        Patient.phone.ilike(tail),
                    )
                )
                .order_by(Patient.created_at.desc())
                .limit(50)
                .all()
            )
            if len(results) == 1:
                return redirect(url_for("patients.profile", hospital_id=results[0].hospital_id))
        if not results:
            like = f"%{q}%"
            results = (
                Patient.query.filter(
                    or_(
                        Patient.hospital_id.ilike(like),
                        Patient.first_name.ilike(like),
                        Patient.last_name.ilike(like),
                        Patient.other_names.ilike(like),
                        Patient.phone.ilike(like),
                        Patient.email.ilike(like),
                    )
                )
                .order_by(Patient.created_at.desc())
                .limit(50)
                .all()
            )
        if not results:
            flash(f"No patient found for “{q}”.", "warning")
    return render_template("patients/lookup.html", q=q, results=results)


@bp.route("/")
@roles_required(*CLINICAL_ROLES)
def index():
    patients = Patient.query.order_by(Patient.created_at.desc()).limit(200).all()
    return render_template("patients/index.html", patients=patients)


@bp.route("/<path:hospital_id>")
@roles_required(*CLINICAL_ROLES)
def profile(hospital_id):
    patient = get_patient_or_404(hospital_id)
    payments = sorted((p for b in patient.bills for p in b.payments), key=lambda p: p.id, reverse=True)
    return render_template("patients/profile.html", p=patient, payments=payments)


@bp.route("/<path:hospital_id>/card")
@roles_required("cashier")
def card(hospital_id):
    return render_template("patients/card.html", p=get_patient_or_404(hospital_id))


@bp.route("/<path:hospital_id>/edit", methods=["GET", "POST"])
@roles_required("cashier")
def edit(hospital_id):
    patient = get_patient_or_404(hospital_id)
    if request.method == "POST":
        if not request.form.get("first_name") or not request.form.get("last_name"):
            flash("First and last name are required.", "danger")
        else:
            fill_patient(patient, request.form)
            status = request.form.get("status")
            if status in Patient.STATUSES:
                patient.status = status
            db.session.commit()
            flash("Patient record updated.", "success")
            return redirect(url_for("patients.profile", hospital_id=patient.hospital_id))
    return render_template("patients/edit.html", p=patient, statuses=Patient.STATUSES)


@bp.route("/<path:hospital_id>/status", methods=["POST"])
@roles_required("cashier", "nurse", "doctor", "visiting_doctor")
def set_status(hospital_id):
    patient = get_patient_or_404(hospital_id)
    status = request.form.get("status")
    if status in Patient.STATUSES:
        patient.status = status
        db.session.commit()
        flash(f"Status changed to {status} by {current_user.display_name}.", "success")
    return redirect(url_for("patients.profile", hospital_id=patient.hospital_id))
