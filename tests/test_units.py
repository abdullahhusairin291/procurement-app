"""Uji fungsi murni: format uang, parsing angka, parser OCR."""
from datetime import date
from decimal import Decimal

from app.ocr.parser import match_rows, parse_header, parse_item_line, parse_valid_until
from app.utils import fmt_qty, parse_decimal, rupiah


def test_rupiah_format():
    assert rupiah(Decimal("1250000")) == "Rp 1.250.000"
    assert rupiah(Decimal("1250000.5")) == "Rp 1.250.000,50"
    assert rupiah(None) == "-"


def test_parse_decimal_indonesian_and_english():
    assert parse_decimal("Rp 1.250.000,00") == Decimal("1250000.00")
    assert parse_decimal("1.250.000") == Decimal("1250000")
    assert parse_decimal("1,250,000.50") == Decimal("1250000.50")
    assert parse_decimal("12,5") == Decimal("12.5")
    assert parse_decimal("abc") is None


def test_fmt_qty():
    assert fmt_qty(Decimal("10.00")) == "10"
    assert fmt_qty(Decimal("2.50")) == "2,5"


def test_parse_item_line_with_subtotal():
    row = parse_item_line("1 Laptop Core i5 14 inch 5 unit Rp 12.350.000,00 Rp 61.750.000,00")
    assert row["name"] == "Laptop Core i5 14 inch"
    assert row["qty"] == 5 and row["unit"] == "unit"
    assert row["price"] == Decimal("12350000.00") and row["subtotal"] == Decimal("61750000.00")


def test_parse_item_line_without_subtotal_and_noise():
    row = parse_item_line("Kertas A4 80 gsm 20 rim Rp55.000")
    assert row["name"] == "Kertas A4 80 gsm" and row["qty"] == 20 and row["price"] == Decimal("55000")
    assert parse_item_line("Total Harga: Rp 65.550.000,00") is None
    assert parse_item_line("Tanggal: 22 Oktober 2026") is None
    assert parse_item_line("Lead time: 7 hari") is None


def test_parse_header():
    text = ("PT Prima Solusi Mandiri\nNo. Penawaran: PSM/QT/2026/0142\nVendor: PT Prima Solusi Mandiri\n"
            "Total Harga: Rp 65.550.000,00\nLead time: 2 minggu\n"
            "Syarat pembayaran: Net 30 hari\nMasa berlaku: 31 Desember 2026\n")
    h = parse_header(text)
    assert h["quotation_no"] == "PSM/QT/2026/0142"
    assert h["total"] == Decimal("65550000.00")
    assert h["lead_time_days"] == 14
    assert h["payment_terms"] == "Net 30 hari"
    assert h["valid_until"] == date(2026, 12, 31)


def test_parse_valid_until_formats():
    assert parse_valid_until("15/11/2026") == date(2026, 11, 15)
    assert parse_valid_until("5 Mei 2027") == date(2027, 5, 5)
    assert parse_valid_until("tidak jelas") is None


def test_match_rows_by_name_similarity():
    rows = [{"name": "Mouse Wireless", "price": 1}, {"name": "Laptop Core i5 14", "price": 2}]
    matched, unmatched = match_rows(rows, [(10, "Laptop Core i5 14 inch"), (11, "Mouse Wireless"), (12, "Monitor")])
    assert matched[10][0]["price"] == 2 and matched[11][0]["price"] == 1
    assert 12 not in matched and unmatched == []
