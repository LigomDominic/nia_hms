from datetime import date, datetime, time

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from ..app_settings import doc_number
from ..patient_ids import new_hospital_id
from ..billing import BillingError, cancel_bill, create_bill, deposit_to_wallet, record_payment, withdraw_from_wallet
from ..extensions import db
from ..models import (DOCTOR_ROLES, PAYMENT_METHODS, Bill, LabRequest, LabRequestItem, LabTest, Patient,
                      Payment, Setting, User, Visit, now)
from ..utils import parse_date, parse_int, parse_money, roles_required
from .patients import fill_patient, get_patient_or_404

bp = Blueprint("cashier", __name__, url_prefix="/cashier")

CASH_METHODS = {k: v for k, v in PAYMENT_METHODS.items() if k != "wallet"}


def active_doctors():
    return User.query.filter(User.role.in_(DOCTOR_ROLES), User.is_active_user.is_(True)).order_by(User.full_name).all()


def _sent_to(visit):
    if visit.doctor:
        return f"Assigned to {visit.doctor.display_name}."
    return "Sent to the nurses' station for doctor assignment."


def today_start():
    return datetime.combine(date.today(), time.min)


def file_retrieval_dormant_days(patient):
    """Days since the patient's last visit (0 if never visited)."""
    if not patient.visits:
        return 0
    return (now() - patient.visits[0].created_at).days


def has_unpaid_file_retrieval(patient):
    return any("file retrieval" in (b.description or "").lower()
               and b.status in ("unpaid", "part_paid") for b in patient.bills)


def open_visit(patient, form, visit_type):
    """Create a consultation visit, optionally charging fees. Returns (visit, error, retrieval_bill)."""
    doctor = None
    if form.get("doctor_id"):
        doctor = db.session.get(User, int(form.get("doctor_id") or 0))
        if doctor is None or doctor.role not in DOCTOR_ROLES:
            return None, "Select a valid doctor, or leave it for the nurse to assign.", None
    dormant_days = file_retrieval_dormant_days(patient)
    visit = Visit(patient=patient, visit_type=visit_type,
                  complaint=(form.get("complaint") or "").strip() or None, created_by=current_user)
    db.session.add(visit)
    ret_bill = None
    threshold = int(Setting.get("file_retrieval_days") or 30)
    if dormant_days > threshold and not has_unpaid_file_retrieval(patient):
        fee = Setting.get_money("file_retrieval_fee")
        if fee > 0:
            ret_bill = create_bill(patient, "service",
                                   f"File retrieval - returning after {dormant_days} days", fee,
                                   current_user, visit=visit)
    if doctor:
        visit.assign_doctor(doctor, current_user)
    if form.get("charge_consultation"):
        fee = parse_money(form.get("consultation_fee"))
        if fee > 0:
            visit.consultation_fee = fee
            bill = create_bill(patient, "consultation", f"Consultation - {doctor.display_name}" if doctor else "Consultation", fee,
                               current_user, visit=visit)
            method = form.get("consultation_method")
            if method in CASH_METHODS and bill.balance > 0 and form.get("collect_consultation_now"):
                record_payment(bill, bill.balance, method, current_user, form.get("reference"))
    return visit, None, ret_bill


@bp.route("/")
@roles_required("cashier")
def dashboard():
    pending = (Bill.query.filter(Bill.status.in_(("unpaid", "part_paid")))
               .order_by(Bill.created_at.asc()).all())
    today_payments = Payment.query.filter(Payment.created_at >= today_start()).all()
    totals = {}
    for p in today_payments:
        totals[p.method] = totals.get(p.method, 0) + p.amount
    new_today = Patient.query.filter(Patient.created_at >= today_start()).count()
    return render_template("cashier/dashboard.html", pending=pending, totals=totals,
                           total_today=sum(totals.values()), new_today=new_today)


