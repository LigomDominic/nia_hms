from datetime import date, datetime, time, timedelta

import math
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import (DOCTOR_ROLES, EmergencyDrug, EmergencyDrugUse, EmergencyStockMovement, Patient, User, Visit,
                      now)
from ..permissions import can_access
from ..utils import parse_date, parse_int, roles_required
from .cashier import active_doctors
from .patients import get_patient_or_404
from ..models import PatientObservation

bp = Blueprint("nurse", __name__, url_prefix="/nurse")

VITAL_FIELDS = ("temperature", "blood_pressure", "pulse", "respiration", "weight", "spo2")
ROUTES = ("IV", "IM", "SC", "Oral", "Sublingual", "Inhalation", "Rectal", "Topical")
REMOVE_KINDS = {k: EmergencyStockMovement.KINDS[k] for k in ("expired", "damaged", "adjustment")}


@bp.route("/")
@roles_required("nurse")
def dashboard():
    visits = Visit.query.filter(Visit.status != "completed").order_by(Visit.created_at.asc()).all()
    unassigned = [v for v in visits if v.doctor is None]
    low = [d for d in EmergencyDrug.query.filter_by(is_active=True).all() if d.is_low or d.is_expired]
    return render_template("nurse/dashboard.html", visits=visits, unassigned=unassigned, low_drugs=low)


def observation_trends(entries):
    entries = sorted(entries, key=lambda entry: (entry.created_at, entry.id))
    if not entries:
        return []
    start, end = entries[0].created_at, entries[-1].created_at
    span = (end - start).total_seconds()
    charts = []
    specs = [("temperature", "Temperature (°C)"), ("blood_pressure", "Blood pressure (mmHg)"),
             ("pulse", "Pulse (bpm)"), ("respiration", "Respiration (/min)"),
             ("weight", "Weight (kg)"), ("spo2", "SpO₂ (%)")]
    for field, label in specs:
        series = []
        names = ("Systolic", "Diastolic") if field == "blood_pressure" else (label,)
        for index, name in enumerate(names):
            points = []
            for entry in entries:
                raw = getattr(entry, field) or ""
                if field == "blood_pressure":
                    parts = raw.split("/")
                    raw = parts[index] if len(parts) == 2 else ""
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    value = None
                if value is not None and (not math.isfinite(value) or value <= 0 or value > 10000):
                    value = None
                points.append({"value": value, "time": entry.created_at,
                               "x": round(55 + 410 * (entry.created_at - start).total_seconds() / span, 2)
                               if span else 260})
            series.append({"name": name, "color": ("#245d96", "#a83f5b")[index], "points": points})
        values = [point["value"] for line in series for point in line["points"] if point["value"] is not None]
        if not values:
            charts.append({"label": label, "series": [], "ticks": []})
            continue
        low, high = min(values), max(values)
        padding = max((high - low) * 0.1, 1)
        low, high = max(0, low - padding), high + padding
        for line in series:
            segments, segment = [], []
            for point in line["points"]:
                if point["value"] is None:
                    if segment:
                        segments.append(" ".join(segment))
                        segment = []
                    continue
                point["y"] = round(160 - 130 * (point["value"] - low) / (high - low), 2)
                segment.append(f"{point['x']},{point['y']}")
            if segment:
                segments.append(" ".join(segment))
            line["segments"] = segments
        charts.append({"label": label, "series": series,
                       "ticks": [{"y": 160 - i * 65, "label": f"{low + (high - low) * i / 2:.1f}"}
                                 for i in range(3)], "start": start, "end": end})
    return charts


