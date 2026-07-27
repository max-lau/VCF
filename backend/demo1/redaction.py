"""
redaction.py — ACP-VCF Redaction Module
Endpoints:
  POST   /redact/text            — Redact PII from plain text
  POST   /redact/pdf             — Redact PII from uploaded file
  GET    /redact/files           — List stored redaction results
  DELETE /redact/{id}            — Securely delete a stored redaction
  GET    /redact/{id}/download   — Download a redacted file
  POST   /redact/case-document/{doc_id} — Redact an existing case document

Uses Presidio Analyzer + Anonymizer when available; falls back to Claude-only
PII detection when Presidio is not installed.
"""
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List
import os
import uuid
import json
import re
import logging
from pathlib import Path
from datetime import datetime, timezone

from backend.demo1.pg import get_conn
from backend.demo1.ai_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Configuration ─────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
STORAGE_DIR = Path(os.getenv("REDACTION_STORAGE_DIR", str(_HERE / "storage" / "redactions")))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_TEXT_LEN = 25_000
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def init_redaction_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Redaction] DB table initialized [OK]")


# ── Auth helper ───────────────────────────────────────────────────────────────
def _require_auth(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _get_firm_id(request: Request) -> str:
    return getattr(request.state, "firm_id", "default")


# ── Presidio lazy init ────────────────────────────────────────────────────────
_analyzer = None
_anonymizer = None
_presidio_available = None

ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
    "DATE_TIME", "US_SSN", "MEDICAL_LICENSE", "US_PASSPORT",
    "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "URL",
    "US_DRIVER_LICENSE", "US_BANK_NUMBER", "US_ITIN",
]


def _check_presidio() -> bool:
    global _presidio_available
    if _presidio_available is None:
        try:
            import presidio_analyzer  # noqa: F401
            import presidio_anonymizer  # noqa: F401
            _presidio_available = True
        except ImportError:
            _presidio_available = False
            logger.info("[redaction] Presidio not installed; using Claude-only fallback")
    return _presidio_available


def _get_presidio():
    global _analyzer, _anonymizer
    if not _check_presidio():
        raise HTTPException(
            503,
            "Presidio not installed. Run: "
            ".\\venv\\Scripts\\python -m pip install presidio-analyzer presidio-anonymizer "
            "&& .\\venv\\Scripts\\python -m spacy download en_core_web_lg"
        )
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        _analyzer = AnalyzerEngine()
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


# ── Style mapping ─────────────────────────────────────────────────────────────
STYLE_REPLACE = {
    "label":  lambda t: f"[{t}]",
    "tag":    lambda t: f"[{t}]",
    "redact": lambda t: "█████",
    "black":  lambda t: "█████",
    "white":  lambda t: "",
    "highlight": lambda t: f"[[{t}]]",
}


def _normalize_style(style: str) -> str:
    style = (style or "label").lower().strip()
    if style in ("black", "redact"):
        return "redact"
    if style == "white":
        return "white"
    if style == "highlight":
        return "highlight"
    return "label"


def _apply_style(text: str, style: str) -> str:
    return STYLE_REPLACE.get(style, STYLE_REPLACE["label"])(text)


# ── JSON cleaning helper (avoid circular import from main.py) ──────────────────
def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


# ── Presidio redaction ────────────────────────────────────────────────────────
def _run_presidio(text: str, threshold: float, style: str):
    from presidio_anonymizer.entities import OperatorConfig
    analyzer, anonymizer = _get_presidio()
    results = analyzer.analyze(text=text, entities=ENTITIES, language="en", score_threshold=threshold)

    if style == "redact":
        operators = {e: OperatorConfig("replace", {"new_value": "█████"}) for e in ENTITIES}
    elif style == "white":
        operators = {e: OperatorConfig("replace", {"new_value": ""}) for e in ENTITIES}
    elif style == "highlight":
        operators = {e: OperatorConfig("replace", {"new_value": f"[[{e}]]"}) for e in ENTITIES}
    else:
        operators = {e: OperatorConfig("replace", {"new_value": f"[{e}]"}) for e in ENTITIES}

    anon_result = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    findings = [
        {"text": text[r.start:r.end], "category": r.entity_type,
         "score": round(r.score, 3), "start": r.start, "end": r.end}
        for r in results
    ]
    avg_conf = round(sum(r.score for r in results) / len(results), 3) if results else 0.0
    return anon_result.text, findings, avg_conf


