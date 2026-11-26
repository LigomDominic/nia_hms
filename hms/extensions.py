from flask import has_request_context, session
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session


class EnvSession(Session):
    """Route database work to the demo engine when the user's session is in
    training mode (session['env'] == 'demo'). All models stay on the default
    (live) engine; only the engine chosen here differs."""

    def get_bind(self, mapper=None, clause=None, bind=None, **kwargs):
        if bind is None and has_request_context() and session.get("env") == "demo":
            try:
                return self._db.engines["demo"]
            except KeyError:
                pass
        return super().get_bind(mapper=mapper, clause=clause, bind=bind, **kwargs)


db = SQLAlchemy(session_options={"class_": EnvSession})
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"
