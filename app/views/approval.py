"""Modul 4: approval PR oleh atasan dan approval PO oleh manajer procurement."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import PurchaseOrder, PurchaseRequest, User
from ..services import (approval_history, audit, budget_summary, log_approval, notify,
                        users_with_role)

bp = Blueprint("approval", __name__, url_prefix="/approval")

# nilai tombol di form -> (keputusan, status baru)
PR_DECISIONS = {"setuju": (C.D_APPROVE, C.PR_APPROVED), "revisi": (C.D_REVISE, C.PR_REVISION),
                "tolak": (C.D_REJECT, C.PR_REJECTED)}
PO_DECISIONS = {"setuju": (C.D_APPROVE, C.PO_APPROVED), "revisi": (C.D_REVISE, C.PO_REVISION)}


# ------------------------------------------------------------------ PR (4.1, 4.2)
@bp.route("/pr")
@roles_required(C.AT)
def pr_queue():
    """Antrian PR berstatus Diajukan milik bawahan atasan yang login."""
    rows = db.session.execute(
        select(PurchaseRequest)
        .where(PurchaseRequest.status == C.PR_SUBMITTED,
               PurchaseRequest.requester_id.in_(select(User.id).where(User.supervisor_id == current_user.id)))
        .order_by(PurchaseRequest.submitted_at)
    ).scalars().all()
    return render_template("approval/pr_queue.html", rows=rows)


@bp.route("/pr/<int:pr_id>", methods=["GET", "POST"])
@roles_required(C.AT)
def pr_review(pr_id):
    pr = db.session.get(PurchaseRequest, pr_id)
    if pr is None:
        abort(404)
    # atasan hanya boleh memutuskan PR bawahannya, dan tidak boleh PR miliknya sendiri
    if pr.requester.supervisor_id != current_user.id or pr.requester_id == current_user.id:
        abort(403)

    if request.method == "POST":
        if pr.status != C.PR_SUBMITTED:
            flash("PR ini sudah diputuskan atau tidak berstatus Diajukan.", "warning")
            return redirect(url_for("approval.pr_queue"))
        choice = request.form.get("decision")
        note = (request.form.get("note") or "").strip()
        if choice not in PR_DECISIONS:
            flash("Pilih keputusan terlebih dahulu.", "danger")
        elif choice in ("revisi", "tolak") and not note:
            flash("Catatan wajib diisi untuk keputusan revisi atau tolak.", "danger")
        else:
            decision, new_status = PR_DECISIONS[choice]
            if choice == "setuju":
                limit, _used, remaining = budget_summary(pr.department_id, pr.period)
                if limit is None or pr.total > remaining:
                    flash("Anggaran departemen tidak mencukupi untuk menyetujui PR ini.", "danger")
                    return redirect(url_for("approval.pr_review", pr_id=pr.id))
            pr.status = new_status
            log_approval("PR", pr.id, decision, note)
            audit(f"PR_{choice.upper()}", "PR", pr.id, f"{pr.number}: {note}" if note else pr.number)
            link = url_for("pr.detail", pr_id=pr.id)
            msg = f"PR {pr.number} {decision.lower()} oleh {current_user.full_name}."
            if note:
                msg += f" Catatan: {note}"
            notify(pr.requester, msg, link)
            if choice == "setuju":
                notify(users_with_role(C.SP), f"PR {pr.number} disetujui dan siap diverifikasi untuk RFQ.", link)
            db.session.commit()
            flash(f"Keputusan tersimpan: {decision}.", "success")
            return redirect(url_for("approval.pr_queue"))

    limit, used, remaining = budget_summary(pr.department_id, pr.period)
    return render_template("approval/pr_review.html", pr=pr, history=approval_history("PR", pr.id),
                           budget=(limit, used, remaining))


# ------------------------------------------------------------------ PO (4.3)
@bp.route("/po")
@roles_required(C.MP)
def po_queue():
    rows = db.session.execute(
        select(PurchaseOrder).where(PurchaseOrder.status == C.PO_WAITING).order_by(PurchaseOrder.submitted_at)
    ).scalars().all()
    return render_template("approval/po_queue.html", rows=rows)


@bp.route("/po/<int:po_id>", methods=["GET", "POST"])
@roles_required(C.MP)
def po_review(po_id):
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        abort(404)
    if request.method == "POST":
        if po.status != C.PO_WAITING:
            flash("PO ini tidak sedang menunggu approval.", "warning")
            return redirect(url_for("approval.po_queue"))
        choice = request.form.get("decision")
        note = (request.form.get("note") or "").strip()
        if choice not in PO_DECISIONS:
            flash("Pilih keputusan terlebih dahulu.", "danger")
        elif choice == "revisi" and not note:
            flash("Catatan wajib diisi untuk keputusan revisi.", "danger")
        else:
            decision, new_status = PO_DECISIONS[choice]
            po.status = new_status
            log_approval("PO", po.id, decision, note)
            audit(f"PO_{choice.upper()}", "PO", po.id, f"{po.number}: {note}" if note else po.number)
            msg = f"PO {po.number} {decision.lower()} oleh {current_user.full_name}."
            if note:
                msg += f" Catatan: {note}"
            notify(po.created_by, msg, url_for("po.detail", po_id=po.id))
            db.session.commit()
            flash(f"Keputusan tersimpan: {decision}.", "success")
            return redirect(url_for("approval.po_queue"))
    return render_template("approval/po_review.html", po=po, history=approval_history("PO", po.id))
