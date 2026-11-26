import json
from itertools import zip_longest

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..mailer import send_lab_result
from ..models import CLINICAL_ROLES, MICRO_DRUG_PANELS, LabRequest, Patient, now
from ..patient_ids import new_hospital_id
from ..utils import roles_required

bp = Blueprint("lab", __name__, url_prefix="/lab")

FLAGS = ("", "Normal", "High", "Low", "Positive", "Negative", "Reactive", "Non-reactive")

# Standard antibiotic panel rows for the microbiology (MCS) entry form: (gram+ve drug, gram-ve drug)
MICRO_PANEL_ROWS = list(zip_longest(MICRO_DRUG_PANELS["pos"], MICRO_DRUG_PANELS["neg"]))


def _save_micro(item):
    """Store one microbiology (MCS) item's sheet data as JSON and summarise it into item.result."""
    f = request.form
    data = {k: (f.get(f"micro_{k}_{item.id}") or "").strip() for k in
            ("specimen", "macroscopy", "microscopy", "culture", "gram_stain")}
    drugs = []
    for name, grp, res in zip(f.getlist(f"mdr_{item.id}"), f.getlist(f"mgr_{item.id}"),
                              f.getlist(f"mre_{item.id}")):
        name = (name or "").strip()
        if name and grp in ("pos", "neg") and res in ("S", "R"):
            drugs.append({"name": name[:120], "group": grp, "res": res})
    data["drugs"] = drugs
    if drugs or any(data[k] for k in ("macroscopy", "microscopy", "culture", "gram_stain")):
        item.micro_data = json.dumps(data)
        item.result = (data["culture"] or data["microscopy"] or data["gram_stain"]
                       or data["macroscopy"] or "See MCS report")[:250]
    else:
        item.micro_data = None
        item.result = None
    item.flag = None


def _save_template(item, fields):
    """Store a templated test's per-analyte values as JSON and summarise into item.result."""
    f = request.form
    values = {}
    for idx, fld in enumerate(fields):
        v = (f.get(f"res_{item.id}_{idx}") or "").strip()[:120]
        flag = f.get(f"rfl_{item.id}_{idx}") or ""
        if v or flag:
            values[fld["n"]] = {"v": v, "f": flag if flag in FLAGS else ""}
    if values:
        item.result_data = json.dumps(values)
        summary = "; ".join(f"{k}: {d['v']}" for k, d in values.items() if d["v"])
        item.result = (summary or "See full report")[:250]
    else:
        item.result_data = None
        item.result = None
    item.flag = None


def _deliver(req):
    if req.delivery_method == "email":
        ok, msg = send_lab_result(req)
        req.delivery_status = "emailed" if ok else "email_failed"
        req.delivery_note = msg
        return ok, msg
    req.delivery_status = "awaiting_collection"
    req.delivery_note = "Patient to collect a printed copy."
    return True, "Result ready for manual collection."


@bp.route("/")
@roles_required("lab")
def dashboard():
    queue = LabRequest.query.filter(LabRequest.status.in_(("sent_to_lab", "in_progress"))).order_by(
        LabRequest.posted_to_lab_at).all()
    awaiting_payment = LabRequest.query.filter_by(status="awaiting_payment").count()
    to_collect = LabRequest.query.filter(LabRequest.status == "completed",
                                         LabRequest.delivery_status.in_(("awaiting_collection", "email_failed"))
                                         ).order_by(LabRequest.completed_at.desc()).all()
    done = LabRequest.query.filter_by(status="completed").order_by(LabRequest.completed_at.desc()).limit(20).all()
    return render_template("lab/dashboard.html", queue=queue, awaiting_payment=awaiting_payment,
                           to_collect=to_collect, done=done)


