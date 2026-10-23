"""Konfigurasi aplikasi. Nilai sensitif dibaca dari environment / file .env."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)


def _database_uri():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        # Cadangan agar aplikasi tetap bisa jalan tanpa PostgreSQL (hanya untuk uji cepat).
        return "sqlite:///" + str(INSTANCE_DIR / "procurement.db")
    if url.startswith("postgres://"):  # gaya lama
        url = "postgresql://" + url[len("postgres://"):]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-ganti-di-env")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sesi berbatas waktu (fitur 1.1)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    UPLOAD_FOLDER = str(INSTANCE_DIR / "uploads")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB
    TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "").strip()
