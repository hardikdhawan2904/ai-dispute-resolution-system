"""
Unified text extractor — routes by file type to the appropriate extraction method.

Image       → Tesseract OCR (pytesseract)
PDF         → pdfplumber; falls back to Tesseract OCR for scanned PDFs
XLSX / CSV  → openpyxl / csv module
"""
import csv
import os
from pathlib import Path

_MAX_CHARS = 4000
_SUPPORTED = {".jpg", ".jpeg", ".png", ".pdf", ".xlsx", ".csv"}


def extract_text(file_path: str) -> str:
    """
    Extract readable text from any supported file.
    Returns empty string for unsupported or unreadable files.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if not path.exists() or ext not in _SUPPORTED:
        return ""

    if ext in {".jpg", ".jpeg", ".png"}:
        return _ocr_image(file_path)
    if ext == ".pdf":
        return _extract_pdf(file_path)
    if ext == ".xlsx":
        return _extract_xlsx(file_path)
    if ext == ".csv":
        return _extract_csv(file_path)
    return ""


def _ocr_image(file_path: str) -> str:
    """Extract text from an image using Tesseract OCR.
    Falls back to a filename stub when Tesseract is unavailable so the LLM
    still knows a document was attached."""
    path = Path(file_path)
    stub = (
        f"[Document attached: {path.name}. "
        f"Automatic OCR text reading is unavailable. "
        f"Assess document relevance based on its filename and the dispute context. "
        f"Do NOT set evidence_match to null — a document was submitted.]"
    )

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return stub

    tess_cmd = os.getenv("TESSERACT_CMD")
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img).strip()[:_MAX_CHARS]
        return text if text else stub
    except Exception:
        return stub


def _extract_pdf(file_path: str) -> str:
    import pdfplumber
    lines = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    lines.append(text.strip())
    except Exception:
        pass

    text = "\n".join(lines).strip()
    if text:
        return text[:_MAX_CHARS]

    # No text layer — scanned PDF, fall back to Tesseract OCR
    return _ocr_pdf_tesseract(file_path)


def _ocr_pdf_tesseract(file_path: str) -> str:
    """Render each PDF page as a high-res image and run Tesseract OCR on it."""
    try:
        import fitz  # pymupdf
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        return ""

    # Allow overriding the Tesseract binary path via env var (useful on Windows)
    tess_cmd = os.getenv("TESSERACT_CMD")
    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

    pages_text = []
    try:
        doc = fitz.open(file_path)
        for page in doc:
            # 2× zoom gives ~144 DPI — good enough for Tesseract without being huge
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img)
            if text.strip():
                pages_text.append(text.strip())
        doc.close()
    except Exception:
        return ""

    return "\n".join(pages_text)[:_MAX_CHARS]


def _extract_csv(file_path: str) -> str:
    rows = []
    try:
        with open(file_path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                if any(cell.strip() for cell in row):
                    rows.append(", ".join(row))
    except Exception:
        return ""
    return "\n".join(rows)[:_MAX_CHARS]


def _extract_xlsx(file_path: str) -> str:
    import openpyxl
    rows = []
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        for sheet in wb.worksheets:
            rows.append(f"[Sheet: {sheet.title}]")
            for row in sheet.iter_rows(values_only=True):
                if any(c is not None for c in row):
                    rows.append("\t".join(str(c) if c is not None else "" for c in row))
    except Exception:
        return ""
    return "\n".join(rows)[:_MAX_CHARS]