@bp.route("/walk-in", methods=["GET", "POST"])
@roles_required("lab")
def walk_in():
    """Walk-in customers: look up an existing patient or quick-register a one-off one."""
    if request.method == "POST":
        hid = (request.form.get("hospital_id") or "").strip().upper()
        if hid:
            patient = Patient.query.filter_by(hospital_id=hid).first()
            if patient is None:
                flash(f"No patient with hospital ID '{hid}'. Enter their name below to register them quickly.",
                      "warning")
                return render_template("lab/walk_in.html", q=hid)
            return redirect(url_for("cashier.walk_in_lab", hospital_id=patient.hospital_id))
        first = (request.form.get("first_name") or "").strip()
        last = (request.form.get("last_name") or "").strip()
        if not first or not last:
            flash("Enter the hospital ID, or the customer's first and last name.", "danger")
            return render_template("lab/walk_in.html", q="")
        patient = Patient(first_name=first, last_name=last,
                          other_names=(request.form.get("other_names") or "").strip() or None,
                          gender=request.form.get("gender") or None,
                          phone=(request.form.get("phone") or "").strip() or None,
                          registered_by=current_user)
        db.session.add(patient)
        db.session.flush()
        patient.hospital_id = new_hospital_id(patient)
        db.session.commit()
        flash(f"Registered {patient.full_name} as walk-in customer {patient.hospital_id}.", "info")
        return redirect(url_for("cashier.walk_in_lab", hospital_id=patient.hospital_id))
    return render_template("lab/walk_in.html", q=request.args.get("q", ""))


@bp.route("/request/<int:req_id>", methods=["GET", "POST"])
@roles_required("lab")
def process(req_id):
    req = db.get_or_404(LabRequest, req_id)
    if req.status == "awaiting_payment":
        flash("This request has not been paid for at the Cashier yet.", "warning")
        return redirect(url_for("lab.dashboard"))
    if request.method == "POST":
        for item in req.items:
            if item.is_micro:
                _save_micro(item)
            elif item.result_template:
                _save_template(item, item.result_template["fields"])
            else:
                item.result = (request.form.get(f"result_{item.id}") or "").strip() or None
                flag = request.form.get(f"flag_{item.id}") or ""
                item.flag = flag if flag in FLAGS and flag else None
        req.lab_comment = request.form.get("lab_comment")
        if request.form.get("action") == "complete":
            if any(not i.result for i in req.items):
                db.session.commit()
                flash("Enter a result for every test before posting.", "danger")
                return redirect(url_for("lab.process", req_id=req.id))
            req.status = "completed"
            req.completed_at = now()
            req.completed_by = current_user
            req.delivery_method = "email" if request.form.get("delivery") == "email" else "manual"
            ok, msg = _deliver(req)
            db.session.commit()
            flash(f"Result posted to {req.doctor.display_name if req.doctor else 'the doctor'}. {msg}",
                  "success" if ok else "warning")
            return redirect(url_for("lab.dashboard"))
        req.status = "in_progress"
        db.session.commit()
        flash("Results saved (not yet posted).", "info")
        return redirect(url_for("lab.process", req_id=req.id))
    return render_template("lab/process.html", req=req, flags=FLAGS, micro_rows=MICRO_PANEL_ROWS)


@bp.route("/request/<int:req_id>/collected", methods=["POST"])
@roles_required("lab", "cashier")
def collected(req_id):
    req = db.get_or_404(LabRequest, req_id)
    req.delivery_status = "collected"
    req.collected_at = now()
    req.delivery_note = f"Collected - handed over by {current_user.display_name}"
    db.session.commit()
    flash("Marked as collected by patient.", "success")
    return redirect(request.referrer or url_for("lab.dashboard"))


@bp.route("/request/<int:req_id>/email", methods=["POST"])
@roles_required("lab")
def email(req_id):
    req = db.get_or_404(LabRequest, req_id)
    req.delivery_method = "email"
    ok, msg = _deliver(req)
    db.session.commit()
    flash(msg, "success" if ok else "warning")
    return redirect(request.referrer or url_for("lab.dashboard"))


@bp.route("/request/<int:req_id>/print")
@roles_required(*CLINICAL_ROLES)
def print_result(req_id):
    return render_template("lab/result.html", req=db.get_or_404(LabRequest, req_id), printable=True)
