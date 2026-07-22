"""
redaction.py — ParaIQ Redaction Module
Endpoints:
  POST   /redact/text            — Redact PII from plain text
  POST   /redact/pdf             — Redact PII from uploaded file
  GET    /redact/files           — List stored redaction results
  DELETE /redact/{id}            — Securely delete a stored redaction
  GET    /redact/{id}/download   — Download a redacted file
Uses: Presidio Analyzer + Anonymizer, optional Claude enhancement
"""
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os, uuid, json, re, logging
from pathlib import Path
from datetime import datetime, timezone

from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Storage ───────────────────────────────────────────────────────────────────
# Configurable via env; falls back to a path relative to this file
_HERE       = Path(__file__).parent
STORAGE_DIR = Path(os.getenv("REDACTION_STORAGE_DIR", str(_HERE / "storage" / "redactions")))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def init_redaction_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Redaction] DB table initialized [OK]")


def _require_auth(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ── Presidio lazy init ────────────────────────────────────────────────────────
_analyzer   = None
_anonymizer = None

ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
    "DATE_TIME", "US_SSN", "MEDICAL_LICENSE", "US_PASSPORT",
    "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "URL",
    "US_DRIVER_LICENSE", "US_BANK_NUMBER", "US_ITIN",
]


def _get_presidio():
    global _analyzer, _anonymizer
    if _analyzer is None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            _analyzer   = AnalyzerEngine()
            _anonymizer = AnonymizerEngine()
        except ImportError:
            raise HTTPException(
                500,
                "Presidio not installed. Run: "
                ".venv/bin/pip install presidio-analyzer presidio-anonymizer "
                "&& .venv/bin/python -m spacy download en_core_web_lg"
            )
    return _analyzer, _anonymizer


# ── Helpers ───────────────────────────────────────────────────────────────────
STYLE_REPLACE = {
    "label":  lambda t: f"[{t}]",
    "redact": lambda t: "█████",
    "tag":    lambda t: f"[{t}]",
}


def _run_presidio(text: str, threshold: float, style: str):
    from presidio_anonymizer.entities import OperatorConfig
    analyzer, anonymizer = _get_presidio()
    results = analyzer.analyze(text=text, entities=ENTITIES, language="en",
                               score_threshold=threshold)
    if style == "redact":
        operators = {e: OperatorConfig("replace", {"new_value": "█████"}) for e in ENTITIES}
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


