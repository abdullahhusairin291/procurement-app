"""Modul 1: autentikasi, ubah password, profil (fitur 1.1, 1.5)."""
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from ..extensions import db
from ..models import User
from ..services import audit

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Hanya terima alamat relatif di aplikasi ini (cegah open redirect)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = db.session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user and user.active and user.check_password(password):
            login_user(user)
            session.permanent = True  # umur sesi diatur PERMANENT_SESSION_LIFETIME
            audit("LOGIN", "user", user.id, user=user)
            db.session.commit()
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
        audit("LOGIN_GAGAL", "user", None, f"username={username[:50]}")
        db.session.commit()
        flash("Username atau password salah, atau akun nonaktif.", "danger")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("LOGOUT", "user", current_user.id)
    db.session.commit()
    logout_user()
    flash("Anda sudah keluar.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        old = request.form.get("old_password") or ""
        new = request.form.get("new_password") or ""
        again = request.form.get("confirm_password") or ""
        if not current_user.check_password(old):
            flash("Password lama salah.", "danger")
        elif len(new) < 8:
            flash("Password baru minimal 8 karakter.", "danger")
        elif new != again:
            flash("Konfirmasi password tidak cocok.", "danger")
        else:
            current_user.set_password(new)
            audit("UBAH_PASSWORD", "user", current_user.id)
            db.session.commit()
            flash("Password berhasil diubah.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/password.html")


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = (request.form.get("full_name") or "").strip()
        if not name:
            flash("Nama lengkap wajib diisi.", "danger")
        else:
            current_user.full_name = name
            current_user.email = (request.form.get("email") or "").strip() or None
            audit("UBAH_PROFIL", "user", current_user.id)
            db.session.commit()
            flash("Profil diperbarui.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html")
