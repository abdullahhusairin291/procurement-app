# Aplikasi Procurement (Soal 2 - Programming)

Aplikasi web pengadaan barang/jasa dari Purchase Request sampai barang diterima di gudang.
Python 3.10+, Flask 3, Flask-SQLAlchemy, PostgreSQL (SQLite hanya untuk tes), Bootstrap 5 lokal (tanpa CDN).
Fitur nilai plus: input penawaran vendor dengan OCR (Tesseract) yang hasilnya diperiksa pengguna sebelum disimpan.

Acuan analisis: `docs/procurement.bpmn`, `docs/procurement.png`, `docs/WBS_Aplikasi_Procurement.docx`, `docs/er-diagram.md`.

## 1. Instalasi

### Windows (PowerShell)
```powershell
cd procurement-app
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env          # isi DATABASE_URL dan SECRET_KEY
python scripts/create_db.py
flask --app run init-db
flask --app run seed-demo
python run.py
```
Bila PowerShell menolak mengaktifkan venv: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### macOS / Linux
```bash
cd procurement-app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env             # isi DATABASE_URL dan SECRET_KEY
python scripts/create_db.py
flask --app run init-db
flask --app run seed-demo
python run.py
```

Buka http://127.0.0.1:5000. Alternatif menjalankan: `flask --app run run --debug`.

Membuat database lewat SQL (jika tidak memakai `create_db.py`): `psql -U postgres -f scripts/create_db.sql`.

### Konfigurasi `.env`
| Variabel | Isi |
|---|---|
| `DATABASE_URL` | `postgresql://USER:PASSWORD@localhost:5432/procurement` |
| `SECRET_KEY` | teks acak panjang (untuk sesi dan CSRF) |
| `TESSERACT_CMD` | opsional, lokasi `tesseract` bila tidak ada di PATH |

