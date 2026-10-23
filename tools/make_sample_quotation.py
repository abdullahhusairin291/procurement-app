"""Membuat contoh dokumen penawaran (PNG dan PDF) untuk mendemokan fitur OCR.

Jalankan dari folder proyek:  python tools/make_sample_quotation.py
Hasil: samples/penawaran_vendor3.png (perlu Tesseract) dan samples/penawaran_vendor3.pdf (PDF digital).

Isinya sesuai skenario demo: PR pemohon1 berisi Laptop Core i5 14 inch x5, Mouse Wireless x10,
Keyboard USB x10. Dokumen ini mewakili penawaran PT Prima Solusi Mandiri (vendor3)."""
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"
MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
          "Oktober", "November", "Desember"]
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
]

COMPANY = "PT Prima Solusi Mandiri"
ADDRESS = "Jl. Industri No. 7, Tangerang"
ITEMS = [  # nama, qty, satuan, harga satuan
    ("Laptop Core i5 14 inch", 5, "unit", 12350000),
    ("Mouse Wireless", 10, "pcs", 145000),
    ("Keyboard USB", 10, "pcs", 235000),
]


def idr(value):
    """12350000 -> 'Rp 12.350.000,00'"""
    return "Rp " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tanggal(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def load_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)  # Pillow >= 10.1


def make_png(path, today, valid_until):
    img = Image.new("RGB", (1500, 1000), "white")
    d = ImageDraw.Draw(img)
    font, bold = load_font(28), load_font(34)
    d.text((70, 50), COMPANY, font=bold, fill="black")
    d.text((70, 95), ADDRESS, font=font, fill="black")
    d.text((70, 160), "SURAT PENAWARAN HARGA", font=bold, fill="black")
    d.text((70, 215), "No. Penawaran: PSM/QT/2026/0142", font=font, fill="black")
    d.text((70, 255), f"Tanggal: {tanggal(today)}", font=font, fill="black")
    d.text((70, 295), f"Vendor: {COMPANY}", font=font, fill="black")
    cols = [70, 140, 640, 740, 880, 1160]
    y = 360
    for x, label in zip(cols, ["No", "Nama Barang", "Qty", "Satuan", "Harga Satuan", "Subtotal"]):
        d.text((x, y), label, font=font, fill="black")
    d.line((60, y + 42, 1440, y + 42), fill="black", width=2)
    y += 60
    total = 0
    for no, (name, qty, unit, price) in enumerate(ITEMS, start=1):
        sub = qty * price
        total += sub
        for x, text in zip(cols, [str(no), name, str(qty), unit, idr(price), idr(sub)]):
            d.text((x, y), text, font=font, fill="black")
        y += 50
    d.line((60, y, 1440, y), fill="black", width=2)
    y += 20
    d.text((880, y), f"Total Harga: {idr(total)}", font=font, fill="black")
    y += 90
    for line in ["Lead time: 7 hari", "Syarat pembayaran: Net 30 hari setelah barang diterima",
                 f"Masa berlaku: {tanggal(valid_until)}"]:
        d.text((70, y), line, font=font, fill="black")
        y += 45
    img.save(path)


def make_pdf(path, today, valid_until):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 60
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, COMPANY)
    c.setFont("Helvetica", 10)
    c.drawString(50, y - 16, ADDRESS)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y - 50, "SURAT PENAWARAN HARGA")
    c.setFont("Helvetica", 10)
    for i, line in enumerate(["No. Penawaran: PSM/QT/2026/0142", f"Tanggal: {tanggal(today)}",
                              f"Vendor: {COMPANY}"]):
        c.drawString(50, y - 72 - i * 15, line)
    y -= 140
    xs = [50, 75, 270, 305, 355, 450]
    for x, label in zip(xs, ["No", "Nama Barang", "Qty", "Satuan", "Harga Satuan", "Subtotal"]):
        c.drawString(x, y, label)
    c.line(50, y - 5, 545, y - 5)
    y -= 22
    total = 0
    for no, (name, qty, unit, price) in enumerate(ITEMS, start=1):
        sub = qty * price
        total += sub
        for x, text in zip(xs, [str(no), name, str(qty), unit, idr(price), idr(sub)]):
            c.drawString(x, y, text)
        y -= 18
    c.line(50, y + 8, 545, y + 8)
    c.drawString(355, y - 10, f"Total Harga: {idr(total)}")
    y -= 50
    for line in ["Lead time: 7 hari", "Syarat pembayaran: Net 30 hari setelah barang diterima",
                 f"Masa berlaku: {tanggal(valid_until)}"]:
        c.drawString(50, y, line)
        y -= 16
    c.save()


def main():
    OUT_DIR.mkdir(exist_ok=True)
    today = date.today()
    valid_until = today + timedelta(days=60)
    make_png(OUT_DIR / "penawaran_vendor3.png", today, valid_until)
    make_pdf(OUT_DIR / "penawaran_vendor3.pdf", today, valid_until)
    print(f"Contoh dokumen dibuat di {OUT_DIR}")


if __name__ == "__main__":
    main()
