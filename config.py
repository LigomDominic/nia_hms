import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "nia-hospitals-app-v002-2026-dom")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "hms.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    HOSPITAL_NAME = os.environ.get("HOSPITAL_NAME", "NIA HOSPITAL")
    PATIENT_ID_PREFIX = os.environ.get("PATIENT_ID_PREFIX", "NIA")
    CURRENCY = os.environ.get("CURRENCY", "₦")
    # Sample lab tests are only for demos; the hospital's own tests are added in Admin > Lab Test Catalog.
    SEED_SAMPLE_LAB_TESTS = os.environ.get("SEED_SAMPLE_LAB_TESTS", "0") == "1"
    # Sample pharmacy/store/emergency stock is demo data; production adds real stock itself.
    SEED_SAMPLE_INVENTORY = os.environ.get("SEED_SAMPLE_INVENTORY", "0") == "1"

    # Outgoing email for lab results (leave MAIL_SERVER empty to disable)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "mail.niahospitals.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "465"))
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "1") == "1"  # port 465 (SSL); else STARTTLS on MAIL_PORT
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1") == "1"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "info@niahospitals.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "Nia123")
    MAIL_SENDER = os.environ.get("MAIL_SENDER", "") or MAIL_USERNAME
