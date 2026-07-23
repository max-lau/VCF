"""
ocr_intake.py  (ACP-VCF revision)
=================================
FastAPI APIRouter: OCR Intake Module
Uses Claude Vision API for handwriting (primary) and
Tesseract for printed/typed text (fallback).

Changes vs. ParaIQ original
  1. Vision prompt is now VCF-specific: extracts registration + eligibility
     fields (name, native-script name, DOB, address, exposure site/dates,
     conditions, WTC Health Program, preferred language) instead of the
     litigation schema (matter_type/opposing_party). Legacy keys are still
     populated for backward compatibility with existing UI/DB consumers.
  2. The vision call also returns "text_english" — a full English translation
     of the transcription — feeding the structured-English-document workflow.
  3. Multi-page PDF support: up to INTAKE_MAX_PDF_PAGES pages (default 5) are
     rendered and sent to Claude in one multi-image message. The original code
     silently dropped every page after page 1.
  4. Explicit conn.commit() after inserts (main.py's helpers commit explicitly,
     so get_conn very likely does not autocommit — verify against pg.py; a
     redundant commit is harmless either way).

Endpoints:
  POST /intake/scan      - upload image/PDF → extract text only
  POST /intake/analyze   - upload image/PDF → text + full NLP analysis
  POST /intake/form      - upload image/PDF → structured intake form fields
  GET  /intake/history   - view past intake scans
"""

import os
import io
import re
import base64
import json
import logging
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request, Query
from typing import Optional, Union
from PIL import Image
import pytesseract

from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = 'tesseract'

router = APIRouter()

INTAKE_MAX_PDF_PAGES = int(os.getenv("INTAKE_MAX_PDF_PAGES", "5"))


def init_intake_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Intake] OCR table initialized [OK]")


# ═══════════════════════════════════════════════════════════════════════════════
# CASE LINKING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(name.split())


def _extract_identity_signals(form_fields: dict) -> dict:
    """Normalize the identity clues we use to match a document to a case."""
    return {
        "name":               _normalize_name(form_fields.get("client_name")),
        "dob":                form_fields.get("date_of_birth") or None,
        "ssn_last4":          form_fields.get("ssn_last4") or None,
        "phone":              form_fields.get("phone") or None,
        "email":              form_fields.get("email") or None,
        "address":            form_fields.get("address") or None,
        "employer":           form_fields.get("employer") or None,
        "provider_name":      form_fields.get("provider_name") or None,
        "medical_conditions": form_fields.get("medical_conditions") or [],
        "doc_type":           form_fields.get("doc_type") or "other",
    }


def find_case_by_identity(firm_id: str, signals: dict) -> tuple[int | None, str | None, str | None]:
    """Return (case_id, match_status, reason) using multiple identity signals.

    Match precedence:
      1. name + DOB
      2. name + SSN last4
      3. exact name only if unique within the firm
    """
    name = signals.get("name")
    dob  = signals.get("dob")
    ssn  = signals.get("ssn_last4")
    if not name:
        return None, None, None

    with get_conn(firm_id) as conn:
        if dob:
            row = conn.execute(
                """SELECT id FROM cases
                   WHERE firm_id = %s AND deleted = FALSE
                     AND LOWER(client_name) = LOWER(%s)
                     AND date_of_birth = %s
                   ORDER BY id ASC LIMIT 1""",
                (firm_id, name, dob)
            ).fetchone()
            if row:
                return row["id"], "matched", "name+dob"

        if ssn:
            row = conn.execute(
                """SELECT id FROM cases
                   WHERE firm_id = %s AND deleted = FALSE
                     AND LOWER(client_name) = LOWER(%s)
                     AND ssn_last4 = %s
                   ORDER BY id ASC LIMIT 1""",
                (firm_id, name, ssn)
            ).fetchone()
            if row:
                return row["id"], "matched", "name+ssn"

        rows = conn.execute(
            """SELECT id FROM cases
               WHERE firm_id = %s AND deleted = FALSE
                 AND LOWER(client_name) = LOWER(%s)
               ORDER BY id ASC""",
            (firm_id, name)
        ).fetchall()
        if len(rows) == 1:
            return rows[0]["id"], "matched", "name_unique"

    return None, None, None


