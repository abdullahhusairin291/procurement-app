"""Membaca teks dari dokumen penawaran: PDF (lapisan teks, atau render + OCR) dan gambar (Tesseract)."""
from pathlib import Path

INSTALL_HELP = (
    "Tesseract OCR belum terpasang atau tidak ditemukan. "
    "Windows: pasang installer UB Mannheim (https://github.com/UB-Mannheim/tesseract/wiki), "
    "centang data bahasa Indonesia, lalu isi TESSERACT_CMD di file .env "
    "(mis. C:\\Program Files\\Tesseract-OCR\\tesseract.exe). "
    "macOS: brew install tesseract tesseract-lang. Linux: sudo apt install tesseract-ocr tesseract-ocr-ind."
)


class OCRUnavailable(Exception):
    """Dependensi OCR tidak tersedia; pesan sudah siap ditampilkan ke pengguna."""


def _pytesseract(cmd):
    import pytesseract
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract


def tesseract_status(cmd=""):
    """(tersedia, pesan). Tidak melempar error agar halaman OCR tetap bisa tampil."""
    try:
        pt = _pytesseract(cmd)
        version = pt.get_tesseract_version()
        langs = pt.get_languages(config="")
        extra = "" if "ind" in langs else " Data bahasa Indonesia (ind) belum ada, memakai bahasa Inggris."
        return True, f"Tesseract {version} siap.{extra}"
    except Exception:  # termasuk TesseractNotFoundError dan ImportError
        return False, INSTALL_HELP


def _language(pt):
    try:
        return "ind+eng" if "ind" in pt.get_languages(config="") else "eng"
    except Exception:
        return "eng"


def _ocr_image(pt, image):
    from PIL import Image
    gray = image.convert("L")
    if gray.width < 1500:  # gambar kecil dibesarkan agar lebih mudah dibaca
        gray = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
    try:
        return pt.image_to_string(gray, lang=_language(pt), config="--psm 6")
    except pt.TesseractNotFoundError as exc:
        raise OCRUnavailable(INSTALL_HELP) from exc


def extract_text(path, tesseract_cmd=""):
    """Mengembalikan (teks, metode). Melempar OCRUnavailable bila alat yang dibutuhkan tidak ada."""
    from PIL import Image
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise OCRUnavailable("PyMuPDF belum terpasang. Jalankan: pip install -r requirements.txt") from exc
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
            if len(text.strip()) >= 40:  # PDF digital: lapisan teks lebih akurat daripada OCR
                return text, "teks PDF"
            pt = _pytesseract(tesseract_cmd)
            parts = []
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                parts.append(_ocr_image(pt, img))
        return "\n".join(parts), "OCR halaman PDF"
    with Image.open(path) as img:
        return _ocr_image(_pytesseract(tesseract_cmd), img), "OCR gambar"
