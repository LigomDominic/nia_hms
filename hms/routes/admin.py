import os
import shutil
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from sqlalchemy import func

from .. import app_settings as aps
from ..extensions import db
from ..patient_ids import PATIENT_ID_FORMATS
from ..permissions import MODULES
from ..models import (ROLES, Bill, CleaningTask, Drug, LabRequest, LabRequestItem, LabTest, Patient, Payment, Prescription,
                      Setting, StoreItem, User, UserAccess, Visit)
from ..utils import parse_date, parse_money, roles_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@roles_required()
def dashboard():
    start = datetime.combine(date.today(), time.min)
    stats = {
        "patients": Patient.query.count(),
        "new_today": Patient.query.filter(Patient.created_at >= start).count(),
        "revenue_today": db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.created_at >= start, Payment.method != "wallet").scalar(),
        "wallet_held": db.session.query(func.coalesce(func.sum(Patient.wallet_balance), 0)).scalar(),
        "outstanding": sum(b.balance for b in Bill.query.filter(Bill.status.in_(("unpaid", "part_paid")))),
        "waiting": Visit.query.filter(Visit.status != "completed").count(),
        "lab_queue": LabRequest.query.filter(LabRequest.status.in_(("sent_to_lab", "in_progress"))).count(),
        "rx_queue": Prescription.query.filter_by(status="ready_to_dispense").count(),
        "low_drugs": sum(1 for d in Drug.query.all() if d.is_low),
        "low_store": sum(1 for i in StoreItem.query.all() if i.is_low),
        "staff": User.query.filter(User.is_active_user.is_(True)).count(),
    }
    recent = Patient.query.order_by(Patient.created_at.desc()).limit(8).all()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


@bp.route("/users")
@roles_required()
def users():
    rows = User.query.order_by(User.role, User.full_name).all()
    return render_template("admin/users.html", users=rows)


@bp.route("/users/new", methods=["GET", "POST"])
@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required()
def user_form(user_id=None):
    user = db.get_or_404(User, user_id) if user_id else User(is_active_user=True)
    if request.method == "POST":
        f = request.form
        username = (f.get("username") or "").strip().lower()
        password = f.get("password") or ""
        clash = User.query.filter(User.username == username, User.id != (user.id or 0)).first()
        if not username or not f.get("full_name") or f.get("role") not in ROLES:
            flash("Username, full name and role are required.", "danger")
        elif clash:
            flash("That username is already taken.", "danger")
        elif password and len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif user.id == current_user.id and (f.get("role") != "admin" or not f.get("is_active_user")):
            flash("You cannot remove your own admin access.", "danger")
        else:
            user.username = username
            user.full_name = f["full_name"].strip()
            user.email = f.get("email") or None
            user.phone = f.get("phone") or None
            user.role = f["role"]
            user.specialty = f.get("specialty") or None
            user.is_active_user = bool(f.get("is_active_user"))
            if password:
                user.set_password(password)
            if user_id is None:
                db.session.add(user)
            db.session.flush()
            _save_access_overrides(user)
            db.session.commit()
            flash(f"{user.display_name} saved.", "success")
            return redirect(url_for("admin.users"))
    access = {row.module: row.level for row in UserAccess.query.filter_by(user_id=user.id)} if user.id else {}
    return render_template("admin/user_form.html", user=user, is_new=user_id is None,
                           modules=MODULES, access=access)


def _save_access_overrides(user):
    """Save the per-module access grid. Empty/'inherit' selections remove the override."""
    for module in MODULES:
        level = request.form.get(f"access_{module}")
        row = db.session.get(UserAccess, (user.id, module))
        if level in UserAccess.LEVELS:
            if row is None:
                row = UserAccess(user_id=user.id, module=module)
                db.session.add(row)
            row.level = level
        elif row is not None:
            db.session.delete(row)


@bp.route("/settings", methods=["GET", "POST"])
@roles_required()
def settings():
    if request.method == "POST":
        errors = _save_settings(request.form)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "danger")
        else:
            db.session.commit()
            aps.clear_cache()
            flash("Settings saved.", "success")
        return redirect(url_for("admin.settings", tab=request.form.get("tab") or "general"))
    return render_template("admin/settings.html", card_fee=Setting.get_money("card_fee"),
                           consultation_fee=Setting.get_money("consultation_fee"),
                           anc_fee=Setting.get_money("anc_fee"),
                           file_retrieval_fee=Setting.get_money("file_retrieval_fee"), aps=aps,
                           id_formats=PATIENT_ID_FORMATS,
                           tab=request.args.get("tab", "general"))