@bp.route("/observations/<path:hospital_id>", methods=["GET", "POST"])
@roles_required("nurse", "doctor", "visiting_doctor")
def observations(hospital_id):
    patient = get_patient_or_404(hospital_id)
    if "observation_token" not in session:
        session["observation_token"] = secrets.token_hex(32)
    if request.method == "POST":
        if not can_access(current_user, "nursing", "manage"):
            abort(403)
        token = request.form.get("csrf_token", "")
        if not secrets.compare_digest(token, session["observation_token"]):
            abort(400)
        notes = (request.form.get("notes") or "").strip()
        medication = (request.form.get("medication") or "").strip()
        signature = (request.form.get("signature") or "").strip()
        values = {key: (request.form.get(key) or "").strip() for key in VITAL_FIELDS}
        if not notes or len(notes) > 10000 or any(len(value) > 30 for value in values.values()):
            flash("Enter observation notes (up to 10,000 characters); vital fields allow 30 characters each.", "danger")
        elif len(medication) > 5000 or len(signature) > 120:
            flash("Medication allows 5,000 characters and signature allows 120 characters.", "danger")
        else:
            db.session.add(PatientObservation(patient=patient, recorded_by=current_user, notes=notes,
                                              medication=medication or None, signature=signature or None,
                                              **{key: value or None for key, value in values.items()}))
            db.session.commit()
            flash("Patient observation recorded.", "success")
            return redirect(url_for("nurse.observations", hospital_id=patient.hospital_id))
    page = max(1, request.args.get("page", 1, type=int))
    entries = PatientObservation.query.filter_by(patient_id=patient.id).order_by(
        PatientObservation.created_at.desc(), PatientObservation.id.desc()).paginate(page=page, per_page=30)
    recent = PatientObservation.query.filter_by(patient_id=patient.id).order_by(
        PatientObservation.created_at.desc(), PatientObservation.id.desc()).limit(100).all()
    return render_template("nurse/observations.html", p=patient, entries=entries,
                           trends=observation_trends(recent), csrf_token=session["observation_token"])


@bp.route("/vitals/<int:visit_id>", methods=["GET", "POST"])
@roles_required("nurse", "doctor", "visiting_doctor")
def vitals(visit_id):
    visit = db.get_or_404(Visit, visit_id)
    if request.method == "POST":
        for field in VITAL_FIELDS:
            setattr(visit, field, (request.form.get(field) or "").strip() or None)
        visit.vitals_by = current_user
        visit.vitals_at = now()
        db.session.commit()
        flash(f"Vitals recorded for {visit.patient.full_name}.", "success")
        if current_user.role in ("doctor", "visiting_doctor"):
            return redirect(url_for("doctor.consult", visit_id=visit.id))
        return redirect(url_for("nurse.dashboard"))
    return render_template("nurse/vitals.html", v=visit)


@bp.route("/assign/<int:visit_id>", methods=["GET", "POST"])
@roles_required("nurse")
def assign(visit_id):
    visit = db.get_or_404(Visit, visit_id)
    if visit.status == "completed":
        flash("This visit is already completed. Start a new visit at the cashier.", "warning")
        return redirect(url_for("nurse.dashboard"))
    if request.method == "POST":
        doctor = db.session.get(User, parse_int(request.form.get("doctor_id")))
        if doctor is None or doctor.role not in DOCTOR_ROLES or not doctor.is_active_user:
            flash("Select a doctor.", "danger")
        elif visit.assign_doctor(doctor, current_user, (request.form.get("note") or "").strip() or None):
            db.session.commit()
            flash(f"{visit.patient.full_name} assigned to {doctor.display_name}.", "success")
            return redirect(url_for("nurse.dashboard"))
        else:
            flash(f"{visit.patient.full_name} is already with {doctor.display_name}.", "info")
    return render_template("nurse/assign.html", v=visit, doctors=active_doctors())


# ---------------------------------------------------------------- emergency drugs (nurses' office)

def move_emergency_stock(drug, change, kind, note=None, use=None):
    drug.quantity += change
    db.session.add(EmergencyStockMovement(drug=drug, change=change, balance_after=drug.quantity, kind=kind,
                                          note=note, use=use, user=current_user))


