from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from auth_utils import current_user, get_db, login_required, role_required
from learning_assets import build_course_assets
from project_settings import ALLOWED_EXTENSIONS, UPLOAD_FOLDER
from youtube_playlist import extract_playlist_id, extract_video_id, fetch_playlist_lectures


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _domain_courses(created_by: int) -> list[tuple[str, str, str, int, str, str | None, str | None, int]]:
    return [
        (
            "IT Fundamentals",
            "it",
            "Information Technology",
            1,
            "Learn operating systems, networking basics, hardware-software flow, and IT support practices.",
            None,
            "https://www.youtube.com/watch?v=qwN8wyU-DZY",
            created_by,
        ),
        (
            "Networking Basics for IT",
            "it",
            "Computer Networks",
            2,
            "Understand IP addressing, routing, switching, and secure connectivity concepts for IT careers.",
            None,
            "https://www.youtube.com/watch?v=qiQR5rTSshw",
            created_by,
        ),
        (
            "Digital Literacy Essentials",
            "non-it",
            "Digital Literacy",
            1,
            "Understand email, online tools, internet safety, and digital productivity in daily work.",
            None,
            "https://www.youtube.com/watch?v=O5nskjZ_GoI",
            created_by,
        ),
        (
            "Business Communication",
            "non-it",
            "Communication",
            2,
            "Build professional writing, presentation, and collaboration communication skills.",
            None,
            "https://www.youtube.com/watch?v=HAnw168huqA",
            created_by,
        ),
        (
            "Data Science Foundations",
            "datascience",
            "Data Science",
            1,
            "Learn data lifecycle, analysis basics, visualization, and interpretation for decision-making.",
            None,
            "https://www.youtube.com/watch?v=ua-CiDNNj30",
            created_by,
        ),
        (
            "Statistics for Data Science",
            "datascience",
            "Statistics",
            2,
            "Cover descriptive statistics, probability intuition, hypothesis testing, and confidence intervals.",
            None,
            "https://www.youtube.com/watch?v=xxpc-HPKN28",
            created_by,
        ),
        (
            "Professional Soft Skills",
            "softskills",
            "Soft Skills",
            1,
            "Strengthen teamwork, adaptability, ownership, and workplace etiquette.",
            None,
            "https://www.youtube.com/watch?v=KQw0h2s1R2I",
            created_by,
        ),
        (
            "Interview and Career Readiness",
            "softskills",
            "Career Skills",
            2,
            "Practice resume strategy, interview communication, and confidence-building techniques.",
            None,
            "https://www.youtube.com/watch?v=8BFtSg2wA0w",
            created_by,
        ),
    ]