_CHOICES = {
    "theme": aps.THEMES, "report_paper": aps.REPORT_PAPER_SIZES, "receipt_paper": aps.PAPER_SIZES,
    "report_orientation": aps.ORIENTATIONS, "date_format": aps.DATE_FORMATS, "time_format": aps.TIME_FORMATS,
    "currency_position": aps.CURRENCY_POSITIONS, "patient_id_format": PATIENT_ID_FORMATS, "currency_decimals": aps.DECIMALS, "voice_language": aps.VOICE_LANGUAGES,
}
_TEXT = {"hospital_name": 120, "hospital_tagline": 150, "hospital_address": 255, "hospital_phone": 60,
         "hospital_email": 120, "currency_symbol": 5, "currency_code": 5, "document_footer": 255}
_FLAGS = ["auto_print_receipt", "print_show_address", "receipt_show_wallet", "voice_enabled", "voice_punctuation"]
_INTS = {"print_margin_mm": (0, 40), "doc_number_digits": (1, 10)}


def _save_settings(form):
    errors = []
    if "card_fee" in form:
        Setting.set("card_fee", parse_money(form.get("card_fee")))
        Setting.set("consultation_fee", parse_money(form.get("consultation_fee")))
        Setting.set("anc_fee", parse_money(form.get("anc_fee")))
        Setting.set("file_retrieval_fee", parse_money(form.get("file_retrieval_fee")))
    for key, options in _CHOICES.items():
        if key in form:
            if form[key] not in options:
                errors.append(f"Invalid choice for {key.replace('_', ' ')}.")
            else:
                Setting.set(key, form[key])
    for key, limit in _TEXT.items():
        if key in form:
            value = form[key].strip()[:limit]
            if key in ("hospital_name", "currency_symbol") and not value:
                errors.append(f"{key.replace('_', ' ').capitalize()} cannot be empty.")
            else:
                Setting.set(key, value)
    for key, (lo, hi) in _INTS.items():
        if key in form:
            try:
                value = int(form[key])
                if not lo <= value <= hi:
                    raise ValueError
                Setting.set(key, value)
            except ValueError:
                errors.append(f"{key.replace('_', ' ').capitalize()} must be a number from {lo} to {hi}.")
    if "patient_id_prefix" in form:
        prefix = form["patient_id_prefix"].strip().upper()
        if not prefix.isalnum() or len(prefix) > 8:
            errors.append("Patient ID prefix must be 1-8 letters/numbers (e.g. NIA).")
        else:
            Setting.set("patient_id_prefix", prefix)
    for kind in aps.DOCUMENT_TYPES:
        key = f"doc_prefix_{kind}"
        if key in form:
            Setting.set(key, form[key].strip()[:12])
    section_flags = form.getlist("flags_section")
    for key in _FLAGS:
        if key in section_flags:
            Setting.set(key, "1" if form.get(key) else "0")
    return errors


