import secrets
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from ..extensions import db
from ..models import EXPENSE_CATEGORIES, EXPENSE_METHODS, Expense
from ..permissions import can_access
from ..utils import parse_date, parse_money, roles_required

bp = Blueprint("expenses", __name__, url_prefix="/expenses")


def _token():
    if "expense_token" not in session:
        session["expense_token"] = secrets.token_hex(32)
    return session["expense_token"]


def _check_token():
    token = session.get("expense_token", "")
    if not token or not secrets.compare_digest(request.form.get("csrf_token", ""), token):
        abort(400)


@bp.route("/")
@roles_required("cashier")
def index():
    start = parse_date(request.args.get("start")) or date.today().replace(day=1)
    end = parse_date(request.args.get("end")) or date.today()
    method = request.args.get("method", "")
    category = request.args.get("category", "")
    query = Expense.query.filter(Expense.expense_date.between(start, end))
    if method in EXPENSE_METHODS:
        query = query.filter_by(method=method)
    if category:
        query = query.filter_by(category=category)
    entries = query.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()
    cash_total = sum(e.amount for e in entries if e.method == "cash")
    bank_total = sum(e.amount for e in entries if e.method == "bank")
    by_category = {}
    for e in entries:
        by_category[e.category] = by_category.get(e.category, 0) + e.amount
    return render_template("expenses/index.html", entries=entries, start=start, end=end,
                           method=method, category=category, categories=EXPENSE_CATEGORIES,
                           methods=EXPENSE_METHODS, cash_total=cash_total, bank_total=bank_total,
                           total=cash_total + bank_total, by_category=by_category, csrf_token=_token())


@bp.route("/new", methods=["GET", "POST"])
@roles_required("cashier")
def new():
    _token()
    if request.method == "POST":
        if not can_access(current_user, "expenses", "manage"):
            abort(403)
        _check_token()
        expense_date = parse_date(request.form.get("expense_date"))
        category = (request.form.get("category") or "").strip()
        description = (request.form.get("description") or "").strip()
        method = request.form.get("method")
        amount = parse_money(request.form.get("amount"), -1)
        payee = (request.form.get("payee") or "").strip()[:120]
        reference = (request.form.get("reference") or "").strip()[:80]
        if expense_date is None or expense_date > date.today():
            flash("Enter a valid expense date (not in the future).", "danger")
        elif category not in EXPENSE_CATEGORIES:
            flash("Choose a category.", "danger")
        elif not description or len(description) > 255:
            flash("Enter a description (up to 255 characters).", "danger")
        elif method not in EXPENSE_METHODS:
            flash("Choose cash or bank.", "danger")
        elif amount <= 0 or amount > 1_000_000_000:
            flash("Enter a valid amount greater than zero.", "danger")
        else:
            db.session.add(Expense(expense_date=expense_date, category=category,
                                   description=description, method=method, amount=amount,
                                   payee=payee or None, reference=reference or None,
                                   recorded_by=current_user))
            db.session.commit()
            flash(f"Expense recorded: {EXPENSE_METHODS[method]} {description}.", "success")
            return redirect(url_for("expenses.index"))
    return render_template("expenses/new.html", categories=EXPENSE_CATEGORIES,
                           methods=EXPENSE_METHODS, today=date.today(), csrf_token=_token())


@bp.route("/<int:expense_id>/delete", methods=["POST"])
@roles_required()
def delete(expense_id):
    _check_token()
    expense = db.get_or_404(Expense, expense_id)
    db.session.delete(expense)
    db.session.commit()
    flash("Expense entry deleted.", "info")
    return redirect(url_for("expenses.index"))
