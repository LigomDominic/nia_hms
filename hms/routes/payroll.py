import re
import secrets
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from ..extensions import db
from ..models import EXPENSE_METHODS, Expense, IouSettlement, SalaryPayment, StaffIou, User
from ..permissions import can_access
from ..utils import parse_money, roles_required

bp = Blueprint("payroll", __name__, url_prefix="/payroll")

_PERIOD = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _token():
    if "payroll_token" not in session:
        session["payroll_token"] = secrets.token_hex(32)
    return session["payroll_token"]


def _check_token():
    token = session.get("payroll_token", "")
    if not token or not secrets.compare_digest(request.form.get("csrf_token", ""), token):
        abort(400)


def _can_manage():
    if not can_access(current_user, "payroll", "manage"):
        abort(403)


def _outstanding_ious(user_id):
    return [i for i in StaffIou.query.filter_by(user_id=user_id).order_by(StaffIou.created_at, StaffIou.id)
            if i.remaining > 0]


def _period_label(period):
    from datetime import datetime
    return datetime.strptime(period, "%Y-%m").strftime("%B %Y")


@bp.route("/")
@roles_required("cashier")
def index():
    staff = User.query.filter_by(is_active_user=True).order_by(User.role, User.full_name).all()
    iou_totals = {u.id: sum(i.remaining for i in _outstanding_ious(u.id)) for u in staff}
    current = date.today().strftime("%Y-%m")
    paid = {p.user_id: p for p in SalaryPayment.query.filter_by(period=current)}
    return render_template("payroll/index.html", staff=staff, iou_totals=iou_totals,
                           paid=paid, period=current, csrf_token=_token())


@bp.route("/<int:user_id>")
@roles_required("cashier")
def detail(user_id):
    staff = db.get_or_404(User, user_id)
    ious = StaffIou.query.filter_by(user_id=user_id).order_by(StaffIou.created_at.desc(),
                                                             StaffIou.id.desc()).all()
    payments = (SalaryPayment.query.filter_by(user_id=user_id)
                .order_by(SalaryPayment.period.desc(), SalaryPayment.id.desc()).all())
    outstanding = sum(i.remaining for i in ious if i.remaining > 0)
    return render_template("payroll/detail.html", staff=staff, ious=ious, payments=payments,
                           outstanding=outstanding, methods=EXPENSE_METHODS,
                           current_period=date.today().strftime("%Y-%m"), csrf_token=_token())


@bp.route("/<int:user_id>/salary", methods=["POST"])
@roles_required("cashier")
def set_salary(user_id):
    _can_manage()
    _check_token()
    staff = db.get_or_404(User, user_id)
    amount = parse_money(request.form.get("monthly_salary"), -1)
    if amount < 0 or amount > 100_000_000:
        flash("Enter a valid monthly salary (0 or more).", "danger")
    else:
        staff.monthly_salary = amount or None
        db.session.commit()
        flash(f"{staff.full_name}: monthly salary updated.", "success")
    return redirect(request.form.get("next") or url_for("payroll.index"))


@bp.route("/<int:user_id>/pay", methods=["POST"])
@roles_required("cashier")
def pay(user_id):
    _can_manage()
    _check_token()
    staff = db.get_or_404(User, user_id)
    period = (request.form.get("period") or "").strip()
    gross = parse_money(request.form.get("gross"), -1)
    deduction = parse_money(request.form.get("iou_deduction"), 0)
    method = request.form.get("method")
    note = (request.form.get("note") or "").strip()[:255]
    outstanding = _outstanding_ious(user_id)
    max_deduction = round(sum(i.remaining for i in outstanding), 2)
    today_period = date.today().strftime("%Y-%m")

    if not _PERIOD.match(period) or period > today_period:
        flash("Choose a valid salary month (not in the future).", "danger")
    elif gross <= 0 or gross > 100_000_000:
        flash("Enter a valid gross salary greater than zero.", "danger")
    elif method not in EXPENSE_METHODS:
        flash("Choose cash or bank.", "danger")
    elif deduction < 0 or deduction > min(max_deduction, gross):
        flash(f"IOU deduction must be between 0 and {min(max_deduction, gross):,.2f} "
              f"(outstanding {max_deduction:,.2f}, gross {gross:,.2f}).", "danger")
    elif SalaryPayment.query.filter_by(user_id=user_id, period=period).first():
        flash(f"{staff.full_name} has already been paid for {_period_label(period)}.", "danger")
    else:
        net = round(gross - deduction, 2)
        payment = SalaryPayment(user=staff, period=period, gross=gross, iou_deduction=deduction,
                                net=net, method=method, note=note or None, paid_by=current_user)
        db.session.add(payment)
        db.session.flush()
        left = deduction
        for iou in outstanding:
            if left <= 0:
                break
            applied = round(min(iou.remaining, left), 2)
            iou.settled_amount = round(iou.settled_amount + applied, 2)
            db.session.add(IouSettlement(iou=iou, amount=applied, kind="salary_deduction",
                                         salary_payment=payment, recorded_by=current_user,
                                         note=f"Deducted from {_period_label(period)} salary"))
            left = round(left - applied, 2)
        desc = f"Salary {_period_label(period)} — {staff.full_name}"
        if deduction:
            desc += f" (IOU deducted: {deduction:,.2f})"
        exp = Expense(expense_date=date.today(), category="Salaries & wages", description=desc,
                      method=method, amount=net, payee=staff.full_name,
                      reference=f"SAL{period}-U{staff.id}", recorded_by=current_user)
        db.session.add(exp)
        db.session.flush()
        payment.expense_id = exp.id
        db.session.commit()
        flash(f"{staff.full_name} paid {net:,.2f} for {_period_label(period)}"
              + (f" (gross {gross:,.2f}, IOU deducted {deduction:,.2f})." if deduction else "."),
              "success")
    return redirect(url_for("payroll.detail", user_id=user_id))


