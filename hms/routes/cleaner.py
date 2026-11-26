from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import CleaningTask, now
from ..utils import roles_required

bp = Blueprint("cleaner", __name__, url_prefix="/cleaner")


@bp.route("/")
@roles_required("cleaner")
def dashboard():
    query = CleaningTask.query
    if current_user.role == "cleaner":
        query = query.filter_by(assigned_to_id=current_user.id)
    pending = query.filter_by(status="pending").order_by(CleaningTask.due_date).all()
    done = query.filter_by(status="done").order_by(CleaningTask.completed_at.desc()).limit(20).all()
    return render_template("cleaner/dashboard.html", pending=pending, done=done)


@bp.route("/task/<int:task_id>/done", methods=["POST"])
@roles_required("cleaner")
def done(task_id):
    task = db.get_or_404(CleaningTask, task_id)
    if current_user.role == "cleaner" and task.assigned_to_id != current_user.id:
        abort(403)
    task.status = "done"
    task.completed_at = now()
    task.remark = request.form.get("remark") or None
    db.session.commit()
    flash(f"{task.area} marked as cleaned.", "success")
    return redirect(url_for("cleaner.dashboard"))
