"""Perintah CLI: `flask --app run init-db` dan `flask --app run seed-demo`.

Tanpa Alembic: init-db memakai create_all. Ini keputusan sederhana untuk keperluan tes;
untuk produksi sebaiknya memakai migrasi."""
import click
from .extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Membuat semua tabel (aman dijalankan ulang)."""
        from . import models  # noqa: F401
        db.create_all()
        click.echo("Tabel siap.")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Mengisi data demo (idempotent: dilewati bila data demo sudah ada)."""
        from .seed import seed_demo
        created = seed_demo()
        if created:
            click.echo("Data demo dibuat. Semua akun berpassword: Demo@123 (khusus demo).")
        else:
            click.echo("Data demo sudah ada, tidak ada yang diubah.")

    @app.cli.command("show-config")
    def show_config():
        """Menampilkan jenis database yang dipakai (tanpa menampilkan password)."""
        click.echo(f"Database: {db.engine.url.render_as_string(hide_password=True)}")
