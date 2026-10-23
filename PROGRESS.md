# PROGRESS

Legenda status: **belum** / **sedang** / **selesai (ditulis)** = kode lengkap tetapi belum dijalankan / **diuji** = dijalankan dan diverifikasi.

| Kode | Fitur | Status | Lokasi |
|---|---|---|---|
| 1.1 | Autentikasi | selesai (ditulis) | views/auth.py |
| 1.2 | RBAC | selesai (ditulis) | decorators.py, navigation.py |
| 1.3 | Manajemen pengguna | selesai (ditulis) | views/users.py |
| 1.4 | Akun vendor | selesai (ditulis) | views/users.py (vendor_account) |
| 2.1 | Departemen & atasan | selesai (ditulis) | master + users |
| 2.2 | Anggaran departemen | selesai (ditulis) | master (budgets), services.budget_summary |
| 2.3 | Kategori & satuan | selesai (ditulis) | master |
| 2.4 | Master barang/jasa | selesai (ditulis) | master |
| 2.5 | Master vendor | selesai (ditulis) | master |
| 2.6 | Gudang | selesai (ditulis) | master |
| 2.7 | Penomoran otomatis | selesai (ditulis) | services.next_number |
| 3.1 | Buat PR | selesai (ditulis) | views/pr.py |
| 3.2 | Draft, ubah, hapus | selesai (ditulis) | views/pr.py |
| 3.3 | Submit PR | selesai (ditulis) | services.validate_pr_for_submit |
| 3.4 | Revisi PR | selesai (ditulis) | views/pr.py (edit) |
| 3.5 | Daftar & pencarian PR | selesai (ditulis) | views/pr.py (index) |
| 3.6 | Pelacakan & linimasa | selesai (ditulis) | services.pr_timeline |
| 4.1 | Antrian approval PR | selesai (ditulis) | views/approval.py |
| 4.2 | Keputusan PR | selesai (ditulis) | views/approval.py |
| 4.3 | Approval PO | selesai (ditulis) | views/approval.py |
| 4.4 | Riwayat approval | selesai (ditulis) | services.approval_history |
| 4.5 | Notifikasi approval | selesai (ditulis) | services.notify |
| 5.1 | Verifikasi PR | selesai (ditulis) | views/rfq.py (new) |
| 5.2 | Pilih calon vendor | selesai (ditulis) | views/rfq.py (new) |
| 5.3 | Buat RFQ | selesai (ditulis) | views/rfq.py |
| 5.4 | Kirim RFQ | selesai (ditulis) | views/rfq.py (send) |
| 5.5 | Portal vendor: RFQ masuk | selesai (ditulis) | views/vendor_portal.py |
| 5.6 | Input penawaran | selesai (ditulis) | services.save_quotation |
| 5.8 | Perbandingan penawaran | selesai (ditulis) | views/rfq.py (compare) |
| 5.9 | Pemenang | selesai (ditulis) | views/rfq.py (winner) |
| 6.1 | Buat PO | selesai (ditulis) | views/po.py |
| 6.2 | Ajukan & revisi PO | selesai (ditulis) | views/po.py |
| 6.3 | Kirim PO ke vendor | selesai (ditulis) | views/po.py (issue) |
| 6.4 | Konfirmasi PO vendor | selesai (ditulis) | views/vendor_portal.py |
| 6.5 | Informasi pengiriman | selesai (ditulis) | views/vendor_portal.py |
| 6.6 | Cetak PO PDF | diuji (sebagian) | pdf.py (PDF dihasilkan, diuji dengan data tiruan) |
| 7.1 | Daftar PO menunggu | selesai (ditulis) | views/gr.py |
| 7.2 | Pemeriksaan penerimaan | selesai (ditulis) | views/gr.py |
| 7.3 | Buat GR (sebagian) | selesai (ditulis) | views/gr.py |
| 7.4 | Retur & komplain | selesai (ditulis) | views/gr.py |
| 7.5 | Kirim ulang vendor | selesai (ditulis) | views/vendor_portal.py |
| 7.6 | Verifikasi GR & tutup PO | selesai (ditulis) | views/po.py (close) |
| 8.1 | Notifikasi | selesai (ditulis) | views/main.py |
| 8.2 | Dashboard per role | selesai (ditulis) | views/main.py |
| 8.3 | Laporan PR & PO | selesai (ditulis) | views/report.py |
| 9.1 | Audit log | selesai (ditulis) | services.audit, views/report.py |
| 9.2 | Validasi & error | selesai (ditulis) | validasi di tiap view, errors/error.html |
| 9.3 | Keamanan | selesai (ditulis) | CSRFProtect, hash Werkzeug, decorator, ORM |
| 9.4 | Basis data & seed | selesai (ditulis) | models.py, seed.py, cli.py |
| 9.5 | Dokumentasi | diuji (sebagian) | README.md, PROGRESS.md |
| 9.6 | Pengujian | selesai (ditulis) | tests/ (belum dijalankan) |
| 5.7 | OCR penawaran (nilai plus) | diuji (sebagian) | app/ocr/, views/ocr.py (engine + parser diuji dengan Tesseract nyata) |
| 1.5 | Profil (opsional) | selesai (ditulis) | views/auth.py |
| 8.4 | Ekspor CSV (opsional) | selesai (ditulis) | views/report.py |

## Milestone
M0-M8 selesai ditulis. Tidak ada yang berstatus 'diuji end-to-end'.

## Yang belum terverifikasi (penting)
Lingkungan pembangun memblokir PyPI sehingga Flask-SQLAlchemy, Flask-Login, Flask-WTF, SQLAlchemy, psycopg2, PyMuPDF, dan pytest tidak dapat dipasang di sana. Akibatnya:
- **Seluruh aplikasi Flask (view, model, tes pytest) belum pernah dijalankan.** Yang dijalankan: kompilasi seluruh berkas Python, kompilasi seluruh template Jinja, parser OCR + Tesseract pada gambar contoh, pembuatan PDF PO dengan data tiruan, dan skrip pembuat sampel.
- Tidak ada pengujian pada PostgreSQL maupun SQLite lewat SQLAlchemy.
- Jalur PDF digital via PyMuPDF belum dicoba.
- Instal bersih dari ZIP (skenario selesai #10) belum diuji.
Langkah pertama di mesin Anda: ikuti README, lalu jalankan `pytest`. Kegagalan yang muncul kemungkinan besar kesalahan kecil (nama atribut, impor, template); kirim ZIP ini beserta keluaran `pytest` untuk dilanjutkan (mode lanjut).

## Bug yang diketahui
Belum ada yang diketahui (karena belum dijalankan).

## Keputusan desain
Lihat README bagian Catatan.

## Langkah berikutnya
1. Jalankan `pytest` dan perbaiki kegagalan. 2. Coba skenario di browser. 3. Opsional: 3.9 cetak PR, 2.8 impor CSV, 3.7 lampiran PR.