@bp.route("/emergency")
@roles_required("nurse")
def emergency():
    drugs = EmergencyDrug.query.order_by(EmergencyDrug.is_active.desc(), EmergencyDrug.name).all()
    today = datetime.combine(date.today(), time.min)
    recent = EmergencyDrugUse.query.order_by(EmergencyDrugUse.id.desc()).limit(10).all()
    used_today = EmergencyDrugUse.query.filter(EmergencyDrugUse.created_at >= today).count()
    return render_template("nurse/emergency.html", drugs=drugs, recent=recent, used_today=used_today,
                           low=sum(1 for d in drugs if d.is_active and d.is_low),
                           expiring=sum(1 for d in drugs if d.is_active and (d.is_expired or d.expires_soon)))


@bp.route("/emergency/use", methods=["GET", "POST"])
@roles_required("nurse")
def emergency_use():
    drugs = EmergencyDrug.query.filter_by(is_active=True).order_by(EmergencyDrug.name).all()
    form = request.form if request.method == "POST" else request.args
    if request.method == "POST":
        hid = (form.get("hospital_id") or "").strip().upper()
        patient = Patient.query.filter_by(hospital_id=hid).first()
        drug = db.session.get(EmergencyDrug, parse_int(form.get("drug_id")))
        qty = parse_int(form.get("quantity"))
        reason = (form.get("reason") or "").strip()
        error = None
        if patient is None:
            error = f"No patient with hospital ID '{hid}'."
        elif drug is None or not drug.is_active:
            error = "Select the drug used."
        elif qty <= 0:
            error = "Enter the quantity used."
        elif qty > drug.quantity:
            error = f"Only {drug.quantity} {drug.unit} of {drug.label} left in the office."
        elif drug.is_expired:
            error = f"{drug.label} (batch {drug.batch_no or '-'}) is expired. Remove it from stock instead."
        elif not reason:
            error = "Enter the reason / indication."
        if error:
            flash(error, "danger")
        else:
            use = EmergencyDrugUse(drug=drug, patient=patient, visit=patient.current_visit, quantity=qty,
                                   dose=(form.get("dose") or "").strip() or None, route=form.get("route") or None,
                                   reason=reason, notes=(form.get("notes") or "").strip() or None,
                                   witness=(form.get("witness") or "").strip() or None,
                                   administered_by=current_user)
            db.session.add(use)
            move_emergency_stock(drug, -qty, "used", f"{patient.hospital_id} {patient.full_name} - {reason}", use)
            db.session.commit()
            flash(f"Recorded: {qty} {drug.unit} of {drug.label} given to {patient.full_name} "
                  f"({patient.hospital_id}). {drug.quantity} left.", "success")
            if drug.is_low:
                flash(f"{drug.label} is now at or below its reorder level.", "warning")
            return redirect(url_for("nurse.emergency"))
    patient = None
    if form.get("hospital_id"):
        patient = Patient.query.filter_by(hospital_id=form.get("hospital_id").strip().upper()).first()
    return render_template("nurse/emergency_use.html", drugs=drugs, form=form, patient=patient, routes=ROUTES)


@bp.route("/emergency/drug/new", methods=["GET", "POST"])
@bp.route("/emergency/drug/<int:drug_id>/edit", methods=["GET", "POST"])
@roles_required("nurse")
def emergency_drug_form(drug_id=None):
    drug = db.get_or_404(EmergencyDrug, drug_id) if drug_id else None
    if request.method == "POST":
        f = request.form
        name = (f.get("name") or "").strip()
        if not name:
            flash("Drug name is required.", "danger")
            return render_template("nurse/emergency_drug_form.html", drug=drug, form=f)
        is_new = drug is None
        if is_new:
            drug = EmergencyDrug(quantity=0)
            db.session.add(drug)
        drug.name = name
        for field in ("form", "strength", "batch_no"):
            setattr(drug, field, (f.get(field) or "").strip() or None)
        drug.unit = (f.get("unit") or "").strip() or "unit"
        drug.reorder_level = parse_int(f.get("reorder_level"))
        drug.expiry_date = parse_date(f.get("expiry_date"))
        drug.is_active = is_new or bool(f.get("is_active"))
        if is_new and parse_int(f.get("quantity")) > 0:
            db.session.flush()
            move_emergency_stock(drug, parse_int(f.get("quantity")), "opening", "Opening stock")
        db.session.commit()
        flash(f"{drug.label} saved.", "success")
        return redirect(url_for("nurse.emergency_stock", drug_id=drug.id))
    return render_template("nurse/emergency_drug_form.html", drug=drug, form={})


