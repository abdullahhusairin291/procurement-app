"""Fixture pengujian: SQLite in-memory, tanpa PostgreSQL, tanpa Tesseract."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.seed import DEMO_PASSWORD, seed_demo  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
    })
    with app.app_context():
        db.create_all()
        seed_demo()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def login(app):
    """Mengembalikan fungsi yang membuat test client baru yang sudah login sebagai username."""
    def _login(username):
        client = app.test_client()
        resp = client.post("/login", data={"username": username, "password": DEMO_PASSWORD})
        assert resp.status_code == 302, f"login {username} gagal"
        return client
    return _login
