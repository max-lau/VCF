"""
ocr_intake.py
=============
FastAPI APIRouter: OCR Intake Module
Uses Claude Vision API for handwriting (primary) and
Tesseract for printed/typed text (fallback).

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
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request
from typing import Optional
from PIL import Image
import pytesseract

from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = 'tesseract'

router = APIRouter()


def init_intake_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Intake] OCR table initialized ✓")


# ── Claude Vision OCR ──────────────────────────────────────────────────────────

def ocr_with_claude(image_bytes: bytes, mime_type: str = "image/jpeg",
                    firm_id: str = "default") -> dict:
    """Use Claude Vision to transcribe handwritten/scanned documents, and to
    extract structured intake fields directly from the image in the same
    call (rather than a separate English-regex pass over the transcribed
    text). Regex on OCR output can't read non-Latin names, can't tell a
    client's own phone number from a firm's letterhead number, and can't
    use layout/context -- Claude reading the image directly can do all
    three. If the JSON response can't be parsed for any reason, this
    falls back to plain-text mode and the caller falls back to the old
    regex-based extract_form_fields() on the transcribed text.
    """
    from backend.demo1.main import claude_with_retry, client, LLM_STRONG
    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = claude_with_retry(
        client.messages.create,
        model=LLM_STRONG,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_image,
                    }
                },
                {
                    "type": "text",
                    "text": """Read this document image and respond with ONLY a JSON object (no markdown fences, no commentary) with exactly these two top-level keys:

"text": the complete verbatim transcription of every word and number visible in the document, in its original language, preserving line breaks and labels (Client:, Date:, etc.)

"fields": an object with these keys, extracted directly from what you see in the image using the document's own layout and language (not an English template):
  "client_name": the client's/claimant's own name, or null if not present. Must be the person the intake is about, not a firm name, attorney name, or letterhead.
  "date": the date on the form in its original format, or null.
  "matter_type": your best classification of the legal matter (e.g. "employment", "criminal", "civil", "immigration", "real estate", "family", "personal injury"), or null.
  "opposing_party": the opposing party/employer/defendant if mentioned, or null.
  "phone": the CLIENT's own phone number, not a firm/letterhead phone number, or null.
  "email": the CLIENT's own email address, not a firm email, or null.
  "key_facts": an array of up to 5 short sentences capturing the most legally significant facts.
  "urgent": true if the document indicates urgency (approaching deadline, emergency, ASAP), otherwise false.

Return ONLY the JSON object."""
                }
            ]
        }],
        firm_id=firm_id,
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

    text = raw
    form_fields = None
    try:
        parsed = json.loads(raw)
        text = (parsed.get("text") or "").strip()
        f = parsed.get("fields") or {}
        form_fields = {
            "client_name":    f.get("client_name"),
            "date":           f.get("date"),
            "matter_type":    f.get("matter_type"),
            "opposing_party": f.get("opposing_party"),
            "phone":          f.get("phone"),
            "email":          f.get("email"),
            "key_facts":      (f.get("key_facts") or [])[:5],
            "urgent":         bool(f.get("urgent")),
        }
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"[Intake] Vision JSON parse failed, falling back to plain-text mode: {e}")
        text = raw

    result = {
        "text":       text,
        "word_count": len(text.split()),
        "confidence": 95.0,
        "engine":     "claude-vision",
    }
    if form_fields is not None:
        result["form_fields"] = form_fields
    return result


# ── Tesseract OCR ──────────────────────────────────────────────────────────────

def ocr_with_tesseract(image_bytes: bytes, lang: str = "eng") -> dict:
    """Tesseract OCR — good for printed text."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
        confidences = [int(c) for c in data["conf"] if int(c) > 30]
        raw_text = pytesseract.image_to_string(image, lang=lang).strip()
        avg_conf  = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

        return {
            "text":       raw_text,
            "word_count": len(raw_text.split()),
            "confidence": avg_conf,
            "engine":     "tesseract",
        }
    except (IOError, OSError, ValueError, pytesseract.TesseractError) as e:
        logger.error(f"[Intake] Tesseract OCR failed: {e}")
        raise HTTPException(400, "OCR failed — could not process the image")


# ── Smart dispatcher ───────────────────────────────────────────────────────────

def extract_text(image_bytes: bytes, lang: str = "eng",
                 engine: str = "auto", mime_type: str = "image/jpeg",
                 firm_id: str = "default") -> dict:
    if engine == "tesseract":
        return ocr_with_tesseract(image_bytes, lang)
    try:
        return ocr_with_claude(image_bytes, mime_type, firm_id=firm_id)
    except (httpx.HTTPError, httpx.TimeoutException, KeyError, IndexError, ValueError) as e:
        logger.warning(f"[Intake] Claude Vision failed, falling back to Tesseract: {e}")
        return ocr_with_tesseract(image_bytes, lang)


def clean_ocr_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ── Form field extractor ───────────────────────────────────────────────────────

