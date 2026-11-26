from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..billing import create_bill
from ..extensions import db
from ..models import (CLINICAL_ROLES, DOCTOR_ROLES, AncProfile, AncVisit, Setting, User, now)
from ..utils import parse_date, parse_int, roles_required
from .cashier import active_doctors
from .patients import get_patient_or_404

bp = Blueprint("anc", __name__, url_prefix="/anc")

ANC_STAFF = ("nurse", "doctor", "visiting_doctor")

# free-text booking fields on the ANC card
TEXT_FIELDS = ("gravida", "para", "ethnic_group", "occupation", "husband_occupation", "height", "weight",
               "special_points", "past_obstetric_history", "past_medical_history", "family_history",
               "hx_oedema", "hx_headache", "hx_bowels", "hx_breath", "hx_micturition", "hx_discharge",
               "ex_teeth", "ex_breasts", "ex_lungs", "ex_heart", "ex_varicose", "ex_pelvics", "ex_cervical",
               "ex_observations", "inv_blood_group", "inv_rhesus", "inv_antibodies", "inv_genotype",
               "inv_vdrl", "inv_rtv", "inv_others", "notes")
DATE_FIELDS = ("lmp", "edd", "quickening_date", "ex_date", "inv_date")


def _fill(anc, form):
    for field in TEXT_FIELDS:
        setattr(anc, field, (form.get(field) or "").strip() or None)
    for field in DATE_FIELDS:
        setattr(anc, field, parse_date(form.get(field)))
    if anc.lmp and not anc.edd:
        anc.edd = anc.lmp + timedelta(days=280)  # Naegele's rule
    consultant = db.session.get(User, parse_int(form.get("consultant_id")))
    anc.consultant = consultant if consultant and consultant.role in DOCTOR_ROLES else None


def _billing_note(bill):
    if bill.status == "paid":
        return "Booking fee fully paid from the patient's e-wallet."
    if bill.amount_paid > 0:
        return f"Part paid from e-wallet; balance {bill.balance:,.2f} posted to the Cashier."
    return "Booking fee bill posted to the Cashier."


@bp.route("/")
@roles_required(*ANC_STAFF)
def dashboard():
    active = (AncProfile.query.filter_by(status="active")
              .join(AncProfile.patient).order_by(AncProfile.created_at.desc()).all())
    closed = (AncProfile.query.filter(AncProfile.status != "active")
              .order_by(AncProfile.delivered_at.desc().nullslast()).limit(20).all())
    today = date.today()
    due_soon = [a for a in active if a.next_visit and a.next_visit <= today + timedelta(days=7)]
    return render_template("anc/dashboard.html", active=active, closed=closed, due_soon=due_soon, today=today)


@bp.route("/book/<path:hospital_id>", methods=["GET", "POST"])
@roles_required(*ANC_STAFF)
def book(hospital_id):
    patient = get_patient_or_404(hospital_id)
    if patient.gender and patient.gender.lower().startswith("m"):
        flash("ANC booking is for female patients - check this patient's record.", "danger")
        return redirect(url_for("patients.profile", hospital_id=patient.hospital_id))
    if patient.current_anc:
        flash("This patient already has an active ANC card.", "info")
        return redirect(url_for("anc.card", anc_id=patient.current_anc.id))
    if request.method == "POST":
        anc = AncProfile(patient=patient, booked_by=current_user)
        db.session.add(anc)
        _fill(anc, request.form)
        fee = Setting.get_money("anc_fee")
        bill = None
        if fee > 0:
            edd_txt = anc.edd.strftime("%d %b %Y") if anc.edd else "-"
            bill = create_bill(patient, "service", f"Ante-natal booking (EDD {edd_txt})", fee, current_user)
        db.session.commit()
        flash(f"ANC card opened for {patient.full_name}. " + (_billing_note(bill) if bill else ""),
              "success")
        return redirect(url_for("anc.card", anc_id=anc.id))
    return render_template("anc/book.html", p=patient, anc=None, doctors=active_doctors(),
                           fee=Setting.get_money("anc_fee"))