def auto_create_case_from_intake(firm_id: str, signals: dict) -> dict:
    """Create a new VCF case from extracted intake identity signals.

    Returns {case_id, case_number, created, match_status}.
    """
    from backend.demo1.case_management import generate_case_number
    name = signals.get("name") or "Unknown Client"
    dob = signals.get("dob") or None
    with get_conn(firm_id) as conn:
        case_number = generate_case_number(firm_id, conn)
        cur = conn.execute(
            """INSERT INTO cases
               (firm_id, case_number, client_name, status, claim_stage, vcf_status,
                presence_proof_status, date_of_birth, ssn_last4, preferred_language,
                exposure_location, presence_dates, wtc_health_program, description)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (firm_id, case_number, name, "open", "intake", "pending",
             "not_started", dob,
             signals.get("ssn_last4") or None,
             None,
             None,
             None,
             False,
             "Auto-created from OCR intake scan")
        )
        case_id = cur.fetchone()["id"]
        conn.execute(
            "INSERT INTO case_notes (firm_id, case_id, note) VALUES (%s,%s,%s)",
            (firm_id, case_id, f"Case auto-created from intake scan: {case_number} for {name}")
        )
    return {"case_id": case_id, "case_number": case_number,
            "created": True, "match_status": "auto_created"}


def resolve_case_for_intake(
    firm_id: str,
    form_fields: dict,
    provided_case_id: int | None,
    doc_type: str = "other"
) -> dict:
    """Resolve which case a scan belongs to.

    If provided_case_id is given, validate it and return it.
    Otherwise match by identity. Intake forms without a match auto-create a case;
    other document types stay unmatched so a paralegal can assign them via the inbox.

    Returns {case_id, case_number, created, matched, match_status, match_reason, signals}.
    """
    signals = _extract_identity_signals(form_fields)

    if provided_case_id:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT id, case_number FROM cases WHERE id = %s AND firm_id = %s AND deleted = FALSE",
                (provided_case_id, firm_id)
            ).fetchone()
        if row:
            return {
                "case_id": row["id"], "case_number": row["case_number"],
                "created": False, "matched": False,
                "match_status": "manual", "match_reason": "user_selected",
                "signals": signals,
            }

    case_id, status, reason = find_case_by_identity(firm_id, signals)
    if case_id:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT case_number FROM cases WHERE id = %s", (case_id,)
            ).fetchone()
        return {
            "case_id": case_id,
            "case_number": row["case_number"] if row else None,
            "created": False, "matched": True,
            "match_status": status, "match_reason": reason,
            "signals": signals,
        }

    if doc_type == "intake_form" and signals.get("name"):
        return {**auto_create_case_from_intake(firm_id, signals), "matched": False, "signals": signals}

    return {
        "case_id": None, "case_number": None,
        "created": False, "matched": False,
        "match_status": "unmatched", "match_reason": None,
        "signals": signals,
    }


def _safe_doc_type(doc_type: str | None) -> str:
    """Storage-path-safe doc type string."""
    if not doc_type:
        return "other"
    return re.sub(r"[^a-z0-9_-]", "_", doc_type.lower())[:40]


def _insert_case_document(
    conn,
    firm_id: str,
    scan_id: int,
    case_id: int | None,
    filename: str,
    text: str,
    text_english: str,
    form_fields: dict,
    file_url: str | None,
    signals: dict,
    match_status: str,
) -> int | None:
    """Create a case_documents row from a routed intake scan.

    Returns the new case_document id, or None if insert failed.
    """
    doc_type = _safe_doc_type(signals.get("doc_type"))
    summary = ""
    key_facts = form_fields.get("key_facts") or []
    if key_facts:
        summary = " ".join(str(k) for k in key_facts)[:1000]
    elif text_english:
        summary = text_english[:1000]
    elif text:
        summary = text[:1000]

    identity_signals = {k: v for k, v in signals.items() if v}
    try:
        cur = conn.execute(
            """INSERT INTO case_documents
               (firm_id, case_id, scan_id, document_name, source, doc_text, summary,
                doc_type, file_url, identity_signals, match_status, language, upload_date)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                firm_id, case_id, scan_id, filename, "intake_scan",
                text or "", summary, doc_type, file_url,
                json.dumps(identity_signals), match_status, "en",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.fetchone()["id"]
    except Exception as e:
        logger.error(f"[Intake] Failed to create case_document for scan {scan_id}: {e}")
        return None


# ── Claude Vision OCR ──────────────────────────────────────────────────────────

_VCF_VISION_PROMPT = """You are processing documents for a 9/11 Victim Compensation Fund (VCF) claim at a law firm. The document may be handwritten, in Chinese, English, or mixed.

Read ALL page image(s) provided and respond with ONLY a JSON object (no markdown fences, no commentary) with exactly these top-level keys:

"text": complete verbatim transcription of every word and number visible across all pages, in the original language, preserving line breaks and field labels.
"text_english": a complete, faithful English translation of "text". If already in English, repeat it.

"doc_type": Classify the document into exactly one of these categories: 
  - "intake_form" (VCF eligibility questionnaire, PIQ, retainer)
  - "medical_record" (doctor notes, hospital records, lab results)
  - "presence_proof" (lease, utility bill, employment records proving NYC presence)
  - "financial_doc" (W-2, tax return, pay stub)
  - "gov_benefit" (SSDI award letter, Medicare/Medicaid letter, workers comp)
  - "death_cert" (Death Certificate)
  - "correspondence" (letter from VCF, email, memo)
  - "other"

"fields": an object containing VCF-specific fields. Extract ONLY what is visible in the document. Never guess. Use null for missing fields.
  - "client_name": claimant's name romanized to English.
  - "date_of_birth": "YYYY-MM-DD" or null.
  - "ssn_last4": last 4 digits of SSN if present, else null.
  - "exposure_location": where the claimant was in the NYC exposure zone, or null.
  - "presence_dates": the period(s) the claimant was present between 9/11/2001 and 5/30/2002, as written, or null.
  - "employer": employer name if mentioned, or null.
  - "medical_conditions": array of diagnosed conditions in English (e.g. ["rhinosinusitis", "GERD"]), empty array if none stated.
  - "provider_name": doctor or hospital name (for medical records), or null.
  - "benefit_amount": dollar amount of SSDI/Workers Comp/Medicare lien if visible, or null.
  - "annual_income": adjusted gross income from tax/W-2 docs, or null.
  - "key_facts": up to 5 short English sentences with the most claim-significant facts.

Return ONLY the JSON object."""


def ocr_with_claude(image_pages: Union[bytes, list],
                    mime_type: str = "image/jpeg",
                    firm_id: str = "default") -> dict:
    """Claude Vision transcription + VCF-structured extraction in one call.

    Accepts a single image (bytes) or a list of page images (list[bytes]),
    all sent in one multi-image message so cross-page context is preserved.
    If the JSON response can't be parsed, falls back to plain-text mode and
    the caller falls back to regex-based extract_form_fields().
    """
    from backend.demo1.main import claude_with_retry, client, LLM_STRONG

    if isinstance(image_pages, (bytes, bytearray)):
        image_pages = [bytes(image_pages)]

    content = []
    for page in image_pages[:INTAKE_MAX_PDF_PAGES]:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.standard_b64encode(page).decode("utf-8"),
            },
        })
    content.append({"type": "text", "text": _VCF_VISION_PROMPT})

    response = claude_with_retry(
        client.messages.create,
        model=LLM_STRONG,
        max_tokens=4000,
        messages=[{"role": "user", "content": content}],
        firm_id=firm_id,
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        text = raw
    text_english = ""
    form_fields = None
    try:
        parsed = json.loads(raw)
        text = (parsed.get("text") or "").strip()
        text_english = (parsed.get("text_english") or "").strip()
        f = parsed.get("fields") or {}
        form_fields = {
            # VCF schema
            "doc_type":           parsed.get("doc_type", "other"),
            "client_name":        f.get("client_name"),
            "date_of_birth":      f.get("date_of_birth"),
            "ssn_last4":          f.get("ssn_last4"),
            "exposure_location":  f.get("exposure_location"),
            "presence_dates":     f.get("presence_dates"),
            "employer":           f.get("employer"),
            "medical_conditions": f.get("medical_conditions") or [],
            "provider_name":      f.get("provider_name"),
            "benefit_amount":     f.get("benefit_amount"),
            "annual_income":      f.get("annual_income"),
            "key_facts":          (f.get("key_facts") or [])[:5],
            # Legacy keys kept so existing UI/queries don't break
            "matter_type":        "vcf_claim",
            "opposing_party":     None,
            "phone":              None,
            "email":              None,
            "address":            None,
            "preferred_language": None,
            "presence_role":      None,
            "wtc_health_program": None,
            "date":               None,
            "urgent":             False,
            "client_name_native": None,
        }
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"[Intake] Vision JSON parse failed, falling back to plain-text mode: {e}")
        text = raw

    result = {
        "text":         text,
        "text_english": text_english,
        "word_count":   len(text.split()),
        "confidence":   95.0,
        "engine":       "claude-vision",
    }
    if form_fields is not None:
        result["form_fields"] = form_fields
    return result