def register_course_routes(app) -> None:
    def _playlist_embed_url(playlist_url: str) -> str:
        playlist_id = extract_playlist_id(playlist_url)
        if not playlist_id:
            return ""
        return f"https://www.youtube.com/embed/videoseries?list={playlist_id}"

    @app.route("/addcourse")
    @role_required("teacher", "admin")
    def addcourse():
        return render_template("addcourses.html")

    @app.route("/add-course", methods=["POST"])
    @role_required("teacher", "admin")
    def add_course():
        user = current_user()
        title = request.form.get("course_name", "").strip()
        category = request.form.get("category", "").strip()
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        youtube = request.form.get("youtube", "").strip()
        playlist_url = request.form.get("playlist_url", "").strip()
        try:
            course_index = int(request.form.get("course_index", "0"))
        except ValueError:
            course_index = 0
        if not all([title, category, subject, description]) or course_index < 1:
            flash("Please complete all required course fields.", "error")
            return redirect(url_for("addcourse"))
        filename = None
        pdf = request.files.get("pdf")
        if pdf and pdf.filename:
            if not allowed_file(pdf.filename):
                flash("Only PDF files are allowed.", "error")
                return redirect(url_for("addcourse"))
            filename = secure_filename(pdf.filename)
            save_path = UPLOAD_FOLDER / filename
            duplicate_counter = 1
            while save_path.exists():
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                filename = f"{stem}-{duplicate_counter}{suffix}"
                save_path = UPLOAD_FOLDER / filename
                duplicate_counter += 1
            pdf.save(save_path)
        lecture_rows: list[tuple[int, int, str, str]] = []
        playlist_lectures = fetch_playlist_lectures(playlist_url) if playlist_url else []
        primary_youtube = youtube
        playlist_embed = _playlist_embed_url(playlist_url) if playlist_url else ""
        if playlist_url and not playlist_lectures and not primary_youtube:
            fallback_video_id = extract_video_id(playlist_url)
            if fallback_video_id:
                primary_youtube = f"https://www.youtube.com/watch?v={fallback_video_id}"
            elif playlist_embed:
                primary_youtube = playlist_embed
        if playlist_lectures and not primary_youtube:
            primary_youtube = playlist_lectures[0]["video_url"]

        cursor = get_db().execute(
            """
            INSERT INTO courses
            (title, category, subject, course_index, description, pdf_file, youtube_url, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, category, subject, course_index, description, filename, primary_youtube, user["id"]),
        )
        course_id = int(cursor.lastrowid)
        if playlist_lectures:
            for idx, lecture in enumerate(playlist_lectures, start=1):
                lecture_rows.append((course_id, idx, lecture["title"], lecture["video_url"]))
        elif primary_youtube:
            lecture_rows.append((course_id, 1, f"{title} - Lecture 1", primary_youtube))
        if lecture_rows:
            get_db().executemany(
                """
                INSERT INTO course_lectures (course_id, lecture_index, title, video_url)
                VALUES (?, ?, ?, ?)
                """,
                lecture_rows,
            )
        get_db().commit()
        if playlist_url and not playlist_lectures:
            flash("Course added, but playlist import failed. Please check YouTube API key or playlist visibility.", "warning")
        else:
            flash("Course added successfully.", "success")
        return redirect(url_for("teacher_dashboard" if user["role"] == "teacher" else "admin_dashboard"))

    @app.route("/edit-course/<int:course_id>")
    @role_required("teacher", "admin")
    def edit_course(course_id: int):
        user = current_user()
        db = get_db()
        if user["role"] == "teacher":
            course = db.execute(
                "SELECT * FROM courses WHERE id = ? AND created_by = ?",
                (course_id, user["id"]),
            ).fetchone()
        else:
            course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found or you do not have permission to edit it.", "error")
            return redirect(url_for("show_courses"))
        return render_template("edit_course.html", course=course)

    @app.route("/update-course/<int:course_id>", methods=["POST"])
    @role_required("teacher", "admin")
    def update_course(course_id: int):
        user = current_user()
        db = get_db()
        if user["role"] == "teacher":
            course = db.execute(
                "SELECT * FROM courses WHERE id = ? AND created_by = ?",
                (course_id, user["id"]),
            ).fetchone()
        else:
            course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found or you do not have permission to update it.", "error")
            return redirect(url_for("show_courses"))

        title = request.form.get("course_name", "").strip()
        category = request.form.get("category", "").strip()
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        youtube = request.form.get("youtube", "").strip()
        playlist_url = request.form.get("playlist_url", "").strip()
        try:
            course_index = int(request.form.get("course_index", "0"))
        except ValueError:
            course_index = 0
        if not all([title, category, subject, description]) or course_index < 1:
            flash("Please complete all required course fields.", "error")
            return redirect(url_for("edit_course", course_id=course_id))

        filename = course["pdf_file"]
        pdf = request.files.get("pdf")
        if pdf and pdf.filename:
            if not allowed_file(pdf.filename):
                flash("Only PDF files are allowed.", "error")
                return redirect(url_for("edit_course", course_id=course_id))
            filename = secure_filename(pdf.filename)
            save_path = UPLOAD_FOLDER / filename
            duplicate_counter = 1
            while save_path.exists():
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                filename = f"{stem}-{duplicate_counter}{suffix}"
                save_path = UPLOAD_FOLDER / filename
                duplicate_counter += 1
            pdf.save(save_path)

        playlist_lectures = fetch_playlist_lectures(playlist_url) if playlist_url else []
        primary_youtube = youtube or course.get("youtube_url") or ""
        playlist_embed = _playlist_embed_url(playlist_url) if playlist_url else ""
        if playlist_lectures and not primary_youtube:
            primary_youtube = playlist_lectures[0]["video_url"]
        if playlist_url and not playlist_lectures and not primary_youtube:
            fallback_video_id = extract_video_id(playlist_url)
            if fallback_video_id:
                primary_youtube = f"https://www.youtube.com/watch?v={fallback_video_id}"
            elif playlist_embed:
                primary_youtube = playlist_embed

        db.execute(
            """
            UPDATE courses
            SET title = ?, category = ?, subject = ?, course_index = ?, description = ?, pdf_file = ?, youtube_url = ?
            WHERE id = ?
            """,
            (title, category, subject, course_index, description, filename, primary_youtube, course_id),
        )

        if playlist_lectures:
            db.execute("DELETE FROM course_lectures WHERE course_id = ?", (course_id,))
            db.executemany(
                """
                INSERT INTO course_lectures (course_id, lecture_index, title, video_url)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (course_id, idx, lecture["title"], lecture["video_url"])
                    for idx, lecture in enumerate(playlist_lectures, start=1)
                ],
            )
        elif primary_youtube:
            existing = db.execute(
                "SELECT COUNT(*) AS total FROM course_lectures WHERE course_id = ?",
                (course_id,),
            ).fetchone()
            if int(existing["total"] or 0) == 0:
                db.execute(
                    """
                    INSERT INTO course_lectures (course_id, lecture_index, title, video_url)
                    VALUES (?, ?, ?, ?)
                    """,
                    (course_id, 1, f"{title} - Lecture 1", primary_youtube),
                )

        db.commit()
        flash("Course updated successfully.", "success")
        return redirect(url_for("show_courses"))

    @app.route("/reset-domain-courses", methods=["POST"])
    @role_required("admin")
    def reset_domain_courses():
        user = current_user()
        db = get_db()
        owner = user["id"]
        teacher = db.execute("SELECT id FROM users WHERE role = 'teacher' ORDER BY id LIMIT 1").fetchone()
        if teacher:
            owner = teacher["id"]

        db.execute("DELETE FROM intervention_outcomes")
        db.execute("DELETE FROM strategy_recommendations")
        db.execute("DELETE FROM emotion_events")
        db.execute("DELETE FROM emotion_feedback")
        db.execute("DELETE FROM course_ai_assets")
        db.execute("DELETE FROM session_insights")
        db.execute("DELETE FROM exam_attempts")
        db.execute("DELETE FROM course_lectures")
        db.execute("DELETE FROM courses")
        db.executemany(
            """
            INSERT INTO courses
            (title, category, subject, course_index, description, pdf_file, youtube_url, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _domain_courses(owner),
        )
        inserted = db.execute(
            "SELECT id, title, youtube_url FROM courses ORDER BY category, course_index, id"
        ).fetchall()
        lecture_rows: list[tuple[int, int, str, str]] = []
        for course in inserted:
            if not course.get("youtube_url"):
                continue
            lecture_rows.append((course["id"], 1, f"{course['title']} - Lecture 1", course["youtube_url"]))
        if lecture_rows:
            db.executemany(
                """
                INSERT INTO course_lectures (course_id, lecture_index, title, video_url)
                VALUES (?, ?, ?, ?)
                """,
                lecture_rows,
            )
        db.commit()
        flash("Old courses removed and new domain-wise catalog added.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/delete-course/<int:course_id>", methods=["POST"])
    @role_required("teacher", "admin")
    def delete_course(course_id: int):
        user = current_user()
        db = get_db()
        if user["role"] == "teacher":
            course = db.execute(
                "SELECT * FROM courses WHERE id = ? AND created_by = ?",
                (course_id, user["id"]),
            ).fetchone()
        else:
            course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found or you do not have permission to delete it.", "error")
            return redirect(url_for("teacher_dashboard" if user["role"] == "teacher" else "admin_dashboard"))

        if course.get("pdf_file") if isinstance(course, dict) else course["pdf_file"]:
            filename = course.get("pdf_file") if isinstance(course, dict) else course["pdf_file"]
            file_path = UPLOAD_FOLDER / filename
            if file_path.exists():
                file_path.unlink()

        db.execute("DELETE FROM intervention_outcomes WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM strategy_recommendations WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM emotion_events WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM emotion_feedback WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM course_ai_assets WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM course_lectures WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM live_lectures WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM chat_messages WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM course_subscriptions WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM session_insights WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM exam_attempts WHERE course_id = ?", (course_id,))
        db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        db.commit()
        flash("Course deleted successfully.", "success")
        return redirect(url_for("teacher_dashboard" if user["role"] == "teacher" else "admin_dashboard"))

    @app.route("/course/<int:course_id>/generate-notes", methods=["POST"])
    @role_required("teacher", "admin")
    def generate_course_notes(course_id: int):
        user = current_user()
        db = get_db()
        if user["role"] == "teacher":
            course = db.execute(
                "SELECT * FROM courses WHERE id = ? AND created_by = ?",
                (course_id, user["id"]),
            ).fetchone()
        else:
            course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found or permission denied.", "error")
            return redirect(url_for("teacher_dashboard" if user["role"] == "teacher" else "admin_dashboard"))
        payload = build_course_assets(dict(course))
        if not payload.get("ok"):
            flash(f"Notes generation failed: {payload.get('error', 'unknown error')}", "error")
            return redirect(url_for("teacher_dashboard" if user["role"] == "teacher" else "admin_dashboard"))
        latest_asset = db.execute(
            """
            SELECT id FROM course_ai_assets
            WHERE course_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        if latest_asset:
            db.execute(
                """
                UPDATE course_ai_assets
                SET generated_by = ?,
                    summary = ?,
                    notes_markdown = ?,
                    quiz_json = ?,
                    provider = ?,
                    transcript_source = ?,
                    pdf_file = ?
                WHERE id = ?
                """,
                (
                    user["id"],
                    payload["summary"],
                    payload["notes_markdown"],
                    payload["quiz_json"],
                    payload["provider"],
                    payload["transcript_source"],
                    payload["pdf_file"],
                    latest_asset["id"],
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO course_ai_assets
                (
                    course_id, generated_by, summary, notes_markdown, quiz_json, provider, transcript_source, pdf_file
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    user["id"],
                    payload["summary"],
                    payload["notes_markdown"],
                    payload["quiz_json"],
                    payload["provider"],
                    payload["transcript_source"],
                    payload["pdf_file"],
                ),
            )
        db.commit()
        flash("Notes + AI exam questions generated successfully.", "success")
        return redirect(url_for("teacher_dashboard" if user["role"] == "teacher" else "admin_dashboard"))

    @app.route("/course/<int:course_id>/generate-exam", methods=["POST"])
    @role_required("teacher", "admin")
    def generate_course_exam(course_id: int):
        # Exam generation reuses the same AI asset pipeline so notes + quiz stay consistent.
        return generate_course_notes(course_id)

    @app.route("/courses")
    @login_required
    def show_courses():
        user = current_user()
        category = request.args.get("category", "").strip()
        query = "SELECT c.*, u.username AS teacher_name FROM courses c LEFT JOIN users u ON u.id = c.created_by"
        params: list[Any] = []
        if category:
            query += " WHERE c.category = ?"
            params.append(category)
        query += """
            ORDER BY
                CASE
                    WHEN c.category IN ('it', 'programming', 'ai-ml', 'webdevelopment') THEN 1
                    WHEN c.category = 'non-it' THEN 2
                    WHEN c.category = 'datascience' THEN 3
                    WHEN c.category = 'softskills' THEN 4
                    ELSE 5
                END,
                c.course_index,
                c.title
        """
        courses = get_db().execute(query, params).fetchall()
        categories = get_db().execute("SELECT DISTINCT category FROM courses ORDER BY category").fetchall()
        subscribed_course_ids = set()
        if user and user["role"] == "student":
            rows = get_db().execute(
                "SELECT course_id FROM course_subscriptions WHERE user_id = ?",
                (user["id"],),
            ).fetchall()
            subscribed_course_ids = {int(row["course_id"]) for row in rows}
        return render_template(
            "viewallcources.html",
            courses=courses,
            selected_category=category,
            categories=categories,
            subscribed_course_ids=subscribed_course_ids,
        )

    @app.route("/viewstudents")
    @role_required("admin", "teacher")
    def view_students():
        records = get_db().execute(
            "SELECT id, username, email, mobile, created_at FROM users WHERE role = 'student' ORDER BY created_at DESC"
        ).fetchall()
        return render_template("viewstudents.html", records=records)

    @app.route("/viewteachers")
    @role_required("admin")
    def view_teachers():
        records = get_db().execute(
            "SELECT id, username, email, mobile, created_at FROM users WHERE role = 'teacher' ORDER BY created_at DESC"
        ).fetchall()
        return render_template("viewteachers.html", records=records)
