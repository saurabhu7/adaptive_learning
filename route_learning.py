from __future__ import annotations

import json
import random

from flask import flash, redirect, render_template, request, url_for

from auth_utils import current_user, get_db, latest_model_info, login_required, role_required
from learning_assets import build_course_assets, build_topic_summary_asset
from learning_logic import (
    analyze_frame_emotion,
    build_guidance_payload,
    build_profile_snapshot,
    calibrate_emotion_with_feedback,
    classify_outcome,
    derive_emotion_state,
    estimate_recovery_seconds,
    realtime_supported,
)


def _student_has_subscription(user_id: int, course_id: int) -> bool:
    row = get_db().execute(
        "SELECT id FROM course_subscriptions WHERE user_id = ? AND course_id = ?",
        (user_id, course_id),
    ).fetchone()
    return bool(row)


def _fetch_live_course_metrics(db, user_id: int, course_id: int) -> dict:
    overview = db.execute(
        """
        SELECT
            COUNT(*) AS total_events,
            COALESCE(ROUND(AVG(confidence) * 100.0, 2), 0) AS avg_confidence,
            COALESCE(
                ROUND(SUM(CASE WHEN quality_state = 'valid' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2),
                0
            ) AS valid_rate
        FROM emotion_events
        WHERE user_id = ? AND course_id = ?
        """,
        (user_id, course_id),
    ).fetchone()
    emotion_mix = db.execute(
        """
        SELECT emotion_smoothed AS emotion, COUNT(*) AS total
        FROM emotion_events
        WHERE user_id = ? AND course_id = ?
        GROUP BY emotion_smoothed
        ORDER BY total DESC, emotion_smoothed
        LIMIT 6
        """,
        (user_id, course_id),
    ).fetchall()
    strategy_pipeline = db.execute(
        """
        SELECT
            COUNT(sr.id) AS strategy_count,
            SUM(CASE WHEN io.outcome_status = 'improved' THEN 1 ELSE 0 END) AS improved_count,
            COALESCE(
                ROUND(SUM(CASE WHEN io.outcome_status = 'improved' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(io.id), 0), 2),
                0
            ) AS recovery_rate
        FROM strategy_recommendations sr
        LEFT JOIN intervention_outcomes io ON io.recommendation_id = sr.id
        WHERE sr.user_id = ? AND sr.course_id = ?
        """,
        (user_id, course_id),
    ).fetchone()
    exam_stats = db.execute(
        """
        SELECT
            COUNT(*) AS attempts,
            COALESCE(ROUND(AVG(score * 100.0 / total_questions), 2), 0) AS avg_score
        FROM exam_attempts
        WHERE user_id = ? AND course_id = ?
        """,
        (user_id, course_id),
    ).fetchone()
    latest_feed = db.execute(
        """
        SELECT emotion, strategy_title, student_message, created_at
        FROM session_insights
        WHERE user_id = ? AND course_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 5
        """,
        (user_id, course_id),
    ).fetchall()
    return {
        "overview": overview,
        "emotion_mix": emotion_mix,
        "strategy_pipeline": strategy_pipeline,
        "exam_stats": exam_stats,
        "latest_feed": latest_feed,
    }


