#!/usr/bin/env python3
"""Extract text from PDF: native layers first; optional OCR for scanned pages.

Depends (install as needed):
  pip install pymupdf
  OCR (optional): pip install pytesseract pillow
  Binary: Tesseract (https://github.com/tesseract-ocr/tesseract) + PATH

Example:
  python scripts/extract_pdf_text.py \"C:\\\\path\\\\book.pdf\" -o docs/generated/out.txt --ocr --dpi 200

If --ocr fails, output still contains native-layer text plus a stderr note."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _native_text_pdf_path(path: Path) -> tuple[str, int]:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    chunks: list[str] = []
    n = len(doc)
    for page_index in range(n):
        page = doc.load_page(page_index)
        chunks.append(page.get_text("text") or "")
    doc.close()
    return "\n\n".join(chunks).strip(), n


def _ocr_pdf_path(path: Path, dpi: int) -> tuple[str, int]:
    import fitz
    import pytesseract  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    doc = fitz.open(path)
    chunks: list[str] = []
    for page_index in range(len(doc)):
        pix = doc.load_page(page_index).get_pixmap(matrix=mat, alpha=False)
        mode = "RGB" if pix.n < 5 else "RGBA"
        image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        if mode == "RGBA":
            image = image.convert("RGB")
        text = pytesseract.image_to_string(image) or ""
        chunks.append(text)
    doc.close()
    return "\n\n".join(chunks).strip(), len(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF text extraction (PyMuPDF + optional Tesseract OCR).")
    parser.add_argument("pdf", type=Path, help="Path to .pdf")
    parser.add_argument("-o", "--out", type=Path, default=None, help="Write extracted text here (UTF-8)")
    parser.add_argument("--ocr", action="store_true", help="Run Tesseract OCR on rendered pages")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI when using --ocr (default 200)")
    parser.add_argument("--min-native-chars", type=int, default=80, help="If native text shorter, suggest --ocr")
    ns = parser.parse_args()

    if not ns.pdf.exists():
        print(f"File not found: {ns.pdf}", file=sys.stderr)
        return 2

    try:
        text, pages = _native_text_pdf_path(ns.pdf)
    except ImportError:
        print("Install PyMuPDF: pip install pymupdf", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"PyMuPDF failed: {exc}", file=sys.stderr)
        return 4

    used_ocr = False
    if ns.ocr:
        try:
            text, pages = _ocr_pdf_path(ns.pdf, ns.dpi)
            used_ocr = True
        except ImportError as exc:
            print(f"OCR deps missing ({exc}). pip install pymupdf pytesseract pillow", file=sys.stderr)
            return 5
        except Exception as exc:
            print(f"OCR failed: {exc}", file=sys.stderr)
            return 6

    header = (
        f"--- extracted from {ns.pdf.name} ({pages} pages)"
        + (" OCR" if used_ocr else " native")
        + " ---\n\n"
    )
    if len(text) < ns.min_native_chars and not ns.ocr:
        print(
            f"Note: only {len(text)} chars via native extraction; retry with --ocr if this is a scan.",
            file=sys.stderr,
        )

    out_txt = header + text + "\n"
    if ns.out:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(out_txt, encoding="utf-8")
        print(str(ns.out.resolve()))
    else:
        sys.stdout.buffer.write(out_txt.encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
