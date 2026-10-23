"""Fitur 5.7 (nilai plus): input penawaran vendor dari dokumen lewat OCR/ekstraksi teks.

Hasil ekstraksi ditampilkan sebagai form yang bisa diedit; tidak ada yang tersimpan sebelum
pengguna memeriksa dan menekan Simpan (diproses oleh rfq.quotation)."""
from decimal import Decimal

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import RFQ
from ..ocr.engine import OCRUnavailable, extract_text, tesseract_status
from ..ocr.parser import match_rows, parse_header, parse_items, similarity
from ..utils import plain_number, save_upload, upload_path
from .rfq import QUOTABLE

bp = Blueprint("ocr", __name__, url_prefix="/ocr")


def analyse(rfq, text):
    """Ubah teks dokumen menjadi isian form penawaran beserta catatan pemeriksaan."""
    header = parse_header(text)
    rows = parse_items(text)
    matched, unmatched = match_rows(rows, [(ri.id, ri.item.name) for ri in rfq.items])
    prefill = {
        "lead_time": header["lead_time_days"] if header["lead_time_days"] is not None else "",
        "payment_terms": header["payment_terms"] or "",
        "valid_until": header["valid_until"].isoformat() if header["valid_until"] else "",
        "notes": f"Nomor penawaran vendor: {header['quotation_no']}" if header["quotation_no"] else "",
        "prices": {ri.id: plain_number(matched[ri.id][0]["price"]) if ri.id in matched else ""
                   for ri in rfq.items},
    }
    warnings = []
    for ri in rfq.items:
        if ri.id not in matched:
            warnings.append(f"Item '{ri.item.name}' tidak ditemukan pada dokumen. Isi harganya secara manual.")
        else:
            row, score = matched[ri.id]
            if row["qty"] != ri.qty:
                warnings.append(f"Qty '{ri.item.name}' pada dokumen ({row['qty']:f}) berbeda dari RFQ ({ri.qty:f}).")
            if score < 0.7:
                warnings.append(f"Pencocokan '{row['name']}' ke '{ri.item.name}' kurang yakin. Periksa kembali.")
    if header["total"] is not None and matched:
        computed = sum((matched[ri.id][0]["price"] * ri.qty for ri in rfq.items if ri.id in matched), Decimal(0))
        if computed != header["total"]:
            warnings.append("Total pada dokumen berbeda dari hasil hitung harga x qty. Periksa kembali angka-angkanya.")
    return {"prefill": prefill, "header": header, "matched": matched, "unmatched": unmatched,
            "warnings": warnings}


@bp.route("/<int:rfq_id>", methods=["GET", "POST"])
@roles_required(C.SP)
def upload(rfq_id):
    rfq = db.session.get(RFQ, rfq_id)
    if rfq is None:
        abort(404)
    if rfq.status not in QUOTABLE:
        flash("Penawaran hanya dapat diinput saat RFQ berstatus Terkirim atau Penawaran Masuk.", "warning")
        return redirect(url_for("rfq.detail", rfq_id=rfq.id))
    cmd = current_app.config.get("TESSERACT_CMD", "")
    available, status_message = tesseract_status(cmd)

    if request.method == "POST":
        vendor_id = request.form.get("vendor_id", "")
        rv = next((x for x in rfq.vendors if str(x.vendor_id) == vendor_id), None)
        file = request.files.get("document")
        if rv is None:
            flash("Pilih vendor yang menawarkan.", "danger")
        elif not file or not file.filename:
            flash("Pilih file penawaran (PDF, PNG, atau JPG).", "danger")
        else:
            try:
                original, stored = save_upload(file)
                text, method = extract_text(upload_path(stored), cmd)
            except ValueError as exc:
                flash(str(exc), "danger")
            except OCRUnavailable as exc:
                flash(str(exc), "danger")
            else:
                result = analyse(rfq, text)
                vendor_hint = result["header"]["vendor_name"]
                if vendor_hint and similarity(vendor_hint, rv.vendor.name) < 0.5:
                    result["warnings"].insert(0, f"Nama vendor pada dokumen ('{vendor_hint}') berbeda dari "
                                                 f"vendor yang dipilih ('{rv.vendor.name}').")
                return render_template("ocr/review.html", rfq=rfq, rv=rv, raw_text=text, method=method,
                                       stored=stored, original=original, **result)
    return render_template("ocr/upload.html", rfq=rfq, available=available, status_message=status_message)
