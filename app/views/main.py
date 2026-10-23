"""Dashboard per role, notifikasi, dan unduhan lampiran (fitur 8.1, 8.2)."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import (GoodsReceipt, Notification, PurchaseOrder, PurchaseRequest, Quotation,
                      RFQ, RFQVendor, ReturnComplaint, User)
from ..utils import STORED_NAME_RE

bp = Blueprint("main", __name__)


def _count(model, *conditions):
    return db.session.execute(select(func.count(model.id)).where(*conditions)).scalar_one()


def _cards_for(user):
    """Kartu ringkasan: (judul, jumlah, tautan, warna)."""
    role = user.role
    cards = []
    if role == C.PM:
        for status, color in ((C.PR_DRAFT, "secondary"), (C.PR_REVISION, "warning"),
                              (C.PR_SUBMITTED, "primary"), (C.PR_APPROVED, "success"),
                              (C.PR_PROCESSED, "info"), (C.PR_DONE, "dark")):
            n = _count(PurchaseRequest, PurchaseRequest.requester_id == user.id,
                       PurchaseRequest.status == status)
            cards.append((f"PR {status}", n, url_for("pr.index", status=status), color))
    elif role == C.AT:
        n = _count(PurchaseRequest, PurchaseRequest.status == C.PR_SUBMITTED,
                   PurchaseRequest.requester_id.in_(select(User.id).where(User.supervisor_id == user.id)))
        cards.append(("PR menunggu approval Anda", n, url_for("approval.pr_queue"), "danger"))
    elif role == C.MP:
        cards.append(("PO menunggu approval", _count(PurchaseOrder, PurchaseOrder.status == C.PO_WAITING),
                      url_for("approval.po_queue"), "danger"))
        running = (C.PO_ISSUED, C.PO_CONFIRMED, C.PO_SHIPPED, C.PO_PARTIAL, C.PO_RECEIVED)
        cards.append(("PO berjalan", _count(PurchaseOrder, PurchaseOrder.status.in_(running)),
                      url_for("po.index"), "info"))
        cards.append(("PO selesai", _count(PurchaseOrder, PurchaseOrder.status == C.PO_DONE),
                      url_for("po.index", status=C.PO_DONE), "dark"))
    elif role == C.SP:
        cards += [
            ("PR disetujui (siap RFQ)", _count(PurchaseRequest, PurchaseRequest.status == C.PR_APPROVED,
                                                 ~PurchaseRequest.id.in_(select(RFQ.pr_id))),
             url_for("rfq.index"), "danger"),
            ("RFQ menunggu penawaran", _count(RFQ, RFQ.status.in_((C.RFQ_SENT, C.RFQ_QUOTED))),
             url_for("rfq.index"), "info"),
            ("RFQ siap dibuatkan PO", _count(RFQ, RFQ.status == C.RFQ_WINNER),
             url_for("rfq.index"), "warning"),
            ("PO perlu tindakan (draft/revisi/disetujui)",
             _count(PurchaseOrder, PurchaseOrder.status.in_((C.PO_DRAFT, C.PO_REVISION, C.PO_APPROVED))),
             url_for("po.index"), "warning"),
            ("PO diterima (siap ditutup)", _count(PurchaseOrder, PurchaseOrder.status == C.PO_RECEIVED),
             url_for("po.index", status=C.PO_RECEIVED), "success"),
            ("Komplain terbuka", _count(ReturnComplaint, ReturnComplaint.status == C.C_OPEN),
             url_for("gr.complaints"), "danger"),
        ]
    elif role == C.VN and user.vendor_id:
        cards += [
            ("RFQ menunggu penawaran Anda",
             _count(RFQ, RFQ.status.in_((C.RFQ_SENT, C.RFQ_QUOTED)),
                    RFQ.id.in_(select(RFQVendor.rfq_id).where(RFQVendor.vendor_id == user.vendor_id)),
                    ~RFQ.id.in_(select(Quotation.rfq_id).where(Quotation.vendor_id == user.vendor_id))),
             url_for("vendor.rfq_index"), "danger"),
            ("PO perlu dikonfirmasi", _count(PurchaseOrder, PurchaseOrder.vendor_id == user.vendor_id,
                                              PurchaseOrder.status == C.PO_ISSUED),
             url_for("vendor.po_index"), "warning"),
            ("PO siap dikirim", _count(PurchaseOrder, PurchaseOrder.vendor_id == user.vendor_id,
                                        PurchaseOrder.status == C.PO_CONFIRMED),
             url_for("vendor.po_index"), "info"),
            ("Komplain perlu kirim ulang",
             _count(ReturnComplaint, ReturnComplaint.status == C.C_FOLLOWED,
                    ReturnComplaint.po_id.in_(select(PurchaseOrder.id).where(
                        PurchaseOrder.vendor_id == user.vendor_id))),
             url_for("vendor.po_index"), "danger"),
        ]
    elif role == C.GD:
        cards += [
            ("PO menunggu penerimaan",
             _count(PurchaseOrder, PurchaseOrder.status.in_((C.PO_SHIPPED, C.PO_PARTIAL)),
                    PurchaseOrder.warehouse_id == user.warehouse_id),
             url_for("gr.waiting"), "danger"),
            ("GR dibuat", _count(GoodsReceipt, GoodsReceipt.po_id.in_(
                select(PurchaseOrder.id).where(PurchaseOrder.warehouse_id == user.warehouse_id))),
             url_for("gr.receipts"), "info"),
        ]
    elif role == C.AD:
        cards += [
            ("Pengguna aktif", _count(User, User.active.is_(True)), url_for("users.index"), "primary"),
            ("PR total", _count(PurchaseRequest), url_for("pr.index"), "info"),
            ("PO total", _count(PurchaseOrder), url_for("po.index"), "info"),
        ]
    return cards


@bp.route("/")
@login_required
def dashboard():
    notifs = db.session.execute(
        select(Notification).where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(5)
    ).scalars().all()
    return render_template("dashboard.html", cards=_cards_for(current_user), notifs=notifs)


@bp.route("/notifications")
@login_required
def notifications():
    rows = db.session.execute(
        select(Notification).where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(200)
    ).scalars().all()
    return render_template("notifications.html", rows=rows)


@bp.route("/notifications/<int:notif_id>/open", methods=["POST"])
@login_required
def notification_open(notif_id):
    n = db.session.get(Notification, notif_id)
    if n is None or n.user_id != current_user.id:
        abort(404)
    n.is_read = True
    db.session.commit()
    return redirect(n.link or url_for("main.notifications"))


@bp.route("/notifications/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    db.session.execute(
        Notification.__table__.update()
        .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.session.commit()
    flash("Semua notifikasi ditandai sudah dibaca.", "info")
    return redirect(url_for("main.notifications"))


@bp.route("/files/<kind>/<int:obj_id>")
@roles_required(C.SP, C.MP, C.AD, C.VN, C.GD)
def attachment(kind, obj_id):
    """Unduh lampiran penawaran atau bukti komplain dengan pengecekan hak akses."""
    if kind == "quotation":
        obj = db.session.get(Quotation, obj_id)
        stored, name = (obj.attachment_path, obj.attachment_name) if obj else (None, None)
        allowed = obj and (current_user.role in (C.SP, C.MP, C.AD) or
                           (current_user.role == C.VN and obj.vendor_id == current_user.vendor_id))
    elif kind == "complaint":
        obj = db.session.get(ReturnComplaint, obj_id)
        stored, name = (obj.evidence_path, obj.evidence_name) if obj else (None, None)
        allowed = obj and (current_user.role in (C.SP, C.MP, C.AD, C.GD) or
                           (current_user.role == C.VN and obj.po.vendor_id == current_user.vendor_id))
    else:
        abort(404)
    if not allowed:
        abort(403 if obj else 404)
    if not stored or not STORED_NAME_RE.match(stored):
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], stored,
                               download_name=name or stored, as_attachment=True)