def register_learning_routes(app) -> None:
    @app.route("/categories")
    @role_required("student")
    def categories():
        categories_data = get_db().execute(
            "SELECT category, COUNT(*) AS total FROM courses GROUP BY category ORDER BY category"
        ).fetchall()
        return render_template("home.html", categories=categories_data)

    @app.route("/check-mood/<category>")
    @role_required("student")
    def check_mood(category: str):
        return render_template("check_mood.html", category=category)

    @app.route("/process-mood", methods=["POST"])
    @role_required("student")
    def process_mood():
        user = current_user()
        category = request.form.get("category", "").strip()
        mood = request.form.get("mood", "").strip().lower()
        if mood not in {"happy", "focused", "neutral", "sad", "stressed"}:
            mood = random.choice(["neutral", "focused", "happy"])
        get_db().execute(
            "INSERT INTO emotions (user_id, category, mood) VALUES (?, ?, ?)",
            (user["id"], category, mood),
        )
        get_db().commit()
        return redirect(url_for("suggest_courses", category=category, mood=mood))

    @app.route("/suggest/<category>/<mood>")
    @role_required("student")
    def suggest_courses(category: str, mood: str):
        db = get_db()
        query = (
            "SELECT * FROM courses WHERE category = ? ORDER BY course_index ASC, title ASC"
            if mood in {"sad", "stressed"}
            else "SELECT * FROM courses WHERE category = ? ORDER BY course_index DESC, title ASC"
        )
        courses = db.execute(query, (category,)).fetchall()
        return render_template("suggestions.html", courses=courses, category=category, mood=mood)

    @app.route("/learn")
    @role_required("student")
    def learn_redirect():
        first_course = get_db().execute("SELECT id FROM courses ORDER BY course_index, title LIMIT 1").fetchone()
        if not first_course:
            flash("No courses are available yet.", "warning")
            return redirect(url_for("student_dashboard"))
        return redirect(url_for("learn_course", course_id=first_course["id"]))

    @app.route("/learn/<int:course_id>")
    @login_required
    def learn_course(course_id: int):
        db = get_db()
        course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("dashboard"))
        user = current_user()
        if user["role"] == "student" and not _student_has_subscription(user["id"], course_id):
            flash("Please subscribe to this course first. Course price is ₹799.", "warning")
            return redirect(url_for("student_dashboard"))
        lectures = db.execute(
            "SELECT * FROM course_lectures WHERE course_id = ? ORDER BY lecture_index ASC, id ASC",
            (course_id,),
        ).fetchall()
        if not lectures and course.get("youtube_url"):
            lectures = [
                {
                    "id": 0,
                    "course_id": course_id,
                    "lecture_index": 1,
                    "title": f"{course['title']} - Lecture 1",
                    "video_url": course["youtube_url"],
                }
            ]
        selected_lecture_id = request.args.get("lecture_id", type=int)
        selected_lecture = None
        if selected_lecture_id:
            selected_lecture = next((lecture for lecture in lectures if lecture["id"] == selected_lecture_id), None)
        if selected_lecture is None and lectures:
            selected_lecture = lectures[0]
        if selected_lecture:
            course = dict(course)
            course["youtube_url"] = selected_lecture["video_url"]
        model_info = latest_model_info()
        live_metrics = _fetch_live_course_metrics(db, user["id"], course_id)
        content_readiness = db.execute(
            """
            SELECT
                COUNT(DISTINCT cl.id) AS lecture_count,
                MAX(CASE WHEN ca.id IS NOT NULL THEN 1 ELSE 0 END) AS ai_asset_ready,
                COALESCE(MAX(JSON_LENGTH(ca.quiz_json)), 0) AS quiz_items,
                MAX(CASE WHEN ca.pdf_file IS NOT NULL AND ca.pdf_file <> '' THEN 1 ELSE 0 END) AS notes_ready
            FROM courses c
            LEFT JOIN course_lectures cl ON cl.course_id = c.id
            LEFT JOIN course_ai_assets ca ON ca.course_id = c.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (course_id,),
        ).fetchone()
        live_quiz_items = []
        latest_asset = db.execute(
            """
            SELECT quiz_json
            FROM course_ai_assets
            WHERE course_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        if latest_asset and latest_asset.get("quiz_json"):
            try:
                parsed_quiz = json.loads(latest_asset["quiz_json"])
                if isinstance(parsed_quiz, list):
                    live_quiz_items = [item for item in parsed_quiz if isinstance(item, dict)]
            except json.JSONDecodeError:
                live_quiz_items = []
        return render_template(
            "learn_interactive.html",
            course=course,
            lectures=lectures,
            selected_lecture=selected_lecture,
            live_metrics=live_metrics,
            content_readiness=content_readiness,
            live_quiz_items=live_quiz_items,
            realtime_supported=realtime_supported(model_info),
            gemini_configured=app.config["GEMINI_CONFIGURED"],
        )

    @app.route("/api/live-metrics/<int:course_id>")
    @role_required("student")
    def live_metrics(course_id: int):
        user = current_user()
        db = get_db()
        course = db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            return {"ok": False, "message": "Course not found."}, 404
        payload = _fetch_live_course_metrics(db, user["id"], course_id)
        return {"ok": True, "metrics": payload}

    @app.route("/course/<int:course_id>/content")
    @role_required("student")
    def course_content(course_id: int):
        db = get_db()
        course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("student_dashboard"))
        user = current_user()
        if user["role"] == "student" and not _student_has_subscription(user["id"], course_id):
            flash("Please subscribe to this course first. Course price is ₹799.", "warning")
            return redirect(url_for("student_dashboard"))
        lectures = db.execute(
            "SELECT * FROM course_lectures WHERE course_id = ? ORDER BY lecture_index ASC, id ASC",
            (course_id,),
        ).fetchall()
        if not lectures and course.get("youtube_url"):
            lectures = [
                {
                    "id": 0,
                    "course_id": course_id,
                    "lecture_index": 1,
                    "title": f"{course['title']} - Lecture 1",
                    "video_url": course["youtube_url"],
                }
            ]
        ai_asset = db.execute(
            """
            SELECT *
            FROM course_ai_assets
            WHERE course_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        return render_template(
            "course_content.html",
            course=course,
            lectures=lectures,
            ai_asset=ai_asset,
        )

    @app.route("/learn/<int:course_id>/download-notes")
    @role_required("student", "teacher", "admin")
    def download_course_notes(course_id: int):
        user = current_user()
        db = get_db()
        course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("dashboard"))
        if user["role"] == "student" and not _student_has_subscription(user["id"], course_id):
            flash("Please subscribe to this course first. Course price is ₹799.", "warning")
            return redirect(url_for("student_dashboard"))

        latest_asset = db.execute(
            """
            SELECT *
            FROM course_ai_assets
            WHERE course_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        force_refresh = request.args.get("refresh", "0").strip() == "1"
        if latest_asset and latest_asset.get("pdf_file") and not force_refresh:
            return redirect(url_for("static", filename=f"uploads/notes/{latest_asset['pdf_file']}"))

        course_payload = dict(course)
        first_lecture = db.execute(
            """
            SELECT video_url
            FROM course_lectures
            WHERE course_id = ?
            ORDER BY lecture_index ASC, id ASC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        if first_lecture and first_lecture.get("video_url"):
            # Prefer a real lecture video URL so transcript extraction is reliable.
            course_payload["youtube_url"] = first_lecture["video_url"]

        payload = build_course_assets(course_payload)
        if not payload.get("ok"):
            flash(f"Could not generate notes: {payload.get('error', 'unknown error')}", "error")
            return redirect(url_for("learn_course", course_id=course_id))

        quiz_json_value = payload.get("quiz_json") or "[]"
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
                    quiz_json_value,
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
                    course_id,
                    generated_by,
                    summary,
                    notes_markdown,
                    quiz_json,
                    provider,
                    transcript_source,
                    pdf_file
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    user["id"],
                    payload["summary"],
                    payload["notes_markdown"],
                    quiz_json_value,
                    payload["provider"],
                    payload["transcript_source"],
                    payload["pdf_file"],
                ),
            )
        db.commit()
        return redirect(url_for("static", filename=f"uploads/notes/{payload['pdf_file']}"))

    @app.route("/api/session-emotion", methods=["POST"])
    @role_required("student")
    def session_emotion():
        user = current_user()
        course_id = request.form.get("course_id", type=int)
        frame_data = request.form.get("frame", "")
        db = get_db()
        course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            return {"ok": False, "message": "Course not found."}, 404
        emotion, confidence, analysis_provider = analyze_frame_emotion(frame_data)
        feedback_rows = db.execute(
            """
            SELECT predicted_emotion, actual_emotion, COUNT(*) AS total
            FROM emotion_feedback
            WHERE user_id = ?
            GROUP BY predicted_emotion, actual_emotion
            """,
            (user["id"],),
        ).fetchall()
        emotion, confidence = calibrate_emotion_with_feedback(emotion, confidence, feedback_rows)
        recent_events = db.execute(
            """
            SELECT emotion_raw, emotion_smoothed, confidence, created_at
            FROM emotion_events
            WHERE user_id = ? AND course_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 12
            """,
            (user["id"], course_id),
        ).fetchall()
        emotion_state = derive_emotion_state(emotion, confidence, recent_events)
        recovery_stats = db.execute(
            """
            SELECT
                COALESCE(ROUND(SUM(CASE WHEN outcome_status = 'improved' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2), 0) AS recovery_rate
            FROM intervention_outcomes
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        exam_stats = db.execute(
            """
            SELECT COALESCE(ROUND(AVG(score * 100.0 / total_questions), 2), 0) AS exam_avg
            FROM exam_attempts
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        profile_snapshot = build_profile_snapshot(
            emotion_state,
            float((exam_stats or {}).get("exam_avg") or 0),
            float((recovery_stats or {}).get("recovery_rate") or 0),
            recent_events,
        )
        guidance = build_guidance_payload(
            course,
            emotion_state["emotion_smoothed"],
            confidence,
            emotion_state=emotion_state,
            profile_snapshot=profile_snapshot,
        )
        db.execute(
            """
            INSERT INTO session_insights
            (
                user_id,
                course_id,
                emotion,
                confidence,
                strategy_title,
                strategy_text,
                generator_provider,
                analysis_provider,
                student_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                course_id,
                emotion_state["emotion_smoothed"],
                confidence,
                guidance["strategy"]["title"],
                guidance["summary"],
                guidance["generator_provider"],
                analysis_provider,
                guidance["student_message"],
            ),
        )
        db.execute(
            """
            INSERT INTO emotion_events
            (
                user_id,
                course_id,
                emotion_raw,
                emotion_smoothed,
                confidence,
                quality_state,
                trend_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                course_id,
                emotion_state["emotion_raw"],
                emotion_state["emotion_smoothed"],
                confidence,
                emotion_state["quality_state"],
                emotion_state["trend_label"],
            ),
        )
        strategy_cursor = db.execute(
            """
            INSERT INTO strategy_recommendations
            (
                user_id,
                course_id,
                emotion,
                trend_label,
                strategy_code,
                strategy_title,
                strategy_text,
                strategy_confidence,
                reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                course_id,
                emotion_state["emotion_smoothed"],
                guidance["trend_label"],
                guidance["strategy_code"],
                guidance["strategy"]["title"],
                guidance["summary"],
                guidance["strategy_confidence"],
                guidance["strategy_reason"],
            ),
        )
        previous_emotion = (recent_events[0].get("emotion_smoothed") if recent_events else None)
        previous_created_at = (recent_events[0].get("created_at") if recent_events else None)
        outcome_status = classify_outcome(previous_emotion, emotion_state["emotion_smoothed"])
        db.execute(
            """
            INSERT INTO intervention_outcomes
            (
                user_id,
                course_id,
                recommendation_id,
                before_emotion,
                after_emotion,
                outcome_status,
                recovery_seconds,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                course_id,
                int(strategy_cursor.lastrowid) if getattr(strategy_cursor, "lastrowid", None) else None,
                previous_emotion,
                emotion_state["emotion_smoothed"],
                outcome_status,
                estimate_recovery_seconds(previous_created_at, outcome_status),
                f"Trend: {emotion_state['trend_label']}",
            ),
        )
        db.execute(
            """
            INSERT INTO student_profiles
            (
                user_id,
                stability_score,
                engagement_score,
                risk_score,
                recovery_rate,
                recommended_pacing
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                stability_score = VALUES(stability_score),
                engagement_score = VALUES(engagement_score),
                risk_score = VALUES(risk_score),
                recovery_rate = VALUES(recovery_rate),
                recommended_pacing = VALUES(recommended_pacing)
            """,
            (
                user["id"],
                profile_snapshot["stability_score"],
                profile_snapshot["engagement_score"],
                profile_snapshot["risk_score"],
                profile_snapshot["recovery_rate"],
                profile_snapshot["recommended_pacing"],
            ),
        )
        db.commit()
        return {
            "ok": True,
            "emotion": emotion_state["emotion_smoothed"],
            "emotion_raw": emotion_state["emotion_raw"],
            "trend_label": emotion_state["trend_label"],
            "confidence": round(confidence, 2),
            "strategy_title": guidance["strategy"]["title"],
            "strategy_text": guidance["summary"],
            "strategy_code": guidance["strategy_code"],
            "strategy_confidence": guidance["strategy_confidence"],
            "strategy_reason": guidance["strategy_reason"],
            "support_state": guidance["support_plan"]["support_state"],
            "headline": guidance["support_plan"]["headline"],
            "coach_message": guidance["coach_message"],
            "simple_explanation": guidance["student_message"],
            "topic_focus": guidance["topic_focus"],
            "intervention_reason": guidance["intervention_reason"],
            "quiz_question": guidance["quiz"]["question"],
            "quiz_answer": guidance["quiz"]["answer"],
            "support_mode": analysis_provider,
            "generator_provider": guidance["generator_provider"],
            "student_message": guidance["student_message"],
            "live_summary": guidance["summary"],
            "easy_strategy": guidance["student_message"],
            "profile_recommended_pacing": profile_snapshot["recommended_pacing"],
            "profile_recovery_rate": profile_snapshot["recovery_rate"],
            "profile_risk_score": profile_snapshot["risk_score"],
        }

    @app.route("/api/emotion-feedback", methods=["POST"])
    @role_required("student")
    def emotion_feedback():
        user = current_user()
        course_id = request.form.get("course_id", type=int)
        predicted_emotion = (request.form.get("predicted_emotion", "") or "").strip().lower()
        actual_emotion = (request.form.get("actual_emotion", "") or "").strip().lower()
        confidence = request.form.get("confidence", type=float) or 0.0
        allowed = {"happy", "focused", "neutral", "sad", "stressed", "confused", "bored", "fear", "angry", "disgust"}
        if not course_id or not predicted_emotion or actual_emotion not in allowed:
            return {"ok": False, "message": "Invalid feedback payload."}, 400
        get_db().execute(
            """
            INSERT INTO emotion_feedback
            (user_id, course_id, predicted_emotion, actual_emotion, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], course_id, predicted_emotion, actual_emotion, confidence),
        )
        get_db().commit()
        return {"ok": True}

    @app.route("/api/topic-summary", methods=["POST"])
    @role_required("student")
    def topic_summary():
        user = current_user()
        db = get_db()
        course_id = request.form.get("course_id", type=int)
        topic = (request.form.get("topic", "") or "").strip()
        lecture_id = request.form.get("lecture_id", type=int)
        if not course_id or not topic:
            return {"ok": False, "message": "Course and topic are required."}, 400
        course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            return {"ok": False, "message": "Course not found."}, 404
        lecture = None
        if lecture_id:
            lecture = db.execute(
                "SELECT * FROM course_lectures WHERE id = ? AND course_id = ?",
                (lecture_id, course_id),
            ).fetchone()
        lecture_title = lecture["title"] if lecture else f"{course['title']} Lecture"
        lecture_url = lecture["video_url"] if lecture else (course.get("youtube_url") or "")
        payload = build_topic_summary_asset(
            course=dict(course),
            topic=topic,
            lecture_title=lecture_title,
            lecture_url=lecture_url,
        )
        if not payload.get("ok"):
            return {"ok": False, "message": payload.get("error", "Topic summary generation failed.")}, 500
        db.execute(
            """
            INSERT INTO session_insights
            (
                user_id, course_id, emotion, confidence, strategy_title, strategy_text,
                generator_provider, analysis_provider, student_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                course_id,
                "focused",
                0.95,
                f"Topic Summary: {payload['topic']}",
                payload["summary_markdown"][:3000],
                payload.get("provider", "rule-based"),
                "topic-summary",
                "Topic summary generated successfully.",
            ),
        )
        db.commit()
        return {
            "ok": True,
            "topic": payload["topic"],
            "summary_markdown": payload["summary_markdown"],
            "provider": payload.get("provider", "rule-based"),
            "notes_url": url_for("static", filename=f"uploads/notes/{payload['pdf_file']}"),
        }
