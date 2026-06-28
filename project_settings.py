from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads" / "pdfs"
ALLOWED_EXTENSIONS = {"pdf"}

SECRET_KEY = os.getenv("SECRET_KEY", "adaptive-learning-final-project-secret")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower()
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3-mini").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

DB_BACKEND = "mysql"
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost").strip()
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root123")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "adaptive_learning_platform").strip()
