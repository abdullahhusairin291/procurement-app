"""Modul 8-9: laporan PR/PO (8.3, 8.4) dan audit log (9.1)."""
import csv
from datetime import datetime, time, timedelta
from io import StringIO

from flask import Blueprint, Response, render_template, request
from sqlalchemy import select

from .. import constants as C
from ..decorators import roles_required
from ..extensions import db
from ..models import AuditLog, Department, PurchaseOrder, PurchaseRequest, Vendor
from ..utils import parse_date, tgl

bp = Blueprint("report", __name__, url_prefix="/report")

REPORT_ROLES = (C.MP, C.SP, C.AD)


def _date_range(column, stmt, args):
    """Terapkan filter tanggal dari parameter date_from/date_to pada kolom DateTime."""
    start, end = parse_date(args.get("date_from")), parse_date(args.get("date_to"))
    if start:
        stmt = stmt.where(column >= datetime.combine(start, time.min))
    if end:
        stmt = stmt.where(column < datetime.combine(end + timedelta(days=1), time.min))
    return stmt


def _csv_response(filename, header, rows):
    buf = StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    # BOM agar Excel membaca UTF-8 dengan benar
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.route("/pr")
@roles_required(*REPORT_ROLES)
def pr_report():
    stmt = select(PurchaseRequest).where(PurchaseRequest.status != C.PR_DRAFT)
    stmt = _date_range(PurchaseRequest.created_at, stmt, request.args)
    dept, status = request.args.get("department_id", ""), request.args.get("status", "")
    if dept.isdigit():
        stmt = stmt.where(PurchaseRequest.department_id == int(dept))
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    rows = db.session.execute(stmt.order_by(PurchaseRequest.id.desc())).scalars().all()
    if request.args.get("export") == "csv":
        return _csv_response("laporan_pr.csv",
                             ["Nomor", "Tanggal", "Pemohon", "Departemen", "Status", "Total Estimasi"],
                             [[r.number, tgl(r.created_at), r.requester.full_name, r.department.name,
                               r.status, r.total] for r in rows])
    departments = db.session.execute(select(Department).order_by(Department.name)).scalars().all()
    statuses = [C.PR_SUBMITTED, C.PR_APPROVED, C.PR_REVISION, C.PR_REJECTED, C.PR_PROCESSED, C.PR_DONE]
    return render_template("report/pr.html", rows=rows, total=sum(r.total for r in rows),
                           departments=departments, statuses=statuses, f=request.args)


@bp.route("/po")
@roles_required(*REPORT_ROLES)
def po_report():
    stmt = select(PurchaseOrder)
    stmt = _date_range(PurchaseOrder.created_at, stmt, request.args)
    vendor, dept, status = (request.args.get(k, "") for k in ("vendor_id", "department_id", "status"))
    if vendor.isdigit():
        stmt = stmt.where(PurchaseOrder.vendor_id == int(vendor))
    if dept.isdigit():
        stmt = stmt.where(PurchaseOrder.pr_id.in_(
            select(PurchaseRequest.id).where(PurchaseRequest.department_id == int(dept))))
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    rows = db.session.execute(stmt.order_by(PurchaseOrder.id.desc())).scalars().all()
    if request.args.get("export") == "csv":
        return _csv_response("laporan_po.csv",
                             ["Nomor PO", "Tanggal", "Ref PR", "Departemen", "Vendor", "Status", "Total"],
                             [[r.number, tgl(r.created_at), r.pr.number, r.pr.department.name, r.vendor.name,
                               r.status, r.total] for r in rows])
    departments = db.session.execute(select(Department).order_by(Department.name)).scalars().all()
    vendors = db.session.execute(select(Vendor).order_by(Vendor.name)).scalars().all()
    statuses = [C.PO_DRAFT, C.PO_WAITING, C.PO_REVISION, C.PO_APPROVED, C.PO_ISSUED, C.PO_CONFIRMED,
                C.PO_SHIPPED, C.PO_PARTIAL, C.PO_RECEIVED, C.PO_DONE]
    return render_template("report/po.html", rows=rows, total=sum(r.total for r in rows),
                           departments=departments, vendors=vendors, statuses=statuses, f=request.args)


@bp.route("/audit")
@roles_required(C.AD)
def audit():
    stmt = _date_range(AuditLog.created_at, select(AuditLog), request.args)
    action = (request.args.get("action") or "").strip()
    user = (request.args.get("user") or "").strip()
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if user:
        stmt = stmt.where(AuditLog.username.ilike(f"%{user}%"))
    rows = db.session.execute(stmt.order_by(AuditLog.id.desc()).limit(500)).scalars().all()
    return render_template("report/audit.html", rows=rows, f=request.args)
