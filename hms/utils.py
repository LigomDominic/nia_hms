from datetime import datetime
from functools import wraps

from flask import abort, request
from flask_login import current_user, login_required

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def roles_required(*roles):
    """Allow the listed roles. Admin is always allowed.

    A per-user module override (set in Admin > Staff & Users) takes precedence:
    'none' blocks, 'view' allows safe methods for any role, 'manage' allows everything.
    """

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != "admin":
                from .permissions import MODULE_BY_BLUEPRINT, explicit_level

                level = explicit_level(current_user, MODULE_BY_BLUEPRINT.get(request.blueprint))
                if level is None:
                    if current_user.role not in roles:
                        abort(403)
                elif level == "none" or (level == "view" and request.method not in SAFE_METHODS):
                    abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_money(value, default=0.0):
    try:
        return round(float(str(value).replace(",", "").strip()), 2)
    except (TypeError, ValueError):
        return default


def parse_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
