from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..billing import create_bill
from ..extensions import db
from ..models import DOCTOR_ROLES, Drug, LabRequest, LabRequestItem, LabTest, Prescription, PrescriptionItem, Visit, now
from ..utils import parse_int, roles_required

bp = Blueprint("doctor", __name__, url_prefix="/doctor")


def _mine(query, column):
    if current_user.role in DOCTOR_ROLES:
        return query.filter(column == current_user.id)
    return query


def _visit_for_me(visit_id):
    visit = db.get_or_404(Visit, visit_id)
    if current_user.role in DOCTOR_ROLES and visit.doctor_id != current_user.id:
        abort(403)
    return visit


def _billing_note(bill, target):
    if bill.status == "paid":
        return f"Fully paid from the patient's e-wallet - sent straight to the {target}."
    if bill.amount_paid > 0:
        return (f"Part paid from e-wallet; balance {bill.balance:,.2f} posted to the Cashier. "
                f"It goes to the {target} once paid.")
    return f"Bill posted to the Cashier. It goes to the {target} once paid."


@bp.route("/")
@roles_required(*DOCTOR_ROLES)
def dashboard():
    visits = _mine(Visit.query.filter(Visit.status != "completed"), Visit.doctor_id).order_by(Visit.created_at).all()
    new_results = _mine(
        LabRequest.query.filter(LabRequest.status == "completed", LabRequest.doctor_viewed_at.is_(None)),
        LabRequest.doctor_id,
    ).order_by(LabRequest.completed_at.desc()).all()
    pending_labs = _mine(LabRequest.query.filter(LabRequest.status.in_(("awaiting_payment", "sent_to_lab",
                                                                         "in_progress"))),
                         LabRequest.doctor_id).order_by(LabRequest.created_at.desc()).all()
    recent = _mine(Visit.query.filter(Visit.status == "completed"), Visit.doctor_id).order_by(
        Visit.completed_at.desc()).limit(10).all()
    return render_template("doctor/dashboard.html", visits=visits, new_results=new_results,
                           pending_labs=pending_labs, recent=recent)


@bp.route("/consult/<int:visit_id>", methods=["GET", "POST"])
@roles_required(*DOCTOR_ROLES)
def consult(visit_id):
    visit = _visit_for_me(visit_id)
    if request.method == "POST":
        if "complaint" in request.form:
            visit.complaint = (request.form.get("complaint") or "").strip() or None
        visit.notes = request.form.get("notes")
        visit.diagnosis = request.form.get("diagnosis")
        if request.form.get("action") == "complete":
            visit.status = "completed"
            visit.completed_at = now()
            db.session.commit()
            flash("Consultation completed.", "success")
            return redirect(url_for("doctor.dashboard"))
        if visit.status == "waiting":
            visit.status = "in_consultation"
        db.session.commit()
        flash("Consultation notes saved.", "success")
        return redirect(url_for("doctor.consult", visit_id=visit.id))
    if visit.status == "waiting":
        visit.status = "in_consultation"
        db.session.commit()
    tests = LabTest.query.filter_by(is_active=True).order_by(LabTest.name).all()
    drugs = Drug.query.filter(Drug.is_active.is_(True)).order_by(Drug.name).all()
    return render_template("doctor/consult.html", v=visit, p=visit.patient, tests=tests, drugs=drugs)


@bp.route("/consult/<int:visit_id>/lab", methods=["POST"])
@roles_required(*DOCTOR_ROLES)
def request_lab(visit_id):
    visit = _visit_for_me(visit_id)
    tests = [db.session.get(LabTest, parse_int(t)) for t in request.form.getlist("test_ids")]
    tests = [t for t in tests if t is not None and t.is_active]
    if not tests:
        flash("Select at least one test.", "danger")
        return redirect(url_for("doctor.consult", visit_id=visit.id))
    req = LabRequest(patient=visit.patient, visit=visit, doctor=visit.doctor or current_user,
                     clinical_notes=request.form.get("clinical_notes"))
    for t in tests:
        req.items.append(LabRequestItem(test=t, test_name=t.name, price=t.price, unit=t.unit,
                                        reference_range=t.reference_range))
    db.session.add(req)
    bill = create_bill(visit.patient, "lab", f"Lab: {req.test_names}", req.total, current_user, visit=visit,
                       record=req)
    db.session.commit()
    flash(f"Lab request #{req.id} created. " + _billing_note(bill, "Laboratory"), "success")
    return redirect(url_for("doctor.consult", visit_id=visit.id))


@bp.route("/consult/<int:visit_id>/prescribe", methods=["POST"])
@roles_required(*DOCTOR_ROLES)
def prescribe(visit_id):
    visit = _visit_for_me(visit_id)
    rx = Prescription(patient=visit.patient, visit=visit, doctor=visit.doctor or current_user,
                      notes=request.form.get("rx_notes"))
    f = request.form
    with db.session.no_autoflush:
        for drug_id, dosage, freq, duration, qty in zip(f.getlist("drug_id"), f.getlist("dosage"),
                                                         f.getlist("frequency"), f.getlist("duration"),
                                                         f.getlist("quantity")):
            drug = db.session.get(Drug, parse_int(drug_id))
            qty = parse_int(qty)
            if drug is None or qty <= 0:
                continue
            rx.items.append(PrescriptionItem(drug=drug, drug_name=drug.label, dosage=dosage, frequency=freq,
                                             duration=duration, quantity=qty, unit_price=drug.unit_price))
    if not rx.items:
        rx.patient = None
        rx.visit = None
        flash("Add at least one drug with a quantity.", "danger")
        return redirect(url_for("doctor.consult", visit_id=visit.id))
    db.session.add(rx)
    bill = create_bill(visit.patient, "pharmacy", f"Drugs: {', '.join(i.drug_name for i in rx.items)}",
                       rx.total, current_user, visit=visit, record=rx)
    db.session.commit()
    flash(f"Prescription #{rx.id} created. " + _billing_note(bill, "Pharmacy"), "success")
    return redirect(url_for("doctor.consult", visit_id=visit.id))


@bp.route("/result/<int:req_id>")
@roles_required(*DOCTOR_ROLES)
def result(req_id):
    req = db.get_or_404(LabRequest, req_id)
    if current_user.role in DOCTOR_ROLES and req.doctor_id == current_user.id and req.status == "completed" \
            and req.doctor_viewed_at is None:
        req.doctor_viewed_at = now()
        db.session.commit()
    return render_template("lab/result.html", req=req, printable=False)