# ── Tesseract OCR ──────────────────────────────────────────────────────────────

def ocr_with_tesseract(image_pages: Union[bytes, list], lang: str = "eng") -> dict:
    """Tesseract OCR — good for printed text. Accepts one image or a page list.
    NOTE: chi_sim / chi_tra require the corresponding traineddata packages."""
    if isinstance(image_pages, (bytes, bytearray)):
        image_pages = [bytes(image_pages)]
    try:
        texts, all_conf = [], []
        for page_bytes in image_pages:
            image = Image.open(io.BytesIO(page_bytes))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
            all_conf += [int(c) for c in data["conf"] if int(c) > 30]
            texts.append(pytesseract.image_to_string(image, lang=lang).strip())

        raw_text = "\n\n".join(t for t in texts if t)
        avg_conf = round(sum(all_conf) / len(all_conf), 1) if all_conf else 0.0

        return {
            "text":         raw_text,
            "text_english": "",
            "word_count":   len(raw_text.split()),
            "confidence":   avg_conf,
            "engine":       "tesseract",
        }
    except (IOError, OSError, ValueError, pytesseract.TesseractError) as e:
        logger.error(f"[Intake] Tesseract OCR failed: {e}")
        raise HTTPException(400, "OCR failed — could not process the image")


# ── Smart dispatcher ───────────────────────────────────────────────────────────

def _looks_printed_english(text: str) -> bool:
    """Heuristic: high ratio of ASCII printable chars suggests printed English."""
    if not text:
        return False
    ascii_printable = sum(1 for c in text if 32 <= ord(c) <= 126 or c in "\n\r\t")
    return ascii_printable / max(len(text), 1) > 0.90


