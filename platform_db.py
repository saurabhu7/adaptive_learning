from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from project_settings import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

import pymysql


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = DATA_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


APP_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(255) NOT NULL,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        mobile VARCHAR(40),
        role VARCHAR(20) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS courses (
        id INT PRIMARY KEY AUTO_INCREMENT,
        title VARCHAR(255) NOT NULL,
        category VARCHAR(100) NOT NULL,
        subject VARCHAR(255) NOT NULL,
        course_index INT NOT NULL,
        description TEXT NOT NULL,
        pdf_file VARCHAR(255),
        youtube_url TEXT,
        created_by INT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_courses_user FOREIGN KEY (created_by) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS course_lectures (
        id INT PRIMARY KEY AUTO_INCREMENT,
        course_id INT NOT NULL,
        lecture_index INT NOT NULL,
        title VARCHAR(255) NOT NULL,
        video_url TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_lectures_course FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS emotions (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        category VARCHAR(100) NOT NULL,
        mood VARCHAR(40) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_emotions_user FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exam_attempts (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        course_id INT NULL,
        category VARCHAR(100) NOT NULL,
        score INT NOT NULL,
        total_questions INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_attempts_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_attempts_course FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_insights (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        course_id INT NOT NULL,
        emotion VARCHAR(40) NOT NULL,
        confidence DOUBLE DEFAULT 0,
        strategy_title VARCHAR(255) NOT NULL,
        strategy_text TEXT NOT NULL,
        generator_provider VARCHAR(60) NOT NULL DEFAULT 'rule-based',
        analysis_provider VARCHAR(60) NOT NULL DEFAULT 'fallback',
        student_message TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_insights_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_insights_course FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS training_runs (
        id INT PRIMARY KEY AUTO_INCREMENT,
        model_name VARCHAR(255) NOT NULL,
        dataset_name VARCHAR(255) NOT NULL,
        dataset_path TEXT NOT NULL,
        train_samples INT NOT NULL DEFAULT 0,
        validation_samples INT NOT NULL DEFAULT 0,
        test_samples INT NOT NULL DEFAULT 0,
        image_size VARCHAR(40) NOT NULL,
        epochs INT NOT NULL DEFAULT 0,
        batch_size INT NOT NULL DEFAULT 0,
        train_accuracy DOUBLE DEFAULT 0,
        val_accuracy DOUBLE DEFAULT 0,
        test_accuracy DOUBLE DEFAULT 0,
        test_loss DOUBLE DEFAULT 0,
        label_map_json JSON NOT NULL,
        model_path TEXT NOT NULL,
        history_path TEXT NOT NULL,
        confusion_matrix_path TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS emotion_events (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        course_id INT NOT NULL,
        emotion_raw VARCHAR(40) NOT NULL,
        emotion_smoothed VARCHAR(40) NOT NULL,
        confidence DOUBLE DEFAULT 0,
        quality_state VARCHAR(30) NOT NULL DEFAULT 'valid',
        trend_label VARCHAR(40) NOT NULL DEFAULT 'steady',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_emotion_events_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_emotion_events_course FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_recommendations (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        course_id INT NOT NULL,
        emotion VARCHAR(40) NOT NULL,
        trend_label VARCHAR(40) NOT NULL DEFAULT 'steady',
        strategy_code VARCHAR(60) NOT NULL,
        strategy_title VARCHAR(255) NOT NULL,
        strategy_text TEXT NOT NULL,
        strategy_confidence DOUBLE DEFAULT 0,
        reason TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_strategy_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_strategy_course FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS intervention_outcomes (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        course_id INT NOT NULL,
        recommendation_id INT NULL,
        before_emotion VARCHAR(40),
        after_emotion VARCHAR(40),
        outcome_status VARCHAR(30) NOT NULL,
        recovery_seconds INT,
        notes TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_outcomes_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_outcomes_course FOREIGN KEY (course_id) REFERENCES courses(id),
        CONSTRAINT fk_outcomes_recommendation FOREIGN KEY (recommendation_id) REFERENCES strategy_recommendations(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS student_profiles (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL UNIQUE,
        stability_score DOUBLE DEFAULT 0,
        engagement_score DOUBLE DEFAULT 0,
        risk_score DOUBLE DEFAULT 0,
        recovery_rate DOUBLE DEFAULT 0,
        recommended_pacing VARCHAR(40) NOT NULL DEFAULT 'normal',
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_profile_user FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS emotion_feedback (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        course_id INT NOT NULL,
        predicted_emotion VARCHAR(40) NOT NULL,
        actual_emotion VARCHAR(40) NOT NULL,
        confidence DOUBLE DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_feedback_course FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS course_ai_assets (
        id INT PRIMARY KEY AUTO_INCREMENT,
        course_id INT NOT NULL,
        generated_by INT NOT NULL,
        summary TEXT NOT NULL,
        notes_markdown LONGTEXT NOT NULL,
        quiz_json JSON NOT NULL,
        provider VARCHAR(40) NOT NULL DEFAULT 'rule-based',
        transcript_source VARCHAR(30) NOT NULL DEFAULT 'none',
        pdf_file VARCHAR(255),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_ai_assets_course FOREIGN KEY (course_id) REFERENCES courses(id),
        CONSTRAINT fk_ai_assets_user FOREIGN KEY (generated_by) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS live_lectures (
        id INT PRIMARY KEY AUTO_INCREMENT,
        course_id INT NOT NULL,
        teacher_id INT NOT NULL,
        title VARCHAR(255) NOT NULL,
        meeting_date DATE NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NULL,
        meet_link TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_live_lectures_course FOREIGN KEY (course_id) REFERENCES courses(id),
        CONSTRAINT fk_live_lectures_teacher FOREIGN KEY (teacher_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INT PRIMARY KEY AUTO_INCREMENT,
        room_type VARCHAR(20) NOT NULL,
        room_key VARCHAR(120) NOT NULL,
        course_id INT NULL,
        sender_id INT NOT NULL,
        receiver_id INT NULL,
        message_text TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_chat_room_time (room_key, created_at, id),
        CONSTRAINT fk_chat_course FOREIGN KEY (course_id) REFERENCES courses(id),
        CONSTRAINT fk_chat_sender FOREIGN KEY (sender_id) REFERENCES users(id),
        CONSTRAINT fk_chat_receiver FOREIGN KEY (receiver_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS course_subscriptions (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        course_id INT NOT NULL,
        price INT NOT NULL DEFAULT 799,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_course_subscription (user_id, course_id),
        CONSTRAINT fk_subscription_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_subscription_course FOREIGN KEY (course_id) REFERENCES courses(id)
    )
    """,
]


def _normalize_query(query: str) -> str:
    return query.replace("?", "%s")


class DatabaseConnection:
    def __init__(self, native: Any):
        self.native = native
        self.backend = "mysql"

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None):
        cursor = self.native.cursor()
        cursor.execute(_normalize_query(query), tuple(params or ()))
        return cursor

    def executemany(self, query: str, params_seq: list[tuple[Any, ...]]):
        cursor = self.native.cursor()
        cursor.executemany(_normalize_query(query), params_seq)
        return cursor

    def cursor(self):
        return self.native.cursor()

    def commit(self) -> None:
        self.native.commit()

    def rollback(self) -> None:
        self.native.rollback()

    def close(self) -> None:
        self.native.close()


def app_database_backend() -> str:
    return "mysql"


def mysql_configured() -> bool:
    return all([MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_DATABASE])


def _ensure_mysql_database() -> None:
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`")
    finally:
        connection.close()


def connect_app_db(*, row_factory: bool = True) -> DatabaseConnection:
    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor if row_factory else pymysql.cursors.Cursor,
        autocommit=False,
    )
    return DatabaseConnection(connection)


def _apply_schema(db: DatabaseConnection) -> None:
    for statement in APP_TABLE_STATEMENTS:
        db.execute(statement)
    db.commit()


def _column_exists(db: DatabaseConnection, table_name: str, column_name: str) -> bool:
    row = db.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = ?
          AND COLUMN_NAME = ?
        """,
        (table_name, column_name),
    ).fetchone()
    return bool(row and row[0] > 0)


def _index_exists(db: DatabaseConnection, table_name: str, index_name: str) -> bool:
    row = db.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = ?
          AND INDEX_NAME = ?
        """,
        (table_name, index_name),
    ).fetchone()
    return bool(row and row[0] > 0)


def _apply_schema_migrations(db: DatabaseConnection) -> None:
    column_migrations = [
        (
            "session_insights",
            "generator_provider",
            "ALTER TABLE session_insights ADD COLUMN generator_provider VARCHAR(60) NOT NULL DEFAULT 'rule-based'",
        ),
        (
            "session_insights",
            "analysis_provider",
            "ALTER TABLE session_insights ADD COLUMN analysis_provider VARCHAR(60) NOT NULL DEFAULT 'fallback'",
        ),
        (
            "session_insights",
            "student_message",
            "ALTER TABLE session_insights ADD COLUMN student_message TEXT",
        ),
        (
            "courses",
            "youtube_url",
            "ALTER TABLE courses ADD COLUMN youtube_url TEXT",
        ),
        (
            "courses",
            "created_by",
            "ALTER TABLE courses ADD COLUMN created_by INT NULL",
        ),
    ]
    for table_name, column_name, statement in column_migrations:
        if not _column_exists(db, table_name, column_name):
            db.execute(statement)

    index_migrations = [
        ("emotion_events", "idx_emotion_events_user_course_time", "CREATE INDEX idx_emotion_events_user_course_time ON emotion_events(user_id, course_id, created_at)"),
        ("session_insights", "idx_session_insights_user_course_time", "CREATE INDEX idx_session_insights_user_course_time ON session_insights(user_id, course_id, created_at)"),
        ("exam_attempts", "idx_exam_attempts_user_course_time", "CREATE INDEX idx_exam_attempts_user_course_time ON exam_attempts(user_id, course_id, created_at)"),
        ("emotion_feedback", "idx_emotion_feedback_user_course_time", "CREATE INDEX idx_emotion_feedback_user_course_time ON emotion_feedback(user_id, course_id, created_at)"),
    ]
    for table_name, index_name, statement in index_migrations:
        if not _index_exists(db, table_name, index_name):
            db.execute(statement)
    db.commit()


def init_databases(seed_callback: Callable[[DatabaseConnection], None] | None = None) -> None:
    _ensure_mysql_database()
    app_db = connect_app_db(row_factory=False)
    try:
        _apply_schema(app_db)
        _apply_schema_migrations(app_db)
        if seed_callback is not None:
            seed_callback(app_db)
    finally:
        app_db.close()


def record_training_run(payload: dict[str, Any]) -> int:
    db = connect_app_db(row_factory=False)
    try:
        cursor = db.execute(
            """
            INSERT INTO training_runs (
                model_name,
                dataset_name,
                dataset_path,
                train_samples,
                validation_samples,
                test_samples,
                image_size,
                epochs,
                batch_size,
                train_accuracy,
                val_accuracy,
                test_accuracy,
                test_loss,
                label_map_json,
                model_path,
                history_path,
                confusion_matrix_path,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["model_name"],
                payload["dataset_name"],
                payload["dataset_path"],
                payload["train_samples"],
                payload["validation_samples"],
                payload["test_samples"],
                payload["image_size"],
                payload["epochs"],
                payload["batch_size"],
                payload["train_accuracy"],
                payload["val_accuracy"],
                payload["test_accuracy"],
                payload["test_loss"],
                json.dumps(payload["label_map"], sort_keys=True),
                payload["model_path"],
                payload["history_path"],
                payload["confusion_matrix_path"],
                payload.get("notes"),
            ),
        )
        db.commit()
        return int(cursor.lastrowid)
    finally:
        db.close()


def fetch_latest_training_run() -> dict[str, Any] | None:
    db = connect_app_db()
    try:
        row = db.execute(
            "SELECT * FROM training_runs ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        label_map = row.get("label_map_json")
        if isinstance(label_map, str):
            try:
                row["label_map_json"] = json.loads(label_map)
            except json.JSONDecodeError:
                pass
        return row
    finally:
        db.close()
