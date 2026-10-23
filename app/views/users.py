"""Modul 1: manajemen pengguna dan akun vendor (fitur 1.3, 1.4)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import Department, User, Vendor, Warehouse
from ..services import audit

bp = Blueprint("users", __name__, url_prefix="/users")


def _form_options():
    return {
        "roles": C.ROLE_LABELS,
        "departments": db.session.execute(select(Department).order_by(Department.name)).scalars().all(),
        "supervisors": db.session.execute(
            select(User).where(User.role == C.AT, User.active.is_(True)).order_by(User.full_name)
        ).scalars().all(),
        "vendors": db.session.execute(select(Vendor).order_by(Vendor.name)).scalars().all(),
        "warehouses": db.session.execute(select(Warehouse).order_by(Warehouse.name)).scalars().all(),
    }


def _int_or_none(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def _apply_form(user, form, creating):
    """Isi objek User dari form. Mengembalikan daftar kesalahan."""
    errors = []
    if creating:
        user.username = (form.get("username") or "").strip().lower()
        if not user.username:
            errors.append("Username wajib diisi.")
        password = form.get("password") or ""
        if len(password) < 8:
            errors.append("Password minimal 8 karakter.")
        else:
            user.set_password(password)
    user.full_name = (form.get("full_name") or "").strip()
    user.email = (form.get("email") or "").strip() or None
    role = form.get("role")
    if not user.full_name:
        errors.append("Nama lengkap wajib diisi.")
    if role not in C.ROLE_LABELS:
        errors.append("Role tidak valid.")
    user.role = role
    user.department_id = _int_or_none(form.get("department_id"))
    user.supervisor_id = _int_or_none(form.get("supervisor_id"))
    user.vendor_id = _int_or_none(form.get("vendor_id"))
    user.warehouse_id = _int_or_none(form.get("warehouse_id"))
    if role == C.PM and not (user.department_id and user.supervisor_id):
        errors.append("Pemohon wajib punya departemen dan atasan.")
    if role == C.AT and not user.department_id:
        errors.append("Atasan wajib punya departemen.")
    if role == C.VN and not user.vendor_id:
        errors.append("Akun vendor wajib terhubung ke master vendor.")
    if role == C.GD and not user.warehouse_id:
        errors.append("Petugas gudang wajib terhubung ke gudang.")
    if user.supervisor_id is not None and user.id is not None and user.supervisor_id == user.id:
        errors.append("Atasan tidak boleh diri sendiri.")
    # kolom yang tidak relevan untuk role dikosongkan agar data konsisten
    if role != C.VN:
        user.vendor_id = None
    if role != C.GD:
        user.warehouse_id = None
    if role != C.PM:
        user.supervisor_id = None
    return errors


@bp.route("/")
@roles_required(C.AD)
def index():
    rows = db.session.execute(select(User).order_by(User.role, User.username)).scalars().all()
    return render_template("users/list.html", rows=rows)


@bp.route("/new", methods=["GET", "POST"])
@roles_required(C.AD)
def new():
    user = User(active=True)
    if request.method == "POST":
        errors = _apply_form(user, request.form, creating=True)
        if not errors:
            db.session.add(user)
            try:
                db.session.flush()
                audit("BUAT_USER", "user", user.id, f"{user.username} ({user.role})")
                db.session.commit()
                flash("Pengguna ditambahkan.", "success")
                return redirect(url_for("users.index"))
            except IntegrityError:
                db.session.rollback()
                errors.append("Username sudah dipakai.")
        for e in errors:
            flash(e, "danger")
    return render_template("users/form.html", user=user, creating=True, **_form_options())


@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required(C.AD)
def edit(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if request.method == "POST":
        errors = _apply_form(user, request.form, creating=False)
        # akun sendiri tidak boleh dinonaktifkan agar admin tidak terkunci
        active = request.form.get("active") == "on"
        if user.id == current_user.id and not active:
            errors.append("Anda tidak dapat menonaktifkan akun sendiri.")
        if user.id == current_user.id and user.role != C.AD:
            errors.append("Anda tidak dapat mengubah role akun sendiri.")
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "danger")
            user = db.session.get(User, user_id)
        else:
            user.active = active
            audit("UBAH_USER", "user", user.id, f"{user.username} role={user.role} aktif={user.active}")
            db.session.commit()
            flash("Pengguna diperbarui.", "success")
            return redirect(url_for("users.index"))
    return render_template("users/form.html", user=user, creating=False, **_form_options())


@bp.route("/<int:user_id>/reset-password", methods=["POST"])
@roles_required(C.AD)
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    new_password = request.form.get("new_password") or ""
    if len(new_password) < 8:
        flash("Password baru minimal 8 karakter.", "danger")
    else:
        user.set_password(new_password)
        audit("RESET_PASSWORD", "user", user.id, user.username)
        db.session.commit()
        flash(f"Password {user.username} direset.", "success")
    return redirect(url_for("users.edit", user_id=user.id))


@bp.route("/vendor-account/<int:vendor_id>", methods=["GET", "POST"])
@roles_required(C.AD, C.SP)
def vendor_account(vendor_id):
    """Fitur 1.4: buat akun login vendor yang terhubung ke master vendor."""
    vendor = db.session.get(Vendor, vendor_id)
    if vendor is None:
        abort(404)
    existing = db.session.execute(select(User).where(User.vendor_id == vendor.id)).scalars().all()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip() or vendor.name
        password = request.form.get("password") or ""
        if not username:
            flash("Username wajib diisi.", "danger")
        elif len(password) < 8:
            flash("Password minimal 8 karakter.", "danger")
        else:
            user = User(username=username, full_name=full_name, role=C.VN, vendor_id=vendor.id,
                        email=vendor.email, active=True)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.flush()
                audit("BUAT_AKUN_VENDOR", "user", user.id, f"{username} -> {vendor.name}")
                db.session.commit()
                flash("Akun vendor dibuat.", "success")
                return redirect(url_for("users.vendor_account", vendor_id=vendor.id))
            except IntegrityError:
                db.session.rollback()
                flash("Username sudah dipakai.", "danger")
    return render_template("users/vendor_account.html", vendor=vendor, existing=existing)
