"""Logika bersama: penomoran, audit log, notifikasi, anggaran, linimasa PR, kuotasi."""
from datetime import datetime
from decimal import Decimal

from flask_login import current_user
from sqlalchemy import func, select

from . import constants as C
from .extensions import db
from .models import (ApprovalLog, AuditLog, Budget, DocumentSequence, Notification, PRItem,
                      PurchaseOrder, PurchaseRequest, Quotation, QuotationItem, RFQ, User)
from .utils import now, parse_decimal, plain_number, today


# -------------------------------------------------------- penomoran (fitur 2.7)
def next_number(doc_type, when=None):
    """Nomor unik per jenis dokumen per bulan, mis. PR-202610-0001."""
    period = (when or today()).strftime("%Y%m")
    seq = db.session.execute(
        select(DocumentSequence)
        .where(DocumentSequence.doc_type == doc_type, DocumentSequence.period == period)
        .with_for_update()
    ).scalar_one_or_none()
    if seq is None:
        seq = DocumentSequence(doc_type=doc_type, period=period, last_number=0)
        db.session.add(seq)
        db.session.flush()
    seq.last_number += 1
    db.session.flush()
    return f"{C.DOC_PREFIX[doc_type]}-{period}-{seq.last_number:04d}"


# ------------------------------------------------------------ audit (fitur 9.1)
def audit(action, entity=None, entity_id=None, detail=None, user=None):
    """Catat aktivitas penting. Pemanggil yang melakukan commit."""
    actor = user if user is not None else (current_user if current_user.is_authenticated else None)
    db.session.add(AuditLog(
        user_id=actor.id if actor else None,
        username=actor.username if actor else None,
        action=action, entity=entity, entity_id=entity_id, detail=detail,
    ))


# ------------------------------------------------------- notifikasi (fitur 8.1)
def notify(users, message, link=None):
    """Kirim notifikasi dalam aplikasi ke satu atau beberapa pengguna."""
    if users is None:
        return
    if isinstance(users, User):
        users = [users]
    seen = set()
    for u in users:
        if u is None or u.id in seen:
            continue
        seen.add(u.id)
        db.session.add(Notification(user_id=u.id, message=message[:300], link=link))


def users_with_role(role):
    return db.session.execute(
        select(User).where(User.role == role, User.active.is_(True))
    ).scalars().all()


def vendor_users(vendor_ids):
    if not vendor_ids:
        return []
    return db.session.execute(
        select(User).where(User.role == C.VN, User.active.is_(True), User.vendor_id.in_(vendor_ids))
    ).scalars().all()


# ----------------------------------------------------------- anggaran (fitur 2.2)
def budget_summary(department_id, period):
    """(pagu, terpakai, sisa). Terpakai dihitung dari PR Disetujui/Diproses/Selesai lewat query."""
    limit = db.session.execute(
        select(Budget.amount).where(Budget.department_id == department_id, Budget.period == period)
    ).scalar_one_or_none()
    used = db.session.execute(
        select(func.coalesce(func.sum(PRItem.qty * PRItem.est_price), 0))
        .select_from(PRItem)
        .join(PurchaseRequest, PRItem.pr_id == PurchaseRequest.id)
        .where(
            PurchaseRequest.department_id == department_id,
            PurchaseRequest.period == period,
            PurchaseRequest.status.in_(C.PR_BUDGET_STATUSES),
        )
    ).scalar_one()
    limit = Decimal(str(limit)) if limit is not None else None
    used = Decimal(str(used or 0))
    remaining = (limit - used) if limit is not None else None
    return limit, used, remaining


