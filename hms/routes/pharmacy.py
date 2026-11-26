from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import Drug, DrugStockMovement, Prescription, now
from ..utils import parse_date, parse_int, parse_money, roles_required

bp = Blueprint("pharmacy", __name__, url_prefix="/pharmacy")


def move_stock(drug, change, reason, note=None):
    drug.quantity += change
    db.session.add(DrugStockMovement(drug=drug, change=change, balance_after=drug.quantity, reason=reason,
                                     note=note, user=current_user))


@bp.route("/")
@roles_required("pharmacist")
def dashboard():
    ready = Prescription.query.filter_by(status="ready_to_dispense").order_by(Prescription.posted_at).all()
    awaiting = Prescription.query.filter_by(status="awaiting_payment").order_by(Prescription.created_at).all()
    dispensed = Prescription.query.filter_by(status="dispensed").order_by(
        Prescription.dispensed_at.desc()).limit(15).all()
    drugs = Drug.query.filter(Drug.is_active.is_(True)).all()
    low = [d for d in drugs if d.is_low]
    expiring = [d for d in drugs if d.is_expired or d.expires_soon]
    return render_template("pharmacy/dashboard.html", ready=ready, awaiting=awaiting, dispensed=dispensed,
                           low=low, expiring=expiring)


@bp.route("/dispense/<int:rx_id>", methods=["GET", "POST"])
@roles_required("pharmacist")
def dispense(rx_id):
    rx = db.get_or_404(Prescription, rx_id)
    if request.method == "POST":
        if rx.status != "ready_to_dispense":
            flash("Only paid prescriptions can be dispensed.", "danger")
            return redirect(url_for("pharmacy.dispense", rx_id=rx.id))
        short = [i for i in rx.items if i.drug is None or i.drug.quantity < i.quantity]
        if short:
            flash("Not enough stock for: " + ", ".join(i.drug_name for i in short), "danger")
            return redirect(url_for("pharmacy.dispense", rx_id=rx.id))
        for item in rx.items:
            move_stock(item.drug, -item.quantity, "dispense",
                       f"Rx #{rx.id} - {rx.patient.hospital_id} {rx.patient.full_name}")
        rx.status = "dispensed"
        rx.dispensed_at = now()
        rx.dispensed_by = current_user
        db.session.commit()
        flash(f"Prescription #{rx.id} dispensed to {rx.patient.full_name}. Stock updated.", "success")
        return redirect(url_for("pharmacy.dashboard"))
    return render_template("pharmacy/dispense.html", rx=rx)


@bp.route("/inventory")
@roles_required("pharmacist")
def inventory():
    q = (request.args.get("q") or "").strip()
    query = Drug.query
    if q:
        query = query.filter(or_(Drug.name.ilike(f"%{q}%"), Drug.batch_no.ilike(f"%{q}%")))
    drugs = query.order_by(Drug.name).all()
    stock_value = sum(d.quantity * d.unit_price for d in drugs)
    return render_template("pharmacy/inventory.html", drugs=drugs, q=q, stock_value=stock_value)


def _fill_drug(drug, form):
    drug.name = form.get("name", "").strip()
    drug.form = form.get("form") or None
    drug.strength = form.get("strength") or None
    drug.unit_price = parse_money(form.get("unit_price"))
    drug.reorder_level = parse_int(form.get("reorder_level"), 10)
    drug.batch_no = form.get("batch_no") or None
    drug.expiry_date = parse_date(form.get("expiry_date"))
    drug.is_active = bool(form.get("is_active"))


@bp.route("/drug/new", methods=["GET", "POST"])
@bp.route("/drug/<int:drug_id>/edit", methods=["GET", "POST"])
@roles_required("pharmacist")
def drug_form(drug_id=None):
    drug = db.get_or_404(Drug, drug_id) if drug_id else Drug(is_active=True, quantity=0)
    if request.method == "POST":
        if not request.form.get("name"):
            flash("Drug name is required.", "danger")
        else:
            _fill_drug(drug, request.form)
            if drug_id is None:
                db.session.add(drug)
                db.session.flush()
                opening = parse_int(request.form.get("opening_quantity"))
                if opening > 0:
                    move_stock(drug, opening, "opening", "Opening stock")
            db.session.commit()
            flash(f"{drug.label} saved.", "success")
            return redirect(url_for("pharmacy.inventory"))
    return render_template("pharmacy/drug_form.html", drug=drug, is_new=drug_id is None)


@bp.route("/drug/<int:drug_id>/stock", methods=["GET", "POST"])
@roles_required("pharmacist")
def stock(drug_id):
    drug = db.get_or_404(Drug, drug_id)
    if request.method == "POST":
        qty = parse_int(request.form.get("quantity"))
        kind = request.form.get("kind")
        if qty <= 0:
            flash("Enter a quantity greater than zero.", "danger")
        elif kind == "restock":
            if request.form.get("batch_no"):
                drug.batch_no = request.form.get("batch_no")
            if parse_date(request.form.get("expiry_date")):
                drug.expiry_date = parse_date(request.form.get("expiry_date"))
            move_stock(drug, qty, "restock", request.form.get("note") or "Restock")
            db.session.commit()
            flash(f"Added {qty} to {drug.label}.", "success")
        elif kind == "remove":
            if qty > drug.quantity:
                flash("Cannot remove more than is in stock.", "danger")
            else:
                move_stock(drug, -qty, "adjustment", request.form.get("note") or "Removed (damaged/expired)")
                db.session.commit()
                flash(f"Removed {qty} from {drug.label}.", "success")
        return redirect(url_for("pharmacy.stock", drug_id=drug.id))
    moves = DrugStockMovement.query.filter_by(drug_id=drug.id).order_by(DrugStockMovement.id.desc()).all()
    return render_template("pharmacy/stock.html", drug=drug, moves=moves)


@bp.route("/movements")
@roles_required("pharmacist")
def movements():
    moves = DrugStockMovement.query.order_by(DrugStockMovement.id.desc()).limit(300).all()
    return render_template("pharmacy/movements.html", moves=moves)