### Tesseract (opsional, hanya untuk fitur OCR)
Aplikasi tetap berjalan normal tanpa Tesseract; halaman OCR akan menampilkan pesan dan input manual tetap tersedia.
- Windows: pasang installer UB Mannheim (https://github.com/UB-Mannheim/tesseract/wiki), centang data bahasa Indonesia, lalu isi `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` di `.env`.
- macOS: `brew install tesseract tesseract-lang`
- Linux: `sudo apt install tesseract-ocr tesseract-ocr-ind`

## 2. Akun demo
Semua berpassword **`Demo@123`** (hanya untuk demo, jangan dipakai di produksi).

| Username | Role | Catatan |
|---|---|---|
| `admin` | Administrator | pengguna, master data, anggaran, audit log |
| `pemohon1` | Pemohon (IT) | atasan: `atasan1` |
| `pemohon2` | Pemohon (Umum) | atasan: `atasan2` |
| `atasan1`, `atasan2` | Atasan Pemohon | approval PR bawahan |
| `manajer1` | Manajer Procurement | approval PO, laporan |
| `staf1` | Staf Procurement | verifikasi, RFQ, PO, tutup PO |
| `gudang1` | Petugas Gudang | Gudang Pusat |
| `vendor1`, `vendor2`, `vendor3` | Vendor | PT Maju Teknologi, CV Sinar Office, PT Prima Solusi |

Data awal: 2 departemen (IT, Umum) dengan anggaran tahun berjalan, 3 vendor, 11 barang/jasa, 1 gudang.

## 3. Panduan alur (skenario demo)
1. `pemohon1`: **Buat PR** (mis. Laptop x5, Mouse x10, Keyboard USB x10) lalu *Simpan & ajukan*.
2. `atasan1`: **Approval PR** > Tinjau > *Minta revisi* (catatan wajib). `pemohon1` memperbaiki dan mengajukan ulang; `atasan1` *Setujui*. (Cabang tolak: PR lain ditolak dengan catatan.)
3. `staf1`: menu **RFQ** > *Verifikasi & buat RFQ*, pilih 3 vendor, isi batas waktu > *Kirim ke vendor*.
4. `vendor1` dan `vendor2`: **RFQ Masuk** > isi harga > *Kirim penawaran*.
5. `staf1`: untuk vendor3 pakai **OCR**: unggah `samples/penawaran_vendor3.png` (atau `.pdf`), periksa isian yang terisi otomatis, koreksi bila perlu, *Simpan*. Buat contoh dokumen dengan `python tools/make_sample_quotation.py`. Lalu **Bandingkan penawaran** dan *Tetapkan pemenang* (alasan wajib).
6. `staf1`: **Buat PO** > *Ajukan ke manajer*. `manajer1`: **Approval PO** (revisi lalu setuju). `staf1`: *Terbitkan & kirim ke vendor*; PDF PO tersedia di tombol *Cetak PDF*.
7. Vendor pemenang: **PO Saya** > *Konfirmasi*, lalu isi *info pengiriman* (nomor surat jalan).
8. `gudang1`: **Menunggu Penerimaan** > Periksa; tandai item *Tidak Sesuai* (alasan wajib) sehingga komplain terbentuk. `staf1`: **Komplain** > teruskan ke vendor. Vendor: *Kirim ulang*. `gudang1`: periksa lagi, kali ini Sesuai.
9. `staf1`: buka PO > *Verifikasi GR & tutup PO*. PO dan PR menjadi **Selesai**.
10. Dashboard tiap role, **Laporan PR/PO** (dengan unduh CSV), dan **Audit Log** (admin) mencatat seluruh langkah.

## 4. Pengujian
```bash
pytest
```
Tes memakai SQLite in-memory (tidak perlu PostgreSQL maupun Tesseract). `tests/test_flow.py` menjalankan skenario end-to-end (revisi, tolak, RFQ 3 vendor, penawaran tidak lengkap, PO revisi, komplain, kirim ulang, tutup PO, hak akses 403). `tests/test_units.py` menguji format uang, parsing angka Indonesia, dan parser OCR.

## 5. Struktur proyek
```
app/
  __init__.py   application factory       models.py     seluruh model
  services.py   penomoran, audit, notifikasi, anggaran, linimasa, penawaran
  views/        satu Blueprint per modul: auth, main, users, master, pr, approval, rfq,
                vendor_portal, po, gr, report, ocr
  ocr/          engine (baca teks), parser (regex), matcher (difflib)
  templates/ static/ (Bootstrap lokal)
scripts/        create_db.py, create_db.sql      tools/  make_sample_quotation.py
samples/        contoh dokumen penawaran         tests/  pytest        docs/  BPMN, WBS, ER
```

## 6. Troubleshooting
- **`could not connect to server` / `connection refused`**: layanan PostgreSQL belum berjalan, atau host/port di `DATABASE_URL` salah.
- **`password authentication failed`**: user/password di `DATABASE_URL` salah. Karakter khusus pada password perlu di-URL-encode (mis. `@` menjadi `%40`).
- **`database "procurement" does not exist`**: jalankan `python scripts/create_db.py`.
- **`relation "users" does not exist`**: jalankan `flask --app run init-db` sebelum `seed-demo`.
- **Tesseract tidak ditemukan**: lihat bagian Tesseract; isi `TESSERACT_CMD`. Fitur lain tidak terpengaruh.
- **Port 5000 terpakai** (umum di macOS karena AirPlay): ubah port di `run.py`, atau `flask --app run run --port 5001`.
- **Token formulir tidak valid**: muat ulang halaman (sesi habis setelah 8 jam).

## 7. Catatan
- **Migrasi**: tanpa Alembic; `init-db` memakai `create_all` (keputusan sederhana untuk keperluan tes). Perubahan skema pada database yang sudah ada tidak otomatis diterapkan.
- **Selisih kecil dengan dokumen**: Blueprint disatukan dalam paket `app/views/` (satu berkas per modul) alih-alih satu paket per modul. Periode anggaran berupa tahun. Waktu disimpan sebagai WIB (UTC+7, offset tetap karena tanpa DST).
- **Aturan yang dipilih**: RFQ dibuat bersamaan dengan verifikasi PR (satu halaman); satu RFQ per PR; PO dibuat dari RFQ berstatus *Pemenang Dipilih* dan RFQ menjadi *Ditutup*; qty yang dihitung "diterima" hanya yang hasilnya *Sesuai*; selama ada komplain yang belum dikirim ulang, gudang tidak bisa membuat GR baru untuk PO itu.
- **OCR**: PDF digital dibaca dari lapisan teksnya (tanpa Tesseract); gambar dan PDF hasil scan dibaca dengan Tesseract. Hasil ekstraksi selalu ditampilkan sebagai form yang bisa diedit; periksa kembali sebelum menyimpan. Akurasi tidak dijamin.
- **Fitur opsional yang dikerjakan**: 1.5 (profil), 8.4 (unduh CSV). Lainnya belum (2.8, 3.7, 3.8, 3.9, 4.6, 4.7, 5.10, 6.7, 7.7, 8.5, 8.6).
- **Status verifikasi**: lihat `PROGRESS.md` (bagian "Yang belum terverifikasi").
