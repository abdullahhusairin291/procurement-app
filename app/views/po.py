"""Modul 6: Purchase Order (fitur 6.1, 6.2, 6.3, 6.6) dan penutupan PO (7.6)."""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import POItem, PurchaseOrder, RFQ, Warehouse
from ..pdf import build_po_pdf
from ..services import (approval_history, audit, next_number, notify, users_with_role, vendor_users)
from ..utils import now, parse_date, rupiah, today

bp = Blueprint("po", __name__, url_prefix="/po")

VIEW_ROLES = (C.SP, C.MP, C.AD)
EDITABLE = (C.PO_DRAFT, C.PO_REVISION)


def _get_po_or_404(po_id):
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        abort(404)
    return po


def _warehouses():
    return db.session.execute(select(Warehouse).order_by(Warehouse.name)).scalars().all()


def _read_header(form):
    """Baca isian header PO: (nilai, kesalahan)."""
    errors = []
    wh = db.session.get(Warehouse, int(form["warehouse_id"])) if (form.get("warehouse_id") or "").isdigit() else None
    if wh is None:
        errors.append("Gudang tujuan wajib dipilih.")
    delivery = parse_date(form.get("delivery_date"))
    if delivery is None or delivery < today():
        errors.append("Tanggal kirim wajib diisi dan tidak boleh lebih awal dari hari ini.")
    values = {"warehouse_id": wh.id if wh else None, "delivery_date": delivery,
              "payment_terms": (form.get("payment_terms") or "").strip()[:150] or None,
              "notes": (form.get("notes") or "").strip() or None}
    return values, errors


@bp.route("/")
@roles_required(*VIEW_ROLES)
def index():
    stmt = select(PurchaseOrder)
    status = request.args.get("status", "")
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    rows = db.session.execute(stmt.order_by(PurchaseOrder.id.desc()).limit(300)).scalars().all()
    statuses = [C.PO_DRAFT, C.PO_WAITING, C.PO_REVISION, C.PO_APPROVED, C.PO_ISSUED, C.PO_CONFIRMED,
                C.PO_SHIPPED, C.PO_PARTIAL, C.PO_RECEIVED, C.PO_DONE]
    return render_template("po/list.html", rows=rows, statuses=statuses, status=status)