def validate_pr_for_submit(pr):
    """Aturan submit PR (fitur 3.3). Mengembalikan daftar pesan kesalahan."""
    errors = []
    if not pr.justification or not pr.justification.strip():
        errors.append("Justifikasi kebutuhan wajib diisi.")
    if pr.needed_date is None:
        errors.append("Tanggal dibutuhkan wajib diisi.")
    elif pr.needed_date < today():
        errors.append("Tanggal dibutuhkan tidak boleh lebih awal dari hari ini.")
    if not pr.items:
        errors.append("Minimal harus ada 1 item.")
    for idx, it in enumerate(pr.items, start=1):
        if it.qty is None or it.qty <= 0:
            errors.append(f"Item #{idx}: qty harus lebih dari 0.")
    if pr.requester.supervisor_id is None:
        errors.append("Akun Anda belum memiliki atasan. Hubungi administrator.")
    if pr.items and not errors:
        limit, _used, remaining = budget_summary(pr.department_id, pr.period)
        if limit is None:
            errors.append(f"Anggaran departemen untuk periode {pr.period} belum ditetapkan.")
        elif pr.total > remaining:
            errors.append("Total estimasi melebihi sisa anggaran departemen.")
    return errors


def log_approval(doc_type, doc_id, decision, note):
    db.session.add(ApprovalLog(doc_type=doc_type, doc_id=doc_id, actor_id=current_user.id,
                               decision=decision, note=note or None))


def approval_history(doc_type, doc_id):
    return db.session.execute(
        select(ApprovalLog).where(ApprovalLog.doc_type == doc_type, ApprovalLog.doc_id == doc_id)
        .order_by(ApprovalLog.created_at, ApprovalLog.id)
    ).scalars().all()


def last_approval_note(doc_type, doc_id):
    logs = approval_history(doc_type, doc_id)
    return logs[-1] if logs else None


# ---------------------------------------------------------- linimasa (fitur 3.6)
def pr_timeline(pr):
    """Daftar peristiwa PR sampai barang diterima, terurut waktu. Item: (waktu, teks)."""
    ev = [(pr.created_at, f"PR dibuat oleh {pr.requester.full_name} (Draft)")]
    if pr.submitted_at:
        ev.append((pr.submitted_at, "PR diajukan ke atasan"))
    for log in approval_history("PR", pr.id):
        txt = f"Atasan {log.actor.full_name}: {log.decision}"
        if log.note:
            txt += f" - {log.note}"
        ev.append((log.created_at, txt))
    if pr.verified_at:
        ev.append((pr.verified_at, f"PR diverifikasi oleh {pr.verified_by.full_name}"))

    rfqs = db.session.execute(select(RFQ).where(RFQ.pr_id == pr.id).order_by(RFQ.id)).scalars().all()
    for r in rfqs:
        ev.append((r.created_at, f"RFQ {r.number} dibuat"))
        if r.sent_at:
            ev.append((r.sent_at, f"RFQ {r.number} dikirim ke {len(r.vendors)} vendor"))
        for q in r.quotations:
            ev.append((q.submitted_at, f"Penawaran {q.vendor.name} masuk ({q.entered_via})"))
        if r.selected_at:
            ev.append((r.selected_at, f"Vendor pemenang ditetapkan: {r.winner.vendor.name}"))

    pos = db.session.execute(
        select(PurchaseOrder).where(PurchaseOrder.pr_id == pr.id).order_by(PurchaseOrder.id)
    ).scalars().all()
    for po in pos:
        ev.append((po.created_at, f"PO {po.number} dibuat"))
        for log in approval_history("PO", po.id):
            txt = f"Manajer {log.actor.full_name} atas PO {po.number}: {log.decision}"
            if log.note:
                txt += f" - {log.note}"
            ev.append((log.created_at, txt))
        if po.issued_at:
            ev.append((po.issued_at, f"PO {po.number} terbit dan dikirim ke vendor"))
        if po.confirmed_at:
            ev.append((po.confirmed_at, f"Vendor mengonfirmasi PO {po.number}"))
        if po.shipped_at:
            ev.append((po.shipped_at, f"Vendor mengirim barang (surat jalan {po.delivery_note_no})"))
        for gr in po.receipts:
            ev.append((gr.created_at, f"GR {gr.number}: {gr.status}"))
            if gr.verified_at:
                ev.append((gr.verified_at, f"GR {gr.number} diverifikasi"))
        for c in po.complaints:
            ev.append((c.created_at, f"Komplain/retur dibuat ({c.status})"))
            if c.followup_at:
                ev.append((c.followup_at, "Komplain ditindaklanjuti staf procurement"))
            if c.resend_at:
                ev.append((c.resend_at, "Vendor mengirim ulang barang"))
        if po.closed_at:
            ev.append((po.closed_at, f"PO {po.number} ditutup (Selesai)"))
    ev.sort(key=lambda e: e[0] or datetime.min)
    return ev, rfqs, pos


