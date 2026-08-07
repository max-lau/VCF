"""
intake_router.py
================
Routing layer for OCR Intake and Email Intake.

Goal: reduce Claude Vision token spend by parsing documents locally first.
Vision remains the final fallback for handwriting, complex forms, and failures.

Rollout phase 1 (Email Intake):
  - Email bodies: plain text / HTML → Markdown (no model).
  - Email attachments:
      * Office / OpenDocument / CSV / EPUB / TXT → local extractor (AnyDoc if installed,
        otherwise mammoth/python-docx for docx, plain decoder for txt/csv) → Markdown.
      * PDF / image → existing OCR pipeline (Vision/Tesseract).

Future phase 2 (OCR Intake):
  - PDF → pdf-inspector: text pages extracted locally, only flagged pages to Vision.
  - Images → local OCR (Tesseract/PaddleOCR), low confidence → Vision.

Output contract (standardized dict):
  {
    "text": str,              # extracted Markdown/text
    "text_english": str,      # English translation if available
    "word_count": int,
    "confidence": float,
    "engine": str,            # e.g. "anydoc", "tesseract", "claude-vision"
    "route_taken": str,       # e.g. "email_body", "anydoc", "ocr_fallback", "vision"
    "content_hash": str,      # sha256 of input bytes
    "form_fields": dict|None, # optional VCF form fields
  }
"""
import os
import io
import re
import html
import time
import hashlib
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional dependencies — if missing, route falls back to existing OCR/Vision.
try:
    import markdownify
    _MARKDOWNIFY_AVAILABLE = True
except Exception:
    markdownify = None
    _MARKDOWNIFY_AVAILABLE = False

try:
    import anydoc
    _ANYDOC_AVAILABLE = True
except Exception:
    anydoc = None
    _ANYDOC_AVAILABLE = False

try:
    import mammoth
    _MAMMOTH_AVAILABLE = True
except Exception:
    mammoth = None
    _MAMMOTH_AVAILABLE = False

try:
    from docx import Document
    _PYTHON_DOCX_AVAILABLE = True
except Exception:
    Document = None
    _PYTHON_DOCX_AVAILABLE = False


# Extensions handled locally without Vision in phase 1.
ANYDOC_EXTENSIONS = {
    ".doc", ".docx", ".docm",
    ".xls", ".xlsx", ".xlsm",
    ".ppt", ".pptx",
    ".rtf", ".odt", ".ods", ".odp",
    ".epub", ".csv", ".txt",
}

# Extensions that go to the existing OCR pipeline (Vision/Tesseract).
OCR_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif",
}

# Observability keys match the spec: route_taken, pages_total, etc.
_ROUTE_LOG_KEYS = ["route_taken", "pages_total", "pages_to_vision", "tokens_used", "latency_ms"]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _find_cached_extraction(content_hash: str, firm_id: str) -> Optional[dict]:
    """Return a previous extraction for the same file bytes if one exists."""
    try:
        from backend.demo1.pg import get_conn
        with get_conn(firm_id) as conn:
            row = conn.execute(
                """SELECT doc_text, summary, doc_type, entities_json, identity_signals
                   FROM case_documents
                   WHERE firm_id = %s AND content_hash = %s
                     AND doc_text IS NOT NULL AND doc_text != ''
                   ORDER BY upload_date DESC NULLS LAST
                   LIMIT 1""",
                (firm_id, content_hash),
            ).fetchone()
        if row:
            return {
                "text": row["doc_text"] or "",
                "text_english": "",
                "word_count": len((row["doc_text"] or "").split()),
                "confidence": 99.0,
                "engine": "cache",
                "route_taken": "dedupe_cache",
                "content_hash": content_hash,
                "form_fields": row.get("entities_json") or row.get("identity_signals") or None,
            }
    except Exception as e:
        logger.warning(f"[intake_router] cache lookup failed: {e}")
    return None


def _html_to_markdown(body_html: str) -> str:
    """Convert HTML email body to Markdown. Falls back to tag stripping."""
    if _MARKDOWNIFY_AVAILABLE:
        try:
            md = markdownify.markdownify(body_html, heading_style="ATX", strip=["script", "style"])
            return _collapse_whitespace(md)
        except Exception as e:
            logger.debug(f"[intake_router] markdownify failed: {e}")
    # Fallback: strip tags and decode entities.
    text = re.sub(r"<script[^>]*>.*?</script>", "", body_html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return _collapse_whitespace(text)


def _collapse_whitespace(text: str) -> str:
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _anydoc_convert(data: bytes, filename: str) -> Optional[dict]:
    """Use AnyDoc to convert Office/OpenDocument/EPUB/CSV/TXT to Markdown."""
    if not _ANYDOC_AVAILABLE:
        return None
    try:
        # AnyDoc API surface is assumed from spec: convert bytes/filename to markdown.
        # The exact call may need adjustment when the real package is installed.
        md = anydoc.convert(io.BytesIO(data), filename=filename)
        text = md if isinstance(md, str) else md.get("markdown", "")
        return {
            "text": _collapse_whitespace(text),
            "text_english": "",
            "word_count": len(text.split()),
            "confidence": 99.0,
            "engine": "anydoc",
            "route_taken": "anydoc",
        }
    except Exception as e:
        logger.warning(f"[intake_router] AnyDoc failed for {filename}: {e}")
    return None


def _mammoth_convert(data: bytes, filename: str) -> Optional[dict]:
    """Use mammoth to convert .docx → HTML → Markdown."""
    if not _MAMMOTH_AVAILABLE or _ext(filename) != ".docx":
        return None
    try:
        result = mammoth.convert_to_html(io.BytesIO(data))
        if result.messages:
            logger.debug(f"[intake_router] mammoth messages for {filename}: {result.messages}")
        html = result.value
        if _MARKDOWNIFY_AVAILABLE:
            md = markdownify.markdownify(html, heading_style="ATX", strip=["script", "style"])
        else:
            md = re.sub(r"<[^>]+>", " ", html)
        return {
            "text": _collapse_whitespace(md),
            "text_english": "",
            "word_count": len(md.split()),
            "confidence": 99.0,
            "engine": "mammoth",
            "route_taken": "mammoth",
        }
    except Exception as e:
        logger.warning(f"[intake_router] mammoth failed for {filename}: {e}")
    return None


def _pythondocx_convert(data: bytes, filename: str) -> Optional[dict]:
    """Use python-docx to extract text from .docx as a fallback."""
    if not _PYTHON_DOCX_AVAILABLE or _ext(filename) != ".docx":
        return None
    try:
        doc = Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n\n".join(paragraphs)
        return {
            "text": _collapse_whitespace(text),
            "text_english": "",
            "word_count": len(text.split()),
            "confidence": 99.0,
            "engine": "python-docx",
            "route_taken": "python-docx",
        }
    except Exception as e:
        logger.warning(f"[intake_router] python-docx failed for {filename}: {e}")
    return None


def _text_convert(data: bytes, filename: str) -> Optional[dict]:
    """Handle plain text and CSV directly without any Office parser."""
    ext = _ext(filename)
    if ext == ".csv":
        import csv
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        rows = [" | ".join(row) for row in reader]
        text = "\n".join(rows)
    elif ext == ".txt":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="ignore")
    else:
        return None
    return {
        "text": _collapse_whitespace(text),
        "text_english": "",
        "word_count": len(text.split()),
        "confidence": 99.0,
        "engine": "text",
        "route_taken": "text",
    }