def extract_form_fields(text: str) -> dict:
    fields = {
        "client_name":    None,
        "date":           None,
        "matter_type":    None,
        "opposing_party": None,
        "phone":          None,
        "email":          None,
        "key_facts":      [],
        "urgent":         False,
    }
    text_lower = text.lower()

    for p in [r'client\s*:\s*([A-Z][a-z]+ [A-Z][a-z]+)',
               r'name\s*:\s*([A-Z][a-z]+ [A-Z][a-z]+)']:
        m = re.search(p, text, re.IGNORECASE)
        if m: fields["client_name"] = m.group(1).strip(); break

    for p in [r'date\s*:\s*([A-Za-z]+ \d{1,2},?\s*\d{4})',
               r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b',
               r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b']:
        m = re.search(p, text, re.IGNORECASE)
        if m: fields["date"] = (m.group(1) if m.lastindex else m.group(0)).strip(); break

    matter_m = re.search(r'matter\s*:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if matter_m:
        fields["matter_type"] = matter_m.group(1).strip()
    else:
        matter_map = {
            "employment":  ["wrongful termination", "fired", "terminated", "harassment", "employer"],
            "criminal":    ["indicted", "charged", "criminal", "felony", "arrest"],
            "civil":       ["lawsuit", "civil", "damages", "negligence"],
            "immigration": ["visa", "green card", "deportation", "asylum"],
            "real estate": ["property", "lease", "mortgage", "landlord"],
            "family":      ["divorce", "custody", "child support", "alimony"],
        }
        for matter, keywords in matter_map.items():
            if any(kw in text_lower for kw in keywords):
                fields["matter_type"] = matter; break

    m = re.search(r'\b(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})\b', text)
    if m: fields["phone"] = m.group(1)

    m = re.search(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b', text)
    if m: fields["email"] = m.group(0)

    fields["urgent"] = any(kw in text_lower for kw in
        ["urgent", "asap", "immediately", "emergency", "deadline"])

    legal_kws = ["terminated", "fired", "severance", "service", "charged",
                 "arrested", "contract", "damages", "employer", "years"]
    for sent in re.split(r'[.!?\n]+', text):
        if any(kw in sent.lower() for kw in legal_kws) and len(sent.strip()) > 15:
            fields["key_facts"].append(sent.strip())
    fields["key_facts"] = fields["key_facts"][:5]

    return fields


def pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
    from pdf2image import convert_from_bytes
    pages = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=200)
    if not pages:
        raise HTTPException(400, "Could not read PDF")
    buf = io.BytesIO()
    pages[0].save(buf, format="PNG")
    return buf.getvalue()


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/scan")
async def scan_document(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form(default="eng"),
    engine: str = Form(default="auto"),
    firm_id: Optional[str] = Form(default=None)
):
    """Upload image/PDF → extract text via OCR."""
    # APIKeyMiddleware already gates entry: if there's no Bearer header here,
    # this request only got through via the validated static API key (M2M path).
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
    mime_type = file.content_type
    if file.content_type == "application/pdf":
        contents = pdf_to_image_bytes(contents); mime_type = "image/png"

    result = extract_text(contents, lang=lang, engine=engine,
                          mime_type=mime_type, firm_id=firm_id)
    result["text"] = clean_ocr_text(result["text"])

    with get_conn(firm_id) as conn:
        conn.execute(
            """INSERT INTO intake_scans
               (firm_id, filename, raw_text, word_count, confidence, ocr_engine, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (firm_id, file.filename, result["text"], result["word_count"],
             result["confidence"], result["engine"],
             datetime.now(timezone.utc).isoformat())
        )

    return {"success": True, "filename": file.filename, **result}


@router.post("/analyze")
async def analyze_document(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form(default="eng"),
    context: str = Form(default="general"),
    engine: str = Form(default="auto")
):
    """Upload image/PDF → OCR → full NLP pipeline."""
    firm_id = getattr(request.state, "firm_id", "default")
    contents = await file.read()
    mime_type = file.content_type
    if file.content_type == "application/pdf":
        contents = pdf_to_image_bytes(contents); mime_type = "image/png"

    ocr_result = extract_text(contents, lang=lang, engine=engine,
                               mime_type=mime_type, firm_id=firm_id)
    text = clean_ocr_text(ocr_result["text"])

    if not text or len(text.split()) < 3:
        return {"success": False, "error": "Could not extract readable text.",
                "ocr_confidence": ocr_result["confidence"]}

    from backend.demo1.risk_scorer import score_text
    risk = score_text(text, context=context)

    import spacy
    nlp = spacy.load("en_core_web_sm")
    entities = [{"text": e.text, "type": e.label_} for e in nlp(text[:5000]).ents]

    from backend.demo1.custom_entities import extract_custom_entities
    custom_ents = extract_custom_entities(text)

    form_fields = ocr_result.get("form_fields") or extract_form_fields(text)

    with get_conn(firm_id) as conn:
        conn.execute(
            """INSERT INTO intake_scans
               (firm_id, filename, raw_text, word_count, confidence, ocr_engine,
                risk_score, risk_level, entities_json, form_fields, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (firm_id, file.filename, text, ocr_result["word_count"],
             ocr_result["confidence"], ocr_result["engine"],
             risk["score"], risk["level"],
             json.dumps(entities), json.dumps(form_fields),
             datetime.now(timezone.utc).isoformat())
        )

    return {
        "success":  True,
        "filename": file.filename,
        "ocr":      {"text": text, "word_count": ocr_result["word_count"],
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
    engine: str = Form(default="auto")
):
    """Upload handwritten intake form → extract structured fields."""
    firm_id = getattr(request.state, "firm_id", "default")
    contents = await file.read()
    mime_type = file.content_type
    if file.content_type == "application/pdf":
        contents = pdf_to_image_bytes(contents); mime_type = "image/png"

    ocr_result = extract_text(contents, lang=lang, engine=engine,
                               mime_type=mime_type, firm_id=firm_id)
    text = clean_ocr_text(ocr_result["text"])

    return {
        "success":     True,
        "filename":    file.filename,
        "raw_text":    text,
        "confidence":  ocr_result["confidence"],
        "engine":      ocr_result["engine"],
        "form_fields": ocr_result.get("form_fields") or extract_form_fields(text),
    }


@router.get("/history")
def intake_history(request: Request, limit: int = 20):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM intake_scans WHERE firm_id=%s ORDER BY id DESC LIMIT %s",
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