@bp.route("/register", methods=["GET", "POST"])
@roles_required("cashier")
def register():
    card_fee = Setting.get_money("card_fee")
    consultation_fee = Setting.get_money("consultation_fee")
    if request.method == "POST":
        form = request.form
        if not form.get("first_name") or not form.get("last_name") or not form.get("phone"):
            flash("First name, last name and phone number are required.", "danger")
            return render_template("cashier/register.html", doctors=active_doctors(), card_fee=card_fee,
                                   consultation_fee=consultation_fee, form=form, methods=CASH_METHODS)
        method = form.get("card_method")
        if method not in CASH_METHODS:
            flash("Select how the card fee was paid.", "danger")
            return render_template("cashier/register.html", doctors=active_doctors(), card_fee=card_fee,
                                   consultation_fee=consultation_fee, form=form, methods=CASH_METHODS)
        try:
            patient = Patient(registered_by=current_user)
            fill_patient(patient, form)
            db.session.add(patient)
            db.session.flush()
            patient.hospital_id = new_hospital_id(patient)

            deposit = parse_money(form.get("wallet_deposit"))
            if deposit > 0:
                deposit_to_wallet(patient, deposit, method, current_user, form.get("reference"),
                                  apply_to_outstanding=False)

            card_bill = create_bill(patient, "card", "Hospital card / registration fee", card_fee,
                                    current_user, auto_wallet=False)
            if card_bill.balance > 0:
                record_payment(card_bill, card_bill.balance, method, current_user, form.get("reference"))

            visit, error, ret_bill = open_visit(patient, form, "New")
            if error:
                raise BillingError(error)
            db.session.commit()
        except BillingError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return render_template("cashier/register.html", doctors=active_doctors(), card_fee=card_fee,
                                   consultation_fee=consultation_fee, form=form, methods=CASH_METHODS)
        flash(f"Patient registered. Hospital ID: {patient.hospital_id}. " + _sent_to(visit), "success")
        return redirect(url_for("patients.profile", hospital_id=patient.hospital_id))
    return render_template("cashier/register.html", doctors=active_doctors(), card_fee=card_fee,
                           consultation_fee=consultation_fee, form={}, methods=CASH_METHODS)


@bp.route("/visit/<path:hospital_id>", methods=["GET", "POST"])
@roles_required("cashier")
def new_visit(hospital_id):
    patient = get_patient_or_404(hospital_id)
    consultation_fee = Setting.get_money("consultation_fee")
    if request.method == "POST":
        try:
            visit, error, ret_bill = open_visit(patient, request.form, "Follow-up")
            if error:
                raise BillingError(error)
            db.session.commit()
        except BillingError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            msg = f"{patient.full_name}: " + _sent_to(visit)
            if ret_bill:
                msg += f" File retrieval fee of {ret_bill.amount:,.2f} billed (returning after {file_retrieval_dormant_days(patient)} days)."
            flash(msg, "success")
            return redirect(url_for("patients.profile", hospital_id=patient.hospital_id))
    return render_template("cashier/new_visit.html", p=patient, doctors=active_doctors(),
                           consultation_fee=consultation_fee, methods=CASH_METHODS,
                           dormant_days=file_retrieval_dormant_days(patient),
                           retrieval_days=int(Setting.get("file_retrieval_days") or 30),
                           retrieval_fee=Setting.get_money("file_retrieval_fee"),
                           retrieval_unpaid=has_unpaid_file_retrieval(patient))


