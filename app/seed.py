"""Data demo untuk `seed-demo` dan pengujian."""
from decimal import Decimal

from sqlalchemy import select

from .extensions import db
from .models import Budget, Category, Department, Item, Unit, User, Vendor, Warehouse
from .utils import today
from . import constants as C

DEMO_PASSWORD = "Demo@123"  # hanya untuk demo


def seed_demo():
    """Isi data demo. Mengembalikan False (tanpa mengubah apa pun) bila sudah pernah di-seed."""
    if db.session.execute(select(User.id).where(User.username == "admin")).first():
        return False

    it = Department(code="IT", name="Teknologi Informasi")
    umum = Department(code="UMUM", name="Umum")
    db.session.add_all([it, umum])
    db.session.add_all([Budget(department=it, period=today().year, amount=Decimal("500000000")),
                        Budget(department=umum, period=today().year, amount=Decimal("200000000"))])

    elek = Category(name="Elektronik & IT")
    atk = Category(name="Alat Tulis & Kantor")
    jasa = Category(name="Jasa Pemeliharaan")
    units = {n: Unit(name=n) for n in ("unit", "pcs", "rim", "box", "kali", "paket")}
    db.session.add_all([elek, atk, jasa, *units.values()])

    catalog = [  # kode, nama, jenis, kategori, satuan, harga acuan, spesifikasi
        ("LPT-001", "Laptop Core i5 14 inch", "Barang", elek, "unit", 12500000, "RAM 16GB, SSD 512GB"),
        ("MSE-001", "Mouse Wireless", "Barang", elek, "pcs", 150000, "2.4GHz, optical"),
        ("KBD-001", "Keyboard USB", "Barang", elek, "pcs", 250000, "Layout standar"),
        ("MON-001", "Monitor LED 24 inch", "Barang", elek, "unit", 2200000, "Full HD, HDMI"),
        ("PRN-001", "Printer Laser Mono", "Barang", elek, "unit", 3500000, "A4, duplex"),
        ("TNR-001", "Toner Printer Hitam", "Barang", elek, "pcs", 950000, "Kompatibel printer laser mono"),
        ("ATK-001", "Kertas A4 80 gsm", "Barang", atk, "rim", 55000, "500 lembar per rim"),
        ("ATK-002", "Pulpen Gel Hitam", "Barang", atk, "box", 48000, "12 pcs per box"),
        ("ATK-003", "Map Folder Plastik", "Barang", atk, "pcs", 7500, "Ukuran folio"),
        ("SVC-001", "Jasa Servis AC", "Jasa", jasa, "kali", 350000, "Cuci dan pengecekan freon"),
        ("SVC-002", "Jasa Instalasi Jaringan", "Jasa", jasa, "paket", 4500000, "Kabel, switch, dan konfigurasi"),
    ]
    for code, name, kind, cat, unit, price, spec in catalog:
        db.session.add(Item(code=code, name=name, kind=kind, category=cat, unit=units[unit],
                            ref_price=Decimal(price), spec=spec, active=True))

    vendors = [
        Vendor(code="V-001", name="PT Maju Teknologi Nusantara", address="Jl. Merdeka No. 10, Jakarta",
               contact_name="Budi Santoso", phone="021-5551001", email="sales@majuteknologi.example",
               category=elek, active=True),
        Vendor(code="V-002", name="CV Sinar Office Supply", address="Jl. Pahlawan No. 25, Bandung",
               contact_name="Sari Wulandari", phone="022-5552002", email="order@sinaroffice.example",
               category=atk, active=True),
        Vendor(code="V-003", name="PT Prima Solusi Mandiri", address="Jl. Industri No. 7, Tangerang",
               contact_name="Andi Prakoso", phone="021-5553003", email="info@primasolusi.example",
               category=elek, active=True),
    ]
    gudang = Warehouse(code="GDG-PUSAT", name="Gudang Pusat", address="Jl. Logistik No. 1, Jakarta Timur",
                       pic_name="Rudi Hartono")
    db.session.add_all([*vendors, gudang])
    db.session.flush()

    def make(username, name, role, **kw):
        user = User(username=username, full_name=name, role=role, active=True,
                    email=f"{username}@demo.example", **kw)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        return user

    make("admin", "Administrator Sistem", C.AD)
    atasan1 = make("atasan1", "Dewi Lestari (Kepala IT)", C.AT, department=it)
    atasan2 = make("atasan2", "Hendra Wijaya (Kepala Umum)", C.AT, department=umum)
    make("pemohon1", "Rina Pratiwi", C.PM, department=it, supervisor=atasan1)
    make("pemohon2", "Agus Setiawan", C.PM, department=umum, supervisor=atasan2)
    make("manajer1", "Maya Kusuma (Manajer Procurement)", C.MP, department=umum)
    make("staf1", "Fajar Nugroho (Staf Procurement)", C.SP, department=umum)
    make("gudang1", "Rudi Hartono (Petugas Gudang)", C.GD, warehouse=gudang)
    for n, vendor in enumerate(vendors, start=1):
        make(f"vendor{n}", f"Akun {vendor.name}", C.VN, vendor=vendor)
    db.session.commit()
    return True
