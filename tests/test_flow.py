"""Uji alur end-to-end PR -> RFQ -> PO -> GR -> tutup PO, lengkap dengan cabang revisi, tolak, dan komplain."""
from datetime import timedelta

from sqlalchemy import select

from app import constants as C
from app.extensions import db
from app.models import (AuditLog, GoodsReceipt, Item, Notification, PurchaseOrder, PurchaseRequest,
                        RFQ, ReturnComplaint, Vendor)
from app.utils import now, today


def _item_id(code):
    return db.session.execute(select(Item.id).where(Item.code == code)).scalar_one()


def _pr_form(action="submit", needed=None):
    return {
        "needed_date": (needed or today() + timedelta(days=14)).isoformat(),
        "justification": "Penggantian perangkat kerja tim",
        "item_id": [_item_id("LPT-001"), _item_id("MSE-001"), _item_id("KBD-001")],
        "spec": ["", "", ""], "qty": ["5", "10", "10"], "price": ["12500000", "150000", "250000"],
        "action": action,
    }


def _status(model, obj_id):
    db.session.expire_all()
    return db.session.get(model, obj_id).status


def test_full_procurement_flow(app, login):
    pemohon, atasan = login("pemohon1"), login("atasan1")
    staf, manajer = login("staf1"), login("manajer1")
    gudang, admin = login("gudang1"), login("admin")
    vendors = {n: login(f"vendor{n}") for n in (1, 2, 3)}

    # 1. PR dibuat dan diajukan; atasan minta revisi (wajib catatan), pemohon merevisi, atasan setuju
    resp = pemohon.post("/pr/new", data=_pr_form())
    assert resp.status_code == 302
    pr = db.session.execute(select(PurchaseRequest)).scalars().one()
    assert pr.status == C.PR_SUBMITTED and pr.number.startswith("PR-") and pr.number.endswith("-0001")

    atasan.post(f"/approval/pr/{pr.id}", data={"decision": "revisi", "note": ""})
    assert _status(PurchaseRequest, pr.id) == C.PR_SUBMITTED  # tanpa catatan ditolak sistem
    atasan.post(f"/approval/pr/{pr.id}", data={"decision": "revisi", "note": "Kurangi jumlah mouse"})
    assert _status(PurchaseRequest, pr.id) == C.PR_REVISION
    data = _pr_form()
    data["qty"] = ["5", "10", "10"]
    assert pemohon.post(f"/pr/{pr.id}/edit", data=data).status_code == 302
    assert _status(PurchaseRequest, pr.id) == C.PR_SUBMITTED
    atasan.post(f"/approval/pr/{pr.id}", data={"decision": "setuju", "note": ""})
    assert _status(PurchaseRequest, pr.id) == C.PR_APPROVED

    # 2. cabang tolak
    pemohon.post("/pr/new", data=_pr_form())
    pr2 = db.session.execute(select(PurchaseRequest).where(PurchaseRequest.id != pr.id)).scalars().one()
    atasan.post(f"/approval/pr/{pr2.id}", data={"decision": "tolak", "note": "Tidak sesuai prioritas"})
    assert _status(PurchaseRequest, pr2.id) == C.PR_REJECTED
    assert pemohon.post(f"/pr/{pr2.id}/submit").status_code == 302  # tidak bisa diajukan lagi
    assert _status(PurchaseRequest, pr2.id) == C.PR_REJECTED

    # 3. verifikasi + RFQ untuk 3 vendor
    vendor_ids = [v.id for v in db.session.execute(select(Vendor).order_by(Vendor.id)).scalars()]
    deadline = (now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    resp = staf.post(f"/rfq/new/{pr.id}", data={"deadline": deadline, "verified": "on", "vendor_id": vendor_ids,
                                                 "method": "RFQ ke beberapa vendor", "terms": "Harga sudah termasuk kirim"})
    assert resp.status_code == 302
    rfq = db.session.execute(select(RFQ)).scalars().one()
    assert rfq.status == C.RFQ_DRAFT and len(rfq.vendors) == 3
    assert vendors[1].get(f"/vendor/rfq/{rfq.id}").status_code == 404  # belum dikirim
    staf.post(f"/rfq/{rfq.id}/send")
    assert _status(RFQ, rfq.id) == C.RFQ_SENT
    assert vendors[1].get(f"/vendor/rfq/{rfq.id}").status_code == 200

    db.session.expire_all()
    ri = {r.item.code: r.id for r in rfq.items}

    def prices(laptop, mouse, kbd):
        return {f"price_{ri['LPT-001']}": laptop, f"price_{ri['MSE-001']}": mouse, f"price_{ri['KBD-001']}": kbd,
                "lead_time_days": "7", "payment_terms": "Net 30"}

    assert vendors[1].post(f"/vendor/rfq/{rfq.id}/quote", data=prices("12400000", "148000", "245000")).status_code == 302
    assert vendors[2].post(f"/vendor/rfq/{rfq.id}/quote", data=prices("12600000", "150000", "240000")).status_code == 302
    assert _status(RFQ, rfq.id) == C.RFQ_QUOTED
    # vendor3 diinput staf (jalur OCR: hasil sudah diperiksa pengguna), harga kedua item saja = tidak lengkap
    staf.post(f"/rfq/{rfq.id}/quotation/{vendor_ids[2]}", data={**prices("12350000", "145000", ""), "via": "OCR"})
    compare = staf.get(f"/rfq/{rfq.id}/compare")
    assert compare.status_code == 200 and b"tidak lengkap" in compare.data

    db.session.expire_all()
    q_by_vendor = {q.vendor_id: q for q in rfq.quotations}
    assert q_by_vendor[vendor_ids[2]].entered_via == "OCR" and not q_by_vendor[vendor_ids[2]].is_complete
    # pemenang wajib alasan dan penawaran lengkap
    staf.post(f"/rfq/{rfq.id}/winner", data={"quotation_id": q_by_vendor[vendor_ids[0]].id, "reason": ""})
    assert _status(RFQ, rfq.id) == C.RFQ_QUOTED
    staf.post(f"/rfq/{rfq.id}/winner", data={"quotation_id": q_by_vendor[vendor_ids[2]].id, "reason": "murah"})
    assert _status(RFQ, rfq.id) == C.RFQ_QUOTED
    staf.post(f"/rfq/{rfq.id}/winner", data={"quotation_id": q_by_vendor[vendor_ids[0]].id, "reason": "Harga total terendah"})
    assert _status(RFQ, rfq.id) == C.RFQ_WINNER and _status(PurchaseRequest, pr.id) == C.PR_PROCESSED

    # 4. PO: manajer minta revisi, staf merevisi, manajer setuju, staf menerbitkan
    from app.models import Warehouse
    wh = db.session.execute(select(Warehouse.id)).scalar_one()
    po_form = {"warehouse_id": wh, "delivery_date": (today() + timedelta(days=10)).isoformat(), "payment_terms": "Net 30"}
    assert staf.post(f"/po/new/{rfq.id}", data=po_form).status_code == 302
    po = db.session.execute(select(PurchaseOrder)).scalars().one()
    assert po.status == C.PO_DRAFT and po.total == 5 * 12400000 + 10 * 148000 + 10 * 245000
    staf.post(f"/po/{po.id}/submit")
    assert _status(PurchaseOrder, po.id) == C.PO_WAITING
    manajer.post(f"/approval/po/{po.id}", data={"decision": "revisi", "note": ""})
    assert _status(PurchaseOrder, po.id) == C.PO_WAITING
    manajer.post(f"/approval/po/{po.id}", data={"decision": "revisi", "note": "Majukan jadwal kirim"})
    assert _status(PurchaseOrder, po.id) == C.PO_REVISION
    po_form["delivery_date"] = (today() + timedelta(days=7)).isoformat()
    staf.post(f"/po/{po.id}/edit", data=po_form)
    staf.post(f"/po/{po.id}/submit")
    manajer.post(f"/approval/po/{po.id}", data={"decision": "setuju", "note": ""})
    assert _status(PurchaseOrder, po.id) == C.PO_APPROVED
    assert vendors[1].get(f"/vendor/po/{po.id}").status_code == 404  # belum terbit
    staf.post(f"/po/{po.id}/issue")
    assert _status(PurchaseOrder, po.id) == C.PO_ISSUED
    assert staf.get(f"/po/{po.id}/pdf").data.startswith(b"%PDF")
    assert vendors[1].get(f"/po/{po.id}/pdf").status_code == 200
    assert vendors[2].get(f"/vendor/po/{po.id}").status_code == 404  # bukan PO miliknya

    # 5. vendor konfirmasi dan kirim
    vendors[1].post(f"/vendor/po/{po.id}/confirm", data={"promised_date": (today() + timedelta(days=5)).isoformat()})
    assert _status(PurchaseOrder, po.id) == C.PO_CONFIRMED
    vendors[1].post(f"/vendor/po/{po.id}/ship", data={"delivery_note_no": "SJ-001", "eta": (today() + timedelta(days=6)).isoformat()})
    assert _status(PurchaseOrder, po.id) == C.PO_SHIPPED

    # 6. gudang: laptop tidak sesuai -> komplain; tindak lanjut; kirim ulang; terima sesuai
    db.session.expire_all()
    pi = {i.item.code: i.id for i in po.items}
    bad = {f"qty_{pi['LPT-001']}": "5", f"result_{pi['LPT-001']}": C.RES_BAD, f"note_{pi['LPT-001']}": "Layar retak",
           f"qty_{pi['MSE-001']}": "10", f"result_{pi['MSE-001']}": C.RES_OK,
           f"qty_{pi['KBD-001']}": "10", f"result_{pi['KBD-001']}": C.RES_OK}
    assert gudang.post(f"/gr/receive/{po.id}", data=bad).status_code == 302
    complaint = db.session.execute(select(ReturnComplaint)).scalars().one()
    assert complaint.status == C.C_OPEN and _status(PurchaseOrder, po.id) == C.PO_PARTIAL
    # selama komplain terbuka gudang tidak bisa memeriksa lagi
    assert gudang.get(f"/gr/receive/{po.id}").status_code == 302
    staf.post(f"/gr/complaints/{complaint.id}/followup", data={"note": "Minta penggantian unit"})
    assert _status(ReturnComplaint, complaint.id) == C.C_FOLLOWED
    vendors[1].post(f"/vendor/po/{po.id}/resend", data={"delivery_note_no": "SJ-002", "eta": (today() + timedelta(days=2)).isoformat()})
    assert _status(ReturnComplaint, complaint.id) == C.C_RESENT and _status(PurchaseOrder, po.id) == C.PO_SHIPPED
    # qty melebihi sisa ditolak; sisa laptop 5 diterima sesuai
    assert gudang.post(f"/gr/receive/{po.id}", data={f"qty_{pi['LPT-001']}": "9", f"result_{pi['LPT-001']}": C.RES_OK}).status_code == 200
    assert gudang.post(f"/gr/receive/{po.id}", data={f"qty_{pi['LPT-001']}": "5", f"result_{pi['LPT-001']}": C.RES_OK}).status_code == 302
    assert _status(PurchaseOrder, po.id) == C.PO_RECEIVED

    # 7. staf menutup PO; PO dan PR selesai
    staf.post(f"/po/{po.id}/close")
    assert _status(PurchaseOrder, po.id) == C.PO_DONE and _status(PurchaseRequest, pr.id) == C.PR_DONE
    grs = db.session.execute(select(GoodsReceipt)).scalars().all()
    assert len(grs) == 2 and all(g.verified_at for g in grs)

    # 8. dashboard, laporan, audit log, notifikasi
    for client in (pemohon, atasan, staf, manajer, gudang, admin, vendors[1]):
        assert client.get("/").status_code == 200
    assert b"PO-" in staf.get("/report/po").data
    assert staf.get("/report/po?export=csv").data.startswith(b"\xef\xbb\xbf")
    assert manajer.get("/report/pr").status_code == 200
    actions = {a.action for a in db.session.execute(select(AuditLog)).scalars()}
    assert {"LOGIN", "SUBMIT_PR", "PR_SETUJU", "PR_TOLAK", "BUAT_RFQ", "TETAPKAN_PEMENANG", "BUAT_PO",
            "PO_SETUJU", "BUAT_GR", "BUAT_KOMPLAIN", "TUTUP_PO"} <= actions
    assert b"TUTUP_PO" in admin.get("/report/audit").data
    assert db.session.execute(select(Notification).where(Notification.message.like("%selesai%"))).first()
    assert pemohon.get(f"/pr/{pr.id}").status_code == 200  # linimasa dapat dibuka


def test_access_control_returns_403(app, login):
    pemohon, vendor, gudang = login("pemohon1"), login("vendor1"), login("gudang1")
    assert pemohon.get("/approval/po").status_code == 403
    assert pemohon.get("/approval/pr").status_code == 403
    assert pemohon.get("/users/").status_code == 403
    assert pemohon.get("/report/audit").status_code == 403
    assert vendor.get("/po/").status_code == 403
    assert vendor.get("/pr/").status_code == 403
    assert gudang.get("/rfq/").status_code == 403
    assert app.test_client().get("/pr/").status_code == 302  # belum login -> ke halaman login


def test_pr_submit_rules_and_isolation(app, login):
    pemohon1, pemohon2, atasan2 = login("pemohon1"), login("pemohon2"), login("atasan2")
    # tanggal lampau ditolak, PR tetap draft
    pemohon1.post("/pr/new", data=_pr_form(needed=today() - timedelta(days=1)))
    pr = db.session.execute(select(PurchaseRequest)).scalars().one()
    assert pr.status == C.PR_DRAFT
    # melebihi anggaran ditolak
    big = _pr_form()
    big["qty"] = ["100", "1", "1"]
    pemohon1.post(f"/pr/{pr.id}/edit", data={**big, "action": "draft"})
    pemohon1.post(f"/pr/{pr.id}/submit")
    assert _status(PurchaseRequest, pr.id) == C.PR_DRAFT
    # pemohon lain tidak boleh melihat atau mengubah; atasan lain tidak bisa memutuskan
    assert pemohon2.get(f"/pr/{pr.id}").status_code == 403
    assert pemohon2.post(f"/pr/{pr.id}/edit", data=_pr_form()).status_code == 403
    assert atasan2.get(f"/approval/pr/{pr.id}").status_code == 403
    # draft milik sendiri boleh dihapus
    assert pemohon1.post(f"/pr/{pr.id}/delete").status_code == 302
    assert db.session.execute(select(PurchaseRequest)).first() is None


def test_seed_is_idempotent(app):
    from app.seed import seed_demo
    assert seed_demo() is False


def test_document_numbering_is_unique_and_sequential(app):
    from app.services import next_number
    a, b = next_number("PR"), next_number("PR")
    assert a.endswith("-0001") and b.endswith("-0002")
    assert next_number("RFQ").endswith("-0001")
