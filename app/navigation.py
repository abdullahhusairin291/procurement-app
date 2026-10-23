"""Menu navigasi per role. Pembatasan sebenarnya tetap di decorator pada tiap view."""
from . import constants as C

_DASH = ("main.dashboard", "Dashboard")

MENUS = {
    C.PM: [_DASH, ("pr.index", "PR Saya"), ("pr.new", "Buat PR")],
    C.AT: [_DASH, ("approval.pr_queue", "Approval PR"), ("pr.index", "PR Bawahan")],
    C.MP: [_DASH, ("approval.po_queue", "Approval PO"), ("po.index", "PO"), ("pr.index", "PR"),
           ("report.pr_report", "Laporan PR"), ("report.po_report", "Laporan PO"),
           ("master.entity_list|budgets", "Anggaran")],
    C.SP: [_DASH, ("pr.index", "PR"), ("rfq.index", "RFQ"), ("po.index", "PO"),
           ("gr.receipts", "Penerimaan"), ("gr.complaints", "Komplain"),
           ("master.index", "Master Data"), ("report.pr_report", "Laporan PR"),
           ("report.po_report", "Laporan PO")],
    C.VN: [_DASH, ("vendor.rfq_index", "RFQ Masuk"), ("vendor.po_index", "PO Saya")],
    C.GD: [_DASH, ("gr.waiting", "Menunggu Penerimaan"), ("gr.receipts", "Riwayat GR"),
           ("gr.complaints", "Komplain")],
    C.AD: [_DASH, ("users.index", "Pengguna"), ("master.index", "Master Data"),
           ("pr.index", "PR"), ("rfq.index", "RFQ"), ("po.index", "PO"),
           ("report.pr_report", "Laporan PR"), ("report.po_report", "Laporan PO"),
           ("report.audit", "Audit Log")],
}


def menu_for(role):
    """Mengembalikan daftar (endpoint, argumen, label). 'a|b' berarti endpoint a dengan entity=b."""
    items = []
    for endpoint, label in MENUS.get(role, [_DASH]):
        if "|" in endpoint:
            name, entity = endpoint.split("|", 1)
            items.append((name, {"entity": entity}, label))
        else:
            items.append((endpoint, {}, label))
    return items
