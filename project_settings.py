from __future__ import annotations

import os
from pathlib import Path

# ==========================
# Project Paths
# ==========================
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads" / "pdfs"

ALLOWED_EXTENSIONS = {"pdf"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

# ==========================
# Flask Settings
# ==========================
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "adaptive-learning-final-project-secret"
)

# ==========================
# AI API Keys
# ==========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")

AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower()
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3-mini").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

# ==========================
# Database
# ==========================
DB_BACKEND = "mysql"

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

# Optional check
if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
    raise RuntimeError(
        "MySQL environment variables are missing. "
        "Please configure MYSQL_HOST, MYSQL_PORT, MYSQL_USER, "
        "MYSQL_PASSWORD and MYSQL_DATABASE in Render."
    )