# ── Claude-only fallback redaction ────────────────────────────────────────────
LLM_FAST = os.getenv("LLM_FAST", "claude-haiku-4-5-20251001")

MEDICAL_SYSTEM_PROMPT = (
    "You are ACP-VCF, an expert AI assistant helping paralegals and attorneys at WAW law firm process 9/11 Victim Compensation Fund claims. "
    "You produce precise, structured analysis of medical records, presence proofs, and financial documents. "
    "Always respond with valid JSON only — no markdown, no backticks, no preamble. "
    "Be rigorous, cite relevant facts from the provided text, and flag missing information explicitly."
)


def _claude_redact(text: str, style: str, firm_id: str = "default"):
    """Claude-only PII detection and redaction. Used when Presidio is unavailable."""
    client = get_client()
    prompt = f"""You are a PII redaction assistant. Identify all personally identifiable information in the text below and return a JSON object with the redacted text and a findings list.

IMPORTANT: Return ONLY raw JSON. No markdown, no backticks, no explanation.

Text:
{text[:8000] if len(text) <= 8000 else text[:8000] + '... [TRUNCATED]'}

Return exactly:
{{
  "redacted_text": "the text with PII replaced according to the style rules below",
  "findings": [
    {{"text": "exact PII string", "category": "PERSON|EMAIL_ADDRESS|PHONE_NUMBER|LOCATION|DATE_TIME|US_SSN|MEDICAL_LICENSE|CREDIT_CARD|OTHER_PII", "score": 0.95}}
  ]
}}

Style rules:
- If style is 'redact' or 'black', replace each PII with █████.
- If style is 'white', replace each PII with an empty string.
- If style is 'highlight', wrap each PII like [[CATEGORY]].
- Otherwise (label), replace each PII like [CATEGORY]."""

    try:
        message = client.messages.create(
            model=LLM_FAST,
            max_tokens=4000,
            system=MEDICAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = json.loads(_clean_json(message.content[0].text))
        redacted = parsed.get("redacted_text", text)
        findings = []
        for f in parsed.get("findings", []):
            pos = text.find(f["text"])
            findings.append({
                "text": f["text"],
                "category": f.get("category", "OTHER_PII"),
                "score": round(float(f.get("score", 0.8)), 3),
                "start": pos if pos >= 0 else 0,
                "end": pos + len(f["text"]) if pos >= 0 else len(f["text"]),
                "source": "claude",
            })
        avg_conf = round(sum(f["score"] for f in findings) / len(findings), 3) if findings else 0.0
        return redacted, findings, avg_conf
    except Exception as e:
        logger.error(f"[redaction] Claude-only redaction failed: {e}")
        raise HTTPException(500, "Redaction service encountered an error. Please try again.")


# ── Claude enhancement for Presidio results ───────────────────────────────────
def _claude_enhance(text: str, existing_findings: list, style: str, firm_id: str = "default") -> list:
    """Use Claude to catch PII that Presidio missed."""
    client = get_client()
    already = [f["text"] for f in existing_findings]
    prompt = (
        "You are a PII detection assistant. Find any personally identifiable "
        "information in the text that was NOT already detected.\n"
        f"Already detected: {', '.join(already) if already else 'none'}.\n\n"
        "Return ONLY a JSON array (empty [] if nothing missed):\n"
        '[{"text":"...","category":"PERSON|DATE_TIME|PHONE_NUMBER|'
        'EMAIL_ADDRESS|LOCATION|US_SSN|MEDICAL_LICENSE|CREDIT_CARD|OTHER_PII",'
        '"score":0.9}]\n\n'
        f"Text:\n{text[:3000]}"
    )
    try:
        message = client.messages.create(
            model=LLM_FAST,
            max_tokens=1024,
            system=MEDICAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        extras = json.loads(_clean_json(message.content[0].text.strip()))
        existing_spans = {(f["start"], f["end"]) for f in existing_findings if "start" in f}
        for cf in extras:
            pos = text.find(cf["text"])
            if pos >= 0 and (pos, pos + len(cf["text"])) not in existing_spans:
                existing_findings.append({
                    "text": cf["text"],
                    "category": cf.get("category", "OTHER_PII"),
                    "score": round(float(cf.get("score", 0.8)), 3),
                    "start": pos,
                    "end": pos + len(cf["text"]),
                    "source": "claude",
                })
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning(f"[redaction] Claude enhance parse error: {e}")
    return existing_findings


def _apply_claude_extras(redacted: str, findings: list, style: str) -> str:
    label_fn = STYLE_REPLACE.get(style, STYLE_REPLACE["label"])
    for f in findings:
        if f.get("source") == "claude" and f.get("text"):
            redacted = redacted.replace(f["text"], label_fn(f["category"]))
    return redacted


# ── Core redaction dispatcher ─────────────────────────────────────────────────
def _redact_text(text: str, threshold: float, style: str, use_claude: bool, firm_id: str = "default"):
    """Run Presidio if available, optionally enhance with Claude; otherwise use Claude-only."""
    if _check_presidio():
        redacted, findings, confidence = _run_presidio(text, threshold, style)
        if use_claude:
            try:
                findings = _claude_enhance(text, findings, style, firm_id=firm_id)
                redacted = _apply_claude_extras(redacted, findings, style)
            except Exception as e:
                logger.warning(f"[redaction] Claude enhance failed: {e}")
    else:
        redacted, findings, confidence = _claude_redact(text, style, firm_id=firm_id)
    return redacted, findings, confidence


# ── Request models ────────────────────────────────────────────────────────────
class RedactTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)
    threshold: float = Field(0.5, ge=0.0, le=1.0)
    style: str = Field("label")
    use_claude: bool = Field(True)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/text")
async def redact_text_endpoint(request: Request, req: RedactTextRequest):
    _require_auth(request)
    firm_id = _get_firm_id(request)
    style = _normalize_style(req.style)

    try:
        redacted, findings, confidence = _redact_text(req.text, req.threshold, style, req.use_claude, firm_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[redaction] Presidio error: {e}")
        raise HTTPException(500, "Redaction service encountered an error. Please try again.")

    categories_found = list({f["category"] for f in findings})
    claude_findings_count = sum(1 for f in findings if f.get("source") == "claude")
    return {
        "redacted_text": redacted,
        "original_text": req.text,
        "findings": findings,
        "total_redactions": len(findings),
        "confidence_score": confidence,
        "style": style,
        "categories_found": categories_found,
        "claude_findings_count": claude_findings_count,
        "presidio_available": _check_presidio(),
    }


@router.post("/pdf")
async def redact_pdf(
    request: Request,
    file: UploadFile = File(...),
    threshold: float = Query(0.5, ge=0.0, le=1.0),
    style: str = Query("label"),
    use_claude: bool = Query(False),
):
    _require_auth(request)
    firm_id = _get_firm_id(request)
    style = _normalize_style(style)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Max size is {MAX_FILE_SIZE // (1024*1024)} MB.")

    text = ""
    fname = file.filename or "document"

    if fname.lower().endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
        except ImportError:
            try:
                import pdfplumber
                import io
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            except ImportError:
                text = content.decode("utf-8", errors="ignore")
    else:
        text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(400, "No text could be extracted from the file")

    try:
        redacted, findings, confidence = _redact_text(text, threshold, style, use_claude, firm_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[redaction] Redaction error: {e}")
        raise HTTPException(500, "Redaction failed. Please try again.")

    rec_id = str(uuid.uuid4())[:8]
    base = os.path.splitext(fname)[0]
    out_name = f"{base}_redacted_{rec_id}.txt"
    out_path = STORAGE_DIR / out_name
    out_path.write_text(redacted, encoding="utf-8")
    size_kb = round(out_path.stat().st_size / 1024, 2)

    with get_conn(firm_id) as conn:
        conn.execute(
            """INSERT INTO redactions
               (id, firm_id, filename, original_filename, size_kb, style,
                total_redactions, confidence_score, file_path, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rec_id, firm_id, out_name, fname, size_kb, style,
             len(findings), confidence, str(out_path),
             datetime.now(timezone.utc).isoformat()),
        )

    categories_found = list({f["category"] for f in findings})
    return {
        "redacted_text": redacted,
        "redacted_preview": redacted[:1000],
        "original_text": text[:500] + ("..." if len(text) > 500 else ""),
        "findings": findings,
        "text_findings": findings,
        "total_redactions": len(findings),
        "confidence_score": confidence,
        "redaction_id": rec_id,
        "download_url": f"/redact/{rec_id}/download",
        "filename": out_name,
        "size_kb": size_kb,
        "categories_found": categories_found,
        "pages_processed": 1,
        "presidio_available": _check_presidio(),
    }


@router.get("/files")
async def list_redacted_files(request: Request):
    _require_auth(request)
    firm_id = _get_firm_id(request)
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """SELECT id, filename, size_kb, style, created_at FROM redactions
               WHERE firm_id = %s ORDER BY created_at DESC""",
            (firm_id,)
        ).fetchall()
    files = []
    for r in rows:
        if (STORAGE_DIR / r["filename"]).exists():
            files.append({
                "id": r["id"],
                "redaction_id": r["id"],
                "filename": r["filename"],
                "style": r["style"],
                "size_kb": r["size_kb"],
                "created_at": str(r["created_at"]),
                "download_url": f"/redact/{r['id']}/download",
            })
    return {"files": files}


@router.delete("/{redaction_id}")
async def delete_redacted_file(request: Request, redaction_id: str):
    _require_auth(request)
    firm_id = _get_firm_id(request)
    if not re.match(r"^[a-zA-Z0-9_-]+$", redaction_id):
        raise HTTPException(400, "Invalid redaction ID")

    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT file_path, filename FROM redactions WHERE id = %s AND firm_id = %s",
            (redaction_id, firm_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Redaction not found")
        try:
            Path(row["file_path"]).unlink(missing_ok=True)
        except (OSError, PermissionError) as e:
            logger.warning(f"[redaction] Failed to delete file {row.get('file_path')}: {e}")
        conn.execute(
            "DELETE FROM redactions WHERE id = %s AND firm_id = %s",
            (redaction_id, firm_id)
        )
    return {"message": f"'{row['filename']}' securely deleted.", "id": redaction_id}


@router.post("/case-document/{doc_id}")
async def redact_case_document(doc_id: int, request: Request, use_claude: bool = Query(True)):
    _require_auth(request)
    firm_id = _get_firm_id(request)

    with get_conn(firm_id) as conn:
        doc = conn.execute(
            """SELECT id, document_name, doc_text, content_hash, case_id
               FROM case_documents
               WHERE id = %s AND firm_id = %s""",
            (doc_id, firm_id),
        ).fetchone()

    if not doc:
        raise HTTPException(404, "Document not found")

    text = (doc["doc_text"] or "").strip()
    if not text:
        raise HTTPException(400, "No extracted text available for this document. Run OCR/intake first.")

    try:
        redacted, findings, confidence = _redact_text(text, 0.5, "label", use_claude, firm_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[redaction] Case-document redaction error: {e}")
        raise HTTPException(500, "Redaction failed. Please try again.")

    rec_id = str(uuid.uuid4())[:8]
    base = os.path.splitext(doc["document_name"] or "document")[0]
    out_name = f"{base}_redacted_{rec_id}.txt"
    out_path = STORAGE_DIR / out_name
    out_path.write_text(redacted, encoding="utf-8")
    size_kb = round(out_path.stat().st_size / 1024, 2)

    with get_conn(firm_id) as conn:
        conn.execute(
            """INSERT INTO redactions
               (id, firm_id, filename, original_filename, size_kb, style,
                total_redactions, confidence_score, file_path, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rec_id, firm_id, out_name, doc["document_name"], size_kb, "label",
             len(findings), confidence, str(out_path),
             datetime.now(timezone.utc).isoformat()),
        )

    categories_found = list({f["category"] for f in findings})
    return {
        "success": True,
        "redaction_id": rec_id,
        "download_url": f"/redact/{rec_id}/download",
        "filename": out_name,
        "total_redactions": len(findings),
        "categories_found": categories_found,
        "confidence_score": confidence,
        "presidio_available": _check_presidio(),
    }


@router.get("/{redaction_id}/download")
async def download_redacted_file(request: Request, redaction_id: str):
    _require_auth(request)
    firm_id = _get_firm_id(request)
    if not re.match(r"^[a-zA-Z0-9_-]+$", redaction_id):
        raise HTTPException(400, "Invalid redaction ID")

    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT file_path, filename FROM redactions WHERE id = %s AND firm_id = %s",
            (redaction_id, firm_id)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Redaction not found")
    fpath = Path(row["file_path"])
    if not fpath.exists():
        raise HTTPException(404, "File no longer exists on disk")
    return FileResponse(path=str(fpath), filename=row["filename"], media_type="text/plain")