@bp.route("/new/<int:rfq_id>", methods=["GET", "POST"])
@roles_required(C.SP)
def new(rfq_id):
    """Buat PO dari penawaran pemenang; item dan harga disalin otomatis (fitur 6.1)."""
    rfq = db.session.get(RFQ, rfq_id)
    if rfq is None:
        abort(404)
    winner = rfq.winner
    if rfq.status != C.RFQ_WINNER or winner is None:
        flash("PO hanya dapat dibuat dari RFQ yang pemenangnya sudah ditetapkan dan belum dibuatkan PO.", "warning")
        return redirect(url_for("rfq.detail", rfq_id=rfq.id))
    if request.method == "POST":
        values, errors = _read_header(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            po = PurchaseOrder(number=next_number("PO"), rfq_id=rfq.id, pr_id=rfq.pr_id, quotation_id=winner.id,
                               vendor_id=winner.vendor_id, created_by_id=current_user.id, status=C.PO_DRAFT,
                               **values)
            for ri in rfq.items:
                price = winner.price_for(ri.id).unit_price
                po.items.append(POItem(item_id=ri.item_id, spec=ri.spec, qty=ri.qty, unit_price=price))
            rfq.status = C.RFQ_CLOSED
            db.session.add(po)
            db.session.flush()
            audit("BUAT_PO", "PO", po.id, po.number)
            db.session.commit()
            flash(f"PO {po.number} dibuat sebagai Draft.", "success")
            return redirect(url_for("po.detail", po_id=po.id))
    return render_template("po/form.html", rfq=rfq, winner=winner, po=None, warehouses=_warehouses(),
                           min_date=today().isoformat(), default_terms=winner.payment_terms)


@bp.route("/<int:po_id>/edit", methods=["GET", "POST"])
@roles_required(C.SP)
def edit(po_id):
    po = _get_po_or_404(po_id)
    if po.status not in EDITABLE:
        flash("PO yang sudah diajukan atau terbit tidak dapat diubah.", "warning")
        return redirect(url_for("po.detail", po_id=po.id))
    if request.method == "POST":
        values, errors = _read_header(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            for k, v in values.items():
                setattr(po, k, v)
            audit("UBAH_PO", "PO", po.id, po.number)
            db.session.commit()
            flash("PO diperbarui.", "success")
            return redirect(url_for("po.detail", po_id=po.id))
    return render_template("po/form.html", rfq=po.rfq, winner=po.quotation, po=po, warehouses=_warehouses(),
                           min_date=today().isoformat(), default_terms=po.payment_terms)


@bp.route("/<int:po_id>/submit", methods=["POST"])
@roles_required(C.SP)
def submit(po_id):
    """Ajukan PO ke manajer (fitur 6.2); juga dipakai untuk mengajukan ulang setelah revisi."""
    po = _get_po_or_404(po_id)
    if po.status not in EDITABLE:
        flash("PO tidak dapat diajukan pada status ini.", "warning")
    else:
        po.status = C.PO_WAITING
        po.submitted_at = now()
        notify(users_with_role(C.MP), f"PO {po.number} ({po.vendor.name}, {rupiah(po.total)}) menunggu approval Anda.",
               url_for("approval.po_review", po_id=po.id))
        audit("SUBMIT_PO", "PO", po.id, po.number)
        db.session.commit()
        flash("PO diajukan ke Manajer Procurement.", "success")
    return redirect(url_for("po.detail", po_id=po.id))


@bp.route("/<int:po_id>/issue", methods=["POST"])
@roles_required(C.SP)
def issue(po_id):
    """Terbitkan PO yang sudah disetujui dan tampilkan di portal vendor (fitur 6.3)."""
    po = _get_po_or_404(po_id)
    if po.status != C.PO_APPROVED:
        flash("Hanya PO berstatus Disetujui yang dapat diterbitkan.", "warning")
    else:
        po.status = C.PO_ISSUED
        po.issued_at = now()
        notify(vendor_users([po.vendor_id]), f"PO {po.number} diterbitkan untuk Anda. Mohon konfirmasi.",
               url_for("vendor.po_detail", po_id=po.id))
        audit("TERBITKAN_PO", "PO", po.id, po.number)
        db.session.commit()
        flash("PO diterbitkan dan dikirim ke vendor.", "success")
    return redirect(url_for("po.detail", po_id=po.id))


@bp.route("/<int:po_id>")
@roles_required(*VIEW_ROLES)
def detail(po_id):
    po = _get_po_or_404(po_id)
    return render_template("po/detail.html", po=po, history=approval_history("PO", po.id))


@bp.route("/<int:po_id>/close", methods=["POST"])
@roles_required(C.SP)
def close(po_id):
    """Verifikasi GR dan tutup PO; PR terkait ikut Selesai (fitur 7.6)."""
    po = _get_po_or_404(po_id)
    if po.status != C.PO_RECEIVED:
        flash("PO hanya dapat ditutup setelah seluruh barang/jasa diterima dengan sesuai.", "warning")
    elif any(c.status != C.C_RESENT for c in po.complaints):
        flash("Masih ada komplain yang belum selesai.", "danger")
    else:
        stamp = now()
        for gr in po.receipts:
            gr.verified_by_id, gr.verified_at = current_user.id, stamp
            if gr.status == C.GR_OK:
                gr.status = C.GR_VERIFIED
        po.status = C.PO_DONE
        po.closed_at, po.closed_by_id = stamp, current_user.id
        po.pr.status = C.PR_DONE
        link = url_for("pr.detail", pr_id=po.pr_id)
        notify(po.pr.requester, f"Pengadaan PR {po.pr.number} selesai: barang/jasa sudah diterima di gudang.", link)
        audit("TUTUP_PO", "PO", po.id, po.number)
        db.session.commit()
        flash(f"PO {po.number} ditutup. PR {po.pr.number} berstatus Selesai.", "success")
    return redirect(url_for("po.detail", po_id=po.id))


@bp.route("/<int:po_id>/pdf")
@login_required
def pdf(po_id):
    po = _get_po_or_404(po_id)
    allowed = current_user.role in VIEW_ROLES or (
        current_user.role == C.VN and po.vendor_id == current_user.vendor_id
        and po.status not in (C.PO_DRAFT, C.PO_WAITING, C.PO_REVISION, C.PO_APPROVED))
    if not allowed:
        abort(403)
    return Response(build_po_pdf(po), mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{po.number}.pdf"'})