@bp.route("/<int:anc_id>/edit", methods=["GET", "POST"])
@roles_required(*ANC_STAFF)
def edit(anc_id):
    anc = db.get_or_404(AncProfile, anc_id)
    if request.method == "POST":
        _fill(anc, request.form)
        db.session.commit()
        flash("ANC booking details updated.", "success")
        return redirect(url_for("anc.card", anc_id=anc.id))
    return render_template("anc/book.html", p=anc.patient, anc=anc, doctors=active_doctors(),
                           fee=0)


@bp.route("/<int:anc_id>")
@roles_required(*ANC_STAFF)
def card(anc_id):
    return render_template("anc/card.html", anc=db.get_or_404(AncProfile, anc_id))


@bp.route("/<int:anc_id>/visit", methods=["POST"])
@roles_required(*ANC_STAFF)
def add_visit(anc_id):
    anc = db.get_or_404(AncProfile, anc_id)
    if anc.status != "active":
        flash("Re-open the card before recording a visit.", "warning")
        return redirect(url_for("anc.card", anc_id=anc.id))
    f = request.form
    visit_date = parse_date(f.get("visit_date")) or date.today()
    v = AncVisit(
        anc=anc, visit_date=visit_date,
        gest_age=(f.get("gest_age") or "").strip() or anc.gest_age(visit_date) or None,
        weight=(f.get("weight") or "").strip() or None,
        urine_alb=(f.get("urine_alb") or "").strip() or None,
        urine_sugar=(f.get("urine_sugar") or "").strip() or None,
        bp=(f.get("bp") or "").strip() or None,
        sfh=(f.get("sfh") or "").strip() or None,
        presentation=(f.get("presentation") or "").strip() or None,
        fhr=(f.get("fhr") or "").strip() or None,
        oedema=(f.get("oedema") or "").strip() or None,
        pcv=(f.get("pcv") or "").strip() or None,
        next_visit=parse_date(f.get("next_visit")),
        seen_by=current_user,
    )
    db.session.add(v)
    db.session.commit()
    flash(f"ANC visit of {visit_date.strftime('%d %b %Y')} recorded.", "success")
    return redirect(url_for("anc.card", anc_id=anc.id) + "#visits")


@bp.route("/<int:anc_id>/exam", methods=["POST"])
@roles_required(*ANC_STAFF)
def exam(anc_id):
    anc = db.get_or_404(AncProfile, anc_id)
    anc.exam_head_brim = (request.form.get("exam_head_brim") or "").strip() or None
    anc.exam_pelvic_capacity = (request.form.get("exam_pelvic_capacity") or "").strip() or None
    anc.exam_date = parse_date(request.form.get("exam_date")) or date.today()
    anc.exam_by = current_user
    db.session.commit()
    flash("35/7-weeks examination recorded.", "success")
    return redirect(url_for("anc.card", anc_id=anc.id))


@bp.route("/<int:anc_id>/note", methods=["POST"])
@roles_required(*ANC_STAFF)
def note(anc_id):
    anc = db.get_or_404(AncProfile, anc_id)
    anc.notes = (request.form.get("notes") or "").strip()[:5000] or None
    db.session.commit()
    flash("Note saved on the ANC card.", "success")
    return redirect(url_for("anc.card", anc_id=anc.id) + "#note")


@bp.route("/<int:anc_id>/status", methods=["POST"])
@roles_required(*ANC_STAFF)
def set_status(anc_id):
    anc = db.get_or_404(AncProfile, anc_id)
    status = request.form.get("status")
    if status in AncProfile.STATUS_LABELS:
        anc.status = status
        anc.delivered_at = now() if status == "delivered" else None
        db.session.commit()
        flash(f"ANC card marked {anc.status_label.lower()}.", "success")
    return redirect(url_for("anc.card", anc_id=anc.id))


@bp.route("/<int:anc_id>/print")
@roles_required(*CLINICAL_ROLES)
def print_card(anc_id):
    return render_template("anc/print.html", anc=db.get_or_404(AncProfile, anc_id))