# ------------------------------------------------------ kuotasi (fitur 5.6/5.7)
def parse_quotation_form(rfq, form):
    """Baca isian penawaran dari form. Mengembalikan (data, errors).

    data = {lead_time, payment_terms, valid_until, notes, prices: {rfq_item_id: Decimal|None}}
    Harga kosong diperbolehkan (penawaran tidak lengkap akan diberi tanda)."""
    from .utils import parse_date
    errors = []
    prices = {}
    for ri in rfq.items:
        raw = (form.get(f"price_{ri.id}") or "").strip()
        if not raw:
            prices[ri.id] = None
            continue
        val = parse_decimal(raw)
        if val is None or val < 0:
            errors.append(f"Harga untuk '{ri.item.name}' tidak valid.")
            prices[ri.id] = None
        else:
            prices[ri.id] = val
    if all(v is None for v in prices.values()):
        errors.append("Isi harga minimal untuk satu item.")

    lead_raw = (form.get("lead_time_days") or "").strip()
    lead = None
    if lead_raw:
        if lead_raw.isdigit():
            lead = int(lead_raw)
        else:
            errors.append("Lead time harus berupa angka (hari).")

    valid_raw = (form.get("valid_until") or "").strip()
    valid_until = parse_date(valid_raw) if valid_raw else None
    if valid_raw and valid_until is None:
        errors.append("Masa berlaku tidak valid.")

    data = {
        "lead_time": lead,
        "payment_terms": (form.get("payment_terms") or "").strip()[:150] or None,
        "valid_until": valid_until,
        "notes": (form.get("notes") or "").strip() or None,
        "prices": prices,
    }
    return data, errors


def save_quotation(rfq, vendor_id, data, via, user, attachment=None):
    """Simpan (buat/ubah) penawaran vendor. Mengembalikan objek Quotation."""
    q = next((x for x in rfq.quotations if x.vendor_id == vendor_id), None)
    if q is None:
        q = Quotation(rfq_id=rfq.id, vendor_id=vendor_id)
        db.session.add(q)
        rfq.quotations.append(q)
    q.lead_time_days = data["lead_time"]
    q.payment_terms = data["payment_terms"]
    q.valid_until = data["valid_until"]
    q.notes = data["notes"]
    q.entered_via = via
    q.submitted_by_id = user.id
    q.submitted_at = now()
    q.status = C.Q_SUBMITTED
    if attachment and attachment[0]:
        q.attachment_name, q.attachment_path = attachment
    q.items.clear()
    db.session.flush()
    for rfq_item_id, price in data["prices"].items():
        if price is not None:
            q.items.append(QuotationItem(rfq_item_id=rfq_item_id, unit_price=price))
    if rfq.status == C.RFQ_SENT:
        rfq.status = C.RFQ_QUOTED
    return q


def quotation_prefill(rfq, q=None, form=None):
    """Nilai awal form penawaran: dari isian yang gagal divalidasi, dari penawaran tersimpan, atau kosong."""
    if form is not None:
        return {"lead_time": form.get("lead_time_days", ""), "payment_terms": form.get("payment_terms", ""),
                "valid_until": form.get("valid_until", ""), "notes": form.get("notes", ""),
                "prices": {ri.id: form.get(f"price_{ri.id}", "") for ri in rfq.items}}
    if q is not None:
        prices = {}
        for ri in rfq.items:
            qi = q.price_for(ri.id)
            prices[ri.id] = plain_number(qi.unit_price) if qi else ""
        return {"lead_time": q.lead_time_days if q.lead_time_days is not None else "",
                "payment_terms": q.payment_terms or "",
                "valid_until": q.valid_until.isoformat() if q.valid_until else "",
                "notes": q.notes or "", "prices": prices}
    return {"lead_time": "", "payment_terms": "", "valid_until": "", "notes": "",
            "prices": {ri.id: "" for ri in rfq.items}}
