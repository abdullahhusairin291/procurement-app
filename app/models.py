"""Model basis data. Uang memakai Numeric(18, 2), bukan float."""
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import constants as C
from .extensions import db, login_manager
from .utils import now

ZERO = Decimal("0")


# --------------------------------------------------------------- pengguna
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    role = db.Column(db.String(20), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    supervisor_id = db.Column(db.Integer, db.ForeignKey("users.id"))  # atasan pemohon
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"))    # untuk akun vendor
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"))  # untuk petugas gudang
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    department = db.relationship("Department", foreign_keys=[department_id])
    supervisor = db.relationship("User", remote_side=[id], foreign_keys=[supervisor_id],
                                 backref="subordinates")
    vendor = db.relationship("Vendor", foreign_keys=[vendor_id])
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])

    @property
    def is_active(self):  # dipakai Flask-Login: akun nonaktif tidak bisa login
        return bool(self.active)

    @property
    def role_label(self):
        return C.ROLE_LABELS.get(self.role, self.role)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ------------------------------------------------------------- master data
class Department(db.Model):
    __tablename__ = "departments"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)


class Budget(db.Model):
    """Pagu anggaran per departemen per periode (tahun). Sisa dihitung lewat query."""
    __tablename__ = "budgets"
    __table_args__ = (db.UniqueConstraint("department_id", "period", name="uq_budget_dept_period"),)
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    period = db.Column(db.Integer, nullable=False)  # tahun, mis. 2026
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    department = db.relationship("Department")


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Unit(db.Model):
    __tablename__ = "units"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)


class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    kind = db.Column(db.String(10), nullable=False, default="Barang")  # Barang / Jasa
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=False)
    spec = db.Column(db.Text)
    ref_price = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)
    category = db.relationship("Category")
    unit = db.relationship("Unit")


class Vendor(db.Model):
    __tablename__ = "vendors"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text)
    contact_name = db.Column(db.String(100))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(120))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    active = db.Column(db.Boolean, nullable=False, default=True)
    category = db.relationship("Category")


class Warehouse(db.Model):
    __tablename__ = "warehouses"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text)
    pic_name = db.Column(db.String(100))


# ----------------------------------------------------------- purchase request
class PurchaseRequest(db.Model):
    __tablename__ = "purchase_requests"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(30), unique=True, nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False, index=True)
    needed_date = db.Column(db.Date)
    justification = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default=C.PR_DRAFT, index=True)
    period = db.Column(db.Integer, nullable=False)  # tahun anggaran
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    submitted_at = db.Column(db.DateTime)
    # verifikasi oleh staf procurement (fitur 5.1)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    verified_at = db.Column(db.DateTime)
    verification_note = db.Column(db.Text)
    procurement_method = db.Column(db.String(40))

    requester = db.relationship("User", foreign_keys=[requester_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_id])
    department = db.relationship("Department")
    items = db.relationship("PRItem", back_populates="pr", cascade="all, delete-orphan",
                            order_by="PRItem.id")

    @property
    def total(self):
        return sum((i.subtotal for i in self.items), ZERO)


