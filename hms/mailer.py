import smtplib
from email.message import EmailMessage

from flask import current_app, render_template

from .app_settings import doc_number, setting


def mail_configured():
    return bool(current_app.config.get("MAIL_SERVER"))


def send_mail(subject, html, text, to):
    """Send one email through the configured SMTP account. Returns (ok, error)."""
    to = (to or "").strip()
    if not mail_configured() or not to:
        return False, "Email server not configured or no recipient address."
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{setting('hospital_name')} <{cfg.get('MAIL_SENDER') or cfg.get('MAIL_USERNAME')}>"
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        cls = smtplib.SMTP_SSL if cfg.get("MAIL_USE_SSL") else smtplib.SMTP
        with cls(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=20) as server:
            if cls is smtplib.SMTP and cfg.get("MAIL_USE_TLS"):
                server.starttls()
            if cfg["MAIL_USERNAME"]:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("email to %s failed: %s", to, exc)
        return False, f"Email failed: {exc}"
    return True, ""


def send_lab_result(lab_request):
    """Email a lab result to the patient. Returns (ok, message)."""
    patient = lab_request.patient
    if not patient.email:
        return False, "Patient has no email address on file."
    if not mail_configured():
        return False, "Email server is not configured (set MAIL_SERVER etc.)."
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = f"{setting('hospital_name')} - Laboratory Result {doc_number('lab', lab_request.id)}"
    msg["From"] = cfg["MAIL_SENDER"]
    msg["To"] = patient.email
    msg.set_content(render_template("email/lab_result.txt", req=lab_request))
    msg.add_alternative(render_template("email/lab_result.html", req=lab_request), subtype="html")
    try:
        use_ssl = cfg.get("MAIL_USE_SSL")
        cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with cls(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=20) as server:
            if not use_ssl and cfg["MAIL_USE_TLS"]:
                server.starttls()
            if cfg["MAIL_USERNAME"]:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - report any SMTP failure to the user
        return False, f"Email failed: {exc}"
    return True, f"Result emailed to {patient.email}."