@bp.route("/lab-tests", methods=["GET", "POST"])
@roles_required()
def lab_tests():
    from ..lab_templates import RESULT_TEMPLATES, TEST_LIBRARY

    if request.method == "POST":
        test_id = request.form.get("test_id")
        test = db.get_or_404(LabTest, int(test_id)) if test_id else LabTest()
        name = (request.form.get("name") or "").strip()
        clash = LabTest.query.filter(func.lower(LabTest.name) == name.lower(), LabTest.id != (test.id or 0)).first()
        if not name:
            flash("Test name is required.", "danger")
        elif clash:
            flash(f"A test called {clash.name} already exists.", "danger")
        else:
            test.name = name
            test.category = (request.form.get("category") or "").strip() or None
            test.sample_type = (request.form.get("sample_type") or "").strip() or None
            test.unit = (request.form.get("unit") or "").strip() or None
            test.reference_range = (request.form.get("reference_range") or "").strip() or None
            test.price = parse_money(request.form.get("price"))
            tpl_key = (request.form.get("template") or "").strip()
            test.template = tpl_key if tpl_key in RESULT_TEMPLATES else None
            test.is_active = bool(request.form.get("is_active"))
            if not test_id:
                db.session.add(test)
            db.session.commit()
            flash(f"{test.name} saved.", "success")
            return redirect(url_for("admin.lab_tests"))
        return redirect(url_for("admin.lab_tests", edit=test_id) if test_id else url_for("admin.lab_tests"))

    from ..seed import LAB_CATEGORIES, SAMPLE_LAB_TEST_NAMES

    q = (request.args.get("q") or "").strip()
    category = request.args.get("category") or ""
    query = LabTest.query
    if q:
        query = query.filter(LabTest.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(LabTest.category.is_(None) if category == "_none" else LabTest.category == category)
    tests = query.order_by(LabTest.category, LabTest.name).all()
    used = {c for (c,) in db.session.query(LabTest.category).filter(LabTest.category.isnot(None)).distinct()}
    edit = db.session.get(LabTest, int(request.args["edit"])) if request.args.get("edit") else None
    samples_left = LabTest.query.filter(LabTest.name.in_(SAMPLE_LAB_TEST_NAMES), LabTest.is_active.is_(True)).count()
    library_names = {name for name, _c, _s, _p, _t in TEST_LIBRARY}
    library_missing = len(library_names - {name for (name,) in db.session.query(LabTest.name).all()})
    return render_template("admin/lab_tests.html", tests=tests, edit=edit, q=q, category=category,
                           categories=sorted(used | set(LAB_CATEGORIES)), used_categories=sorted(used),
                           total=LabTest.query.count(), samples_left=samples_left,
                           result_templates=RESULT_TEMPLATES, library_missing=library_missing)


def _remove_lab_test(test):
    """Delete a test, or deactivate it if past requests refer to it. Returns True if deleted."""
    if LabRequestItem.query.filter_by(test_id=test.id).first():
        test.is_active = False
        return False
    db.session.delete(test)
    return True


@bp.route("/lab-tests/<int:test_id>/delete", methods=["POST"])
@roles_required()
def lab_test_delete(test_id):
    test = db.get_or_404(LabTest, test_id)
    name = test.name
    if _remove_lab_test(test):
        flash(f"{name} deleted.", "success")
    else:
        flash(f"{name} has been requested before, so it was deactivated instead of deleted (old results stay intact).", "warning")
    db.session.commit()
    return redirect(url_for("admin.lab_tests"))


@bp.route("/lab-tests/remove-samples", methods=["POST"])
@roles_required()
def lab_tests_remove_samples():
    from ..seed import SAMPLE_LAB_TEST_NAMES

    deleted = deactivated = 0
    for test in LabTest.query.filter(LabTest.name.in_(SAMPLE_LAB_TEST_NAMES)).all():
        if _remove_lab_test(test):
            deleted += 1
        elif test.is_active is False:
            deactivated += 1
    db.session.commit()
    flash(f"Sample tests removed: {deleted} deleted, {deactivated} deactivated (already used on patients).", "success")
    return redirect(url_for("admin.lab_tests"))


@bp.route("/lab-tests/load-library", methods=["POST"])
@roles_required()
def lab_tests_load_library():
    from ..lab_templates import install_library

    added, updated, skipped = install_library()
    flash(f"Standard test library loaded: {added} new test(s) added, {updated} existing test(s) linked to a result "
          f"template, {len(skipped)} already in your catalog (untouched).", "success")
    return redirect(url_for("admin.lab_tests"))


@bp.route("/reset-demo", methods=["POST"])
@roles_required()
def reset_demo():
    if "demo" not in db.engines:
        flash("No training database is configured on this installation.", "warning")
        return redirect(url_for("main.environment"))
    from .. import _init_demo_db

    _init_demo_db(current_app, force_copy=True)
    flash("Training database reset to a fresh copy of the live data.", "success")
    return redirect(url_for("main.environment"))


@bp.route("/lab-tests/bulk", methods=["POST"])
@roles_required()
def lab_tests_bulk():
    from ..lab_templates import RESULT_TEMPLATES

    added, skipped, errors = 0, [], []
    for n, line in enumerate((request.form.get("lines") or "").splitlines(), 1):
        if not line.strip():
            continue
        parts = [x.strip() for x in (line.split("\t") if "\t" in line else line.split("|"))]
        parts += [""] * (7 - len(parts))
        name, category, sample, unit, ref, price, tpl = parts[:7]
        if not name or name.lower() in ("name", "test name"):
            continue
        if LabTest.query.filter(func.lower(LabTest.name) == name.lower()).first():
            skipped.append(name)
            continue
        try:
            amount = float(price.replace(",", "")) if price else 0.0
        except ValueError:
            errors.append(f"line {n} ({name}): price '{price}' is not a number")
            continue
        if tpl and tpl not in RESULT_TEMPLATES:
            errors.append(f"line {n} ({name}): unknown template '{tpl}'")
            continue
        db.session.add(LabTest(name=name, category=category or None, sample_type=sample or None, unit=unit or None,
                               reference_range=ref or None, price=amount, template=tpl or None, is_active=True))
        db.session.flush()
        added += 1
    db.session.commit()
    msg = f"{added} test(s) added."
    if skipped:
        msg += f" Skipped {len(skipped)} already in the list: {', '.join(skipped[:5])}{'…' if len(skipped) > 5 else ''}."
    flash(msg, "success" if added else "info")
    for e in errors:
        flash(f"Not added — {e}.", "danger")
    return redirect(url_for("admin.lab_tests"))


@bp.route("/reports")
@roles_required()
def reports():
    start = parse_date(request.args.get("start")) or date.today() - timedelta(days=30)
    end = parse_date(request.args.get("end")) or date.today()
    s, e = datetime.combine(start, time.min), datetime.combine(end, time.max)
    payments = Payment.query.filter(Payment.created_at.between(s, e)).all()
    by_category, by_method = {}, {}
    for p in payments:
        by_category[p.bill.category_label] = by_category.get(p.bill.category_label, 0) + p.amount
        by_method[p.method_label] = by_method.get(p.method_label, 0) + p.amount
    deposits = sum(t.amount for p in Patient.query.all() for t in p.wallet_transactions
                   if t.kind == "deposit" and s <= t.created_at <= e)
    ctx = dict(start=start, end=end, by_category=by_category, by_method=by_method,
               total=sum(by_category.values()), deposits=deposits,
               visits=Visit.query.filter(Visit.created_at.between(s, e)).count(),
               new_patients=Patient.query.filter(Patient.created_at.between(s, e)).count(),
               payments=payments)
    if request.args.get("print"):
        return render_template("admin/report_print.html", **ctx)
    return render_template("admin/reports.html", **ctx)


@bp.route("/cleaning", methods=["GET", "POST"])
@roles_required()
def cleaning():
    cleaners = User.query.filter_by(role="cleaner", is_active_user=True).order_by(User.full_name).all()
    if request.method == "POST":
        area = (request.form.get("area") or "").strip()
        cleaner = db.session.get(User, int(request.form.get("assigned_to_id") or 0))
        if not area or cleaner is None:
            flash("Area and cleaner are required.", "danger")
        else:
            db.session.add(CleaningTask(area=area, description=request.form.get("description") or None,
                                        assigned_to=cleaner, created_by=current_user,
                                        due_date=parse_date(request.form.get("due_date")) or date.today()))
            db.session.commit()
            flash(f"Task assigned to {cleaner.full_name}.", "success")
        return redirect(url_for("admin.cleaning"))
    tasks = CleaningTask.query.order_by(CleaningTask.status.desc(), CleaningTask.due_date.desc()).limit(100).all()
    return render_template("admin/cleaning.html", tasks=tasks, cleaners=cleaners, today=date.today())

from ..mailer import send_mail


@bp.route("/email", methods=["GET", "POST"])
@roles_required()
def broadcast_email():
    if request.method == "POST":
        target = request.form.get("target")
        subject = (request.form.get("subject") or "").strip()
        body = (request.form.get("body") or "").strip()
        if not subject or not body:
            flash("Subject and message are required.", "danger")
            return redirect(url_for("admin.broadcast_email"))
        if target == "address":
            emails = [(request.form.get("email") or "").strip()]
        elif target == "patient":
            patient = Patient.query.filter_by(
                hospital_id=(request.form.get("hospital_id") or "").strip().upper()).first()
            if patient is None or not patient.email:
                flash("No patient with that hospital ID, or the patient has no email on file.", "danger")
                return redirect(url_for("admin.broadcast_email"))
            emails = [patient.email]
        else:
            emails = [p.email for p in Patient.query.all() if p.email]
            if not emails:
                flash("No patients have email addresses on file.", "warning")
                return redirect(url_for("admin.broadcast_email"))
        html = render_template("email/broadcast.html", body=body)
        text = render_template("email/broadcast.txt", body=body)
        sent, failed = 0, 0
        for address in emails:
            ok, _err = send_mail(f"{Setting.get('hospital_name')} - {subject}", html, text, address)
            sent += ok
            failed += not ok
        flash(f"Sent to {sent} address(es)" + (f"; {failed} failed." if failed else "."),
              "success" if sent else "warning")
        return redirect(url_for("admin.broadcast_email"))
    count = Patient.query.filter(Patient.email.isnot(None), Patient.email != "").count()
    return render_template("admin/email.html", patient_emails=count)


@bp.route("/reports/email", methods=["POST"])
@roles_required()
def reports_email():
    to = (request.form.get("to") or "").strip()
    start = parse_date(request.form.get("start")) or date.today() - timedelta(days=30)
    end = parse_date(request.form.get("end")) or date.today()
    s, e = datetime.combine(start, time.min), datetime.combine(end, time.max)
    payments = Payment.query.filter(Payment.created_at.between(s, e)).all()
    by_category, by_method = {}, {}
    for p in payments:
        by_category[p.bill.category_label] = by_category.get(p.bill.category_label, 0) + p.amount
        by_method[p.method_label] = by_method.get(p.method_label, 0) + p.amount
    ctx = dict(start=start, end=end, by_category=by_category, by_method=by_method,
               total=sum(by_category.values()),
               count=len(payments))
    ok, err = send_mail(f"{Setting.get('hospital_name')} - Financial report "
                        f"{start:%d %b %Y} - {end:%d %b %Y}",
                        render_template("email/report.html", **ctx),
                        render_template("email/report.txt", **ctx), to)
    flash(f"Report emailed to {to}." if ok else err, "success" if ok else "warning")
    return redirect(url_for("admin.reports", start=start.isoformat(), end=end.isoformat(), print=1))


@bp.route("/database")
@roles_required()
def database():
    db_path = Path(current_app.instance_path) / "hms.db"
    backups = sorted(Path(current_app.instance_path).glob("hms-backup-*.db"), reverse=True)
    stat = db_path.stat() if db_path.exists() else None
    return render_template("admin/database.html", db_name=db_path.name,
                           db_size=stat.st_size if stat else 0,
                           db_mtime=datetime.fromtimestamp(stat.st_mtime) if stat else None,
                           backups=[(b.name, b.stat().st_size) for b in backups[:10]])


@bp.route("/database/download")
@roles_required()
def database_download():
    fd, snap_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    snap = Path(snap_path)
    with db.engine.connect() as conn:
        conn.exec_driver_sql("VACUUM INTO '%s'" % str(snap).replace("'", "''"))
    return send_file(snap, as_attachment=True,
                     download_name=f"nia-hms-backup-{datetime.now():%Y%m%d-%H%M%S}.db")


@bp.route("/database/upload", methods=["POST"])
@roles_required()
def database_upload():
    f = request.files.get("db_file")
    data = f.read() if f else b""
    if not data.startswith(b"SQLite format 3\x00"):
        flash("That file is not a valid HMS database (SQLite) file.", "danger")
        return redirect(url_for("admin.database"))
    db_path = Path(current_app.instance_path) / "hms.db"
    db.session.remove()
    if db_path.exists():
        shutil.copy2(db_path, db_path.with_name(f"hms-backup-{datetime.now():%Y%m%d-%H%M%S}.db"))
    try:
        db_path.write_bytes(data)
    except OSError as exc:
        flash(f"Upload failed: {exc}", "danger")
        return redirect(url_for("admin.database"))
    flash("Database replaced - the old copy was kept as a backup. Restart the app in cPanel "
          "(Setup Python App > Restart) so every worker picks it up.", "warning")
    return redirect(url_for("admin.database"))
