from __future__ import annotations

from typing import Any

from flask import flash, redirect, render_template, request, url_for

from auth_utils import current_user, get_db, latest_model_info, login_required, role_required


def _risk_band(risk_score: float) -> str:
    if risk_score >= 70:
        return "High"
    if risk_score >= 40:
        return "Moderate"
    return "Low"


def _to_number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _domain_bucket(category: str) -> str:
    value = (category or "").strip().lower()
    if value in {"it", "programming", "ai-ml", "webdevelopment"}:
        return "it"
    if value in {"non-it"}:
        return "non-it"
    if value in {"datascience"}:
        return "datascience"
    if value in {"softskills"}:
        return "softskills"
    return "it"


def _direct_room_key(user_a: int, user_b: int) -> str:
    first, second = sorted([int(user_a), int(user_b)])
    return f"direct:{first}:{second}"


def register_dashboard_routes(app) -> None:
    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        if user["role"] == "student":
            return redirect(url_for("student_dashboard"))
        if user["role"] == "teacher":
            return redirect(url_for("teacher_dashboard"))
        return redirect(url_for("admin_dashboard"))

    @app.route("/student")
    @role_required("student")
    def student_dashboard():
        user = current_user()
        db = get_db()
        model_info = latest_model_info()
        courses = db.execute(
            """
            SELECT *
            FROM courses
            ORDER BY
                CASE
                    WHEN category IN ('it', 'programming', 'ai-ml', 'webdevelopment') THEN 1
                    WHEN category = 'non-it' THEN 2
                    WHEN category = 'datascience' THEN 3
                    WHEN category = 'softskills' THEN 4
                    ELSE 5
                END,
                course_index,
                title
            """
        ).fetchall()
        subscribed_rows = db.execute(
            "SELECT course_id FROM course_subscriptions WHERE user_id = ?",
            (user["id"],),
        ).fetchall()
        subscribed_course_ids = {int(row["course_id"]) for row in subscribed_rows}
        domain_order = ["it", "non-it", "datascience", "softskills"]
        grouped_courses = {domain: [] for domain in domain_order}
        for course in courses:
            grouped_courses[_domain_bucket(str(course.get("category", "")))].append(course)
        categories = db.execute(
            "SELECT category, COUNT(*) AS total FROM courses GROUP BY category ORDER BY category"
        ).fetchall()
        attempt_stats = db.execute(
            """
            SELECT COUNT(*) AS attempts,
                   COALESCE(ROUND(AVG(score * 100.0 / total_questions), 0), 0) AS average_score
            FROM exam_attempts
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        recent_attempts = db.execute(
            """
            SELECT a.*, c.title AS course_title
            FROM exam_attempts a
            LEFT JOIN courses c ON c.id = a.course_id
            WHERE a.user_id = ?
            ORDER BY a.created_at DESC
            LIMIT 5
            """,
            (user["id"],),
        ).fetchall()
        recent_insights = db.execute(
            """
            SELECT s.*, c.title AS course_title
            FROM session_insights s
            JOIN courses c ON c.id = s.course_id
            WHERE s.user_id = ?
            ORDER BY s.created_at DESC
            LIMIT 4
            """,
            (user["id"],),
        ).fetchall()
        category_progress = db.execute(
            """
            SELECT a.category,
                   COUNT(*) AS attempts,
                   COALESCE(ROUND(AVG(a.score * 100.0 / a.total_questions), 0), 0) AS average_score,
                   MAX(a.created_at) AS latest_attempt
            FROM exam_attempts a
            WHERE a.user_id = ?
            GROUP BY a.category
            ORDER BY average_score DESC, attempts DESC
            """,
            (user["id"],),
        ).fetchall()
        recent_mood = db.execute(
            """
            SELECT category, mood, created_at
            FROM emotions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user["id"],),
        ).fetchone()
        profile = db.execute(
            """
            SELECT stability_score, engagement_score, risk_score, recovery_rate, recommended_pacing, updated_at
            FROM student_profiles
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        recovery_stats = db.execute(
            """
            SELECT
                COUNT(*) AS total_outcomes,
                SUM(CASE WHEN outcome_status = 'improved' THEN 1 ELSE 0 END) AS improved_outcomes
            FROM intervention_outcomes
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        next_course = db.execute(
            "SELECT * FROM courses ORDER BY course_index ASC, title ASC LIMIT 1"
        ).fetchone()
        interview_courses = db.execute(
            """
            SELECT *
            FROM courses
            WHERE category = 'softskills'
            ORDER BY course_index, title
            """
        ).fetchall()
        interview_exam_stats = db.execute(
            """
            SELECT
                COUNT(*) AS attempts,
                COALESCE(ROUND(AVG(score * 100.0 / total_questions), 0), 0) AS average_score
            FROM exam_attempts
            WHERE user_id = ? AND category = 'softskills'
            """,
            (user["id"],),
        ).fetchone()
        support_count = db.execute(
            "SELECT COUNT(*) AS total FROM session_insights WHERE user_id = ?",
            (user["id"],),
        ).fetchone()["total"]
        per_course_analysis = db.execute(
            """
            SELECT
                c.id,
                c.title,
                c.category,
                c.subject,
                c.course_index,
                COALESCE(ex.attempts, 0) AS exam_attempts,
                COALESCE(ex.avg_score, 0) AS avg_exam_score,
                COALESCE(si.sessions, 0) AS support_sessions,
                COALESCE(si.last_emotion, 'N/A') AS latest_emotion,
                COALESCE(sr.top_strategy, 'N/A') AS top_strategy,
                COALESCE(rc.recovery_rate, 0) AS recovery_rate
            FROM courses c
            LEFT JOIN (
                SELECT
                    course_id,
                    COUNT(*) AS attempts,
                    ROUND(AVG(score * 100.0 / total_questions), 0) AS avg_score
                FROM exam_attempts
                WHERE user_id = ?
                GROUP BY course_id
            ) ex ON ex.course_id = c.id
            LEFT JOIN (
                SELECT
                    course_id,
                    COUNT(*) AS sessions,
                    SUBSTRING_INDEX(GROUP_CONCAT(emotion ORDER BY created_at DESC, id DESC), ',', 1) AS last_emotion
                FROM session_insights
                WHERE user_id = ?
                GROUP BY course_id
            ) si ON si.course_id = c.id
            LEFT JOIN (
                SELECT
                    course_id,
                    SUBSTRING_INDEX(GROUP_CONCAT(strategy_code ORDER BY total DESC SEPARATOR ','), ',', 1) AS top_strategy
                FROM (
                    SELECT course_id, strategy_code, COUNT(*) AS total
                    FROM strategy_recommendations
                    WHERE user_id = ?
                    GROUP BY course_id, strategy_code
                ) grouped
                GROUP BY course_id
            ) sr ON sr.course_id = c.id
            LEFT JOIN (
                SELECT
                    course_id,
                    ROUND(SUM(CASE WHEN outcome_status = 'improved' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS recovery_rate
                FROM intervention_outcomes
                WHERE user_id = ?
                GROUP BY course_id
            ) rc ON rc.course_id = c.id
            ORDER BY c.category, c.course_index, c.title
            """,
            (user["id"], user["id"], user["id"], user["id"]),
        ).fetchall()
        stats = {
            "courses_enrolled": len(courses),
            "categories": len(categories),
            "exam_attempts": attempt_stats["attempts"] or 0,
            "average_score": int(attempt_stats["average_score"] or 0),
            "support_sessions": support_count or 0,
        }
        is_new_student = (stats["exam_attempts"] == 0) and (stats["support_sessions"] == 0)
        stats["improved_outcomes"] = int((recovery_stats or {}).get("improved_outcomes") or 0)
        stats["total_outcomes"] = int((recovery_stats or {}).get("total_outcomes") or 0)
        stats["interview_attempts"] = int((interview_exam_stats or {}).get("attempts") or 0)
        stats["interview_average"] = int((interview_exam_stats or {}).get("average_score") or 0)
        monthly_trend_raw = db.execute(
            """
            SELECT DATE_FORMAT(created_at, '%%Y-%%m') AS period,
                   ROUND(AVG(score * 100.0 / total_questions), 2) AS avg_score,
                   COUNT(*) AS attempts
            FROM exam_attempts
            WHERE user_id = ?
            GROUP BY DATE_FORMAT(created_at, '%%Y-%%m')
            ORDER BY period DESC
            LIMIT 6
            """,
            (user["id"],),
        ).fetchall()
        monthly_trend = list(reversed(monthly_trend_raw))
        emotion_distribution = db.execute(
            """
            SELECT emotion, COUNT(*) AS total
            FROM session_insights
            WHERE user_id = ?
            GROUP BY emotion
            ORDER BY total DESC, emotion
            """,
            (user["id"],),
        ).fetchall()
        emotion_detection_quality = db.execute(
            """
            SELECT
                COUNT(*) AS total_events,
                SUM(CASE WHEN quality_state = 'valid' THEN 1 ELSE 0 END) AS valid_events,
                COALESCE(ROUND(AVG(confidence) * 100.0, 2), 0) AS avg_confidence,
                COALESCE(
                    ROUND(SUM(CASE WHEN quality_state = 'valid' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2),
                    0
                ) AS valid_rate
            FROM emotion_events
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        feedback_alignment = db.execute(
            """
            SELECT
                COUNT(*) AS total_feedback,
                SUM(CASE WHEN predicted_emotion = actual_emotion THEN 1 ELSE 0 END) AS matched_feedback,
                COALESCE(
                    ROUND(SUM(CASE WHEN predicted_emotion = actual_emotion THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2),
                    0
                ) AS match_rate
            FROM emotion_feedback
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        strategy_pipeline = db.execute(
            """
            SELECT
                COUNT(sr.id) AS strategies_used,
                SUM(CASE WHEN io.outcome_status = 'improved' THEN 1 ELSE 0 END) AS improved_outcomes,
                COALESCE(
                    ROUND(SUM(CASE WHEN io.outcome_status = 'improved' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(io.id), 0), 2),
                    0
                ) AS pipeline_recovery_rate
            FROM strategy_recommendations sr
            LEFT JOIN intervention_outcomes io ON io.recommendation_id = sr.id
            WHERE sr.user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        course_content_readiness = db.execute(
            """
            SELECT
                c.id,
                c.title,
                c.category,
                COUNT(DISTINCT cl.id) AS lecture_count,
                MAX(CASE WHEN ca.id IS NOT NULL THEN 1 ELSE 0 END) AS ai_asset_ready,
                COALESCE(MAX(JSON_LENGTH(ca.quiz_json)), 0) AS quiz_items,
                MAX(CASE WHEN ca.pdf_file IS NOT NULL AND ca.pdf_file <> '' THEN 1 ELSE 0 END) AS notes_ready
            FROM courses c
            LEFT JOIN course_lectures cl ON cl.course_id = c.id
            LEFT JOIN course_ai_assets ca ON ca.course_id = c.id
            GROUP BY c.id, c.title, c.category
            ORDER BY c.category, c.course_index, c.title
            LIMIT 8
            """
        ).fetchall()
        velocity_row = db.execute(
            """
            SELECT
                SUM(CASE WHEN created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) AS recent_attempts,
                SUM(CASE WHEN created_at < DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) AS older_attempts
            FROM exam_attempts
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        recovery_rate = _to_number((profile or {}).get("recovery_rate")) if profile else 0.0
        engagement_score = _to_number((profile or {}).get("engagement_score")) if profile else 0.0
        risk_score = _to_number((profile or {}).get("risk_score")) if profile else 50.0
        performance_index = round((0.5 * stats["average_score"]) + (0.3 * recovery_rate) + (0.2 * engagement_score), 2)
        recent_attempts_count = int((velocity_row or {}).get("recent_attempts") or 0)
        older_attempts_count = int((velocity_row or {}).get("older_attempts") or 0)
        if recent_attempts_count > older_attempts_count:
            velocity_label = "Improving"
        elif recent_attempts_count < older_attempts_count:
            velocity_label = "Slower"
        else:
            velocity_label = "Stable"
        bi_analytics = {
            "performance_index": performance_index,
            "risk_band": _risk_band(risk_score),
            "risk_score": round(risk_score, 2),
            "recovery_rate": round(recovery_rate, 2),
            "engagement_score": round(engagement_score, 2),
            "monthly_trend": monthly_trend,
            "emotion_distribution": emotion_distribution,
            "velocity_label": velocity_label,
        }
        negative_emotions = {"confused", "sad", "fear", "stressed", "angry", "disgust", "bored"}
        personalized_learning_plan = []
        for row in per_course_analysis:
            exam_score = _to_number(row.get("avg_exam_score"))
            support_sessions = _to_int(row.get("support_sessions"))
            latest_emotion = str(row.get("latest_emotion") or "").strip().lower()
            if exam_score >= 75 and latest_emotion not in negative_emotions:
                phase = "Advance"
                next_step = "Move to higher-level lecture + attempt challenge quiz."
            elif support_sessions >= 3 or latest_emotion in negative_emotions:
                phase = "Stabilize"
                next_step = "Use easy strategy mode and revise notes before next quiz."
            else:
                phase = "Practice"
                next_step = "Continue lecture flow and take one short MCQ check."
            personalized_learning_plan.append(
                {
                    "course_id": row["id"],
                    "course_title": row["title"],
                    "phase": phase,
                    "next_step": next_step,
                    "exam_score": round(exam_score, 2),
                }
            )
        return render_template(
            "student_dashboard.html",
            user=user,
            courses=courses,
            subscribed_course_ids=subscribed_course_ids,
            grouped_courses=grouped_courses,
            domain_order=domain_order,
            categories=categories,
            recent_attempts=recent_attempts,
            recent_insights=recent_insights,
            category_progress=category_progress,
            recent_mood=recent_mood,
            next_course=next_course,
            interview_courses=interview_courses,
            profile=profile,
            per_course_analysis=per_course_analysis,
            is_new_student=is_new_student,
            bi_analytics=bi_analytics,
            stats=stats,
            emotion_detection_quality=emotion_detection_quality,
            feedback_alignment=feedback_alignment,
            strategy_pipeline=strategy_pipeline,
            course_content_readiness=course_content_readiness,
            personalized_learning_plan=personalized_learning_plan,
            model_info=model_info,
            gemini_configured=app.config["GEMINI_CONFIGURED"],
        )

    @app.route("/subscribe-course/<int:course_id>", methods=["POST"])
    @role_required("student")
    def subscribe_course(course_id: int):
        user = current_user()
        db = get_db()
        course = db.execute("SELECT id, title FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("student_dashboard"))
        db.execute(
            """
            INSERT INTO course_subscriptions (user_id, course_id, price)
            VALUES (?, ?, 799)
            ON DUPLICATE KEY UPDATE price = VALUES(price)
            """,
            (user["id"], course_id),
        )
        db.commit()
        flash(f"Subscription activated for {course['title']}.", "success")
        return redirect(url_for("student_dashboard"))

    @app.route("/live-lectures")
    @role_required("student")
    def live_lecture_schedule():
        db = get_db()
        meetings = db.execute(
            """
            SELECT
                ll.*,
                c.title AS course_title,
                c.subject,
                c.category,
                u.username AS teacher_name
            FROM live_lectures ll
            JOIN courses c ON c.id = ll.course_id
            JOIN users u ON u.id = ll.teacher_id
            ORDER BY ll.meeting_date ASC, ll.start_time ASC, ll.id ASC
            """
        ).fetchall()
        return render_template("live_lectures.html", meetings=meetings)

    @app.route("/doubt-chat", methods=["GET", "POST"])
    @login_required
    def doubt_chat():
        user = current_user()
        db = get_db()
        if request.method == "POST":
            room = (request.form.get("room", "") or "").strip()
            message = (request.form.get("message", "") or "").strip()
            if not room or not message:
                flash("Please select a chat and type a message.", "error")
                return redirect(url_for("doubt_chat", room=room or None))

            course_id = None
            receiver_id = None
            if room.startswith("course:"):
                try:
                    course_id = int(room.split(":", 1)[1])
                except ValueError:
                    flash("Invalid course chat.", "error")
                    return redirect(url_for("doubt_chat"))
                course = db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
                if not course:
                    flash("Course chat not found.", "error")
                    return redirect(url_for("doubt_chat"))
                room_key = f"course:{course_id}"
                room_type = "course"
            elif room.startswith("direct:"):
                try:
                    receiver_id = int(room.split(":", 1)[1])
                except ValueError:
                    flash("Invalid direct chat.", "error")
                    return redirect(url_for("doubt_chat"))
                receiver = db.execute(
                    "SELECT id FROM users WHERE id = ? AND id <> ?",
                    (receiver_id, user["id"]),
                ).fetchone()
                if not receiver:
                    flash("Direct chat user not found.", "error")
                    return redirect(url_for("doubt_chat"))
                room_key = _direct_room_key(user["id"], receiver_id)
                room_type = "direct"
            else:
                flash("Invalid chat room.", "error")
                return redirect(url_for("doubt_chat"))

            db.execute(
                """
                INSERT INTO chat_messages
                (room_type, room_key, course_id, sender_id, receiver_id, message_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (room_type, room_key, course_id, user["id"], receiver_id, message),
            )
            db.commit()
            return redirect(url_for("doubt_chat", room=room))

        if user["role"] == "teacher":
            courses = db.execute(
                "SELECT id, title, subject, category FROM courses WHERE created_by = ? ORDER BY course_index, title",
                (user["id"],),
            ).fetchall()
        else:
            courses = db.execute(
                "SELECT id, title, subject, category FROM courses ORDER BY course_index, title"
            ).fetchall()

        if user["role"] == "student":
            direct_users = db.execute(
                """
                SELECT id, username, email, role
                FROM users
                WHERE role IN ('teacher', 'admin')
                ORDER BY role DESC, username
                """
            ).fetchall()
        elif user["role"] == "teacher":
            direct_users = db.execute(
                """
                SELECT id, username, email, role
                FROM users
                WHERE id <> ? AND role IN ('student', 'admin')
                ORDER BY role, username
                """,
                (user["id"],),
            ).fetchall()
        else:
            direct_users = db.execute(
                """
                SELECT id, username, email, role
                FROM users
                WHERE id <> ?
                ORDER BY role, username
                """,
                (user["id"],),
            ).fetchall()

        direct_students = [person for person in direct_users if person["role"] == "student"]
        direct_teachers = [person for person in direct_users if person["role"] == "teacher"]
        direct_admins = [person for person in direct_users if person["role"] == "admin"]
        direct_staff = direct_teachers + direct_admins
        selected_room = (request.args.get("room", "") or "").strip()
        if not selected_room and courses:
            selected_room = f"course:{courses[0]['id']}"
        elif not selected_room and direct_users:
            selected_room = f"direct:{direct_users[0]['id']}"

        active = {"type": "", "key": "", "title": "Doubt Discussion", "subtitle": "Select a course or direct chat."}
        messages = []
        if selected_room.startswith("course:"):
            try:
                selected_course_id = int(selected_room.split(":", 1)[1])
            except ValueError:
                selected_course_id = 0
            course = db.execute("SELECT * FROM courses WHERE id = ?", (selected_course_id,)).fetchone()
            if course:
                active = {
                    "type": "course",
                    "key": f"course:{course['id']}",
                    "title": course["title"],
                    "subtitle": f"{course['subject']} | Course group discussion",
                }
                messages = db.execute(
                    """
                    SELECT cm.*, u.username, u.role
                    FROM chat_messages cm
                    JOIN users u ON u.id = cm.sender_id
                    WHERE cm.room_key = ?
                    ORDER BY cm.created_at ASC, cm.id ASC
                    LIMIT 200
                    """,
                    (active["key"],),
                ).fetchall()
        elif selected_room.startswith("direct:"):
            try:
                other_user_id = int(selected_room.split(":", 1)[1])
            except ValueError:
                other_user_id = 0
            other_user = db.execute(
                "SELECT id, username, email, role FROM users WHERE id = ? AND id <> ?",
                (other_user_id, user["id"]),
            ).fetchone()
            if other_user:
                active = {
                    "type": "direct",
                    "key": _direct_room_key(user["id"], other_user["id"]),
                    "title": other_user["username"],
                    "subtitle": f"Direct chat with {other_user['role'].title()}",
                }
                messages = db.execute(
                    """
                    SELECT cm.*, u.username, u.role
                    FROM chat_messages cm
                    JOIN users u ON u.id = cm.sender_id
                    WHERE cm.room_key = ?
                    ORDER BY cm.created_at ASC, cm.id ASC
                    LIMIT 200
                    """,
                    (active["key"],),
                ).fetchall()

        return render_template(
            "doubt_chat.html",
            courses=courses,
            direct_users=direct_users,
            direct_students=direct_students,
            direct_teachers=direct_teachers,
            direct_admins=direct_admins,
            direct_staff=direct_staff,
            selected_room=selected_room,
            active=active,
            messages=messages,
        )

    @app.route("/doubt-chat/message/<int:message_id>/delete", methods=["POST"])
    @login_required
    def delete_chat_message(message_id: int):
        user = current_user()
        db = get_db()
        room = (request.form.get("room", "") or "").strip()
        message = db.execute(
            "SELECT id, sender_id FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if not message:
            flash("Message not found.", "error")
            return redirect(url_for("doubt_chat", room=room or None))
        if int(message["sender_id"]) != int(user["id"]) and user["role"] != "admin":
            flash("You can delete only your own message.", "error")
            return redirect(url_for("doubt_chat", room=room or None))
        db.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))
        db.commit()
        flash("Message deleted.", "success")
        return redirect(url_for("doubt_chat", room=room or None))

    @app.route("/teacher/live-meetings", methods=["GET", "POST"])
    @role_required("teacher", "admin")
    def teacher_live_meetings():
        user = current_user()
        db = get_db()
        if request.method == "POST":
            course_id = request.form.get("course_id", type=int)
            title = (request.form.get("title", "") or "").strip()
            meeting_date = (request.form.get("meeting_date", "") or "").strip()
            start_time = (request.form.get("start_time", "") or "").strip()
            end_time = (request.form.get("end_time", "") or "").strip() or None
            meet_link = (request.form.get("meet_link", "") or "").strip()
            notes = (request.form.get("notes", "") or "").strip()
            if not all([course_id, title, meeting_date, start_time, meet_link]):
                flash("Please fill course, title, date, start time, and Google Meet link.", "error")
                return redirect(url_for("teacher_live_meetings"))
            if not meet_link.startswith(("https://meet.google.com/", "http://meet.google.com/")):
                flash("Please enter a valid Google Meet link.", "error")
                return redirect(url_for("teacher_live_meetings"))
            if user["role"] == "teacher":
                course = db.execute(
                    "SELECT id FROM courses WHERE id = ? AND created_by = ?",
                    (course_id, user["id"]),
                ).fetchone()
            else:
                course = db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not course:
                flash("Course not found or permission denied.", "error")
                return redirect(url_for("teacher_live_meetings"))
            db.execute(
                """
                INSERT INTO live_lectures
                (course_id, teacher_id, title, meeting_date, start_time, end_time, meet_link, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (course_id, user["id"], title, meeting_date, start_time, end_time, meet_link, notes),
            )
            db.commit()
            flash("Live lecture meeting added successfully.", "success")
            return redirect(url_for("teacher_live_meetings"))

        if user["role"] == "teacher":
            courses = db.execute(
                "SELECT id, title, subject FROM courses WHERE created_by = ? ORDER BY course_index, title",
                (user["id"],),
            ).fetchall()
            meetings = db.execute(
                """
                SELECT ll.*, c.title AS course_title, c.subject
                FROM live_lectures ll
                JOIN courses c ON c.id = ll.course_id
                WHERE ll.teacher_id = ?
                ORDER BY ll.meeting_date ASC, ll.start_time ASC, ll.id ASC
                """,
                (user["id"],),
            ).fetchall()
        else:
            courses = db.execute("SELECT id, title, subject FROM courses ORDER BY course_index, title").fetchall()
            meetings = db.execute(
                """
                SELECT ll.*, c.title AS course_title, c.subject
                FROM live_lectures ll
                JOIN courses c ON c.id = ll.course_id
                ORDER BY ll.meeting_date ASC, ll.start_time ASC, ll.id ASC
                """
            ).fetchall()
        return render_template("teacher_live_meetings.html", courses=courses, meetings=meetings)

    @app.route("/teacher/subscription-catalog")
    @role_required("teacher", "admin")
    def teacher_subscription_catalog():
        user = current_user()
        db = get_db()
        owner_filter = ""
        params: list[Any] = []
        if user["role"] == "teacher":
            owner_filter = "WHERE c.created_by = ?"
            params.append(user["id"])

        course_rows = db.execute(
            f"""
            SELECT
                c.id,
                c.title,
                c.category,
                c.subject,
                COUNT(DISTINCT cs.user_id) AS subscriber_count,
                COALESCE(SUM(cs.price), 0) AS total_amount,
                COUNT(DISTINCT a.id) AS exam_attempts,
                COALESCE(ROUND(AVG(a.score * 100.0 / a.total_questions), 0), 0) AS average_score
            FROM courses c
            LEFT JOIN course_subscriptions cs ON cs.course_id = c.id
            LEFT JOIN exam_attempts a ON a.course_id = c.id
            {owner_filter}
            GROUP BY c.id, c.title, c.category, c.subject
            ORDER BY c.category, c.course_index, c.title
            """,
            params,
        ).fetchall()

        subscriber_filter = ""
        subscriber_params: list[Any] = []
        if user["role"] == "teacher":
            subscriber_filter = "WHERE c.created_by = ?"
            subscriber_params.append(user["id"])
        subscriber_rows = db.execute(
            f"""
            SELECT
                c.id AS course_id,
                c.title AS course_title,
                c.category,
                c.subject,
                u.username,
                u.email,
                cs.price,
                cs.created_at,
                COUNT(a.id) AS exam_attempts,
                COALESCE(ROUND(AVG(a.score * 100.0 / a.total_questions), 0), 0) AS average_score
            FROM courses c
            JOIN course_subscriptions cs ON cs.course_id = c.id
            JOIN users u ON u.id = cs.user_id
            LEFT JOIN exam_attempts a ON a.course_id = c.id AND a.user_id = u.id
            {subscriber_filter}
            GROUP BY c.id, c.title, c.category, c.subject, u.id, u.username, u.email, cs.price, cs.created_at
            ORDER BY c.category, c.title, u.username
            """,
            subscriber_params,
        ).fetchall()

        return render_template(
            "teacher_subscription_catalog.html",
            course_rows=course_rows,
            subscriber_rows=subscriber_rows,
        )

    @app.route("/teacher")
    @role_required("teacher", "admin")
    def teacher_dashboard():
        user = current_user()
        db = get_db()
        model_info = latest_model_info()
        courses = db.execute(
            """
            SELECT c.*,
                   (SELECT COUNT(*) FROM exam_attempts a WHERE a.course_id = c.id) AS attempt_count,
                   (SELECT COUNT(*) FROM session_insights s WHERE s.course_id = c.id) AS support_count,
                   (
                       SELECT COALESCE(ROUND(AVG(a.score * 100.0 / a.total_questions), 0), 0)
                       FROM exam_attempts a
                       WHERE a.course_id = c.id
                   ) AS average_score
            FROM courses c
            WHERE c.created_by = ?
            ORDER BY c.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        recent_support = db.execute(
            """
            SELECT s.*, c.title AS course_title, u.username AS student_name
            FROM session_insights s
            JOIN courses c ON c.id = s.course_id
            JOIN users u ON u.id = s.user_id
            WHERE c.created_by = ?
            ORDER BY s.created_at DESC
            LIMIT 6
            """,
            (user["id"],),
        ).fetchall()
        performance_by_category = db.execute(
            """
            SELECT c.category,
                   COUNT(DISTINCT c.id) AS course_count,
                   (
                       SELECT COUNT(*)
                       FROM exam_attempts a
                       JOIN courses c2 ON c2.id = a.course_id
                       WHERE c2.created_by = ? AND c2.category = c.category
                   ) AS attempts,
                   (
                       SELECT COUNT(*)
                       FROM session_insights s
                       JOIN courses c2 ON c2.id = s.course_id
                       WHERE c2.created_by = ? AND c2.category = c.category
                   ) AS support_events,
                   (
                       SELECT COALESCE(ROUND(AVG(a.score * 100.0 / a.total_questions), 0), 0)
                       FROM exam_attempts a
                       JOIN courses c2 ON c2.id = a.course_id
                       WHERE c2.created_by = ? AND c2.category = c.category
                   ) AS average_score
            FROM courses c
            WHERE c.created_by = ?
            GROUP BY c.category
            ORDER BY c.category
            """,
            (user["id"], user["id"], user["id"], user["id"]),
        ).fetchall()
        strategy_effectiveness = db.execute(
            """
            SELECT
                sr.strategy_code,
                COUNT(*) AS used_count,
                COALESCE(
                    ROUND(SUM(CASE WHEN io.outcome_status = 'improved' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(io.id), 0), 2),
                    0
                ) AS recovery_rate
            FROM strategy_recommendations sr
            LEFT JOIN intervention_outcomes io ON io.recommendation_id = sr.id
            JOIN courses c ON c.id = sr.course_id
            WHERE c.created_by = ?
            GROUP BY sr.strategy_code
            ORDER BY recovery_rate DESC, used_count DESC
            LIMIT 5
            """,
            (user["id"],),
        ).fetchall()
        course_delivery_health = db.execute(
            """
            SELECT
                c.id,
                c.title,
                c.category,
                COUNT(DISTINCT cl.id) AS lecture_count,
                MAX(CASE WHEN ca.id IS NOT NULL THEN 1 ELSE 0 END) AS ai_asset_ready,
                COALESCE(MAX(JSON_LENGTH(ca.quiz_json)), 0) AS quiz_items,
                MAX(CASE WHEN ca.pdf_file IS NOT NULL AND ca.pdf_file <> '' THEN 1 ELSE 0 END) AS notes_ready
            FROM courses c
            LEFT JOIN course_lectures cl ON cl.course_id = c.id
            LEFT JOIN course_ai_assets ca ON ca.course_id = c.id
            WHERE c.created_by = ?
            GROUP BY c.id, c.title, c.category
            ORDER BY c.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        at_risk_students = db.execute(
            """
            SELECT
                u.id,
                u.username,
                COUNT(s.id) AS support_events,
                SUM(CASE WHEN s.emotion IN ('confused', 'sad', 'fear', 'stressed', 'angry', 'disgust', 'bored') THEN 1 ELSE 0 END) AS negative_events,
                COALESCE(ROUND(AVG(e.score * 100.0 / e.total_questions), 0), 0) AS avg_score
            FROM users u
            JOIN session_insights s ON s.user_id = u.id
            JOIN courses c ON c.id = s.course_id
            LEFT JOIN exam_attempts e ON e.user_id = u.id AND e.course_id = c.id
            WHERE c.created_by = ? AND u.role = 'student'
            GROUP BY u.id, u.username
            ORDER BY negative_events DESC, support_events DESC
            LIMIT 8
            """,
            (user["id"],),
        ).fetchall()
        emotion_reliability = db.execute(
            """
            SELECT
                c.id,
                c.title,
                COUNT(ev.id) AS event_count,
                COALESCE(ROUND(AVG(ev.confidence) * 100.0, 2), 0) AS avg_confidence,
                COALESCE(
                    ROUND(SUM(CASE WHEN ev.quality_state = 'valid' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(ev.id), 0), 2),
                    0
                ) AS valid_rate
            FROM courses c
            LEFT JOIN emotion_events ev ON ev.course_id = c.id
            WHERE c.created_by = ?
            GROUP BY c.id, c.title
            ORDER BY event_count DESC, c.title
            LIMIT 8
            """,
            (user["id"],),
        ).fetchall()
        student_count = db.execute(
            "SELECT COUNT(*) AS total FROM users WHERE role = 'student'"
        ).fetchone()["total"]
        stats = {
            "course_count": len(courses),
            "student_count": student_count,
            "attempt_count": sum(course["attempt_count"] for course in courses),
            "support_alerts": sum(course["support_count"] for course in courses),
            "ai_ready_courses": sum(1 for item in course_delivery_health if item["ai_asset_ready"]),
        }
        return render_template(
            "teacher_dashboard.html",
            user=user,
            courses=courses,
            recent_support=recent_support,
            performance_by_category=performance_by_category,
            strategy_effectiveness=strategy_effectiveness,
            course_delivery_health=course_delivery_health,
            at_risk_students=at_risk_students,
            emotion_reliability=emotion_reliability,
            stats=stats,
            model_info=model_info,
            gemini_configured=app.config["GEMINI_CONFIGURED"],
        )

    @app.route("/admin")
    @role_required("admin")
    def admin_dashboard():
        db = get_db()
        model_info = latest_model_info()
        users = db.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 8").fetchall()
        courses = db.execute(
            """
            SELECT c.*, u.username AS teacher_name
            FROM courses c
            LEFT JOIN users u ON u.id = c.created_by
            ORDER BY c.created_at DESC
            LIMIT 8
            """
        ).fetchall()
        attempts = db.execute(
            """
            SELECT a.*, u.username, c.title AS course_title
            FROM exam_attempts a
            JOIN users u ON u.id = a.user_id
            LEFT JOIN courses c ON c.id = a.course_id
            ORDER BY a.created_at DESC
            LIMIT 8
            """
        ).fetchall()
        support_feed = db.execute(
            """
            SELECT s.*, u.username, c.title AS course_title
            FROM session_insights s
            JOIN users u ON u.id = s.user_id
            JOIN courses c ON c.id = s.course_id
            ORDER BY s.created_at DESC
            LIMIT 8
            """
        ).fetchall()
        category_overview = db.execute(
            """
            SELECT c.category,
                   COUNT(DISTINCT c.id) AS course_count,
                   (
                       SELECT COUNT(*)
                       FROM exam_attempts a
                       JOIN courses c2 ON c2.id = a.course_id
                       WHERE c2.category = c.category
                   ) AS attempts,
                   (
                       SELECT COUNT(*)
                       FROM session_insights s
                       JOIN courses c2 ON c2.id = s.course_id
                       WHERE c2.category = c.category
                   ) AS support_events,
                   (
                       SELECT COALESCE(ROUND(AVG(a.score * 100.0 / a.total_questions), 0), 0)
                       FROM exam_attempts a
                       JOIN courses c2 ON c2.id = a.course_id
                       WHERE c2.category = c.category
                   ) AS average_score
            FROM courses c
            GROUP BY c.category
            ORDER BY c.category
            """
        ).fetchall()
        counts = {
            "users": db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"],
            "students": db.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'student'").fetchone()["total"],
            "teachers": db.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'teacher'").fetchone()["total"],
            "courses": db.execute("SELECT COUNT(*) AS total FROM courses").fetchone()["total"],
            "attempts": db.execute("SELECT COUNT(*) AS total FROM exam_attempts").fetchone()["total"],
            "insights": db.execute("SELECT COUNT(*) AS total FROM session_insights").fetchone()["total"],
        }
        recovery_overview = db.execute(
            """
            SELECT
                COUNT(*) AS total_outcomes,
                SUM(CASE WHEN outcome_status = 'improved' THEN 1 ELSE 0 END) AS improved_outcomes,
                COALESCE(
                    ROUND(SUM(CASE WHEN outcome_status = 'improved' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2),
                    0
                ) AS recovery_rate
            FROM intervention_outcomes
            """
        ).fetchone()
        top_strategies = db.execute(
            """
            SELECT strategy_code, COUNT(*) AS used_count
            FROM strategy_recommendations
            GROUP BY strategy_code
            ORDER BY used_count DESC
            LIMIT 5
            """
        ).fetchall()
        model_quality = db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM emotion_events) AS emotion_events,
                (SELECT COALESCE(ROUND(AVG(confidence) * 100.0, 2), 0) FROM emotion_events) AS avg_confidence,
                (SELECT COALESCE(ROUND(SUM(CASE WHEN quality_state = 'valid' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2), 0) FROM emotion_events) AS valid_signal_rate,
                (SELECT COUNT(*) FROM emotion_feedback) AS feedback_samples,
                (SELECT COALESCE(ROUND(SUM(CASE WHEN predicted_emotion = actual_emotion THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2), 0) FROM emotion_feedback) AS feedback_match_rate
            """
        ).fetchone()
        platform_content_health = db.execute(
            """
            SELECT
                COUNT(*) AS total_courses,
                SUM(CASE WHEN lecture_count > 0 THEN 1 ELSE 0 END) AS courses_with_lectures,
                SUM(CASE WHEN ai_asset_ready = 1 THEN 1 ELSE 0 END) AS ai_ready_courses,
                SUM(CASE WHEN notes_ready = 1 THEN 1 ELSE 0 END) AS notes_ready_courses
            FROM (
                SELECT
                    c.id,
                    COUNT(DISTINCT cl.id) AS lecture_count,
                    MAX(CASE WHEN ca.id IS NOT NULL THEN 1 ELSE 0 END) AS ai_asset_ready,
                    MAX(CASE WHEN ca.pdf_file IS NOT NULL AND ca.pdf_file <> '' THEN 1 ELSE 0 END) AS notes_ready
                FROM courses c
                LEFT JOIN course_lectures cl ON cl.course_id = c.id
                LEFT JOIN course_ai_assets ca ON ca.course_id = c.id
                GROUP BY c.id
            ) summary
            """
        ).fetchone()
        provider_mix = db.execute(
            """
            SELECT
                analysis_provider,
                COUNT(*) AS total
            FROM session_insights
            GROUP BY analysis_provider
            ORDER BY total DESC
            LIMIT 6
            """
        ).fetchall()
        highest_risk_students = db.execute(
            """
            SELECT
                u.id,
                u.username,
                COALESCE(sp.risk_score, 0) AS risk_score,
                COALESCE(sp.recovery_rate, 0) AS recovery_rate,
                COALESCE(sp.engagement_score, 0) AS engagement_score
            FROM student_profiles sp
            JOIN users u ON u.id = sp.user_id
            WHERE u.role = 'student'
            ORDER BY sp.risk_score DESC, sp.updated_at DESC
            LIMIT 8
            """
        ).fetchall()
        students = db.execute(
            "SELECT id, username, email FROM users WHERE role = 'student' ORDER BY username"
        ).fetchall()
        selected_student_id = request.args.get("student_id", type=int)
        if selected_student_id is None and students:
            selected_student_id = students[0]["id"]
        selected_student = None
        student_overview = {
            "stats": {"courses_enrolled": 0, "exam_attempts": 0, "average_score": 0, "support_sessions": 0},
            "recent_attempts": [],
            "recent_insights": [],
            "per_course_analysis": [],
            "category_progress": [],
            "bi_analytics": {
                "performance_index": 0,
                "risk_band": "N/A",
                "risk_score": 0,
                "recovery_rate": 0,
                "engagement_score": 0,
                "monthly_trend": [],
                "emotion_distribution": [],
                "velocity_label": "N/A",
            },
        }
        if selected_student_id:
            selected_student = db.execute(
                "SELECT id, username, email FROM users WHERE id = ? AND role = 'student'",
                (selected_student_id,),
            ).fetchone()
        if selected_student:
            courses_all = db.execute("SELECT * FROM courses ORDER BY category, course_index, title").fetchall()
            attempt_stats = db.execute(
                """
                SELECT COUNT(*) AS attempts,
                       COALESCE(ROUND(AVG(score * 100.0 / total_questions), 0), 0) AS average_score
                FROM exam_attempts
                WHERE user_id = ?
                """,
                (selected_student["id"],),
            ).fetchone()
            recent_attempts = db.execute(
                """
                SELECT a.*, c.title AS course_title
                FROM exam_attempts a
                LEFT JOIN courses c ON c.id = a.course_id
                WHERE a.user_id = ?
                ORDER BY a.created_at DESC
                LIMIT 8
                """,
                (selected_student["id"],),
            ).fetchall()
            recent_insights = db.execute(
                """
                SELECT s.*, c.title AS course_title
                FROM session_insights s
                JOIN courses c ON c.id = s.course_id
                WHERE s.user_id = ?
                ORDER BY s.created_at DESC
                LIMIT 8
                """,
                (selected_student["id"],),
            ).fetchall()
            category_progress = db.execute(
                """
                SELECT a.category,
                       COUNT(*) AS attempts,
                       COALESCE(ROUND(AVG(a.score * 100.0 / a.total_questions), 0), 0) AS average_score,
                       MAX(a.created_at) AS latest_attempt
                FROM exam_attempts a
                WHERE a.user_id = ?
                GROUP BY a.category
                ORDER BY average_score DESC, attempts DESC
                """,
                (selected_student["id"],),
            ).fetchall()
            support_count = db.execute(
                "SELECT COUNT(*) AS total FROM session_insights WHERE user_id = ?",
                (selected_student["id"],),
            ).fetchone()["total"]
            profile = db.execute(
                """
                SELECT stability_score, engagement_score, risk_score, recovery_rate, recommended_pacing, updated_at
                FROM student_profiles
                WHERE user_id = ?
                """,
                (selected_student["id"],),
            ).fetchone()
            per_course_analysis = db.execute(
                """
                SELECT
                    c.id,
                    c.title,
                    c.category,
                    c.subject,
                    c.course_index,
                    COALESCE(ex.attempts, 0) AS exam_attempts,
                    COALESCE(ex.avg_score, 0) AS avg_exam_score,
                    COALESCE(si.sessions, 0) AS support_sessions,
                    COALESCE(si.last_emotion, 'N/A') AS latest_emotion,
                    COALESCE(sr.top_strategy, 'N/A') AS top_strategy,
                    COALESCE(rc.recovery_rate, 0) AS recovery_rate
                FROM courses c
                LEFT JOIN (
                    SELECT
                        course_id,
                        COUNT(*) AS attempts,
                        ROUND(AVG(score * 100.0 / total_questions), 0) AS avg_score
                    FROM exam_attempts
                    WHERE user_id = ?
                    GROUP BY course_id
                ) ex ON ex.course_id = c.id
                LEFT JOIN (
                    SELECT
                        course_id,
                        COUNT(*) AS sessions,
                        SUBSTRING_INDEX(GROUP_CONCAT(emotion ORDER BY created_at DESC, id DESC), ',', 1) AS last_emotion
                    FROM session_insights
                    WHERE user_id = ?
                    GROUP BY course_id
                ) si ON si.course_id = c.id
                LEFT JOIN (
                    SELECT
                        course_id,
                        SUBSTRING_INDEX(GROUP_CONCAT(strategy_code ORDER BY total DESC SEPARATOR ','), ',', 1) AS top_strategy
                    FROM (
                        SELECT course_id, strategy_code, COUNT(*) AS total
                        FROM strategy_recommendations
                        WHERE user_id = ?
                        GROUP BY course_id, strategy_code
                    ) grouped
                    GROUP BY course_id
                ) sr ON sr.course_id = c.id
                LEFT JOIN (
                    SELECT
                        course_id,
                        ROUND(SUM(CASE WHEN outcome_status = 'improved' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS recovery_rate
                    FROM intervention_outcomes
                    WHERE user_id = ?
                    GROUP BY course_id
                ) rc ON rc.course_id = c.id
                ORDER BY c.category, c.course_index, c.title
                """,
                (selected_student["id"], selected_student["id"], selected_student["id"], selected_student["id"]),
            ).fetchall()
            monthly_trend_raw = db.execute(
                """
                SELECT DATE_FORMAT(created_at, '%%Y-%%m') AS period,
                       ROUND(AVG(score * 100.0 / total_questions), 2) AS avg_score,
                       COUNT(*) AS attempts
                FROM exam_attempts
                WHERE user_id = ?
                GROUP BY DATE_FORMAT(created_at, '%%Y-%%m')
                ORDER BY period DESC
                LIMIT 6
                """,
                (selected_student["id"],),
            ).fetchall()
            monthly_trend = list(reversed(monthly_trend_raw))
            emotion_distribution = db.execute(
                """
                SELECT emotion, COUNT(*) AS total
                FROM session_insights
                WHERE user_id = ?
                GROUP BY emotion
                ORDER BY total DESC, emotion
                """,
                (selected_student["id"],),
            ).fetchall()
            velocity_row = db.execute(
                """
                SELECT
                    SUM(CASE WHEN created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) AS recent_attempts,
                    SUM(CASE WHEN created_at < DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) AS older_attempts
                FROM exam_attempts
                WHERE user_id = ?
                """,
                (selected_student["id"],),
            ).fetchone()
            recovery_rate = _to_number((profile or {}).get("recovery_rate")) if profile else 0.0
            engagement_score = _to_number((profile or {}).get("engagement_score")) if profile else 0.0
            risk_score = _to_number((profile or {}).get("risk_score")) if profile else 50.0
            performance_index = round(
                (0.5 * int(attempt_stats["average_score"] or 0)) + (0.3 * recovery_rate) + (0.2 * engagement_score),
                2,
            )
            recent_attempts_count = int((velocity_row or {}).get("recent_attempts") or 0)
            older_attempts_count = int((velocity_row or {}).get("older_attempts") or 0)
            if recent_attempts_count > older_attempts_count:
                velocity_label = "Improving"
            elif recent_attempts_count < older_attempts_count:
                velocity_label = "Slower"
            else:
                velocity_label = "Stable"
            student_overview = {
                "stats": {
                    "courses_enrolled": len(courses_all),
                    "exam_attempts": attempt_stats["attempts"] or 0,
                    "average_score": int(attempt_stats["average_score"] or 0),
                    "support_sessions": support_count or 0,
                },
                "recent_attempts": recent_attempts,
                "recent_insights": recent_insights,
                "per_course_analysis": per_course_analysis,
                "category_progress": category_progress,
                "bi_analytics": {
                    "performance_index": performance_index,
                    "risk_band": _risk_band(risk_score),
                    "risk_score": round(risk_score, 2),
                    "recovery_rate": round(recovery_rate, 2),
                    "engagement_score": round(engagement_score, 2),
                    "monthly_trend": monthly_trend,
                    "emotion_distribution": emotion_distribution,
                    "velocity_label": velocity_label,
                },
            }
        return render_template(
            "admin_dashboard.html",
            users=users,
            courses=courses,
            attempts=attempts,
            support_feed=support_feed,
            category_overview=category_overview,
            counts=counts,
            recovery_overview=recovery_overview,
            top_strategies=top_strategies,
            model_quality=model_quality,
            platform_content_health=platform_content_health,
            provider_mix=provider_mix,
            highest_risk_students=highest_risk_students,
            students=students,
            selected_student=selected_student,
            student_overview=student_overview,
            model_info=model_info,
            gemini_configured=app.config["GEMINI_CONFIGURED"],
        )
