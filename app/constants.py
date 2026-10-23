"""Konstanta role dan status dokumen (sesuai siklus status di PRD)."""

# Kode role (disimpan di kolom users.role)
PM = "pemohon"
AT = "atasan"
MP = "manajer"
SP = "staf"
VN = "vendor"
GD = "gudang"
AD = "admin"

ROLE_LABELS = {
    PM: "Pemohon",
    AT: "Atasan Pemohon",
    MP: "Manajer Procurement",
    SP: "Staf Procurement",
    VN: "Vendor",
    GD: "Petugas Gudang",
    AD: "Administrator",
}

# Status PR
PR_DRAFT = "Draft"
PR_SUBMITTED = "Diajukan"
PR_APPROVED = "Disetujui"
PR_REVISION = "Perlu Revisi"
PR_REJECTED = "Ditolak"
PR_PROCESSED = "Diproses"
PR_DONE = "Selesai"
# Status PR yang menghabiskan anggaran
PR_BUDGET_STATUSES = (PR_APPROVED, PR_PROCESSED, PR_DONE)

# Status RFQ
RFQ_DRAFT = "Draft"
RFQ_SENT = "Terkirim"
RFQ_QUOTED = "Penawaran Masuk"
RFQ_WINNER = "Pemenang Dipilih"
RFQ_CLOSED = "Ditutup"

# Status penawaran
Q_SUBMITTED = "Diajukan"
Q_WON = "Pemenang"
Q_LOST = "Tidak Terpilih"

# Status PO
PO_DRAFT = "Draft"
PO_WAITING = "Menunggu Approval"
PO_REVISION = "Perlu Revisi"
PO_APPROVED = "Disetujui"
PO_ISSUED = "Terbit"
PO_CONFIRMED = "Dikonfirmasi"
PO_SHIPPED = "Dikirim"
PO_PARTIAL = "Diterima Sebagian"
PO_RECEIVED = "Diterima"
PO_DONE = "Selesai"

# Status GR
GR_OK = "Diterima - Sesuai"
GR_BAD = "Diterima - Tidak Sesuai"
GR_VERIFIED = "Terverifikasi"

# Hasil pemeriksaan per item
RES_OK = "Sesuai"
RES_BAD = "Tidak Sesuai"

# Status komplain/retur
C_OPEN = "Terbuka"
C_FOLLOWED = "Ditindaklanjuti"
C_RESENT = "Dikirim Ulang"

# Keputusan approval
D_APPROVE = "Disetujui"
D_REVISE = "Perlu Revisi"
D_REJECT = "Ditolak"

DOC_PREFIX = {"PR": "PR", "RFQ": "RFQ", "PO": "PO", "GR": "GR"}

STATUS_COLORS = {
    PR_DRAFT: "secondary", PR_SUBMITTED: "primary", PR_APPROVED: "success",
    PR_REVISION: "warning", PR_REJECTED: "danger", PR_PROCESSED: "info", PR_DONE: "dark",
    RFQ_SENT: "primary", RFQ_QUOTED: "info", RFQ_WINNER: "success", RFQ_CLOSED: "dark",
    Q_SUBMITTED: "primary", Q_WON: "success", Q_LOST: "secondary",
    PO_WAITING: "primary", PO_ISSUED: "info", PO_CONFIRMED: "info", PO_SHIPPED: "primary",
    PO_PARTIAL: "warning", PO_RECEIVED: "success", PO_DONE: "dark",
    GR_OK: "success", GR_BAD: "danger", GR_VERIFIED: "dark",
    RES_OK: "success", RES_BAD: "danger",
    C_OPEN: "danger", C_FOLLOWED: "warning", C_RESENT: "success",
}
