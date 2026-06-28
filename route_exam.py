from __future__ import annotations

import json
import random

from flask import flash, redirect, render_template, request, url_for

from auth_utils import current_user, get_db, role_required
from learning_assets import build_course_assets
from question_bank import QUESTION_BANK


def _student_has_subscription(user_id: int, course_id: int) -> bool:
    row = get_db().execute(
        "SELECT id FROM course_subscriptions WHERE user_id = ? AND course_id = ?",
        (user_id, course_id),
    ).fetchone()
    return bool(row)


def _normalize_course_quiz(quiz_json_value) -> list[dict]:
    if isinstance(quiz_json_value, str):
        try:
            raw = json.loads(quiz_json_value)
        except json.JSONDecodeError:
            raw = []
    elif isinstance(quiz_json_value, list):
        raw = quiz_json_value
    else:
        raw = []
    questions: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not question or not answer:
            continue
        options_raw = item.get("options")
        options: list[str] = []
        if isinstance(options_raw, list):
            for opt in options_raw:
                text = str(opt).strip()
                if text and text not in options:
                    options.append(text)
        if answer not in options:
            options.insert(0, answer)
        question_lower = question.lower()
        contextual_fillers = [
            f"Only theory is needed for: {question[:50]}",
            f"The lecture does not cover this concept: {question[:45]}",
            f"Use a random approach instead of the taught workflow",
            f"Ignore examples and skip step-by-step validation",
        ]
        if "data" in question_lower:
            contextual_fillers = [
                "Delete data cleaning and jump directly to model output",
                "Use random values without checking columns",
                "Ignore data quality and assumptions",
                "Avoid validation and rely only on intuition",
            ]
        elif "network" in question_lower or "ip" in question_lower:
            contextual_fillers = [
                "Skip addressing rules and guess network configuration",
                "Ignore routing logic and forward blindly",
                "Disable troubleshooting and trust default settings",
                "Avoid protocol checks during diagnosis",
            ]
        elif "web" in question_lower or "html" in question_lower or "css" in question_lower:
            contextual_fillers = [
                "Skip structure and write styles without layout plan",
                "Ignore semantic tags and accessibility",
                "Avoid browser testing and deploy directly",
                "Mix logic and style without clear separation",
            ]

        for filler in contextual_fillers:
            if len(options) >= 4:
                break
            if filler not in options and filler != answer:
                options.append(filler)
        random.shuffle(options)
        questions.append({"question": question, "options": options[:4], "answer": answer})
    return questions[:20]


def register_exam_routes(app) -> None:
    @app.route("/question")
    @role_required("student")
    def exam_home():
        categories_data = get_db().execute(
            "SELECT category, COUNT(*) AS total FROM courses GROUP BY category ORDER BY category"
        ).fetchall()
        course_exams = get_db().execute(
            """
            SELECT c.id, c.title, c.category, c.subject, MAX(ca.updated_at) AS updated_at
            FROM courses c
            JOIN course_ai_assets ca ON ca.course_id = c.id
            GROUP BY c.id, c.title, c.category, c.subject
            ORDER BY c.category, c.course_index, c.title
            """
        ).fetchall()
        return render_template("exam.html", categories=categories_data, course_exams=course_exams)

    @app.route("/exam/<category>", methods=["GET", "POST"])
    @role_required("student")
    def exam(category: str):
        # Prefer syllabus-based course exam over static category bank.
        syllabus_course = get_db().execute(
            """
            SELECT id
            FROM courses
            WHERE category = ?
            ORDER BY course_index ASC, id ASC
            LIMIT 1
            """,
            (category,),
        ).fetchone()
        if syllabus_course:
            return redirect(url_for("exam_course", course_id=syllabus_course["id"]))

        questions = QUESTION_BANK.get(category)
        if not questions:
            flash("No exam is configured for that category.", "error")
            return redirect(url_for("exam_home"))
        user = current_user()
        if request.method == "POST":
            score = sum(
                1
                for index, question in enumerate(questions, start=1)
                if request.form.get(f"answer_{index}") == question["answer"]
            )
            course = get_db().execute(
                "SELECT id FROM courses WHERE category = ? ORDER BY course_index, title LIMIT 1",
                (category,),
            ).fetchone()
            cursor = get_db().execute(
                """
                INSERT INTO exam_attempts (user_id, course_id, category, score, total_questions)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user["id"], course["id"] if course else None, category, score, len(questions)),
            )
            get_db().commit()
            return redirect(url_for("exam_result", attempt_id=cursor.lastrowid))
        return render_template(
            "exam_interactive.html",
            category=category,
            course_title=None,
            source_label="Category Exam",
            questions=questions,
            total=len(questions),
        )

    @app.route("/exam/course/<int:course_id>", methods=["GET", "POST"])
    @role_required("student")
    def exam_course(course_id: int):
        db = get_db()
        user = current_user()
        course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("exam_home"))
        if not _student_has_subscription(user["id"], course_id):
            flash("Please subscribe to this course first. Course price is ₹799.", "warning")
            return redirect(url_for("student_dashboard"))
        ai_asset = db.execute(
            """
            SELECT quiz_json
            FROM course_ai_assets
            WHERE course_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        if not ai_asset:
            payload = build_course_assets(dict(course))
            if not payload.get("ok"):
                flash("Could not generate AI exam from transcript right now.", "error")
                return redirect(url_for("exam_home"))
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
                    payload.get("quiz_json") or "[]",
                    payload.get("provider", "rule-based"),
                    payload.get("transcript_source", "none"),
                    payload.get("pdf_file", ""),
                ),
            )
            db.commit()
            ai_asset = {"quiz_json": payload.get("quiz_json") or "[]"}
        questions = _normalize_course_quiz(ai_asset.get("quiz_json"))
        if not questions:
            flash("AI exam generation is incomplete. Please regenerate exam.", "warning")
            return redirect(url_for("exam_home"))
        if request.method == "POST":
            score = sum(
                1
                for index, question in enumerate(questions, start=1)
                if request.form.get(f"answer_{index}") == question["answer"]
            )
            cursor = db.execute(
                """
                INSERT INTO exam_attempts (user_id, course_id, category, score, total_questions)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user["id"], course_id, course["category"], score, len(questions)),
            )
            db.commit()
            return redirect(url_for("exam_result", attempt_id=cursor.lastrowid))
        return render_template(
            "exam_interactive.html",
            category=course["category"],
            course_title=course["title"],
            source_label="AI Course Exam",
            questions=questions,
            total=len(questions),
        )

    @app.route("/result/<int:attempt_id>")
    @role_required("student", "admin", "teacher")
    def exam_result(attempt_id: int):
        attempt = get_db().execute(
            """
            SELECT a.*, u.username, c.title AS course_title
            FROM exam_attempts a
            JOIN users u ON u.id = a.user_id
            LEFT JOIN courses c ON c.id = a.course_id
            WHERE a.id = ?
            """,
            (attempt_id,),
        ).fetchone()
        if not attempt:
            flash("Result not found.", "error")
            return redirect(url_for("dashboard"))
        percentage = int((attempt["score"] / attempt["total_questions"]) * 100)
        return render_template("result.html", attempt=attempt, percentage=percentage)

    @app.route("/Resultexam")
    @role_required("admin", "teacher")
    def result_exam():
        records = get_db().execute(
            """
            SELECT a.id, u.username, u.email, a.category, a.score, a.total_questions, a.created_at
            FROM exam_attempts a
            JOIN users u ON u.id = a.user_id
            ORDER BY a.created_at DESC
            """
        ).fetchall()
        return render_template("ResultExam.html", records=records)
