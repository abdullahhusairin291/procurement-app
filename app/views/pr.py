"""Modul 3: Purchase Request (fitur 3.1 - 3.6)."""
from datetime import datetime, time, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import Department, Item, PRItem, PurchaseRequest, User
from ..services import (approval_history, audit, budget_summary, last_approval_note, next_number,
                        notify, pr_timeline, validate_pr_for_submit)
from ..utils import now, parse_date, parse_decimal, plain_number, today

bp = Blueprint("pr", __name__, url_prefix="/pr")

EDITABLE = (C.PR_DRAFT, C.PR_REVISION)


def can_view_pr(user, pr):
    """Aturan visibilitas PR sesuai tabel RBAC."""
    if user.role == C.AD:
        return True
    if user.role == C.PM:
        return pr.requester_id == user.id
    if user.role == C.AT:
        return pr.requester.supervisor_id == user.id and pr.status != C.PR_DRAFT
    if user.role in (C.MP, C.SP):
        return pr.status != C.PR_DRAFT
    return False


def _get_pr_or_404(pr_id):
    pr = db.session.get(PurchaseRequest, pr_id)
    if pr is None:
        abort(404)
    return pr


def _owned_editable(pr_id, statuses=EDITABLE):
    """PR milik pengguna yang sedang login dan masih boleh diubah."""
    pr = _get_pr_or_404(pr_id)
    if pr.requester_id != current_user.id:
        abort(403)
    if pr.status not in statuses:
        flash("PR pada status ini tidak dapat diubah.", "warning")
        return pr, False
    return pr, True


def _read_form(form):
    """Baca header dan baris item dari form. Mengembalikan (header, rows, errors)."""
    errors = []
    needed_raw = (form.get("needed_date") or "").strip()
    needed = parse_date(needed_raw) if needed_raw else None
    if needed_raw and needed is None:
        errors.append("Tanggal dibutuhkan tidak valid.")
    header = {"needed_date": needed, "justification": (form.get("justification") or "").strip()}

    rows = []
    for idx, (item_id, spec, qty_raw, price_raw) in enumerate(zip(
            form.getlist("item_id"), form.getlist("spec"), form.getlist("qty"), form.getlist("price")),
            start=1):
        if not (item_id or "").strip():
            continue  # baris kosong diabaikan
        item = db.session.get(Item, int(item_id)) if item_id.isdigit() else None
        if item is None or not item.active:
            errors.append(f"Baris {idx}: barang/jasa tidak valid.")
            continue
        qty = parse_decimal(qty_raw)
        if qty is None or qty <= 0:
            errors.append(f"Baris {idx}: qty harus lebih dari 0.")
            continue
        price = parse_decimal(price_raw, default=item.ref_price) if (price_raw or "").strip() else item.ref_price
        if price is None or price < 0:
            errors.append(f"Baris {idx}: estimasi harga tidak valid.")
            continue
        rows.append({"item_id": item.id, "spec": (spec or "").strip() or None, "qty": qty, "price": price})
    return header, rows, errors


def _apply(pr, header, rows):
    pr.needed_date = header["needed_date"]
    pr.justification = header["justification"]
    pr.items.clear()
    for r in rows:
        pr.items.append(PRItem(item_id=r["item_id"], spec=r["spec"], qty=r["qty"], est_price=r["price"]))


def _submit(pr):
    """Submit PR (fitur 3.3). True bila berhasil."""
    errors = validate_pr_for_submit(pr)
    if errors:
        for e in errors:
            flash(e, "danger")
        return False
    pr.status = C.PR_SUBMITTED
    pr.submitted_at = now()
    notify(pr.requester.supervisor, f"PR {pr.number} dari {pr.requester.full_name} menunggu approval Anda.",
           url_for("approval.pr_review", pr_id=pr.id))
    audit("SUBMIT_PR", "PR", pr.id, pr.number)
    flash(f"PR {pr.number} diajukan ke atasan.", "success")
    return True


def _form_context(pr=None, form=None):
    """Data untuk form PR: katalog barang dan baris yang sudah terisi (bila ada)."""
    catalog = db.session.execute(select(Item).where(Item.active.is_(True)).order_by(Item.name)).scalars().all()
    if form is not None:  # tampilkan ulang isian pengguna setelah gagal validasi
        rows = [{"item_id": i, "spec": s, "qty": q, "price": p} for i, s, q, p in zip(
            form.getlist("item_id"), form.getlist("spec"), form.getlist("qty"), form.getlist("price"))]
        needed, just = form.get("needed_date", ""), form.get("justification", "")
    elif pr is not None:
        rows = [{"item_id": str(i.item_id), "spec": i.spec or "", "qty": plain_number(i.qty),
                 "price": plain_number(i.est_price)} for i in pr.items]
        needed = pr.needed_date.isoformat() if pr.needed_date else ""
        just = pr.justification or ""
    else:
        rows, needed, just = [], "", ""
    return {"pr": pr, "catalog": catalog, "min_date": today().isoformat(), "rows": rows,
            "needed_value": needed, "just_value": just}


