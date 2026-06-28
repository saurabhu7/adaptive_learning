CREATE DATABASE IF NOT EXISTS adaptive_learning_platform;
USE adaptive_learning_platform;

CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    mobile VARCHAR(40),
    role VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE TABLE IF NOT EXISTS course_lectures (
    id INT PRIMARY KEY AUTO_INCREMENT,
    course_id INT NOT NULL,
    lecture_index INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    video_url TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_lectures_course FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS emotions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category VARCHAR(100) NOT NULL,
    mood VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_emotions_user FOREIGN KEY (user_id) REFERENCES users(id)
);

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
);

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
);

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
);

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
);

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
);

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
);

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
);

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
);

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
);

-- Performance indexes are applied safely by platform_db.py migrations at app startup.