@bp.route("/<int:user_id>/iou", methods=["POST"])
@roles_required("cashier")
def issue_iou(user_id):
    _can_manage()
    _check_token()
    staff = db.get_or_404(User, user_id)
    amount = parse_money(request.form.get("amount"), -1)
    method = request.form.get("method")
    reason = (request.form.get("reason") or "").strip()[:255]
    if amount <= 0 or amount > 100_000_000:
        flash("Enter a valid IOU amount greater than zero.", "danger")
    elif method not in EXPENSE_METHODS:
        flash("Choose cash or bank.", "danger")
    elif not reason:
        flash("Give a reason for the advance.", "danger")
    else:
        iou = StaffIou(user=staff, amount=amount, reason=reason, method=method,
                       issued_by=current_user)
        db.session.add(iou)
        db.session.flush()
        exp = Expense(expense_date=date.today(), category="Salaries & wages",
                      description=f"Staff advance (IOU) to {staff.full_name}: {reason}",
                      method=method, amount=amount, payee=staff.full_name,
                      reference=f"IOU-{iou.id}", recorded_by=current_user)
        db.session.add(exp)
        db.session.flush()
        iou.expense_id = exp.id
        db.session.commit()
        flash(f"IOU of {amount:,.2f} issued to {staff.full_name} ({EXPENSE_METHODS[method]}).", "success")
    return redirect(url_for("payroll.detail", user_id=user_id))


@bp.route("/iou/<int:iou_id>/repay", methods=["POST"])
@roles_required("cashier")
def repay_iou(iou_id):
    _can_manage()
    _check_token()
    iou = db.get_or_404(StaffIou, iou_id)
    amount = parse_money(request.form.get("amount"), -1)
    method = request.form.get("method")
    if iou.remaining <= 0:
        flash("This IOU is already settled.", "warning")
    elif amount <= 0 or amount > iou.remaining:
        flash(f"Repayment must be between 0 and {iou.remaining:,.2f} (amount outstanding).", "danger")
    elif method not in EXPENSE_METHODS:
        flash("Choose cash or bank.", "danger")
    else:
        iou.settled_amount = round(iou.settled_amount + amount, 2)
        db.session.add(IouSettlement(iou=iou, amount=amount, kind="repayment", method=method,
                                     recorded_by=current_user, note="Repaid by staff"))
        db.session.commit()
        flash(f"Repayment of {amount:,.2f} recorded; {iou.remaining:,.2f} still outstanding."
              if iou.remaining > 0 else "IOU fully settled.", "success")
    return redirect(url_for("payroll.detail", user_id=iou.user_id))


@bp.route("/iou/<int:iou_id>/void", methods=["POST"])
@roles_required()
def void_iou(iou_id):
    _check_token()
    iou = db.get_or_404(StaffIou, iou_id)
    if iou.settled_amount > 0:
        flash("Cannot void an IOU that already has settlements — record a correction instead.", "danger")
    else:
        if iou.expense:
            db.session.delete(iou.expense)
        db.session.delete(iou)
        db.session.commit()
        flash("IOU voided and its expense entry removed.", "info")
    return redirect(url_for("payroll.detail", user_id=iou.user_id))


@bp.route("/payment/<int:payment_id>/void", methods=["POST"])
@roles_required()
def void_payment(payment_id):
    _check_token()
    payment = db.get_or_404(SalaryPayment, payment_id)
    user_id = payment.user_id
    for s in payment.iou_settlements:
        s.iou.settled_amount = round(s.iou.settled_amount - s.amount, 2)
        db.session.delete(s)
    if payment.expense:
        db.session.delete(payment.expense)
    db.session.delete(payment)
    db.session.commit()
    flash(f"Salary payment for {payment.period_label} voided; any IOU deductions were restored.", "info")
    return redirect(url_for("payroll.detail", user_id=user_id))
