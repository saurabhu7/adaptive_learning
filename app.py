from __future__ import annotations

import os
from datetime import timedelta

from flask import Flask

from auth_utils import category_label, close_db, inject_template_context
from gemini_client import get_gemini_api_key
from platform_db import init_databases
from project_settings import MAX_CONTENT_LENGTH, SECRET_KEY, UPLOAD_FOLDER
from route_auth import register_auth_routes
from route_course import register_course_routes
from route_dashboard import register_dashboard_routes
from route_exam import register_exam_routes
from route_learning import register_learning_routes
from seed_data import seed_db


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["GEMINI_CONFIGURED"] = bool(get_gemini_api_key())
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0").strip() == "1"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=6)

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
        return response

    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    init_databases(seed_db)

    app.teardown_appcontext(close_db)
    app.context_processor(inject_template_context)
    app.add_template_filter(category_label, "category_label")

    register_auth_routes(app)
    register_dashboard_routes(app)
    register_course_routes(app)
    register_learning_routes(app)
    register_exam_routes(app)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
