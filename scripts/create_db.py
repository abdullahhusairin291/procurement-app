"""Membuat database PostgreSQL bila belum ada. Jalankan dari folder proyek:  python scripts/create_db.py

Membaca DATABASE_URL dari .env, lalu terhubung ke database 'postgres' (bawaan) untuk membuat
database yang dituju. Tidak perlu mengedit kode."""
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy.engine import make_url

import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        sys.exit("DATABASE_URL belum diisi di file .env")
    url = make_url(raw.replace("postgres://", "postgresql://", 1))
    if not url.drivername.startswith("postgresql"):
        sys.exit("Skrip ini hanya untuk PostgreSQL. DATABASE_URL saat ini: " + url.drivername)
    target = url.database
    try:
        conn = psycopg2.connect(host=url.host or "localhost", port=url.port or 5432, user=url.username,
                                password=url.password, dbname="postgres")
    except psycopg2.OperationalError as exc:
        sys.exit(f"Tidak bisa terhubung ke PostgreSQL: {exc}\nPeriksa DATABASE_URL (user, password, host, port) "
                 "dan pastikan layanan PostgreSQL berjalan.")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,))
        if cur.fetchone():
            print(f"Database '{target}' sudah ada.")
        else:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
            print(f"Database '{target}' dibuat.")
    conn.close()


if __name__ == "__main__":
    main()
