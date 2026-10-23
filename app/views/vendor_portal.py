"""Portal vendor: RFQ masuk, penawaran, konfirmasi PO, info pengiriman, kirim ulang
(fitur 5.5, 5.6, 6.4, 6.5, 7.5)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import PurchaseOrder, RFQ, RFQVendor, User
from ..services import (audit, notify, parse_quotation_form, quotation_prefill, save_quotation,
                        users_with_role)
from ..utils import now, parse_date, save_upload, today
from .rfq import QUOTABLE

bp = Blueprint("vendor", __name__, url_prefix="/vendor")

VISIBLE_PO = (C.PO_ISSUED, C.PO_CONFIRMED, C.PO_SHIPPED, C.PO_PARTIAL, C.PO_RECEIVED, C.PO_DONE)


def _my_rfq_or_404(rfq_id):
    """Vendor hanya boleh melihat RFQ yang ditujukan kepadanya dan sudah dikirim."""
    rfq = db.session.get(RFQ, rfq_id)
    mine = rfq and rfq.status != C.RFQ_DRAFT and any(
        rv.vendor_id == current_user.vendor_id for rv in rfq.vendors)
    if not mine:
        abort(404)
    return rfq


def _my_po_or_404(po_id):
    po = db.session.get(PurchaseOrder, po_id)
    if po is None or po.vendor_id != current_user.vendor_id or po.status not in VISIBLE_PO:
        abort(404)
    return po


def _warehouse_staff(po):
    return db.session.execute(
        select(User).where(User.role == C.GD, User.active.is_(True), User.warehouse_id == po.warehouse_id)
    ).scalars().all()


# --------------------------------------------------------------------- RFQ
@bp.route("/rfq")
@roles_required(C.VN)
def rfq_index():
    rows = db.session.execute(
        select(RFQ).where(RFQ.status != C.RFQ_DRAFT,
                          RFQ.id.in_(select(RFQVendor.rfq_id).where(RFQVendor.vendor_id == current_user.vendor_id)))
        .order_by(RFQ.id.desc())
    ).scalars().all()
    mine = {r.id: next((q for q in r.quotations if q.vendor_id == current_user.vendor_id), None) for r in rows}
    return render_template("vendor/rfq_list.html", rows=rows, mine=mine)


@bp.route("/rfq/<int:rfq_id>")
@roles_required(C.VN)
def rfq_detail(rfq_id):
    rfq = _my_rfq_or_404(rfq_id)
    q = next((x for x in rfq.quotations if x.vendor_id == current_user.vendor_id), None)
    open_for_quote = rfq.status in QUOTABLE and rfq.deadline >= now()
    return render_template("vendor/rfq_detail.html", rfq=rfq, q=q, open_for_quote=open_for_quote,
                           prefill=quotation_prefill(rfq, q))


@bp.route("/rfq/<int:rfq_id>/quote", methods=["POST"])
@roles_required(C.VN)
def rfq_quote(rfq_id):
    rfq = _my_rfq_or_404(rfq_id)
    if rfq.status not in QUOTABLE or rfq.deadline < now():
        flash("Batas waktu penawaran sudah lewat atau RFQ sudah ditutup.", "danger")
        return redirect(url_for("vendor.rfq_detail", rfq_id=rfq.id))
    data, errors = parse_quotation_form(rfq, request.form)
    attachment = None
    try:
        attachment = save_upload(request.files.get("attachment")) if request.files.get("attachment") else None
    except ValueError as exc:
        errors.append(str(exc))
    if errors:
        for e in errors:
            flash(e, "danger")
        q = next((x for x in rfq.quotations if x.vendor_id == current_user.vendor_id), None)
        return render_template("vendor/rfq_detail.html", rfq=rfq, q=q, open_for_quote=True,
                               prefill=quotation_prefill(rfq, None, request.form))
    save_quotation(rfq, current_user.vendor_id, data, "Vendor", current_user, attachment)
    notify(users_with_role(C.SP), f"Penawaran {current_user.vendor.name} masuk untuk RFQ {rfq.number}.",
           url_for("rfq.compare", rfq_id=rfq.id))
    audit("KIRIM_PENAWARAN", "RFQ", rfq.id, f"{rfq.number} oleh {current_user.vendor.name}")
    db.session.commit()
    flash("Penawaran Anda terkirim.", "success")
    return redirect(url_for("vendor.rfq_detail", rfq_id=rfq.id))


# ---------------------------------------------------------------------- PO
@bp.route("/po")
@roles_required(C.VN)
def po_index():
    rows = db.session.execute(
        select(PurchaseOrder).where(PurchaseOrder.vendor_id == current_user.vendor_id,
                                    PurchaseOrder.status.in_(VISIBLE_PO)).order_by(PurchaseOrder.id.desc())
    ).scalars().all()
    return render_template("vendor/po_list.html", rows=rows)


@bp.route("/po/<int:po_id>")
@roles_required(C.VN)
def po_detail(po_id):
    po = _my_po_or_404(po_id)
    open_complaint = next((c for c in po.complaints if c.status == C.C_FOLLOWED), None)
    return render_template("vendor/po_detail.html", po=po, open_complaint=open_complaint, min_date=today().isoformat())


@bp.route("/po/<int:po_id>/confirm", methods=["POST"])
@roles_required(C.VN)
def po_confirm(po_id):
    po = _my_po_or_404(po_id)
    promised = parse_date(request.form.get("promised_date"))
    if po.status != C.PO_ISSUED:
        flash("PO ini tidak dalam status menunggu konfirmasi.", "warning")
    elif promised is None or promised < today():
        flash("Jadwal kirim wajib diisi dan tidak boleh lebih awal dari hari ini.", "danger")
    else:
        po.status = C.PO_CONFIRMED
        po.confirmed_at = now()
        po.promised_date = promised
        po.confirm_note = (request.form.get("note") or "").strip() or None
        notify(po.created_by, f"{po.vendor.name} mengonfirmasi PO {po.number} (jadwal kirim {promised:%d/%m/%Y}).",
               url_for("po.detail", po_id=po.id))
        audit("KONFIRMASI_PO", "PO", po.id, po.number)
        db.session.commit()
        flash("PO dikonfirmasi.", "success")
    return redirect(url_for("vendor.po_detail", po_id=po.id))


def _read_shipping(form):
    note_no = (form.get("delivery_note_no") or "").strip()
    eta = parse_date(form.get("eta"))
    errors = []
    if not note_no:
        errors.append("Nomor surat jalan wajib diisi.")
    if eta is None:
        errors.append("Estimasi tiba wajib diisi.")
    return note_no[:60], eta, errors


@bp.route("/po/<int:po_id>/ship", methods=["POST"])
@roles_required(C.VN)
def po_ship(po_id):
    po = _my_po_or_404(po_id)
    note_no, eta, errors = _read_shipping(request.form)
    if po.status != C.PO_CONFIRMED:
        flash("Info pengiriman hanya dapat diisi setelah PO dikonfirmasi.", "warning")
    elif errors:
        for e in errors:
            flash(e, "danger")
    else:
        po.status = C.PO_SHIPPED
        po.delivery_note_no, po.eta, po.shipped_at = note_no, eta, now()
        link = url_for("gr.receive", po_id=po.id)
        notify(_warehouse_staff(po), f"PO {po.number} dikirim vendor (surat jalan {note_no}), estimasi tiba {eta:%d/%m/%Y}.", link)
        notify(po.created_by, f"PO {po.number} dalam pengiriman (surat jalan {note_no}).", url_for("po.detail", po_id=po.id))
        audit("KIRIM_BARANG", "PO", po.id, f"{po.number} sj={note_no}")
        db.session.commit()
        flash("Info pengiriman tersimpan.", "success")
    return redirect(url_for("vendor.po_detail", po_id=po.id))


@bp.route("/po/<int:po_id>/resend", methods=["POST"])
@roles_required(C.VN)
def po_resend(po_id):
    """Kirim ulang/perbaikan setelah komplain ditindaklanjuti (fitur 7.5). PO kembali ke Dikirim."""
    po = _my_po_or_404(po_id)
    complaint = next((c for c in po.complaints if c.status == C.C_FOLLOWED), None)
    note_no, eta, errors = _read_shipping(request.form)
    if complaint is None:
        flash("Tidak ada komplain yang menunggu pengiriman ulang.", "warning")
    elif errors:
        for e in errors:
            flash(e, "danger")
    else:
        complaint.status = C.C_RESENT
        complaint.resend_at = now()
        complaint.resend_note = (request.form.get("note") or "").strip() or None
        po.status = C.PO_SHIPPED
        po.delivery_note_no, po.eta, po.shipped_at = note_no, eta, now()
        notify(_warehouse_staff(po), f"Vendor mengirim ulang untuk PO {po.number} (surat jalan {note_no}).",
               url_for("gr.receive", po_id=po.id))
        notify(po.created_by, f"Vendor mengirim ulang barang untuk PO {po.number}.", url_for("po.detail", po_id=po.id))
        audit("KIRIM_ULANG", "PO", po.id, f"{po.number} sj={note_no}")
        db.session.commit()
        flash("Pengiriman ulang tersimpan.", "success")
    return redirect(url_for("vendor.po_detail", po_id=po.id))