@bp.route("/")
@login_required
def index():
    if current_user.role not in (C.PM, C.AT, C.MP, C.SP, C.AD):
        abort(403)
    stmt = select(PurchaseRequest)
    if current_user.role == C.PM:
        stmt = stmt.where(PurchaseRequest.requester_id == current_user.id)
    elif current_user.role == C.AT:
        stmt = stmt.where(PurchaseRequest.status != C.PR_DRAFT, PurchaseRequest.requester_id.in_(
            select(User.id).where(User.supervisor_id == current_user.id)))
    elif current_user.role in (C.MP, C.SP):
        stmt = stmt.where(PurchaseRequest.status != C.PR_DRAFT)

    status = request.args.get("status", "")
    dept = request.args.get("department_id", "")
    date_from = parse_date(request.args.get("date_from"))
    date_to = parse_date(request.args.get("date_to"))
    keyword = (request.args.get("q") or "").strip()
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    if dept.isdigit():
        stmt = stmt.where(PurchaseRequest.department_id == int(dept))
    if date_from:
        stmt = stmt.where(PurchaseRequest.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(PurchaseRequest.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(PurchaseRequest.number.ilike(like), PurchaseRequest.justification.ilike(like)))
    rows = db.session.execute(stmt.order_by(PurchaseRequest.id.desc()).limit(300)).scalars().all()
    statuses = [C.PR_DRAFT, C.PR_SUBMITTED, C.PR_APPROVED, C.PR_REVISION, C.PR_REJECTED,
                C.PR_PROCESSED, C.PR_DONE]
    departments = db.session.execute(select(Department).order_by(Department.name)).scalars().all()
    return render_template("pr/list.html", rows=rows, statuses=statuses, departments=departments,
                           f=request.args)


@bp.route("/new", methods=["GET", "POST"])
@roles_required(C.PM)
def new():
    if not current_user.department_id:
        flash("Akun Anda belum memiliki departemen. Hubungi administrator.", "danger")
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        header, rows, errors = _read_form(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            pr = PurchaseRequest(number=next_number("PR"), requester_id=current_user.id,
                                 department_id=current_user.department_id, period=today().year,
                                 status=C.PR_DRAFT)
            _apply(pr, header, rows)
            db.session.add(pr)
            db.session.flush()
            audit("BUAT_PR", "PR", pr.id, pr.number)
            if request.form.get("action") == "submit":
                _submit(pr)
            db.session.commit()
            return redirect(url_for("pr.detail", pr_id=pr.id))
    return render_template("pr/form.html", **_form_context(form=request.form if request.method == "POST" else None))


@bp.route("/<int:pr_id>/edit", methods=["GET", "POST"])
@roles_required(C.PM)
def edit(pr_id):
    pr, ok = _owned_editable(pr_id)
    if not ok:
        return redirect(url_for("pr.detail", pr_id=pr.id))
    if request.method == "POST":
        header, rows, errors = _read_form(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            _apply(pr, header, rows)
            audit("UBAH_PR", "PR", pr.id, pr.number)
            if request.form.get("action") == "submit":
                _submit(pr)
            else:
                flash("Perubahan disimpan.", "success")
            db.session.commit()
            return redirect(url_for("pr.detail", pr_id=pr.id))
    note = last_approval_note("PR", pr.id) if pr.status == C.PR_REVISION else None
    return render_template("pr/form.html", **_form_context(pr, request.form if request.method == "POST" else None),
                           revision_note=note)


@bp.route("/<int:pr_id>/submit", methods=["POST"])
@roles_required(C.PM)
def submit(pr_id):
    pr, ok = _owned_editable(pr_id)
    if ok:
        _submit(pr)
        db.session.commit()
    return redirect(url_for("pr.detail", pr_id=pr.id))


@bp.route("/<int:pr_id>/delete", methods=["POST"])
@roles_required(C.PM)
def delete(pr_id):
    pr, ok = _owned_editable(pr_id, statuses=(C.PR_DRAFT,))
    if ok:
        number = pr.number
        db.session.delete(pr)
        audit("HAPUS_PR", "PR", pr_id, number)
        db.session.commit()
        flash(f"Draft {number} dihapus.", "info")
        return redirect(url_for("pr.index"))
    return redirect(url_for("pr.detail", pr_id=pr.id))


@bp.route("/<int:pr_id>")
@login_required
def detail(pr_id):
    pr = _get_pr_or_404(pr_id)
    if not can_view_pr(current_user, pr):
        abort(403)
    events, rfqs, pos = pr_timeline(pr)
    limit, used, remaining = budget_summary(pr.department_id, pr.period)
    return render_template(
        "pr/detail.html", pr=pr, events=events, rfqs=rfqs, pos=pos,
        history=approval_history("PR", pr.id),
        budget=(limit, used, remaining),
        revision_note=last_approval_note("PR", pr.id) if pr.status == C.PR_REVISION else None,
        is_owner=pr.requester_id == current_user.id,
        can_follow=current_user.role in (C.SP, C.MP, C.AD),
    )
