"""Parsing teks hasil OCR menjadi data penawaran. Fungsi murni, mudah diuji tanpa Tesseract."""
import re
from datetime import date, timedelta
from difflib import SequenceMatcher

from ..utils import parse_decimal, today

SKIP_PREFIX = re.compile(r"(?i)^\s*(sub\s*total|total|grand\s*total|ppn|pajak|diskon|ongkir|biaya)\b")
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7, "agu": 8,
          "aug": 8, "agt": 8, "ags": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12}


def _numeric(token):
    return bool(re.fullmatch(r"-?\d[\d.,]*", token)) and parse_decimal(token) is not None


def _is_unit(token):
    return bool(re.fullmatch(r"[A-Za-z]{1,12}\.?", token))


def parse_item_line(line):
    """Baca satu baris item: [no] nama qty satuan harga [subtotal]. None bila bukan baris item."""
    if SKIP_PREFIX.match(line):
        return None
    text = re.sub(r"(?i)\bRp\.?\s*", " ", line)  # buang awalan Rp (juga yang menempel pada angka)
    tokens = text.split()
    if tokens and re.fullmatch(r"\d{1,2}[.)]?", tokens[0]) and len(tokens) >= 4:
        tokens = tokens[1:]  # nomor urut baris
    for with_subtotal in (True, False):
        need = 5 if with_subtotal else 4
        if len(tokens) < need:
            continue
        if with_subtotal:
            qty_t, unit_t, price_t, sub_t = tokens[-4:]
            name = " ".join(tokens[:-4])
            if not _numeric(sub_t):
                continue
        else:
            qty_t, unit_t, price_t = tokens[-3:]
            sub_t = None
            name = " ".join(tokens[:-3])
        if not (_numeric(qty_t) and _is_unit(unit_t) and _numeric(price_t)):
            continue
        if not re.search(r"[A-Za-z]", name):
            continue
        if unit_t[:3].lower() in MONTHS and len(unit_t) >= 3:
            continue  # baris tanggal, mis. "22 Oktober 2026"
        qty, price = parse_decimal(qty_t), parse_decimal(price_t)
        if qty is None or qty <= 0 or price is None:
            continue
        return {"name": name.strip(" -:|"), "qty": qty, "unit": unit_t.rstrip("."), "price": price,
                "subtotal": parse_decimal(sub_t) if sub_t else None}
    return None


def parse_items(text):
    return [row for row in (parse_item_line(ln) for ln in text.splitlines()) if row]


def _find(pattern, text):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def parse_valid_until(text):
    """Baca masa berlaku: tanggal (dd/mm/yyyy atau '31 Oktober 2026') atau '30 hari' dari hari ini."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,})\.?\s+(\d{4})", text)
    if m and m.group(2)[:3].lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d+)\s*hari", text, re.I)
    if m:
        return today() + timedelta(days=int(m.group(1)))
    return None


def parse_header(text):
    """Ambil vendor, nomor penawaran, total, lead time, syarat bayar, dan masa berlaku."""
    result = {
        "vendor_name": _find(r"(?im)^\s*(?:vendor|supplier|penyedia|dari)\s*[:\-]\s*(.+)$", text),
        "quotation_no": _find(
            r"(?i)(?:no\.?|nomor)\s*(?:penawaran|quotation)\s*[:\-]?\s*([A-Za-z0-9/\-.]+)", text)
            or _find(r"(?i)quotation\s*no\.?\s*[:\-]?\s*([A-Za-z0-9/\-.]+)", text),
        "total": None, "lead_time_days": None, "payment_terms": None, "valid_until": None,
    }
    if result["vendor_name"] is None:
        m = re.search(r"(?im)^\s*((?:PT|CV|UD)\.?\s+[^\n]{3,80})$", text)
        result["vendor_name"] = m.group(1).strip() if m else None
    m = re.search(r"(?im)^\s*(?:grand\s*total|total(?:\s*harga)?)\s*[:\-]?\s*(?:Rp\.?\s*)?([\d.,]+)", text)
    if m:
        result["total"] = parse_decimal(m.group(1))
    m = re.search(r"(?i)(?:lead\s*time|waktu\s*(?:pengiriman|pengerjaan)|estimasi\s*(?:pengiriman|pengerjaan))"
                  r"\s*[:\-]?\s*(\d+)\s*(hari|minggu|bulan)?", text)
    if m:
        factor = {"minggu": 7, "bulan": 30}.get((m.group(2) or "hari").lower(), 1)
        result["lead_time_days"] = int(m.group(1)) * factor
    result["payment_terms"] = _find(
        r"(?i)(?:syarat\s*(?:pembayaran|bayar)|pembayaran|payment\s*terms?)\s*[:\-]\s*([^\n]+)", text)
    validity = _find(r"(?i)(?:masa\s*berlaku|berlaku\s*(?:s\.?d\.?|sampai|hingga)|valid\s*(?:until|sampai|hingga))"
                     r"\s*[:\-]?\s*([^\n]+)", text)
    result["valid_until"] = parse_valid_until(validity)
    return result


def _norm(text):
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def similarity(a, b):
    """Kemiripan nama 0..1 dengan difflib; kata yang saling memuat diberi bobot lebih."""
    na, nb = " ".join(_norm(a)), " ".join(_norm(b))
    if not na or not nb:
        return 0.0
    score = SequenceMatcher(None, na, nb).ratio()
    if na in nb or nb in na:
        score = max(score, 0.85)
    return score


def match_rows(rows, rfq_items, threshold=0.45):
    """Cocokkan baris hasil ekstraksi ke item RFQ (satu-satu, mulai dari kemiripan tertinggi).

    rfq_items: daftar (id, nama). Mengembalikan ({rfq_item_id: (baris, skor)}, baris_tak_cocok)."""
    pairs = sorted(((similarity(r["name"], name), ri, idx)
                    for idx, r in enumerate(rows) for ri, name in rfq_items), reverse=True)
    matched, used_rows = {}, set()
    for score, ri, idx in pairs:
        if score < threshold:
            break
        if ri in matched or idx in used_rows:
            continue
        matched[ri] = (rows[idx], score)
        used_rows.add(idx)
    unmatched = [r for idx, r in enumerate(rows) if idx not in used_rows]
    return matched, unmatched