class PRItem(db.Model):
    __tablename__ = "pr_items"
    id = db.Column(db.Integer, primary_key=True)
    pr_id = db.Column(db.Integer, db.ForeignKey("purchase_requests.id"), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    spec = db.Column(db.Text)
    qty = db.Column(db.Numeric(14, 2), nullable=False)
    est_price = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    pr = db.relationship("PurchaseRequest", back_populates="items")
    item = db.relationship("Item")

    @property
    def subtotal(self):
        return (self.qty or ZERO) * (self.est_price or ZERO)


class ApprovalLog(db.Model):
    """Riwayat approval PR dan PO (siapa, kapan, keputusan, catatan)."""
    __tablename__ = "approval_logs"
    id = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(5), nullable=False)  # PR / PO
    doc_id = db.Column(db.Integer, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    decision = db.Column(db.String(20), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    actor = db.relationship("User")
    __table_args__ = (db.Index("ix_approval_doc", "doc_type", "doc_id"),)


# ------------------------------------------------------------------- RFQ
class RFQ(db.Model):
    __tablename__ = "rfqs"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(30), unique=True, nullable=False)
    pr_id = db.Column(db.Integer, db.ForeignKey("purchase_requests.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    terms = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default=C.RFQ_DRAFT, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    sent_at = db.Column(db.DateTime)
    win_reason = db.Column(db.Text)
    selected_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    selected_at = db.Column(db.DateTime)

    pr = db.relationship("PurchaseRequest")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    selected_by = db.relationship("User", foreign_keys=[selected_by_id])
    items = db.relationship("RFQItem", back_populates="rfq", cascade="all, delete-orphan",
                            order_by="RFQItem.id")
    vendors = db.relationship("RFQVendor", back_populates="rfq", cascade="all, delete-orphan",
                              order_by="RFQVendor.id")
    quotations = db.relationship("Quotation", back_populates="rfq", cascade="all, delete-orphan",
                                 order_by="Quotation.id")

    @property
    def winner(self):
        return next((q for q in self.quotations if q.status == C.Q_WON), None)


class RFQItem(db.Model):
    __tablename__ = "rfq_items"
    id = db.Column(db.Integer, primary_key=True)
    rfq_id = db.Column(db.Integer, db.ForeignKey("rfqs.id"), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    spec = db.Column(db.Text)
    qty = db.Column(db.Numeric(14, 2), nullable=False)
    rfq = db.relationship("RFQ", back_populates="items")
    item = db.relationship("Item")


class RFQVendor(db.Model):
    __tablename__ = "rfq_vendors"
    __table_args__ = (db.UniqueConstraint("rfq_id", "vendor_id", name="uq_rfq_vendor"),)
    id = db.Column(db.Integer, primary_key=True)
    rfq_id = db.Column(db.Integer, db.ForeignKey("rfqs.id"), nullable=False, index=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False, index=True)
    rfq = db.relationship("RFQ", back_populates="vendors")
    vendor = db.relationship("Vendor")


class Quotation(db.Model):
    __tablename__ = "quotations"
    __table_args__ = (db.UniqueConstraint("rfq_id", "vendor_id", name="uq_quotation_rfq_vendor"),)
    id = db.Column(db.Integer, primary_key=True)
    rfq_id = db.Column(db.Integer, db.ForeignKey("rfqs.id"), nullable=False, index=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False, index=True)
    lead_time_days = db.Column(db.Integer)
    payment_terms = db.Column(db.String(150))
    valid_until = db.Column(db.Date)
    notes = db.Column(db.Text)
    entered_via = db.Column(db.String(10), nullable=False, default="Vendor")  # Vendor / Staf / OCR
    submitted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    submitted_at = db.Column(db.DateTime, nullable=False, default=now)
    attachment_name = db.Column(db.String(200))
    attachment_path = db.Column(db.String(80))
    status = db.Column(db.String(20), nullable=False, default=C.Q_SUBMITTED)

    rfq = db.relationship("RFQ", back_populates="quotations")
    vendor = db.relationship("Vendor")
    submitted_by = db.relationship("User")
    items = db.relationship("QuotationItem", back_populates="quotation",
                            cascade="all, delete-orphan")

    def price_for(self, rfq_item_id):
        for qi in self.items:
            if qi.rfq_item_id == rfq_item_id:
                return qi
        return None

    @property
    def is_complete(self):
        """Lengkap bila setiap item RFQ punya harga satuan."""
        return all(self.price_for(ri.id) is not None for ri in self.rfq.items)

    @property
    def total(self):
        return sum((qi.subtotal for qi in self.items), ZERO)


class QuotationItem(db.Model):
    __tablename__ = "quotation_items"
    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey("quotations.id"), nullable=False, index=True)
    rfq_item_id = db.Column(db.Integer, db.ForeignKey("rfq_items.id"), nullable=False)
    unit_price = db.Column(db.Numeric(18, 2), nullable=False)
    quotation = db.relationship("Quotation", back_populates="items")
    rfq_item = db.relationship("RFQItem")

    @property
    def subtotal(self):
        return (self.rfq_item.qty or ZERO) * (self.unit_price or ZERO)


# ------------------------------------------------------------ purchase order
class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(30), unique=True, nullable=False)
    rfq_id = db.Column(db.Integer, db.ForeignKey("rfqs.id"), nullable=False, index=True)
    pr_id = db.Column(db.Integer, db.ForeignKey("purchase_requests.id"), nullable=False, index=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey("quotations.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    delivery_date = db.Column(db.Date, nullable=False)
    payment_terms = db.Column(db.String(150))
    notes = db.Column(db.Text)
    status = db.Column(db.String(25), nullable=False, default=C.PO_DRAFT, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    submitted_at = db.Column(db.DateTime)
    issued_at = db.Column(db.DateTime)
    confirmed_at = db.Column(db.DateTime)
    promised_date = db.Column(db.Date)
    confirm_note = db.Column(db.Text)
    shipped_at = db.Column(db.DateTime)
    delivery_note_no = db.Column(db.String(60))
    eta = db.Column(db.Date)
    closed_at = db.Column(db.DateTime)
    closed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    rfq = db.relationship("RFQ")
    pr = db.relationship("PurchaseRequest")
    quotation = db.relationship("Quotation")
    vendor = db.relationship("Vendor")
    warehouse = db.relationship("Warehouse")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    closed_by = db.relationship("User", foreign_keys=[closed_by_id])
    items = db.relationship("POItem", back_populates="po", cascade="all, delete-orphan",
                            order_by="POItem.id")

    @property
    def total(self):
        return sum((i.subtotal for i in self.items), ZERO)

    @property
    def fully_accepted(self):
        return all(i.remaining_qty <= 0 for i in self.items)


class POItem(db.Model):
    __tablename__ = "po_items"
    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    spec = db.Column(db.Text)
    qty = db.Column(db.Numeric(14, 2), nullable=False)
    unit_price = db.Column(db.Numeric(18, 2), nullable=False)
    po = db.relationship("PurchaseOrder", back_populates="items")
    item = db.relationship("Item")

    @property
    def subtotal(self):
        return (self.qty or ZERO) * (self.unit_price or ZERO)

    @property
    def accepted_qty(self):
        """Qty yang sudah diterima dengan hasil Sesuai (kumulatif dari semua GR)."""
        return sum((g.qty_received for g in self.gr_items if g.result == C.RES_OK), ZERO)

    @property
    def remaining_qty(self):
        return (self.qty or ZERO) - self.accepted_qty


# --------------------------------------------------------------- goods receipt
class GoodsReceipt(db.Model):
    __tablename__ = "goods_receipts"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(30), unique=True, nullable=False)
    po_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True)
    received_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    received_date = db.Column(db.Date, nullable=False)
    note = db.Column(db.Text)
    status = db.Column(db.String(30), nullable=False)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    po = db.relationship("PurchaseOrder", backref="receipts")
    received_by = db.relationship("User", foreign_keys=[received_by_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_id])
    items = db.relationship("GRItem", back_populates="gr", cascade="all, delete-orphan",
                            order_by="GRItem.id")

    @property
    def has_problem(self):
        return any(i.result == C.RES_BAD for i in self.items)


class GRItem(db.Model):
    __tablename__ = "gr_items"
    id = db.Column(db.Integer, primary_key=True)
    gr_id = db.Column(db.Integer, db.ForeignKey("goods_receipts.id"), nullable=False, index=True)
    po_item_id = db.Column(db.Integer, db.ForeignKey("po_items.id"), nullable=False, index=True)
    qty_received = db.Column(db.Numeric(14, 2), nullable=False)
    result = db.Column(db.String(15), nullable=False)  # Sesuai / Tidak Sesuai
    note = db.Column(db.Text)
    gr = db.relationship("GoodsReceipt", back_populates="items")
    po_item = db.relationship("POItem", backref="gr_items")


class ReturnComplaint(db.Model):
    __tablename__ = "return_complaints"
    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True)
    gr_id = db.Column(db.Integer, db.ForeignKey("goods_receipts.id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    evidence_name = db.Column(db.String(200))
    evidence_path = db.Column(db.String(80))
    status = db.Column(db.String(20), nullable=False, default=C.C_OPEN, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    followup_note = db.Column(db.Text)
    followup_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    followup_at = db.Column(db.DateTime)
    resend_note = db.Column(db.Text)
    resend_at = db.Column(db.DateTime)

    po = db.relationship("PurchaseOrder", backref="complaints")
    gr = db.relationship("GoodsReceipt", backref="complaints")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    followup_by = db.relationship("User", foreign_keys=[followup_by_id])


# ------------------------------------------------------------------ pendukung
class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(200))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(50))
    action = db.Column(db.String(50), nullable=False, index=True)
    entity = db.Column(db.String(30))
    entity_id = db.Column(db.Integer)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)


class DocumentSequence(db.Model):
    """Penomoran dokumen: satu baris per jenis dokumen per bulan."""
    __tablename__ = "document_sequences"
    __table_args__ = (db.UniqueConstraint("doc_type", "period", name="uq_docseq"),)
    id = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(5), nullable=False)
    period = db.Column(db.String(6), nullable=False)  # YYYYMM
    last_number = db.Column(db.Integer, nullable=False, default=0)