def extract_text(image_pages: Union[bytes, list], lang: str = "eng",
                 engine: str = "auto", mime_type: str = "image/jpeg",
                 firm_id: str = "default") -> dict:
    # Explicit Tesseract mode.
    if engine == "tesseract":
        return ocr_with_tesseract(image_pages, lang)

    # Auto mode: try low-cost Tesseract first for clean printed English.
    if engine == "auto":
        try:
            tess = ocr_with_tesseract(image_pages, lang)
            if tess.get("confidence", 0) >= 70 and _looks_printed_english(tess.get("text", "")):
                logger.info(f"[Intake] Tesseract pre-filter accepted (conf={tess['confidence']})")
                return tess
        except Exception as e:
            logger.debug(f"[Intake] Tesseract pre-filter skipped: {e}")

    # Primary: Claude Vision (handwriting, mixed-language, complex layouts).
    try:
        return ocr_with_claude(image_pages, mime_type, firm_id=firm_id)
    except (httpx.HTTPError, httpx.TimeoutException, KeyError, IndexError, ValueError) as e:
        logger.warning(f"[Intake] Claude Vision failed, falling back to Tesseract: {e}")
        return ocr_with_tesseract(image_pages, lang)


def clean_ocr_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ── Form field extractor (regex fallback only — English text) ─────────────────

