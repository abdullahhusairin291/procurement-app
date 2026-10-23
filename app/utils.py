"""Fungsi bantu: waktu WIB, format uang/tanggal, parsing angka, upload file."""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app

# Asia/Jakarta tidak memakai DST, jadi offset tetap +07:00 sudah akurat dan
# tidak butuh database zona waktu (tzdata) di Windows. Waktu disimpan sebagai WIB.
WIB = timezone(timedelta(hours=7))

MONTHS_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
MONTHS_FULL = ["januari", "februari", "maret", "april", "mei", "juni", "juli",
               "agustus", "september", "oktober", "november", "desember"]


def now() -> datetime:
    """Waktu sekarang (WIB) tanpa info zona, untuk kolom DateTime."""
    return datetime.now(WIB).replace(tzinfo=None)


def today() -> date:
    return now().date()


def rupiah(value) -> str:
    """Contoh: Decimal('1250000') -> 'Rp 1.250.000'."""
    if value is None:
        return "-"
    v = Decimal(str(value)).quantize(Decimal("0.01"))
    text = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if text.endswith(",00"):
        text = text[:-3]
    return "Rp " + text


def fmt_qty(value) -> str:
    if value is None:
        return "-"
    d = Decimal(str(value))
    text = format(d.normalize(), "f")
    return text.replace(".", ",")


def plain_number(value) -> str:
    """Decimal -> teks angka tanpa nol di belakang koma, untuk nilai <input>."""
    return format(Decimal(str(value)).normalize(), "f") if value is not None else ""


def tgl(value) -> str:
    if not value:
        return "-"
    return f"{value.day} {MONTHS_ID[value.month - 1]} {value.year}"


def tgl_waktu(value) -> str:
    if not value:
        return "-"
    return f"{tgl(value)} {value:%H:%M}"


def parse_decimal(text, default=None):
    """Parse angka gaya Indonesia atau Inggris menjadi Decimal.

    '1.250.000,50' -> 1250000.50 | '1.250.000' -> 1250000 | '1,250,000.50' -> 1250000.50
    Mengembalikan `default` bila tidak bisa dibaca.
    """
    if text is None:
        return default
    s = re.sub(r"(?i)rp\.?", "", str(text)).replace(" ", "").replace("\u00a0", "").strip()
    if not s or not re.fullmatch(r"-?[\d.,]+", s):
        return default
    if "." in s and "," in s:
        # pemisah yang muncul terakhir adalah desimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
    elif "," in s:
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return default


def parse_date(text):
    """Baca tanggal 'YYYY-MM-DD' (input type=date). None bila tidak valid."""
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_datetime_local(text):
    """Baca nilai input type=datetime-local ('YYYY-MM-DDTHH:MM')."""
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


# ---------------------------------------------------------------- upload file
ALLOWED_UPLOADS = {"pdf", "png", "jpg", "jpeg"}
STORED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg|jpeg)$")


def save_upload(file_storage):
    """Simpan file unggahan dengan nama acak. Mengembalikan (nama_asli, nama_tersimpan)
    atau (None, None) bila tidak ada file. Melempar ValueError bila tipe tidak diizinkan."""
    if file_storage is None or not file_storage.filename:
        return None, None
    original = Path(file_storage.filename).name
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_UPLOADS:
        raise ValueError("Tipe file tidak diizinkan. Gunakan PDF, PNG, atau JPG.")
    stored = f"{uuid.uuid4().hex}.{ext}"
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    file_storage.save(folder / stored)
    return original, stored


def upload_path(stored_name) -> Path:
    if not stored_name or not STORED_NAME_RE.match(stored_name):
        raise ValueError("Nama file tidak valid.")
    return Path(current_app.config["UPLOAD_FOLDER"]) / stored_name
