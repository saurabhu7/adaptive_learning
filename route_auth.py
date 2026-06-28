from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from auth_utils import current_user, get_db


def register_auth_routes(app) -> None:
    @app.route("/", methods=["GET", "POST"])
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user():
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "").strip().lower()
            if role not in {"student", "teacher", "admin"}:
                flash("Please select a valid role.", "error")
                return render_template("studentlogin.html")
            user = get_db().execute(
                "SELECT * FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                if role != user["role"]:
                    flash(
                        f"Logged in successfully. Note: this account belongs to role '{user['role']}'.",
                        "warning",
                    )
                flash(f"Welcome back, {user['username']}!", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid email, password, or role selection.", "error")

        return render_template("studentlogin.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            return createaccount()
        return render_template("register_new.html")

    @app.route("/createaccount", methods=["POST"])
    def createaccount():
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        mobile = request.form.get("mobile", "").strip()
        role = request.form.get("role", "").strip().lower()
        if not all([username, email, password, mobile, role]):
            flash("Please fill in all fields.", "error")
            return redirect(url_for("register"))
        if role not in {"student", "teacher", "admin"}:
            flash("Please select a valid role.", "error")
            return redirect(url_for("register"))
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("register"))
        db = get_db()
        existing_user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing_user:
            flash("That email is already registered.", "error")
            return redirect(url_for("register"))
        db.execute(
            """
            INSERT INTO users (username, email, password_hash, mobile, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, email, generate_password_hash(password), mobile, role),
        )
        db.commit()
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/loginout")
    def loginout():
        return redirect(url_for("logout"))

    @app.route("/show", methods=["GET", "POST"])
    def legacy_show():
        return redirect(url_for("login"))
