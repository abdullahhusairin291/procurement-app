"""Application factory aplikasi Procurement."""
import os

from flask import Flask, render_template, request
from flask_login import current_user
from sqlalchemy import func, select

from . import constants as C
from .config import Config
from .extensions import csrf, db, login_manager
from .utils import fmt_qty, rupiah, tgl, tgl_waktu


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Silakan login terlebih dahulu."
    login_manager.login_message_category = "warning"

    from . import models  # noqa: F401  (mendaftarkan model ke metadata)
    from .views import register_blueprints
    register_blueprints(app)

    from .cli import register_cli
    register_cli(app)

    register_template_helpers(app)
    register_error_handlers(app)
    return app


def register_template_helpers(app):
    app.jinja_env.filters.update(rupiah=rupiah, qty=fmt_qty, tgl=tgl, tglwaktu=tgl_waktu)
    # global (bukan context processor) agar bisa dipakai di dalam macro yang diimpor
    app.jinja_env.globals["status_color"] = lambda s: C.STATUS_COLORS.get(s, "secondary")

    @app.context_processor
    def inject_globals():
        from .models import Notification
        from .navigation import menu_for
        unread = 0
        menu = []
        if current_user.is_authenticated:
            unread = db.session.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == current_user.id, Notification.is_read.is_(False))
            ).scalar_one()
            menu = menu_for(current_user.role)
        return {
            "C": C,
            "menu": menu,
            "unread_count": unread,
            "current_path": request.path,
        }


def register_error_handlers(app):
    pages = {
        403: ("Akses ditolak", "Anda tidak memiliki hak untuk membuka halaman ini."),
        404: ("Halaman tidak ditemukan", "Alamat yang Anda tuju tidak ada atau datanya sudah tidak tersedia."),
        413: ("File terlalu besar", "Ukuran file melebihi batas 8 MB."),
        500: ("Terjadi kesalahan", "Terjadi kesalahan pada server. Silakan coba lagi atau hubungi administrator."),
    }

    def make_handler(code):
        title, message = pages[code]

        def handler(_error):
            if code == 500:
                db.session.rollback()
            return render_template("errors/error.html", code=code, title=title, message=message), code
        return handler

    for code in pages:
        app.register_error_handler(code, make_handler(code))

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(_error):
        return render_template("errors/error.html", code=400, title="Sesi formulir tidak valid",
                               message="Token keamanan formulir tidak cocok atau kedaluwarsa. "
                                       "Muat ulang halaman lalu coba lagi."), 400