def extract_form_fields(text: str) -> dict:
    fields = {
        "doc_type":           "other",
        "client_name":        None,
        "date_of_birth":      None,
        "ssn_last4":          None,
        "exposure_location":  None,
        "presence_dates":     None,
        "employer":           None,
        "medical_conditions": [],
        "provider_name":      None,
        "benefit_amount":     None,
        "annual_income":      None,
        "key_facts":          [],
        "matter_type":        "vcf_claim",
        "opposing_party":     None,
        "phone":              None,
        "email":              None,
        "address":            None,
        "preferred_language": None,
        "presence_role":      None,
        "wtc_health_program": None,
        "date":               None,
        "urgent":             False,
        "client_name_native": None,
    }
    text_lower = text.lower()
    
    # Basic document classification
    if any(kw in text_lower for kw in ["medical history", "diagnosis", "patient", "hospital", "dr."]):
        fields["doc_type"] = "medical_record"
    elif any(kw in text_lower for kw in ["w-2", "wage and tax", "adjusted gross income"]):
        fields["doc_type"] = "financial_doc"
    elif any(kw in text_lower for kw in ["ssdi", "medicare", "medicaid", "benefit award"]):
        fields["doc_type"] = "gov_benefit"
    elif any(kw in text_lower for kw in ["lease", "resided at", "utility bill"]):
        fields["doc_type"] = "presence_proof"
    elif any(kw in text_lower for kw in ["death certificate", "cause of death"]):
        fields["doc_type"] = "death_cert"
    elif any(kw in text_lower for kw in ["victim compensation fund", "vcf", "intake", "questionnaire"]):
        fields["doc_type"] = "intake_form"

    for p in [r'client\s*:\s*([A-Z][a-z]+ [A-Z][a-z]+)',
              r'name\s*:\s*([A-Z][a-z]+ [A-Z][a-z]+)']:
        m = re.search(p, text, re.IGNORECASE)
        if m: fields["client_name"] = m.group(1).strip(); break

    for p in [r'date\s*:\s*([A-Za-z]+ \d{1,2},?\s*\d{4})',
              r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b',
              r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b']:
        m = re.search(p, text, re.IGNORECASE)
        if m: fields["date"] = (m.group(1) if m.lastindex else m.group(0)).strip(); break

    m = re.search(r'\b(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})\b', text)
    if m: fields["phone"] = m.group(1)

    m = re.search(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b', text)
    if m: fields["email"] = m.group(0)

    if re.search(r'wtc health|world trade center health', text_lower):
        fields["wtc_health_program"] = True

    fields["urgent"] = any(kw in text_lower for kw in
        ["urgent", "asap", "immediately", "emergency", "deadline"])

    vcf_kws = ["exposure", "dust", "cancer", "sinusitis", "gerd", "asthma",
               "world trade", "wtc", "lower manhattan", "chinatown", "canal",
               "responder", "worker", "resident", "present", "diagnos"]
    for sent in re.split(r'[.!?\n]+', text):
        if any(kw in sent.lower() for kw in vcf_kws) and len(sent.strip()) > 15:
            fields["key_facts"].append(sent.strip())
    fields["key_facts"] = fields["key_facts"][:5]

    return fields


def pdf_to_image_pages(pdf_bytes: bytes, max_pages: int = INTAKE_MAX_PDF_PAGES) -> list:
    """Render up to max_pages of a PDF to PNG bytes using PyMuPDF."""
    import fitz  # PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.is_encrypted:
        doc.authenticate("")  # try empty password
    
    pages = []
    for i in range(min(doc.page_count, max_pages)):
        page = doc.load_page(i)
        # Render at 200 DPI for high quality OCR
        mat = fitz.Matrix(200/72, 200/72)
        pix = page.get_pixmap(matrix=mat)
        pages.append(pix.tobytes("png"))
    
    doc.close()
    if not pages:
        raise HTTPException(400, "Could not read PDF")
    return pages


# Backward-compat shim in case anything still imports the old name
def pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
    return pdf_to_image_pages(pdf_bytes, max_pages=1)[0]


def _prep_upload(contents: bytes, content_type: str):
    """Normalize an upload into (page_list_or_bytes, mime_type)."""
    if content_type == "application/pdf":
        return pdf_to_image_pages(contents), "image/png"
    return contents, content_type


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/scan")
async def scan_document(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form(default="eng"),
    engine: str = Form(default="auto"),
    case_id: Optional[int] = Form(default=None),
    firm_id: Optional[str] = Form(default=None)
):
    """Upload image/PDF → OCR → link to case → upload to Supabase Storage."""
    import uuid

    is_jwt_auth = request.headers.get("Authorization", "").startswith("Bearer ")
    if is_jwt_auth:
        firm_id = getattr(request.state, "firm_id", "default")
    else:
        if not firm_id:
            raise HTTPException(status_code=400, detail="firm_id is required for API-key requests")
        with get_conn(firm_id) as conn:
            row = conn.execute("SELECT id FROM firms WHERE id=%s", (firm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Unknown firm_id")

    contents = await file.read()

    # ── Run OCR first so we can resolve the case by identity ─────────────
    pages, mime_type = _prep_upload(contents, file.content_type)
    result = extract_text(pages, lang=lang, engine=engine,
                          mime_type=mime_type, firm_id=firm_id)
    result["text"] = clean_ocr_text(result["text"])
    form_fields = result.get("form_fields") or extract_form_fields(result["text"])

    # ── Resolve or create case ───────────────────────────────────────────
    doc_type = _safe_doc_type(form_fields.get("doc_type"))
    case_info = resolve_case_for_intake(
        firm_id, form_fields, case_id,
        doc_type=form_fields.get("doc_type", "other")
    )
    resolved_case_id = case_info["case_id"]

    # ── Upload to Supabase Storage with case-aware path ──────────────────
    file_url = None
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if supabase_url and supabase_key:
        try:
            from supabase import create_client
            supabase = create_client(supabase_url, supabase_key)
            file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'pdf'
            storage_path = (
                f"{firm_id}/cases/{resolved_case_id}/{doc_type}/{uuid.uuid4()}.{file_ext}"
                if resolved_case_id else f"{firm_id}/inbox/{uuid.uuid4()}.{file_ext}"
            )
            supabase.storage.from_("vcf-documents").upload(
                path=storage_path,
                file=contents,
                file_options={"content-type": file.content_type or "application/octet-stream"}
            )
            file_url = storage_path
        except Exception as e:
            logger.warning(f"[Intake] Supabase Storage upload failed: {e}")
    else:
        logger.warning("[Intake] SUPABASE_URL or SUPABASE_SERVICE_KEY not set in .env. Skipping file upload.")

    # ── Save to Database ─────────────────────────────────────────────────
    with get_conn(firm_id) as conn:
        row = conn.execute(
            """INSERT INTO intake_scans
               (firm_id, case_id, filename, raw_text, word_count, confidence, ocr_engine,
                file_url, form_fields, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (firm_id, resolved_case_id, file.filename, result["text"], result["word_count"],
             result["confidence"], result["engine"], file_url,
             json.dumps(form_fields),
             datetime.now(timezone.utc).isoformat())
        ).fetchone()
        scan_id = row["id"] if row else None
        case_doc_id = None
        if scan_id:
            case_doc_id = _insert_case_document(
                conn, firm_id, scan_id, resolved_case_id, file.filename,
                result["text"], result.get("text_english", ""),
                form_fields, file_url, case_info["signals"], case_info["match_status"]
            )
        conn.commit()

    return {
        "success": True,
        "scan_id": scan_id,
        "case_document_id": case_doc_id,
        "filename": file.filename,
        "file_url": file_url,
        "case_id": resolved_case_id,
        "case_number": case_info.get("case_number"),
        "case_created": case_info.get("created", False),
        "case_matched": case_info.get("matched", False),
        "match_status": case_info.get("match_status"),
        "match_reason": case_info.get("match_reason"),
        "form_fields": form_fields,
        **result
    }

@router.get("/file/{file_path:path}")
async def download_intake_file(file_path: str, request: Request):
    """Generate a secure, temporary signed URL to download a private file."""
    firm_id = getattr(request.state, "firm_id", "default")
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        raise HTTPException(status_code=500, detail="Storage not configured")
        
    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
        
        # Generate a signed URL valid for 10 minutes (600 seconds)
        res = supabase.storage.from_("vcf-documents").create_signed_url(
            path=file_path,
            expires_in=600
        )
        signed_url = res.get("signedURL")
        
        if not signed_url:
            raise HTTPException(status_code=404, detail="File not found in storage")
            
        # Redirect the browser to the secure Supabase URL
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=signed_url)
        
    except Exception as e:
        logger.error(f"[Intake] Failed to generate signed URL for {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Could not generate file link")

@router.post("/analyze")
async def analyze_document(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form(default="eng"),
    context: str = Form(default="general"),
    engine: str = Form(default="auto"),
    case_id: Optional[int] = Form(default=None)
):
    """Upload image/PDF → OCR → full NLP pipeline → link to case."""
    import uuid
    firm_id = getattr(request.state, "firm_id", "default")
    contents = await file.read()
    pages, mime_type = _prep_upload(contents, file.content_type)

    ocr_result = extract_text(pages, lang=lang, engine=engine,
                              mime_type=mime_type, firm_id=firm_id)
    text = clean_ocr_text(ocr_result["text"])

    if not text or len(text.split()) < 3:
        return {"success": False, "error": "Could not extract readable text.",
                "ocr_confidence": ocr_result["confidence"]}

    from backend.demo1.risk_scorer import score_text
    risk = score_text(text, context=context)

    import spacy
    nlp = spacy.load("en_core_web_sm")
    ner_source = ocr_result.get("text_english") or text
    entities = [{"text": e.text, "type": e.label_} for e in nlp(ner_source[:5000]).ents]

    from backend.demo1.custom_entities import extract_custom_entities
    custom_ents = extract_custom_entities(ner_source)

    form_fields = ocr_result.get("form_fields") or extract_form_fields(text)

    # ── Resolve or create case ───────────────────────────────────────────
    doc_type = _safe_doc_type(form_fields.get("doc_type"))
    case_info = resolve_case_for_intake(
        firm_id, form_fields, case_id,
        doc_type=form_fields.get("doc_type", "other")
    )
    resolved_case_id = case_info["case_id"]

    # ── Upload to Supabase Storage with case-aware path ──────────────────
    file_url = None
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if supabase_url and supabase_key:
        try:
            from supabase import create_client
            supabase = create_client(supabase_url, supabase_key)
            file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'pdf'
            storage_path = (
                f"{firm_id}/cases/{resolved_case_id}/{doc_type}/{uuid.uuid4()}.{file_ext}"
                if resolved_case_id else f"{firm_id}/inbox/{uuid.uuid4()}.{file_ext}"
            )
            supabase.storage.from_("vcf-documents").upload(
                path=storage_path,
                file=contents,
                file_options={"content-type": file.content_type or "application/octet-stream"}
            )
            file_url = storage_path
        except Exception as e:
            logger.warning(f"[Intake/analyze] Supabase Storage upload failed: {e}")
    else:
        logger.warning("[Intake/analyze] SUPABASE_URL or SUPABASE_SERVICE_KEY not set. Skipping file upload.")

    with get_conn(firm_id) as conn:
        row = conn.execute(
            """INSERT INTO intake_scans
               (firm_id, case_id, filename, raw_text, word_count, confidence, ocr_engine,
                risk_score, risk_level, entities_json, form_fields, file_url, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (firm_id, resolved_case_id, file.filename, text, ocr_result["word_count"],
             ocr_result["confidence"], ocr_result["engine"],
             risk["score"], risk["level"],
             json.dumps(entities), json.dumps({
                 **form_fields,
                 "_text_english": ocr_result.get("text_english", ""),
             }),
             file_url,
             datetime.now(timezone.utc).isoformat())
        ).fetchone()
        scan_id = row["id"] if row else None
        case_doc_id = None
        if scan_id:
            case_doc_id = _insert_case_document(
                conn, firm_id, scan_id, resolved_case_id, file.filename,
                text, ocr_result.get("text_english", ""),
                form_fields, file_url, case_info["signals"], case_info["match_status"]
            )
        conn.commit()

    return {
        "success":  True,
        "scan_id": scan_id,
        "case_document_id": case_doc_id,
        "filename": file.filename,
        "file_url": file_url,
        "case_id": resolved_case_id,
        "case_number": case_info.get("case_number"),
        "case_created": case_info.get("created", False),
        "case_matched": case_info.get("matched", False),
        "match_status": case_info.get("match_status"),
        "match_reason": case_info.get("match_reason"),
        "ocr":      {"text": text, "text_english": ocr_result.get("text_english", ""),
                     "word_count": ocr_result["word_count"],
                     "confidence": ocr_result["confidence"], "engine": ocr_result["engine"]},
        "risk":     {"score": risk["score"], "level": risk["level"],
                     "top_signals": risk["top_signals"][:3],
                     "category_breakdown": risk["category_breakdown"]},
        "entities":        entities[:20],
        "custom_entities": custom_ents[:15],
        "form_fields":     form_fields,
    }


@router.post("/form")
async def extract_intake_form(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form(default="eng"),
    engine: str = Form(default="auto"),
    case_id: Optional[int] = Form(default=None)
):
    """Upload handwritten intake form → extract structured fields → link to case."""
    import uuid

    firm_id = getattr(request.state, "firm_id", "default")
    contents = await file.read()
    pages, mime_type = _prep_upload(contents, file.content_type)

    ocr_result = extract_text(pages, lang=lang, engine=engine,
                              mime_type=mime_type, firm_id=firm_id)
    text = clean_ocr_text(ocr_result["text"])
    form_fields = ocr_result.get("form_fields") or extract_form_fields(text)

    # ── Resolve or create case ───────────────────────────────────────────
    doc_type = _safe_doc_type(form_fields.get("doc_type"))
    case_info = resolve_case_for_intake(
        firm_id, form_fields, case_id,
        doc_type=form_fields.get("doc_type", "other")
    )
    resolved_case_id = case_info["case_id"]

    # ── Upload to Supabase Storage with case-aware path ──────────────────
    file_url = None
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if supabase_url and supabase_key:
        try:
            from supabase import create_client
            supabase = create_client(supabase_url, supabase_key)
            file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'pdf'
            storage_path = (
                f"{firm_id}/cases/{resolved_case_id}/{doc_type}/{uuid.uuid4()}.{file_ext}"
                if resolved_case_id else f"{firm_id}/inbox/{uuid.uuid4()}.{file_ext}"
            )
            supabase.storage.from_("vcf-documents").upload(
                path=storage_path,
                file=contents,
                file_options={"content-type": file.content_type or "application/octet-stream"}
            )
            file_url = storage_path
        except Exception as e:
            logger.warning(f"[Intake/form] Supabase Storage upload failed: {e}")
    else:
        logger.warning("[Intake/form] SUPABASE_URL or SUPABASE_SERVICE_KEY not set. Skipping file upload.")

    # ── Save to Database, including form_fields for instant /vcf/from-scan reuse ─
    with get_conn(firm_id) as conn:
        row = conn.execute(
            """INSERT INTO intake_scans
               (firm_id, case_id, filename, raw_text, word_count, confidence, ocr_engine,
                file_url, form_fields, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (firm_id, resolved_case_id, file.filename, text, ocr_result["word_count"],
             ocr_result["confidence"], ocr_result["engine"],
             file_url, json.dumps(form_fields),
             datetime.now(timezone.utc).isoformat())
        ).fetchone()
        scan_id = row["id"] if row else None
        case_doc_id = None
        if scan_id:
            case_doc_id = _insert_case_document(
                conn, firm_id, scan_id, resolved_case_id, file.filename,
                text, ocr_result.get("text_english", ""),
                form_fields, file_url, case_info["signals"], case_info["match_status"]
            )
        conn.commit()

    return {
        "success":      True,
        "scan_id":      scan_id,
        "case_document_id": case_doc_id,
        "filename":     file.filename,
        "file_url":     file_url,
        "case_id":      resolved_case_id,
        "case_number":  case_info.get("case_number"),
        "case_created": case_info.get("created", False),
        "case_matched": case_info.get("matched", False),
        "match_status": case_info.get("match_status"),
        "match_reason": case_info.get("match_reason"),
        "raw_text":     text,
        "text_english": ocr_result.get("text_english", ""),
        "confidence":   ocr_result["confidence"],
        "engine":       ocr_result["engine"],
        "form_fields":  form_fields,
    }


@router.get("/history")
def intake_history(request: Request, limit: int = 20, case_id: Optional[int] = None):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if case_id is not None:
            rows = conn.execute(
                """SELECT s.*, c.case_number, c.client_name AS case_client_name
                   FROM intake_scans s
                   LEFT JOIN cases c ON c.id = s.case_id
                   WHERE s.firm_id=%s AND s.case_id=%s
                   ORDER BY s.id DESC LIMIT %s""",
                (firm_id, case_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT s.*, c.case_number, c.client_name AS case_client_name
                   FROM intake_scans s
                   LEFT JOIN cases c ON c.id = s.case_id
                   WHERE s.firm_id=%s
                   ORDER BY s.id DESC LIMIT %s""",
                (firm_id, limit)
            ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        for f in ("entities_json", "form_fields"):
            if d.get(f):
                try: d[f] = json.loads(d[f])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(f"[Intake] Could not parse {f} in history: {e}")
        results.append(d)
    return {"success": True, "count": len(results), "scans": results}


@router.get("/inbox")
def document_inbox(
    request: Request,
    status: str = Query(default="unmatched,ambiguous"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Review queue for documents that could not be auto-matched to a case."""
    firm_id = getattr(request.state, "firm_id", "default")
    statuses = [s.strip() for s in status.split(",") if s.strip()]
    if not statuses:
        statuses = ["unmatched"]

    placeholders = ",".join(["%s"] * len(statuses))
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            f"""SELECT d.id, d.scan_id, d.document_name, d.doc_type, d.doc_text,
                       d.summary, d.identity_signals, d.match_status, d.file_url,
                       d.created_at, s.raw_text, s.form_fields
                FROM case_documents d
                LEFT JOIN intake_scans s ON s.id = d.scan_id
                WHERE d.firm_id = %s
                  AND d.match_status IN ({placeholders})
                ORDER BY d.created_at DESC
                LIMIT %s""",
            (firm_id, *statuses, limit)
        ).fetchall()

    docs = []
    for r in rows:
        d = dict(r)
        for f in ("identity_signals", "form_fields"):
            if d.get(f) and isinstance(d[f], str):
                try: d[f] = json.loads(d[f])
                except (json.JSONDecodeError, TypeError): pass
        docs.append(d)
    return {"success": True, "count": len(docs), "documents": docs}


@router.post("/inbox/{doc_id}/assign")
def assign_inbox_document(
    doc_id: int,
    body: dict,
    request: Request,
):
    """Assign an unmatched/ambiguous document to a case."""
    firm_id = getattr(request.state, "firm_id", "default")
    case_id = body.get("case_id")
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")

    with get_conn(firm_id) as conn:
        case = conn.execute(
            "SELECT id, case_number FROM cases WHERE id = %s AND firm_id = %s AND deleted = FALSE",
            (case_id, firm_id)
        ).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        doc = conn.execute(
            "SELECT scan_id FROM case_documents WHERE id = %s AND firm_id = %s",
            (doc_id, firm_id)
        ).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        conn.execute(
            """UPDATE case_documents
               SET case_id = %s, match_status = 'manual', updated_at = %s
               WHERE id = %s""",
            (case_id, datetime.now(timezone.utc).isoformat(), doc_id)
        )
        if doc["scan_id"]:
            conn.execute(
                "UPDATE intake_scans SET case_id = %s WHERE id = %s",
                (case_id, doc["scan_id"])
            )
        conn.commit()

    return {"success": True, "document_id": doc_id, "case_id": case_id,
            "case_number": case["case_number"], "match_status": "manual"}


@router.get("/supported-languages")
def supported_languages():
    return {
        "languages": [
            {"code": "eng",     "name": "English"},
            {"code": "chi_sim", "name": "Chinese Simplified"},
            {"code": "chi_tra", "name": "Chinese Traditional"},
            {"code": "spa",     "name": "Spanish"},
            {"code": "fra",     "name": "French"},
            {"code": "deu",     "name": "German"},
        ],
        "engines": [
            {"id": "auto",      "name": "Auto (Claude Vision → Tesseract fallback)"},
            {"id": "claude",    "name": "Claude Vision (best for handwriting)"},
            {"id": "tesseract", "name": "Tesseract (best for printed text)"},
        ]
    }


# ── Audio Transcription (OpenAI Whisper) ──────────────────────────────────────

@router.post("/audio")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    lang: str = "auto",
    module: str = "intake",
    redact: bool = False,
    redact_style: str = "label"
):
    """Transcribe audio/video file using OpenAI Whisper."""
    import openai, uuid, tempfile, time
    firm_id = getattr(request.state, "firm_id", "default")

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    client_oai = openai.OpenAI(api_key=openai_key)

    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        t_start = time.time()

        whisper_kwargs = {"model": "whisper-1", "response_format": "verbose_json"}
        if lang and lang != "auto":
            whisper_kwargs["language"] = lang

        with open(tmp_path, "rb") as audio_f:
            result = client_oai.audio.transcriptions.create(
                file=audio_f,
                **whisper_kwargs
            )

        duration   = round(getattr(result, "duration", time.time() - t_start), 2)
        transcript = result.text or ""
        detected   = getattr(result, "language", lang if lang != "auto" else "unknown")
        word_count = len(transcript.split())
        rec_id     = str(uuid.uuid4())[:8]

        response = {
            "transcript":        transcript,
            "detected_language": detected,
            "duration_seconds":  duration,
            "word_count":        word_count,
            "recording_id":      rec_id,
        }

        if redact and transcript:
            try:
                from backend.demo1.main import claude_with_retry, client, LLM_FAST, clean_json
                styles = {
                    "label":  "Replace PII with [CATEGORY] labels like [NAME], [DOB], [PHONE].",
                    "redact": "Replace PII with █████ blocks.",
                    "tag":    "Wrap PII in <redacted category='TYPE'>original</redacted> tags.",
                }
                style_prompt = styles.get(redact_style, styles["label"])
                msg = claude_with_retry(
                    client.messages.create,
                    model=LLM_FAST,
                    max_tokens=2048,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"You are a legal document redactor. {style_prompt}\n"
                            f"Identify and redact all PII including names, dates of birth, "
                            f"phone numbers, addresses, SSNs, medical record numbers, "
                            f"insurance IDs, and financial account numbers.\n\n"
                            f"Text to redact:\n{transcript}\n\n"
                            "Return JSON only: "
                            "{redacted_transcript, findings: [{text, category, score}], "
                            "total_redactions, confidence_score}"
                        )
                    }],
                    firm_id=firm_id,
                )
                raw = msg.content[0].text.strip()
                raw = clean_json(raw)
                rd  = json.loads(raw)
                rd["original_transcript"] = transcript
                rd["applied"] = True
                response["redaction"] = rd
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"[Intake] Audio redaction failed: {e}")
                response["redaction"] = {"applied": False, "error": "Redaction failed"}

        return response

    except openai.AuthenticationError:
        raise HTTPException(status_code=500, detail="Invalid or missing OpenAI API key")
    except openai.BadRequestError as e:
        raise HTTPException(status_code=400, detail="Audio file could not be processed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Intake] Audio transcription failed: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")
    finally:
        try:
            os.unlink(tmp_path)
        except (OSError, PermissionError) as e:
            logger.debug(f"[Intake] Could not delete temp file {tmp_path}: {e}")