def _ocr_fallback(data: bytes, filename: str, firm_id: str) -> dict:
    """Fall back to the existing OCR pipeline (Tesseract → Vision)."""
    from backend.demo1.ocr_intake import (
        extract_text, clean_ocr_text, extract_form_fields, pdf_to_image_pages,
    )

    ext = _ext(filename)
    mime = "application/pdf" if ext == ".pdf" else {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }.get(ext, "image/jpeg")

    try:
        if ext == ".pdf":
            pages = pdf_to_image_pages(data)
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
            pages = data
        else:
            pages = data
        result = extract_text(pages, lang="eng", engine="auto", mime_type=mime, firm_id=firm_id)
        text = clean_ocr_text(result.get("text", ""))
        return {
            "text": text,
            "text_english": result.get("text_english", ""),
            "word_count": result.get("word_count", len(text.split())),
            "confidence": result.get("confidence", 0.0),
            "engine": result.get("engine", "ocr"),
            "route_taken": "ocr_fallback",
            "form_fields": result.get("form_fields") or extract_form_fields(text),
        }
    except Exception as e:
        logger.error(f"[intake_router] OCR fallback failed for {filename}: {e}")
        raise


def route_file(filename: str, data: bytes, firm_id: str) -> dict:
    """Route a file through the cheapest extractor that can handle it.

    Returns a standardized extraction dict. Never returns None — raises on total
    failure so callers can decide whether to reject the file.
    """
    import time
    start = time.perf_counter()
    content_hash = _sha256(data)
    ext = _ext(filename)

    # 1. Hash dedupe.
    cached = _find_cached_extraction(content_hash, firm_id)
    if cached:
        cached["content_hash"] = content_hash
        cached["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return cached

    result: Optional[dict] = None

    # 2. Office / CSV / TXT → local extractors first, Vision last.
    office_local_enabled = os.getenv("INTAKE_OFFICE_LOCAL_ENABLED", "true").lower() in ("1", "true", "yes")
    if office_local_enabled and ext in ANYDOC_EXTENSIONS:
        result = _text_convert(data, filename)
        if result is None:
            result = _anydoc_convert(data, filename)
        if result is None:
            result = _mammoth_convert(data, filename)
        if result is None:
            result = _pythondocx_convert(data, filename)
        if result is None:
            logger.info(f"[intake_router] Local office extractors unavailable for {filename}; falling back to OCR")

    # 3. PDF / image → existing OCR pipeline (Vision/Tesseract).
    if result is None and ext in OCR_EXTENSIONS:
        result = _ocr_fallback(data, filename, firm_id)

    # 4. Final fallback: try OCR on anything else, then let it raise if it fails.
    if result is None:
        if ext in OCR_EXTENSIONS or ext in ANYDOC_EXTENSIONS:
            result = _ocr_fallback(data, filename, firm_id)
        else:
            raise ValueError(f"Unsupported file type for intake routing: {ext}")

    result["content_hash"] = content_hash
    result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)

    # Observability log per spec.
    logger.info(
        f"[intake_router] {filename}: route={result.get('route_taken')} "
        f"engine={result.get('engine')} conf={result.get('confidence')} "
        f"latency={result.get('latency_ms')}ms"
    )
    return result


def route_email_body(body_text: str, body_html: str) -> dict:
    """Convert an email body to Markdown with no model call."""
    start = time.time()
    if body_html and len(body_html.strip()) > len(body_text.strip()):
        text = _html_to_markdown(body_html)
        route = "email_body_html"
    else:
        text = _collapse_whitespace(body_text or "")
        route = "email_body_text"

    return {
        "text": text,
        "text_english": "",
        "word_count": len(text.split()),
        "confidence": 99.0,
        "engine": "email_body",
        "route_taken": route,
        "content_hash": _sha256((body_html or body_text or "").encode("utf-8")),
        "latency_ms": round((time.time() - start) * 1000, 2),
    }
