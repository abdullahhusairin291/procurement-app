"""Modul 5: verifikasi PR, RFQ, input penawaran, perbandingan, dan penetapan pemenang."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import PurchaseOrder, PurchaseRequest, RFQ, RFQItem, RFQVendor, Vendor
from ..services import (audit, next_number, notify, parse_quotation_form, quotation_prefill,
                        save_quotation, vendor_users)
from ..utils import now, parse_datetime_local, save_upload, upload_path, STORED_NAME_RE

bp = Blueprint("rfq", __name__, url_prefix="/rfq")

VIEW_ROLES = (C.SP, C.MP, C.AD)
QUOTABLE = (C.RFQ_SENT, C.RFQ_QUOTED)  # status saat penawaran masih bisa diisi
METHODS = ["RFQ ke beberapa vendor", "Penunjukan langsung"]


def get_rfq_or_404(rfq_id):
    rfq = db.session.get(RFQ, rfq_id)
    if rfq is None:
        abort(404)
    return rfq


@bp.route("/")
@roles_required(*VIEW_ROLES)
def index():
    rows = db.session.execute(select(RFQ).order_by(RFQ.id.desc()).limit(300)).scalars().all()
    waiting = db.session.execute(
        select(PurchaseRequest)
        .where(PurchaseRequest.status == C.PR_APPROVED, ~PurchaseRequest.id.in_(select(RFQ.pr_id)))
        .order_by(PurchaseRequest.id)
    ).scalars().all()
    return render_template("rfq/list.html", rows=rows, waiting=waiting)


@bp.route("/new/<int:pr_id>", methods=["GET", "POST"])
@roles_required(C.SP)
def new(pr_id):
    """Verifikasi PR + pilih calon vendor + buat RFQ (fitur 5.1, 5.2, 5.3)."""
    pr = db.session.get(PurchaseRequest, pr_id)
    if pr is None:
        abort(404)
    if pr.status != C.PR_APPROVED:
        flash("RFQ hanya dapat dibuat dari PR berstatus Disetujui.", "warning")
        return redirect(url_for("pr.detail", pr_id=pr.id))
    if db.session.execute(select(RFQ.id).where(RFQ.pr_id == pr.id)).first():
        flash("PR ini sudah memiliki RFQ.", "warning")
        return redirect(url_for("pr.detail", pr_id=pr.id))

    vendors = db.session.execute(select(Vendor).where(Vendor.active.is_(True)).order_by(Vendor.name)).scalars().all()
    item_categories = {i.item.category_id for i in pr.items if i.item.category_id}
    suggested = {v.id for v in vendors if v.category_id in item_categories}

    if request.method == "POST":
        errors = []
        deadline = parse_datetime_local(request.form.get("deadline"))
        if deadline is None or deadline <= now():
            errors.append("Batas waktu penawaran wajib diisi dan harus di masa depan.")
        if request.form.get("verified") != "on":
            errors.append("Centang konfirmasi bahwa PR sudah diverifikasi.")
        method = request.form.get("method")
        if method not in METHODS:
            errors.append("Metode pengadaan tidak valid.")
        chosen = [int(v) for v in request.form.getlist("vendor_id") if v.isdigit()]
        valid_ids = {v.id for v in vendors}
        chosen = [v for v in dict.fromkeys(chosen) if v in valid_ids]
        if not chosen:
            errors.append("Pilih minimal 1 vendor.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            pr.verified_by_id, pr.verified_at = current_user.id, now()
            pr.verification_note = (request.form.get("verification_note") or "").strip() or None
            pr.procurement_method = method
            rfq = RFQ(number=next_number("RFQ"), pr_id=pr.id, created_by_id=current_user.id,
                      deadline=deadline, terms=(request.form.get("terms") or "").strip() or None,
                      status=C.RFQ_DRAFT)
            for it in pr.items:
                rfq.items.append(RFQItem(item_id=it.item_id, spec=it.spec, qty=it.qty))
            for vid in chosen:
                rfq.vendors.append(RFQVendor(vendor_id=vid))
            db.session.add(rfq)
            db.session.flush()
            audit("VERIFIKASI_PR", "PR", pr.id, pr.number)
            audit("BUAT_RFQ", "RFQ", rfq.id, rfq.number)
            db.session.commit()
            if len(chosen) < 3:
                flash("Peringatan: vendor yang dipilih kurang dari 3. Disarankan minimal 3 vendor.", "warning")
            flash(f"RFQ {rfq.number} dibuat sebagai Draft. Periksa lalu kirim ke vendor.", "success")
            return redirect(url_for("rfq.detail", rfq_id=rfq.id))
    return render_template("rfq/new.html", pr=pr, vendors=vendors, suggested=suggested, methods=METHODS)


@bp.route("/<int:rfq_id>")
@roles_required(*VIEW_ROLES)
def detail(rfq_id):
    rfq = get_rfq_or_404(rfq_id)
    quote_by_vendor = {q.vendor_id: q for q in rfq.quotations}
    po = rfq_po(rfq)
    return render_template("rfq/detail.html", rfq=rfq, quote_by_vendor=quote_by_vendor, po=po,
                           can_quote=rfq.status in QUOTABLE)


def rfq_po(rfq):
    return db.session.execute(select(PurchaseOrder).where(PurchaseOrder.rfq_id == rfq.id)).scalars().first()


@bp.route("/<int:rfq_id>/send", methods=["POST"])
@roles_required(C.SP)
def send(rfq_id):
    """Kirim RFQ ke vendor: tampil di portal vendor dan vendor mendapat notifikasi (fitur 5.4)."""
    rfq = get_rfq_or_404(rfq_id)
    if rfq.status != C.RFQ_DRAFT:
        flash("RFQ sudah dikirim.", "warning")
    elif rfq.deadline <= now():
        flash("Batas waktu penawaran sudah lewat. Buat RFQ baru dengan batas waktu yang valid.", "danger")
    else:
        rfq.status = C.RFQ_SENT
        rfq.sent_at = now()
        notify(vendor_users([rv.vendor_id for rv in rfq.vendors]),
               f"RFQ {rfq.number} baru untuk Anda. Batas penawaran {rfq.deadline:%d/%m/%Y %H:%M}.",
               url_for("vendor.rfq_detail", rfq_id=rfq.id))
        audit("KIRIM_RFQ", "RFQ", rfq.id, rfq.number)
        db.session.commit()
        flash("RFQ dikirim ke vendor.", "success")
    return redirect(url_for("rfq.detail", rfq_id=rfq.id))


def carried_ocr_file(form):
    """File OCR yang dibawa dari halaman review: (nama_asli, nama_tersimpan) bila valid."""
    stored = (form.get("ocr_file") or "").strip()
    if stored and STORED_NAME_RE.match(stored) and upload_path(stored).exists():
        return (form.get("ocr_name") or stored)[:200], stored
    return None


@bp.route("/<int:rfq_id>/quotation/<int:vendor_id>", methods=["GET", "POST"])
@roles_required(C.SP)
def quotation(rfq_id, vendor_id):
    """Staf menginput penawaran atas nama vendor (fitur 5.6; hasil OCR lewat fitur 5.7)."""
    rfq = get_rfq_or_404(rfq_id)
    rv = next((x for x in rfq.vendors if x.vendor_id == vendor_id), None)
    if rv is None:
        abort(404)
    if rfq.status not in QUOTABLE:
        flash("Penawaran hanya dapat diinput saat RFQ berstatus Terkirim atau Penawaran Masuk.", "warning")
        return redirect(url_for("rfq.detail", rfq_id=rfq.id))
    existing = next((q for q in rfq.quotations if q.vendor_id == vendor_id), None)
    prefill = quotation_prefill(rfq, existing)
    if request.method == "POST":
        data, errors = parse_quotation_form(rfq, request.form)
        via = "OCR" if request.form.get("via") == "OCR" else "Staf"
        attachment = None
        try:
            attachment = save_upload(request.files.get("attachment")) if request.files.get("attachment") else None
        except ValueError as exc:
            errors.append(str(exc))
        if attachment is None and via == "OCR":
            attachment = carried_ocr_file(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            prefill = quotation_prefill(rfq, None, request.form)
        else:
            q = save_quotation(rfq, vendor_id, data, via, current_user, attachment)
            audit("INPUT_PENAWARAN", "RFQ", rfq.id, f"{rfq.number} vendor={rv.vendor.name} via={via}")
            db.session.commit()
            flash(f"Penawaran {rv.vendor.name} disimpan.", "success")
            return redirect(url_for("rfq.detail", rfq_id=rfq.id))
    return render_template("rfq/quotation.html", rfq=rfq, rv=rv, prefill=prefill, via="Staf")


@bp.route("/<int:rfq_id>/compare")
@roles_required(*VIEW_ROLES)
def compare(rfq_id):
    """Matriks perbandingan item x vendor (fitur 5.8). Total terendah ditandai."""
    rfq = get_rfq_or_404(rfq_id)
    quotes = list(rfq.quotations)
    lowest_item = {}
    for ri in rfq.items:
        prices = [qi.unit_price for q in quotes for qi in q.items if qi.rfq_item_id == ri.id]
        lowest_item[ri.id] = min(prices) if prices else None
    complete_totals = [q.total for q in quotes if q.is_complete]
    lowest_total = min(complete_totals) if complete_totals else None
    no_quote = [rv.vendor for rv in rfq.vendors if rv.vendor_id not in {q.vendor_id for q in quotes}]
    return render_template("rfq/compare.html", rfq=rfq, quotes=quotes, lowest_item=lowest_item,
                           lowest_total=lowest_total, no_quote=no_quote,
                           can_choose=current_user.role == C.SP and rfq.status == C.RFQ_QUOTED)


@bp.route("/<int:rfq_id>/winner", methods=["POST"])
@roles_required(C.SP)
def winner(rfq_id):
    """Tetapkan vendor pemenang beserta alasan (fitur 5.9). PR menjadi Diproses."""
    rfq = get_rfq_or_404(rfq_id)
    if rfq.status != C.RFQ_QUOTED:
        flash("Pemenang hanya dapat ditetapkan saat RFQ berstatus Penawaran Masuk.", "warning")
        return redirect(url_for("rfq.detail", rfq_id=rfq.id))
    qid = request.form.get("quotation_id", "")
    chosen = next((q for q in rfq.quotations if str(q.id) == qid), None)
    reason = (request.form.get("reason") or "").strip()
    success = False
    if chosen is None:
        flash("Pilih salah satu penawaran.", "danger")
    elif not reason:
        flash("Alasan pemilihan wajib diisi.", "danger")
    elif not chosen.is_complete:
        flash("Penawaran yang tidak lengkap tidak dapat ditetapkan sebagai pemenang.", "danger")
    else:
        for q in rfq.quotations:
            q.status = C.Q_WON if q.id == chosen.id else C.Q_LOST
        rfq.status = C.RFQ_WINNER
        rfq.win_reason = reason
        rfq.selected_by_id, rfq.selected_at = current_user.id, now()
        rfq.pr.status = C.PR_PROCESSED
        notify(vendor_users([chosen.vendor_id]), f"Penawaran Anda untuk RFQ {rfq.number} terpilih sebagai pemenang.",
               url_for("vendor.rfq_detail", rfq_id=rfq.id))
        notify(vendor_users([q.vendor_id for q in rfq.quotations if q.id != chosen.id]),
               f"RFQ {rfq.number}: penawaran Anda tidak terpilih. Terima kasih atas partisipasinya.",
               url_for("vendor.rfq_detail", rfq_id=rfq.id))
        audit("TETAPKAN_PEMENANG", "RFQ", rfq.id, f"{rfq.number}: {chosen.vendor.name} - {reason}")
        db.session.commit()
        flash(f"{chosen.vendor.name} ditetapkan sebagai pemenang. Lanjutkan dengan membuat PO.", "success")
        success = True
    return redirect(url_for("rfq.detail" if success else "rfq.compare", rfq_id=rfq.id))
