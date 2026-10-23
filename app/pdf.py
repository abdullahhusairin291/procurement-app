"""Pembuatan dokumen PDF (reportlab, tanpa dependensi sistem)."""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .utils import fmt_qty, rupiah, tgl


def _esc(text):
    """Escape karakter khusus markup mini reportlab."""
    return (str(text or "-")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_po_pdf(po):
    """PDF Purchase Order resmi (fitur 6.6). Mengembalikan bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Purchase Order {po.number}")
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, leading=12)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=11)
    story = [Paragraph("PURCHASE ORDER", styles["Title"]),
             Paragraph(f"Nomor: <b>{_esc(po.number)}</b> &nbsp;&nbsp; Status: {_esc(po.status)}", small),
             Spacer(1, 0.4 * cm)]

    head = [
        [Paragraph("<b>Vendor</b>", small), Paragraph(f"{_esc(po.vendor.name)}<br/>{_esc(po.vendor.address)}", small),
         Paragraph("<b>Dikirim ke</b>", small),
         Paragraph(f"{_esc(po.warehouse.name)}<br/>{_esc(po.warehouse.address)}", small)],
        [Paragraph("<b>Tanggal PO</b>", small), Paragraph(tgl(po.created_at), small),
         Paragraph("<b>Jadwal kirim</b>", small), Paragraph(tgl(po.delivery_date), small)],
        [Paragraph("<b>Ref. PR</b>", small), Paragraph(_esc(po.pr.number), small),
         Paragraph("<b>Syarat bayar</b>", small), Paragraph(_esc(po.payment_terms), small)],
    ]
    t = Table(head, colWidths=[2.6 * cm, 6 * cm, 2.8 * cm, 5.6 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [t, Spacer(1, 0.5 * cm)]

    rows = [["No", "Barang/Jasa", "Qty", "Satuan", "Harga satuan", "Subtotal"]]
    for no, it in enumerate(po.items, start=1):
        name = f"<b>{_esc(it.item.name)}</b>" + (f"<br/>{_esc(it.spec)}" if it.spec else "")
        rows.append([str(no), Paragraph(name, cell), fmt_qty(it.qty), it.item.unit.name,
                     rupiah(it.unit_price), rupiah(it.subtotal)])
    rows.append(["", "", "", "", "TOTAL", rupiah(po.total)])
    items = Table(rows, colWidths=[1 * cm, 6.4 * cm, 1.6 * cm, 1.8 * cm, 3.1 * cm, 3.1 * cm], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
        ("GRID", (0, 0), (-1, -2), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"), ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(items)
    if po.notes:
        story += [Spacer(1, 0.4 * cm), Paragraph(f"<b>Catatan:</b> {_esc(po.notes)}", small)]
    story += [Spacer(1, 1.2 * cm),
              Paragraph(f"Dibuat oleh: {_esc(po.created_by.full_name)} &nbsp;&nbsp; "
                        f"Dokumen ini dihasilkan otomatis oleh aplikasi Procurement.", small)]
    doc.build(story)
    return buf.getvalue()
