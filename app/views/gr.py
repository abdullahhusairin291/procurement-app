"""Modul 7: penerimaan barang/jasa (Goods Receipt), retur dan komplain (fitur 7.1 - 7.4)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import GRItem, GoodsReceipt, PurchaseOrder, ReturnComplaint
from ..services import audit, next_number, notify, users_with_role, vendor_users
from ..utils import now, parse_date, parse_decimal, save_upload, today

bp = Blueprint("gr", __name__, url_prefix="/gr")

ALL_ROLES = (C.GD, C.SP, C.MP, C.AD)
RECEIVABLE = (C.PO_SHIPPED, C.PO_PARTIAL)
OPEN_COMPLAINT = (C.C_OPEN, C.C_FOLLOWED)


def _scope_po(stmt):
    """Petugas gudang hanya melihat PO untuk gudang miliknya."""
    if current_user.role == C.GD:
        return stmt.where(PurchaseOrder.warehouse_id == current_user.warehouse_id)
    return stmt


def _check_po_access(po):
    if current_user.role == C.GD and po.warehouse_id != current_user.warehouse_id:
        abort(403)


@bp.route("/")
@roles_required(C.GD)
def waiting():
    """Daftar PO menunggu penerimaan untuk gudang petugas (fitur 7.1)."""
    rows = db.session.execute(
        _scope_po(select(PurchaseOrder).where(PurchaseOrder.status.in_(RECEIVABLE)))
        .order_by(PurchaseOrder.eta, PurchaseOrder.id)
    ).scalars().all()
    return render_template("gr/waiting.html", rows=rows)


def _read_inspection(po, form):
    """Baca hasil pemeriksaan per item. Mengembalikan (baris, kesalahan)."""
    rows, errors = [], []
    for pi in po.items:
        remaining = pi.remaining_qty
        if remaining <= 0:
            continue
        qty = parse_decimal((form.get(f"qty_{pi.id}") or "0").strip() or "0")
        result = form.get(f"result_{pi.id}") or C.RES_OK
        note = (form.get(f"note_{pi.id}") or "").strip() or None
        label = pi.item.name
        if qty is None or qty < 0:
            errors.append(f"{label}: qty diterima tidak valid.")
            continue
        if qty > remaining:
            errors.append(f"{label}: qty diterima ({qty:f}) melebihi sisa yang belum diterima ({remaining:f}).")
            continue
        if result not in (C.RES_OK, C.RES_BAD):
            errors.append(f"{label}: hasil pemeriksaan tidak valid.")
            continue
        if qty == 0 and result == C.RES_OK:
            continue  # item ini tidak ikut diterima pada penerimaan kali ini
        if result == C.RES_BAD and not note:
            errors.append(f"{label}: alasan ketidaksesuaian wajib diisi.")
            continue
        rows.append({"po_item": pi, "qty": qty, "result": result, "note": note})
    if not rows and not errors:
        errors.append("Isi qty diterima minimal untuk satu item.")
    return rows, errors


@bp.route("/receive/<int:po_id>", methods=["GET", "POST"])
@roles_required(C.GD)
def receive(po_id):
    """Pemeriksaan penerimaan dan pembuatan GR (fitur 7.2, 7.3, 7.4)."""
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        abort(404)
    _check_po_access(po)
    if po.status not in RECEIVABLE:
        flash("PO ini tidak sedang menunggu penerimaan.", "warning")
        return redirect(url_for("gr.waiting"))
    pending = next((c for c in po.complaints if c.status in OPEN_COMPLAINT), None)
    if pending:
        flash("Ada komplain yang belum selesai. Tunggu vendor mengirim ulang sebelum memeriksa lagi.", "warning")
        return redirect(url_for("gr.complaint_detail", complaint_id=pending.id))

    if request.method == "POST":
        rows, errors = _read_inspection(po, request.form)
        received_date = parse_date(request.form.get("received_date")) or today()
        if received_date > today():
            errors.append("Tanggal terima tidak boleh di masa depan.")
        evidence = None
        try:
            evidence = save_upload(request.files.get("evidence")) if request.files.get("evidence") else None
        except ValueError as exc:
            errors.append(str(exc))
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            has_bad = any(r["result"] == C.RES_BAD for r in rows)
            gr = GoodsReceipt(number=next_number("GR"), po_id=po.id, received_by_id=current_user.id,
                              received_date=received_date, note=(request.form.get("note") or "").strip() or None,
                              status=C.GR_BAD if has_bad else C.GR_OK)
            for r in rows:
                gr.items.append(GRItem(po_item=r["po_item"], qty_received=r["qty"], result=r["result"], note=r["note"]))
            db.session.add(gr)
            db.session.flush()

            # status PO mengikuti qty yang diterima dengan hasil Sesuai
            if po.fully_accepted:
                po.status = C.PO_RECEIVED
            elif any(i.accepted_qty > 0 for i in po.items):
                po.status = C.PO_PARTIAL
            audit("BUAT_GR", "GR", gr.id, f"{gr.number} PO={po.number} {gr.status}")
            link_po = url_for("po.detail", po_id=po.id)
            if has_bad:
                reason = "; ".join(f"{r['po_item'].item.name}: {r['note']}" for r in rows if r["result"] == C.RES_BAD)
                extra = (request.form.get("complaint_reason") or "").strip()
                complaint = ReturnComplaint(po_id=po.id, gr_id=gr.id, created_by_id=current_user.id,
                                            reason=f"{extra}. {reason}" if extra else reason, status=C.C_OPEN)
                if evidence:
                    complaint.evidence_name, complaint.evidence_path = evidence
                db.session.add(complaint)
                db.session.flush()
                audit("BUAT_KOMPLAIN", "PO", po.id, f"PO {po.number}")
                notify(users_with_role(C.SP), f"Komplain/retur baru untuk PO {po.number}. Mohon ditindaklanjuti.",
                       url_for("gr.complaint_detail", complaint_id=complaint.id))
                flash("GR dicatat. Ada item tidak sesuai, komplain/retur dibuat otomatis.", "warning")
            else:
                flash(f"GR {gr.number} dicatat.", "success")
            if po.status == C.PO_RECEIVED:
                notify(po.created_by, f"Seluruh barang/jasa PO {po.number} sudah diterima. PO siap diverifikasi dan ditutup.", link_po)
            db.session.commit()
            return redirect(url_for("gr.detail", gr_id=gr.id))
    return render_template("gr/receive.html", po=po, today=today().isoformat(), f=request.form)


@bp.route("/receipts")
@roles_required(*ALL_ROLES)
def receipts():
    stmt = select(GoodsReceipt).join(PurchaseOrder, GoodsReceipt.po_id == PurchaseOrder.id)
    rows = db.session.execute(_scope_po(stmt).order_by(GoodsReceipt.id.desc()).limit(300)).scalars().all()
    return render_template("gr/receipts.html", rows=rows)


@bp.route("/receipts/<int:gr_id>")
@roles_required(*ALL_ROLES)
def detail(gr_id):
    gr = db.session.get(GoodsReceipt, gr_id)
    if gr is None:
        abort(404)
    _check_po_access(gr.po)
    return render_template("gr/detail.html", gr=gr)


@bp.route("/complaints")
@roles_required(*ALL_ROLES)
def complaints():
    stmt = select(ReturnComplaint).join(PurchaseOrder, ReturnComplaint.po_id == PurchaseOrder.id)
    rows = db.session.execute(_scope_po(stmt).order_by(ReturnComplaint.id.desc()).limit(300)).scalars().all()
    return render_template("gr/complaints.html", rows=rows)


@bp.route("/complaints/<int:complaint_id>")
@roles_required(*ALL_ROLES)
def complaint_detail(complaint_id):
    c = db.session.get(ReturnComplaint, complaint_id)
    if c is None:
        abort(404)
    _check_po_access(c.po)
    return render_template("gr/complaint_detail.html", c=c)


@bp.route("/complaints/<int:complaint_id>/followup", methods=["POST"])
@roles_required(C.SP)
def complaint_followup(complaint_id):
    """Staf procurement menindaklanjuti komplain ke vendor (fitur 7.4)."""
    c = db.session.get(ReturnComplaint, complaint_id)
    if c is None:
        abort(404)
    note = (request.form.get("note") or "").strip()
    if c.status != C.C_OPEN:
        flash("Komplain ini sudah ditindaklanjuti.", "warning")
    elif not note:
        flash("Catatan tindak lanjut wajib diisi.", "danger")
    else:
        c.status = C.C_FOLLOWED
        c.followup_note, c.followup_by_id, c.followup_at = note, current_user.id, now()
        notify(vendor_users([c.po.vendor_id]),
               f"Komplain atas PO {c.po.number}: {c.reason[:120]}. Mohon kirim ulang/perbaiki.",
               url_for("vendor.po_detail", po_id=c.po_id))
        audit("TINDAK_LANJUT_KOMPLAIN", "PO", c.po_id, f"PO {c.po.number}: {note}")
        db.session.commit()
        flash("Komplain diteruskan ke vendor.", "success")
    return redirect(url_for("gr.complaint_detail", complaint_id=c.id))
