"""Unique hospital number generation."""
import secrets

from .app_settings import setting
from .models import Patient, now

PATIENT_ID_FORMATS = {
    "month_year": "{p}-MM/YY-#### (e.g. {p}-10/26-4821, random 4 digits)",
    "month_year_compact": "{p}-MMYY-#### (e.g. {p}-1026-4821, random 4 digits)",
    "sequential": "{p}-###### (e.g. {p}-000123, running number)",
}


def new_hospital_id(patient, when=None):
    """Return a new unique hospital ID for an already-flushed patient."""
    prefix = (setting("patient_id_prefix") or "NIA").upper()
    fmt = setting("patient_id_format")
    if fmt == "sequential":
        return f"{prefix}-{patient.id:06d}"
    period = (when or now()).strftime("%m%y" if fmt == "month_year_compact" else "%m/%y")
    # 4 random digits allow 9,000 IDs per month; fall back to 5-6 digits if a month ever fills up.
    for digits in (4, 4, 5, 6):
        low = 10 ** (digits - 1)
        for _ in range(100):
            candidate = f"{prefix}-{period}-{low + secrets.randbelow(9 * low)}"
            if not Patient.query.filter_by(hospital_id=candidate).first():
                return candidate
    raise RuntimeError("Could not generate a unique hospital ID.")