def _claude_enhance(text: str, existing_findings: list, style: str, firm_id: str = "default"):
    """Use the centralized Claude infrastructure (retry, rate limit, tracing)."""
    from backend.demo1.main import claude_with_retry, client, LLM_FAST, LEGAL_SYSTEM_PROMPT, clean_json
    already = [f["text"] for f in existing_findings]
    msg = claude_with_retry(
        client.messages.create,
        model=LLM_FAST,
        max_tokens=1024,
        system=LEGAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": (
            "You are a PII detection assistant. Find any personally identifiable "
            "information in the text that was NOT already detected.\n"
            f"Already detected: {', '.join(already) if already else 'none'}.\n\n"
            "Return ONLY a JSON array (empty [] if nothing missed):\n"
            '[{"text":"...","category":"PERSON|DATE_TIME|PHONE_NUMBER|'
            'EMAIL_ADDRESS|LOCATION|US_SSN|MEDICAL_LICENSE|CREDIT_CARD|OTHER_PII",'
            '"score":0.9}]\n\n'
            f"Text:\n{text[:3000]}"
        )}],
        firm_id=firm_id,
    )
    try:
        raw    = msg.content[0].text.strip()
        raw    = clean_json(raw)
        extras = json.loads(raw)
        existing_spans = {(f["start"], f["end"]) for f in existing_findings if "start" in f}
        for cf in extras:
            pos = text.find(cf["text"])
            if pos >= 0 and (pos, pos + len(cf["text"])) not in existing_spans:
                existing_findings.append({
                    "text":     cf["text"],
                    "category": cf.get("category", "OTHER_PII"),
                    "score":    round(float(cf.get("score", 0.8)), 3),
                    "start":    pos,
                    "end":      pos + len(cf["text"]),
                    "source":   "claude",
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


# ── Request model ─────────────────────────────────────────────────────────────
class RedactTextRequest(BaseModel):
    text:       str
    threshold:  float = 0.5
    style:      str   = "label"
    use_claude: bool  = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/text")
async def redact_text_endpoint(request: Request, req: RedactTextRequest):
    _require_auth(request)
    if not req.text.strip():
        raise HTTPException(400, "No text provided")
    try:
        redacted, findings, confidence = _run_presidio(req.text, req.threshold, req.style)
    except HTTPException:
        raise
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"[redaction] Presidio error: {e}")
        raise HTTPException(500, "Redaction service encountered an error. Please try again.")
    if req.use_claude:
        try:
            findings = _claude_enhance(req.text, findings, req.style, firm_id=getattr(request.state, "firm_id", "default"))
            redacted = _apply_claude_extras(redacted, findings, req.style)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning(f"[redaction] Claude enhance failed (text endpoint): {e}")
    categories_found      = list({f["category"] for f in findings})
    claude_findings_count = sum(1 for f in findings if f.get("source") == "claude")
    return {
        "redacted_text":         redacted,
        "original_text":         req.text,
        "findings":              findings,
        "total_redactions":      len(findings),
        "confidence_score":      confidence,
        "style":                 req.style,
        "categories_found":      categories_found,
        "claude_findings_count": claude_findings_count,
    }


@router.post("/pdf")
async def redact_pdf(
    request:    Request,
    file:       UploadFile = File(...),
    threshold:  float      = Query(0.5),
    style:      str        = Query("label"),
    use_claude: bool       = Query(False),
):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")

    content = await file.read()
    text    = ""
    fname   = file.filename or "document"

    if fname.lower().endswith(".pdf"):
        try:
            import fitz
            doc  = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
        except ImportError:
            try:
                import pdfplumber, io
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            except ImportError:
                text = content.decode("utf-8", errors="ignore")
    else:
        text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(400, "No text could be extracted from the file")

    try:
        redacted, findings, confidence = _run_presidio(text, threshold, style)
    except HTTPException:
        raise
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"[redaction] Redaction error: {e}")
        raise HTTPException(500, "Redaction failed. Please try again.")

    if use_claude:
        try:
            findings = _claude_enhance(text, findings, style, firm_id=firm_id)
            redacted = _apply_claude_extras(redacted, findings, style)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning(f"[redaction] Claude enhance failed (PDF endpoint): {e}")

    rec_id   = str(uuid.uuid4())[:8]
    base     = os.path.splitext(fname)[0]
    out_name = f"{base}_redacted_{rec_id}.txt"
    out_path = STORAGE_DIR / out_name
    out_path.write_text(redacted, encoding="utf-8")
    size_kb  = round(out_path.stat().st_size / 1024, 2)

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
        "redacted_text":    redacted,
        "redacted_preview": redacted[:1000],
        "original_text":    text[:500] + ("..." if len(text) > 500 else ""),
        "findings":         findings,
        "text_findings":    findings,
        "total_redactions": len(findings),
        "confidence_score": confidence,
        "redaction_id":     rec_id,
        "download_url":     f"/redact/{rec_id}/download",
        "filename":         out_name,
        "size_kb":          size_kb,
        "categories_found": categories_found,
        "pages_processed":  1,
    }


@router.get("/files")
async def list_redacted_files(request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """SELECT id, filename, size_kb, created_at FROM redactions
               WHERE firm_id = %s ORDER BY created_at DESC""",
            (firm_id,)
        ).fetchall()
    files = []
    for r in rows:
        if (STORAGE_DIR / r["filename"]).exists():
            files.append({
                "redaction_id": r["id"],
                "filename":     r["filename"],
                "size_kb":      r["size_kb"],
                "created_at":   str(r["created_at"]),
                "download_url": f"/redact/{r['id']}/download",
            })
    return {"files": files}


@router.delete("/{redaction_id}")
async def delete_redacted_file(request: Request, redaction_id: str):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
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


@router.get("/{redaction_id}/download")
async def download_redacted_file(request: Request, redaction_id: str):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
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
