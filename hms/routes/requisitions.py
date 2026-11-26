import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import func

from ..extensions import db
from ..models import Drug, RequisitionItem, STATIONS, StationRequisition, now
from ..permissions import can_access
from ..utils import parse_int, roles_required
from .pharmacy import move_stock

bp = Blueprint("requisitions", __name__, url_prefix="/requisitions")


def _token():
    if "requisition_token" not in session:
        session["requisition_token"] = secrets.token_hex(32)
    return session["requisition_token"]


def _check_token():
    token = session.get("requisition_token", "")
    if not token or not secrets.compare_digest(request.form.get("csrf_token", ""), token):
        abort(400)


@bp.route("/")
@roles_required("nurse", "pharmacist", "doctor", "visiting_doctor")
def index():
    station = request.args.get("station", "")
    query = StationRequisition.query
    if station in STATIONS:
        query = query.filter_by(station=station)
    pending = query.filter_by(status="pending").order_by(StationRequisition.created_at).all()
    done = query.filter(StationRequisition.status != "pending").order_by(
        StationRequisition.actioned_at.desc()).limit(60).all()
    return render_template("requisitions/index.html", pending=pending, done=done,
                           stations=STATIONS, station=station)


@bp.route("/new", methods=["GET", "POST"])
@roles_required("nurse")
def new():
    _token()
    drugs = Drug.query.filter(Drug.is_active.is_(True), Drug.quantity > 0).order_by(Drug.name).all()
    if request.method == "POST":
        if not can_access(current_user, "requisitions", "manage"):
            abort(403)
        _check_token()
        station = request.form.get("station", "")
        note = (request.form.get("note") or "").strip()[:250]
        items = []
        for drug_id, name, qty, inote in zip(request.form.getlist("drug_id"),
                                            request.form.getlist("item_name"),
                                            request.form.getlist("qty"),
                                            request.form.getlist("item_note")):
            drug = db.session.get(Drug, parse_int(drug_id)) if drug_id else None
            label = (drug.label if drug else (name or "").strip())[:160]
            qty = parse_int(qty)
            if label and qty > 0:
                items.append(RequisitionItem(drug=drug, item_name=label, quantity_requested=qty,
                                             note=(inote or "").strip()[:160]))
        if station not in STATIONS:
            flash("Choose the station making the request.", "danger")
        elif not items:
            flash("Enter at least one item with a quantity.", "danger")
        elif len(items) > 30:
            flash("Too many items - split the request.", "danger")
        else:
            req = StationRequisition(station=station, requested_by=current_user, note=note or None,
                                     items=items)
            db.session.add(req)
            db.session.commit()
            flash(f"Request #{req.id} sent to Pharmacy ({req.total_requested} item(s)).", "success")
            return redirect(url_for("requisitions.index", station=station))
    return render_template("requisitions/new.html", stations=STATIONS, drugs=drugs,
                           csrf_token=_token())


@bp.route("/<int:req_id>")
@roles_required("nurse", "pharmacist", "doctor", "visiting_doctor")
def detail(req_id):
    return render_template("requisitions/detail.html", req=db.get_or_404(StationRequisition, req_id),
                           csrf_token=_token())


@bp.route("/<int:req_id>/issue", methods=["POST"])
@roles_required("pharmacist")
def issue(req_id):
    _check_token()
    req = db.get_or_404(StationRequisition, req_id)
    if req.status != "pending":
        flash("This request has already been processed.", "warning")
        return redirect(url_for("requisitions.detail", req_id=req.id))
    issued = {}
    for item in req.items:
        qty = parse_int(request.form.get(f"issue_{item.id}"))
        if qty < 0 or qty > item.quantity_requested:
            flash(f"{item.item_name}: issue quantity must be 0-{item.quantity_requested}.", "danger")
            return redirect(url_for("requisitions.detail", req_id=req.id))
        issued[item.id] = qty
    shortages = [i.item_name for i in req.items
                 if i.drug is not None and issued[i.id] > i.drug.quantity]
    if shortages:
        flash("Not enough stock for: " + ", ".join(shortages), "danger")
        return redirect(url_for("requisitions.detail", req_id=req.id))
    if not any(issued.values()):
        flash("Enter at least one quantity to issue, or reject the request.", "danger")
        return redirect(url_for("requisitions.detail", req_id=req.id))
    for item in req.items:
        qty = issued[item.id]
        item.quantity_issued = qty
        if qty and item.drug is not None:
            move_stock(item.drug, -qty, "station_issue", f"{req.station} - request #{req.id}")
    req.status = "issued"
    req.actioned_by = current_user
    req.actioned_at = now()
    req.action_note = (request.form.get("action_note") or "").strip()[:250] or None
    db.session.commit()
    flash(f"Request #{req.id} issued to {req.station}. Stock updated.", "success")
    return redirect(url_for("requisitions.index"))


@bp.route("/<int:req_id>/reject", methods=["POST"])
@roles_required("pharmacist")
def reject(req_id):
    _check_token()
    req = db.get_or_404(StationRequisition, req_id)
    if req.status != "pending":
        flash("This request has already been processed.", "warning")
        return redirect(url_for("requisitions.detail", req_id=req.id))
    req.status = "rejected"
    req.actioned_by = current_user
    req.actioned_at = now()
    req.action_note = (request.form.get("action_note") or "").strip()[:250] or None
    db.session.commit()
    flash(f"Request #{req.id} rejected.", "info")
    return redirect(url_for("requisitions.index"))


@bp.route("/tracking")
@roles_required("pharmacist")
def tracking():
    """Quantities issued per item per station - the pharmacy's issue ledger."""
    rows = (db.session.query(RequisitionItem.item_name, StationRequisition.station,
                             func.sum(RequisitionItem.quantity_issued))
            .join(StationRequisition)
            .filter(StationRequisition.status == "issued")
            .group_by(RequisitionItem.item_name, StationRequisition.station)
            .order_by(RequisitionItem.item_name).all())
    by_item = {}
    station_totals = {s: 0 for s in STATIONS}
    for name, station, qty in rows:
        by_item.setdefault(name, {s: 0 for s in STATIONS})
        by_item[name][station] += qty or 0
        station_totals[station] += qty or 0
    return render_template("requisitions/tracking.html", by_item=by_item, stations=STATIONS,
                           station_totals=station_totals, grand_total=sum(station_totals.values()))
