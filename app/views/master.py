"""Modul 2: master data dengan satu set rute generik yang digerakkan oleh tabel MASTERS."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import Budget, Category, Department, Item, Unit, Vendor, Warehouse
from ..services import audit, budget_summary
from ..utils import parse_decimal, today

bp = Blueprint("master", __name__, url_prefix="/master")


class Field:
    """Deskripsi satu kolom pada form master. kind: text, textarea, int, money, select, bool."""

    def __init__(self, name, label, kind="text", required=False, model=None, label_attr="name",
                 choices=None, default=None):
        self.name, self.label, self.kind = name, label, kind
        self.required, self.model, self.label_attr = required, model, label_attr
        self.choices, self.default = choices, default

    def options(self):
        if self.choices:
            return [(c, c) for c in self.choices]
        rows = db.session.execute(select(self.model).order_by(getattr(self.model, self.label_attr))).scalars()
        return [(r.id, getattr(r, self.label_attr)) for r in rows]


# entity -> konfigurasi. roles = yang boleh membuka dan mengubah; view_roles = boleh melihat saja.
MASTERS = {
    "departments": dict(
        model=Department, title="Departemen", roles=(C.AD,), view_roles=(),
        columns=[("code", "Kode"), ("name", "Nama")],
        fields=[Field("code", "Kode", required=True), Field("name", "Nama", required=True)],
        order=Department.name),
    "budgets": dict(
        model=Budget, title="Anggaran Departemen", roles=(C.AD,), view_roles=(C.MP,),
        columns=[("department.name", "Departemen"), ("period", "Periode (tahun)"), ("amount", "Pagu|money")],
        fields=[Field("department_id", "Departemen", "select", True, model=Department),
                Field("period", "Periode (tahun)", "int", True, default=lambda: today().year),
                Field("amount", "Pagu anggaran", "money", True)],
        order=Budget.period.desc()),
    "categories": dict(
        model=Category, title="Kategori Barang/Jasa", roles=(C.AD, C.SP), view_roles=(),
        columns=[("name", "Nama")], fields=[Field("name", "Nama kategori", required=True)],
        order=Category.name),
    "units": dict(
        model=Unit, title="Satuan", roles=(C.AD, C.SP), view_roles=(),
        columns=[("name", "Satuan")], fields=[Field("name", "Nama satuan", required=True)],
        order=Unit.name),
    "items": dict(
        model=Item, title="Barang/Jasa", roles=(C.AD, C.SP), view_roles=(), has_active=True,
        columns=[("code", "Kode"), ("name", "Nama"), ("kind", "Jenis"), ("category.name", "Kategori"),
                 ("unit.name", "Satuan"), ("ref_price", "Harga acuan|money")],
        fields=[Field("code", "Kode", required=True), Field("name", "Nama", required=True),
                Field("kind", "Jenis", "select", True, choices=["Barang", "Jasa"]),
                Field("category_id", "Kategori", "select", False, model=Category),
                Field("unit_id", "Satuan", "select", True, model=Unit),
                Field("spec", "Spesifikasi", "textarea"),
                Field("ref_price", "Harga acuan", "money", True)],
        order=Item.code),
    "vendors": dict(
        model=Vendor, title="Vendor", roles=(C.AD, C.SP), view_roles=(), has_active=True,
        columns=[("code", "Kode"), ("name", "Nama"), ("contact_name", "Kontak"), ("phone", "Telepon"),
                 ("category.name", "Kategori")],
        fields=[Field("code", "Kode", required=True), Field("name", "Nama vendor", required=True),
                Field("address", "Alamat", "textarea"), Field("contact_name", "Nama kontak"),
                Field("phone", "Telepon"), Field("email", "Email"),
                Field("category_id", "Kategori produk", "select", False, model=Category)],
        order=Vendor.name),
    "warehouses": dict(
        model=Warehouse, title="Gudang Tujuan", roles=(C.AD,), view_roles=(),
        columns=[("code", "Kode"), ("name", "Nama"), ("pic_name", "Penanggung jawab")],
        fields=[Field("code", "Kode", required=True), Field("name", "Nama gudang", required=True),
                Field("address", "Alamat", "textarea"), Field("pic_name", "Penanggung jawab")],
        order=Warehouse.name),
}


def _config(entity, edit=False):
    cfg = MASTERS.get(entity)
    if cfg is None:
        abort(404)
    allowed = cfg["roles"] if edit else cfg["roles"] + cfg["view_roles"]
    if current_user.role not in allowed:
        abort(403)
    return cfg


def cell(obj, path):
    """Ambil nilai 'a.b' dari objek; None bila ada rantai yang kosong."""
    for part in path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _read_form(cfg, form):
    """Ubah isian form menjadi dict nilai; kembalikan (values, errors)."""
    values, errors = {}, []
    for f in cfg["fields"]:
        raw = (form.get(f.name) or "").strip()
        if f.kind == "bool":
            values[f.name] = form.get(f.name) == "on"
            continue
        if not raw:
            if f.required:
                errors.append(f"{f.label} wajib diisi.")
            values[f.name] = None
            continue
        if f.kind in ("text", "textarea"):
            values[f.name] = raw
        elif f.kind == "int":
            if raw.isdigit():
                values[f.name] = int(raw)
            else:
                errors.append(f"{f.label} harus berupa angka bulat.")
        elif f.kind == "money":
            val = parse_decimal(raw)
            if val is None or val < 0:
                errors.append(f"{f.label} tidak valid.")
            else:
                values[f.name] = val
        elif f.kind == "select":
            if f.choices:
                if raw in f.choices:
                    values[f.name] = raw
                else:
                    errors.append(f"{f.label} tidak valid.")
            elif raw.isdigit() and db.session.get(f.model, int(raw)) is not None:
                values[f.name] = int(raw)
            else:
                errors.append(f"{f.label} tidak valid.")
    return values, errors


@bp.route("/")
@roles_required(C.AD, C.SP)
def index():
    visible = {k: v for k, v in MASTERS.items() if current_user.role in v["roles"]}
    return render_template("master/index.html", masters=visible)


@bp.route("/<entity>/")
@roles_required(C.AD, C.SP, C.MP)
def entity_list(entity):
    cfg = _config(entity)
    rows = db.session.execute(select(cfg["model"]).order_by(cfg["order"])).scalars().all()
    can_edit = current_user.role in cfg["roles"]
    usage = {}
    if entity == "budgets":  # terpakai dan sisa dihitung lewat query, tidak disimpan
        for b in rows:
            _limit, used, remaining = budget_summary(b.department_id, b.period)
            usage[b.id] = (used, remaining)
    return render_template("master/list.html", entity=entity, cfg=cfg, rows=rows, cell=cell,
                           can_edit=can_edit, usage=usage)


def _save(entity, cfg, obj, creating):
    values, errors = _read_form(cfg, request.form)
    if not errors:
        for name, val in values.items():
            setattr(obj, name, val)
        if creating:
            if cfg.get("has_active"):
                obj.active = True
            db.session.add(obj)
        try:
            db.session.flush()
            audit("BUAT_MASTER" if creating else "UBAH_MASTER", entity, obj.id)
            db.session.commit()
            flash(f"{cfg['title']} disimpan.", "success")
            return True
        except IntegrityError:
            db.session.rollback()
            errors.append("Data duplikat: kode/nama/periode sudah ada.")
    for e in errors:
        flash(e, "danger")
    return False


@bp.route("/<entity>/new", methods=["GET", "POST"])
@roles_required(C.AD, C.SP)
def entity_new(entity):
    cfg = _config(entity, edit=True)
    obj = cfg["model"]()
    if request.method == "POST" and _save(entity, cfg, obj, creating=True):
        return redirect(url_for("master.entity_list", entity=entity))
    defaults = {f.name: f.default() for f in cfg["fields"] if f.default}
    return render_template("master/form.html", entity=entity, cfg=cfg, obj=None, defaults=defaults)


@bp.route("/<entity>/<int:obj_id>/edit", methods=["GET", "POST"])
@roles_required(C.AD, C.SP)
def entity_edit(entity, obj_id):
    cfg = _config(entity, edit=True)
    obj = db.session.get(cfg["model"], obj_id)
    if obj is None:
        abort(404)
    if request.method == "POST":
        if _save(entity, cfg, obj, creating=False):
            return redirect(url_for("master.entity_list", entity=entity))
        obj = db.session.get(cfg["model"], obj_id)
    return render_template("master/form.html", entity=entity, cfg=cfg, obj=obj, defaults={})


@bp.route("/<entity>/<int:obj_id>/toggle", methods=["POST"])
@roles_required(C.AD, C.SP)
def entity_toggle(entity, obj_id):
    cfg = _config(entity, edit=True)
    obj = db.session.get(cfg["model"], obj_id)
    if obj is None or not cfg.get("has_active"):
        abort(404)
    obj.active = not obj.active
    audit("AKTIF_NONAKTIF", entity, obj.id, f"aktif={obj.active}")
    db.session.commit()
    flash("Status diperbarui.", "success")
    return redirect(url_for("master.entity_list", entity=entity))
