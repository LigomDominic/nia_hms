from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import StoreItem, StoreMovement
from ..utils import parse_int, roles_required

bp = Blueprint("store", __name__, url_prefix="/store")

DEPARTMENTS = ("Wards", "Nurses Station", "Laboratory", "Pharmacy", "Theatre", "Consulting Rooms",
               "Cleaning / Janitorial", "Administration", "Cashier", "Other")


def move_item(item, change, kind, department=None, note=None):
    item.quantity += change
    db.session.add(StoreMovement(item=item, change=change, balance_after=item.quantity, kind=kind,
                                 department=department, note=note, user=current_user))


@bp.route("/")
@roles_required("store_keeper")
def dashboard():
    q = (request.args.get("q") or "").strip()
    query = StoreItem.query
    if q:
        query = query.filter(StoreItem.name.ilike(f"%{q}%") | StoreItem.category.ilike(f"%{q}%"))
    items = query.order_by(StoreItem.category, StoreItem.name).all()
    low = [i for i in StoreItem.query.all() if i.is_low]
    recent = StoreMovement.query.order_by(StoreMovement.id.desc()).limit(10).all()
    return render_template("store/dashboard.html", items=items, low=low, recent=recent, q=q)


@bp.route("/item/new", methods=["GET", "POST"])
@bp.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
@roles_required("store_keeper")
def item_form(item_id=None):
    item = db.get_or_404(StoreItem, item_id) if item_id else StoreItem(quantity=0)
    if request.method == "POST":
        if not request.form.get("name"):
            flash("Item name is required.", "danger")
        else:
            item.name = request.form["name"].strip()
            item.category = request.form.get("category") or None
            item.unit = request.form.get("unit") or "pcs"
            item.reorder_level = parse_int(request.form.get("reorder_level"), 5)
            item.location = request.form.get("location") or None
            if item_id is None:
                db.session.add(item)
                db.session.flush()
                opening = parse_int(request.form.get("opening_quantity"))
                if opening > 0:
                    move_item(item, opening, "opening", note="Opening stock")
            db.session.commit()
            flash(f"{item.name} saved.", "success")
            return redirect(url_for("store.dashboard"))
    return render_template("store/item_form.html", item=item, is_new=item_id is None)


@bp.route("/item/<int:item_id>", methods=["GET", "POST"])
@roles_required("store_keeper")
def item(item_id):
    it = db.get_or_404(StoreItem, item_id)
    if request.method == "POST":
        qty = parse_int(request.form.get("quantity"))
        kind = request.form.get("kind")
        note = request.form.get("note") or None
        if qty <= 0:
            flash("Enter a quantity greater than zero.", "danger")
        elif kind == "received":
            move_item(it, qty, "received", note=note or "Received into store")
            db.session.commit()
            flash(f"Received {qty} {it.unit} of {it.name}.", "success")
        elif kind == "issued":
            if qty > it.quantity:
                flash("Cannot issue more than is in stock.", "danger")
            else:
                move_item(it, -qty, "issued", department=request.form.get("department"), note=note)
                db.session.commit()
                flash(f"Issued {qty} {it.unit} of {it.name} to {request.form.get('department')}.", "success")
        return redirect(url_for("store.item", item_id=it.id))
    moves = StoreMovement.query.filter_by(item_id=it.id).order_by(StoreMovement.id.desc()).all()
    return render_template("store/item.html", it=it, moves=moves, departments=DEPARTMENTS)


@bp.route("/movements")
@roles_required("store_keeper")
def movements():
    moves = StoreMovement.query.order_by(StoreMovement.id.desc()).limit(300).all()
    return render_template("store/movements.html", moves=moves)