@bp.route("/bill/<int:bill_id>", methods=["GET", "POST"])
@roles_required("cashier")
def pay_bill(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    if request.method == "POST":
        try:
            record_payment(bill, parse_money(request.form.get("amount")), request.form.get("method"),
                           current_user, request.form.get("reference"))
            db.session.commit()
        except BillingError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            msg = "Payment received."
            if bill.status == "paid":
                if bill.lab_request is not None:
                    msg += " Lab request posted to the Laboratory."
                elif bill.prescription is not None:
                    msg += " Prescription posted to the Pharmacy for dispensing."
            flash(msg, "success")
            return redirect(url_for("cashier.receipt", bill_id=bill.id, print=1))
    return render_template("cashier/pay_bill.html", bill=bill)


@bp.route("/bill/<int:bill_id>/cancel", methods=["POST"])
@roles_required("cashier")
def cancel(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    if bill.status == "paid":
        flash("Paid bills cannot be cancelled here.", "danger")
    elif bill.status != "cancelled":
        cancel_bill(bill, current_user)
        if bill.lab_request is not None:
            bill.lab_request.status = "cancelled"
        if bill.prescription is not None:
            bill.prescription.status = "cancelled"
        db.session.commit()
        flash(f"Bill #{bill.id} cancelled. Any amount paid was returned to the patient's wallet.", "info")
    return redirect(url_for("patients.profile", hospital_id=bill.patient.hospital_id))


@bp.route("/bill/<int:bill_id>/receipt")
@roles_required("cashier")
def receipt(bill_id):
    return render_template("cashier/receipt.html", bill=db.get_or_404(Bill, bill_id))


@bp.route("/bill/<int:bill_id>/receipt-email", methods=["POST"])
@roles_required("cashier")
def receipt_email(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    from ..mailer import send_mail
    ok, err = send_mail(f"{Setting.get('hospital_name')} - Payment receipt "
                        f"{doc_number('receipt', bill.id)}",
                        render_template("email/receipt.html", bill=bill,
                                        cashier=current_user.full_name),
                        render_template("email/receipt.txt", bill=bill,
                                        cashier=current_user.full_name),
                        bill.patient.email)
    flash(f"Receipt emailed to {bill.patient.email}." if ok
          else err or "Receipt could not be emailed.", "success" if ok else "warning")
    return redirect(url_for("cashier.receipt", bill_id=bill_id))


@bp.route("/wallet/<path:hospital_id>", methods=["GET", "POST"])
@roles_required("cashier")
def wallet(hospital_id):
    patient = get_patient_or_404(hospital_id)
    if request.method == "POST":
        action = request.form.get("action", "deposit")
        amount = parse_money(request.form.get("amount"))
        try:
            if action == "refund":
                withdraw_from_wallet(patient, amount, current_user, request.form.get("reason") or "cash refund")
                msg = "Refund recorded."
            else:
                covered = deposit_to_wallet(patient, amount, request.form.get("method"), current_user,
                                            request.form.get("reference"),
                                            apply_to_outstanding=bool(request.form.get("apply_outstanding")))
                msg = "Wallet funded."
                if covered:
                    msg += f" {current_app.jinja_env.filters['money'](covered)} was applied to outstanding bills."
            db.session.commit()
        except BillingError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(msg, "success")
        return redirect(url_for("cashier.wallet", hospital_id=patient.hospital_id))
    return render_template("cashier/wallet.html", p=patient, methods=CASH_METHODS)


@bp.route("/walk-in-lab/<path:hospital_id>", methods=["GET", "POST"])
@roles_required("cashier", "lab")
def walk_in_lab(hospital_id):
    """Lab tests for walk-in patients - no doctor's consultation needed."""
    patient = get_patient_or_404(hospital_id)
    tests = LabTest.query.filter_by(is_active=True).order_by(LabTest.name).all()
    if request.method == "POST":
        chosen = [db.session.get(LabTest, parse_int(t)) for t in request.form.getlist("test_ids")]
        chosen = [t for t in chosen if t is not None and t.is_active]
        if not chosen:
            flash("Select at least one test.", "danger")
        else:
            referring = (request.form.get("referring_doctor") or "").strip()
            notes = "Walk-in request" + (f" - referred by {referring}" if referring else "")
            req = LabRequest(patient=patient, clinical_notes=notes)
            for t in chosen:
                req.items.append(LabRequestItem(test=t, test_name=t.name, price=t.price, unit=t.unit,
                                                reference_range=t.reference_range))
            db.session.add(req)
            bill = create_bill(patient, "lab", f"Lab (walk-in): {req.test_names}", req.total,
                               current_user, record=req)
            db.session.commit()
            if req.status == "sent_to_lab":
                flash("Walk-in lab request created and fully paid - sent to the Laboratory.", "success")
            elif bill.amount_paid > 0:
                flash(f"Request created; balance {bill.balance:,.2f} to collect.", "info")
            else:
                flash("Walk-in lab request created. Collect payment to send it to the Lab.", "info")
            if req.status != "sent_to_lab" and current_user.role in ("admin", "cashier"):
                return redirect(url_for("cashier.pay_bill", bill_id=bill.id))
            return redirect(url_for("lab.dashboard") if req.status == "sent_to_lab"
                            else url_for("patients.profile", hospital_id=patient.hospital_id))
    return render_template("cashier/walk_in_lab.html", p=patient, tests=tests)


@bp.route("/payments")
@roles_required("cashier")
def payments():
    start = parse_date(request.args.get("start"))
    end = parse_date(request.args.get("end"))
    query = Payment.query.order_by(Payment.id.desc())
    if start:
        query = query.filter(Payment.created_at >= datetime.combine(start, time.min))
    if end:
        query = query.filter(Payment.created_at <= datetime.combine(end, time.max))
    rows = query.limit(500 if (start or end) else 300).all()
    by_method = {}
    for p in rows:
        by_method[p.method_label] = by_method.get(p.method_label, 0) + p.amount
    ctx = dict(payments=rows, by_method=by_method, total=sum(p.amount for p in rows),
               start=start, end=end)
    if request.args.get("print"):
        return render_template("cashier/payments_print.html", **ctx)
    return render_template("cashier/payments.html", **ctx)