@bp.route("/emergency/drug/<int:drug_id>", methods=["GET", "POST"])
@roles_required("nurse")
def emergency_stock(drug_id):
    drug = db.get_or_404(EmergencyDrug, drug_id)
    if request.method == "POST":
        f = request.form
        qty = parse_int(f.get("quantity"))
        note = (f.get("note") or "").strip()
        if qty <= 0:
            flash("Enter a quantity greater than zero.", "danger")
        elif f.get("action") == "receive":
            if f.get("batch_no"):
                drug.batch_no = f.get("batch_no").strip()
            if parse_date(f.get("expiry_date")):
                drug.expiry_date = parse_date(f.get("expiry_date"))
            move_emergency_stock(drug, qty, "received", note or "Received")
            db.session.commit()
            flash(f"Received {qty} {drug.unit} of {drug.label}.", "success")
        elif f.get("kind") in REMOVE_KINDS:
            if qty > drug.quantity:
                flash("Cannot remove more than is in stock.", "danger")
            elif not note:
                flash("Give a reason for removing stock.", "danger")
            else:
                move_emergency_stock(drug, -qty, f.get("kind"), note)
                db.session.commit()
                flash(f"Removed {qty} {drug.unit} of {drug.label}.", "success")
        return redirect(url_for("nurse.emergency_stock", drug_id=drug.id))
    return render_template("nurse/emergency_stock.html", drug=drug, remove_kinds=REMOVE_KINDS)


@bp.route("/emergency/log")
@roles_required("nurse")
def emergency_log():
    start = parse_date(request.args.get("start")) or date.today() - timedelta(days=30)
    end = parse_date(request.args.get("end")) or date.today()
    query = EmergencyDrugUse.query.filter(EmergencyDrugUse.created_at.between(datetime.combine(start, time.min),
                                                                              datetime.combine(end, time.max)))
    drug_id, nurse_id = parse_int(request.args.get("drug_id")), parse_int(request.args.get("nurse_id"))
    q = (request.args.get("q") or "").strip()
    if drug_id:
        query = query.filter(EmergencyDrugUse.drug_id == drug_id)
    if nurse_id:
        query = query.filter(EmergencyDrugUse.administered_by_id == nurse_id)
    if q:
        like = f"%{q}%"
        query = query.join(Patient).filter(or_(Patient.hospital_id.ilike(like), Patient.first_name.ilike(like),
                                               Patient.last_name.ilike(like)))
    uses = query.order_by(EmergencyDrugUse.created_at.desc()).all()
    by_drug, by_nurse = {}, {}
    for u in uses:
        key = (u.drug.label, u.drug.unit)
        by_drug[key] = by_drug.get(key, 0) + u.quantity
        name = u.administered_by.full_name
        by_nurse[name] = by_nurse.get(name, 0) + 1
    staff_ids = {i for (i,) in db.session.query(EmergencyDrugUse.administered_by_id).distinct()}
    staff = User.query.filter(or_(User.role == "nurse", User.id.in_(staff_ids))).order_by(User.full_name).all()
    return render_template("nurse/emergency_log.html", uses=uses, start=start, end=end, q=q, drug_id=drug_id,
                           nurse_id=nurse_id, by_drug=by_drug, by_nurse=by_nurse, staff=staff,
                           drugs=EmergencyDrug.query.order_by(EmergencyDrug.name).all())
