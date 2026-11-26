"""Module-level access control.

Every staff member has a role which grants default access to modules.
An admin can override any user's access per module:

  * ``none``   - block the module entirely
  * ``view``   - read-only (GET/HEAD requests only)
  * ``manage`` - full access, including create/update actions

Administrators (role ``admin``) always have full access to every module.
"""
from flask import g
from flask_login import current_user

from .models import CLINICAL_ROLES, DOCTOR_ROLES, UserAccess

# module key -> (label, roles that can view by default, roles that can manage by default)
MODULES = {
    "patients": ("Patients", CLINICAL_ROLES, ("cashier", "nurse") + DOCTOR_ROLES),
    "billing": ("Billing / Cashier", ("cashier",), ("cashier",)),
    "consultation": ("Consultation", DOCTOR_ROLES, DOCTOR_ROLES),
    "nursing": ("Nursing & Observations", ("nurse",) + DOCTOR_ROLES, ("nurse",)),
    "consumables": ("Consumables Record", ("nurse",) + DOCTOR_ROLES, ("nurse",)),
    "fluid_balance": ("Fluid Balance Sheet", ("nurse",) + DOCTOR_ROLES, ("nurse",)),
    "treatment": ("Treatment Charts", ("nurse",) + DOCTOR_ROLES, ("nurse",) + DOCTOR_ROLES),
    "anc": ("Ante-Natal (ANC)", ("nurse",) + DOCTOR_ROLES, ("nurse",) + DOCTOR_ROLES),
    "laboratory": ("Laboratory", CLINICAL_ROLES, ("lab", "cashier")),
    "pharmacy": ("Pharmacy", ("pharmacist",), ("pharmacist",)),
    "requisitions": ("Station Requisitions", ("nurse", "pharmacist") + DOCTOR_ROLES, ("nurse", "pharmacist")),
    "expenses": ("General Expenses", ("cashier",), ("cashier",)),
    "payroll": ("Staff Payroll & IOUs", ("cashier",), ("cashier",)),
    "store": ("General Store", ("store_keeper",), ("store_keeper",)),
    "cleaning": ("Housekeeping", ("cleaner",), ("cleaner",)),
    "administration": ("Administration", (), ()),
}

MODULE_BY_BLUEPRINT = {
    "patients": "patients",
    "cashier": "billing",
    "doctor": "consultation",
    "nurse": "nursing",
    "consumables": "consumables",
    "fluid_balance": "fluid_balance",
    "treatment": "treatment",
    "anc": "anc",
    "lab": "laboratory",
    "pharmacy": "pharmacy",
    "requisitions": "requisitions",
    "expenses": "expenses",
    "payroll": "payroll",
    "store": "store",
    "cleaner": "cleaning",
    "admin": "administration",
}

_LEVEL_RANK = {"none": 0, "view": 1, "manage": 2}


def explicit_level(user, module):
    """The stored override for this user+module, or None if inheriting. Cached per request."""
    if module not in MODULES:
        return None
    rows = g.get("_access_overrides")
    if rows is None or g.get("_access_user_id") != user.id:
        rows = {r.module: r.level for r in UserAccess.query.filter_by(user_id=user.id)}
        g._access_overrides = rows
        g._access_user_id = user.id
    return rows.get(module)


def effective_level(user, module):
    """Final access level after role defaults and overrides."""
    if user.role == "admin":
        return "manage"
    stored = explicit_level(user, module)
    if stored is not None:
        return stored
    _label, view_roles, manage_roles = MODULES[module]
    if user.role in manage_roles:
        return "manage"
    if user.role in view_roles:
        return "view"
    return "none"


def can_access(user, module, level="view"):
    if not user.is_authenticated or module not in MODULES:
        return False
    return _LEVEL_RANK[effective_level(user, module)] >= _LEVEL_RANK[level]


def can_module(module, level="view"):
    """Template helper: can the current user access a module at the given level."""
    return can_access(current_user, module, level)
