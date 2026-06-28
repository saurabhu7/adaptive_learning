from __future__ import annotations

from functools import wraps
from typing import Any

from flask import flash, g, redirect, session, url_for

from platform_db import app_database_backend, connect_app_db, fetch_latest_training_run, mysql_configured


def get_db():
    if "db" not in g:
        g.db = connect_app_db(row_factory=True)
    return g.db


def close_db(_: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def inject_template_context() -> dict[str, Any]:
    return {
        "current_user": current_user(),
        "app_db_backend": app_database_backend(),
        "mysql_ready": mysql_configured(),
    }


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user():
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if user["role"] not in roles:
                flash("You do not have permission to open that page.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def category_label(value: str) -> str:
    mapping = {
        "non-it": "Non-IT",
        "it": "IT",
        "datascience": "Data Science",
        "softskills": "Soft Skills",
        "programming": "Programming",
        "ai-ml": "AI / ML",
        "webdevelopment": "Web Development",
    }
    return mapping.get(value, value.title())


def latest_model_info() -> dict[str, Any] | None:
    return fetch_latest_training_run()
