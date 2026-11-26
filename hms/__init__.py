import os
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from flask_login import current_user

from config import Config

from .extensions import db, login_manager


def _demo_uri(uri):
    """URI for the training copy of the database, or None if not applicable."""
    if not uri:
        return None
    if ":memory:" in uri:
        return "sqlite:///:memory:"
    if uri.startswith("sqlite:///"):
        path, dot, ext = uri.rpartition(".")
        if dot:
            return f"{path}_demo.{ext}"
    return None


def _sqlite_path(uri):
    if uri and uri.startswith("sqlite:///") and ":memory:" not in uri:
        return uri[len("sqlite:///"):]
    return None


def create_app(config_object=Config, test_config=None):
    app = Flask(__name__, instance_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance"))
    app.config.from_object(config_object)
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    demo_uri = _demo_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
    if demo_uri:
        binds = dict(app.config.get("SQLALCHEMY_BINDS") or {})
        binds.setdefault("demo", demo_uri)
        app.config["SQLALCHEMY_BINDS"] = binds

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401
    from .routes import register_blueprints

    register_blueprints(app)

    from . import app_settings as aps

    @app.template_filter("money")
    def money_filter(value):
        return aps.format_money(value)

    @app.template_filter("dt")
    def dt_filter(value, fmt=None):
        if not value:
            return "-"
        return value.strftime(fmt or f"{aps.setting('date_format')}, {aps.setting('time_format')}")

    @app.template_filter("d")
    def d_filter(value):
        return value.strftime(aps.setting("date_format")) if value else "-"

    @app.template_filter("qr")
    def qr_filter(text, scale=4):
        """QR code as a PNG data URI, e.g. {{ hospital_id|qr }}."""
        import base64
        import io

        import segno

        buf = io.BytesIO()
        segno.make(str(text), error="m").save(buf, kind="png", scale=scale, border=2)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    @app.context_processor
    def inject_globals():
        from .models import PAYMENT_METHODS, ROLES
        from .permissions import can_module, explicit_level

        s = aps.get_settings()
        return {
            "S": s,
            "HOSPITAL_NAME": s["hospital_name"],
            "THEME": aps.theme_vars(),
            "page_css": aps.page_css,
            "docno": aps.doc_number,
            "now_dt": datetime.now(),
            "ROLES": ROLES,
            "PAYMENT_METHODS": PAYMENT_METHODS,
            "can_module": can_module,
            "module_override": lambda module: explicit_level(current_user, module),
            "can_lookup": can_module("patients"),
        }

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    _ENV_EXEMPT = {"main.environment", "auth.login", "auth.logout", "static"}
    _ENV_BYPASS_PREFIXES = ("errors.",)

    @app.before_request
    def require_environment_choice():
        """Authenticated users pick the live or training app before anything else."""
        if (not current_user.is_authenticated or session.get("env") in ("live", "demo")
                or request.endpoint in _ENV_EXEMPT
                or (request.endpoint or "").startswith(_ENV_BYPASS_PREFIXES)):
            return None
        return redirect(url_for("main.environment", next=request.full_path.rstrip("?")))

    with app.app_context():
        db.create_all()
        _upgrade_schema()
        from .seed import seed_all

        seed_all()
        _init_demo_db(app)

    return app


# Columns added after the first release; created in place so existing databases keep their data.
_ADDED_COLUMNS = {
    "user": {"monthly_salary": "FLOAT"},
    "lab_test": {"category": "VARCHAR(60)", "template": "VARCHAR(60)"},
    "lab_request_item": {"micro_data": "TEXT", "result_data": "TEXT"},
    "patient_observation": {"medication": "TEXT", "signature": "VARCHAR(120)"},
    "fluid_balance_entry": {"fluid": "VARCHAR(160)", "parenteral": "INTEGER", "other_intake": "INTEGER",
                            "aspirate": "INTEGER", "bowels": "INTEGER", "blood_loss": "INTEGER",
                            "remarks": "TEXT"},
    "anc_profile": {"notes": "TEXT"},
}


def _upgrade_schema(engine=None):
    from sqlalchemy import inspect, text

    eng = engine or db.engine
    inspector = inspect(eng)
    if "fluid_balance_entry" in inspector.get_table_names():
        fb_cols = {c["name"] for c in inspector.get_columns("fluid_balance_entry")}
        if "iv_fluids" in fb_cols or "ng_feed" in fb_cols:
            _rebuild_fluid_balance_table(eng)
            inspector = inspect(eng)
    for table, columns in _ADDED_COLUMNS.items():
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name not in existing:
                with eng.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _rebuild_fluid_balance_table(engine=None):
    """Rebuild a fluid_balance_entry table that still has the first-version column set.

    The first version had NOT NULL columns (iv_fluids, ng_feed, stool, drains, ...)
    that no longer exist in the model, so rows can't be inserted; the table must be
    recreated. Legacy columns are mapped onto the new layout where sensible.
    """
    from sqlalchemy import text

    from .models import FluidBalanceEntry

    eng = engine or db.engine
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE fluid_balance_entry RENAME TO fluid_balance_entry_old"))
    FluidBalanceEntry.__table__.create(eng)
    with eng.begin() as conn:
        conn.execute(text("""
            INSERT INTO fluid_balance_entry
                (id, patient_id, recorded_by_id, entry_at, fluid, oral, parenteral, other_intake,
                 urine, vomit, aspirate, bowels, blood_loss, remarks, created_at)
            SELECT id, patient_id, recorded_by_id, entry_at, NULL, oral,
                   COALESCE(iv_fluids, 0) + COALESCE(blood_transfusion, 0),
                   COALESCE(ng_feed, 0) + COALESCE(drains, 0),
                   urine, vomit, COALESCE(ng_aspirate, 0), COALESCE(stool, 0), 0,
                   notes, created_at
            FROM fluid_balance_entry_old
        """))
        conn.execute(text("DROP TABLE fluid_balance_entry_old"))


def _init_demo_db(app, force_copy=False):
    """Create the training (demo) database next to the live one.

    First run copies the live database so staff practise on familiar data;
    a fresh/empty file gets the schema plus seed data. Existing demo files are
    only schema-upgraded, so training entries are kept between restarts.
    force_copy=True replaces the demo data with a fresh copy of live.
    """
    import sqlite3

    from sqlalchemy import inspect

    try:
        demo_engine = db.engines["demo"]
    except KeyError:
        return

    live_path = _sqlite_path(app.config.get("SQLALCHEMY_DATABASE_URI"))
    demo_path = _sqlite_path((app.config.get("SQLALCHEMY_BINDS") or {}).get("demo"))

    copied = False
    if live_path and demo_path and os.path.exists(live_path):
        # A 0-byte demo file means an earlier startup was interrupted mid-creation — treat it as missing.
        empty_demo = os.path.exists(demo_path) and os.path.getsize(demo_path) == 0
        if force_copy or empty_demo or not os.path.exists(demo_path):
            demo_engine.dispose()
            if force_copy or empty_demo:
                os.remove(demo_path)
            src, dst = sqlite3.connect(live_path), sqlite3.connect(demo_path)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            copied = True

    inspector = inspect(demo_engine)
    fresh = "patient" not in inspector.get_table_names()
    if fresh or not copied:
        # New tables are created on a fresh file and picked up on older copies.
        db.metadata.create_all(demo_engine)
    if fresh or copied:
        # Brand-new or just-recopied demo DBs get the training data set so
        # practice stays usable even after the live database is cleaned.
        with app.test_request_context():
            session["env"] = "demo"
            _upgrade_schema(demo_engine)
            from .seed import seed_all, seed_demo_users

            seed_all(include_samples=True)
            seed_demo_users()
            session.clear()
    else:
        _upgrade_schema(demo_engine)
