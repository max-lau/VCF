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

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os, uuid, json, re, sqlite3
from pathlib import Path
from datetime import datetime, timezone

router = APIRouter()

# ── Storage ───────────────────────────────────────────────────────────────────
STORAGE_DIR = Path('/root/nlp-portfolio/storage/redactions')
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = '/root/nlp-portfolio/backend/demo1/redactions.db'


def _db():
    return sqlite3.connect(DB_PATH)


def init_redaction_table():
    conn = _db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS redactions (
            id               TEXT PRIMARY KEY,
            filename         TEXT,
            original_filename TEXT,
            size_kb          REAL,
            style            TEXT,
            total_redactions INTEGER,
            confidence_score REAL,
            file_path        TEXT,
            created_at       TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print('[Redaction] DB table initialized ✓')


init_redaction_table()

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
    "tag":    lambda t: f"[{t}]",   # frontend shows tag same as label visually
}


def _run_presidio(text: str, threshold: float, style: str):
    """Run Presidio and return (redacted_text, findings, avg_confidence)."""
    from presidio_anonymizer.entities import OperatorConfig

    analyzer, anonymizer = _get_presidio()

    results = analyzer.analyze(
        text=text,
        entities=ENTITIES,
        language="en",
        score_threshold=threshold,
    )

    label_fn = STYLE_REPLACE.get(style, STYLE_REPLACE["label"])
    if style == "redact":
        operators = {e: OperatorConfig("replace", {"new_value": "█████"})
                     for e in ENTITIES}
    else:
        operators = {e: OperatorConfig("replace", {"new_value": f"[{e}]"})
                     for e in ENTITIES}

    anon_result = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators,
    )

    findings = [
        {
            "text":     text[r.start:r.end],
            "category": r.entity_type,
            "score":    round(r.score, 3),
            "start":    r.start,
            "end":      r.end,
        }
        for r in results
    ]

    avg_conf = round(
        sum(r.score for r in results) / len(results), 3
    ) if results else 0.0

    return anon_result.text, findings, avg_conf


def _claude_enhance(text: str, existing_findings: list, style: str):
    """Ask Claude to find PII missed by Presidio. Best-effort."""
    import anthropic as _ant

    client = _ant.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    already = [f["text"] for f in existing_findings]

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                "You are a PII detection assistant. Find any personally identifiable "
                "information in the text that was NOT already detected.\n"
                f"Already detected: {', '.join(already) if already else 'none'}.\n\n"
                "Return ONLY a JSON array (empty [] if nothing missed):\n"
                '[{"text":"...","category":"PERSON|DATE_TIME|PHONE_NUMBER|'
                'EMAIL_ADDRESS|LOCATION|US_SSN|MEDICAL_LICENSE|CREDIT_CARD|OTHER_PII",'
                '"score":0.9}]\n\n'
                f"Text:\n{text[:3000]}"
            ),
        }],
    )

    try:
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
        extras = json.loads(raw)
        existing_spans = {(f["start"], f["end"]) for f in existing_findings
                          if "start" in f}
        label_fn = STYLE_REPLACE.get(style, STYLE_REPLACE["label"])
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
    except Exception:
        pass

    return existing_findings


def _apply_claude_extras(redacted: str, findings: list, style: str) -> str:
    """Apply Claude-sourced redactions to already-Presidio-redacted text."""
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
async def redact_text(req: RedactTextRequest):
    """Redact PII from plain text using Presidio + optional Claude."""
    if not req.text.strip():
        raise HTTPException(400, "No text provided")

    try:
        redacted, findings, confidence = _run_presidio(
            req.text, req.threshold, req.style
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Presidio error: {str(e)}")

    if req.use_claude:
        try:
            findings = _claude_enhance(req.text, findings, req.style)
            redacted = _apply_claude_extras(redacted, findings, req.style)
        except Exception:
            pass  # best-effort

    categories_found      = list({f["category"] for f in findings})
    claude_findings_count = sum(1 for f in findings if f.get("source") == "claude")
    return {
        "redacted_text":        redacted,
        "original_text":        req.text,
        "findings":             findings,
        "total_redactions":     len(findings),
        "confidence_score":     confidence,
        "style":                req.style,
        "categories_found":     categories_found,
        "claude_findings_count": claude_findings_count,
    }


@router.post("/pdf")
async def redact_pdf(
    file:       UploadFile = File(...),
    threshold:  float      = Query(0.5),
    style:      str        = Query("label"),
    use_claude: bool       = Query(False),
):
    """Redact PII from an uploaded PDF or text file."""
    content = await file.read()
    text    = ""
    fname   = file.filename or "document"

    if fname.lower().endswith(".pdf"):
        # Try PyMuPDF → pdfplumber → raw decode
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
        raise HTTPException(500, f"Redaction error: {str(e)}")

    if use_claude:
        try:
            findings = _claude_enhance(text, findings, style)
            redacted = _apply_claude_extras(redacted, findings, style)
        except Exception:
            pass

    # Persist redacted file
    rec_id   = str(uuid.uuid4())[:8]
    base     = os.path.splitext(fname)[0]
    out_name = f"{base}_redacted_{rec_id}.txt"
    out_path = STORAGE_DIR / out_name
    out_path.write_text(redacted, encoding="utf-8")
    size_kb  = round(out_path.stat().st_size / 1024, 2)

    conn = _db()
    conn.execute(
        "INSERT INTO redactions VALUES (?,?,?,?,?,?,?,?,?)",
        (rec_id, out_name, fname, size_kb, style,
         len(findings), confidence, str(out_path),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

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
async def list_redacted_files():
    """List all stored redacted files."""
    conn  = _db()
    rows  = conn.execute(
        "SELECT id, filename, size_kb, created_at "
        "FROM redactions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    files = []
    for rid, fname, size_kb, created_at in rows:
        if (STORAGE_DIR / fname).exists():
            files.append({
                "redaction_id": rid,
                "filename":     fname,
                "size_kb":      size_kb,
                "created_at":   created_at,
                "download_url": f"/redact/{rid}/download",
            })

    return {"files": files}


@router.delete("/{redaction_id}")
async def delete_redacted_file(redaction_id: str):
    """Securely delete a stored redacted file."""
    conn = _db()
    row  = conn.execute(
        "SELECT file_path, filename FROM redactions WHERE id=?",
        (redaction_id,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(404, "Redaction not found")

    file_path, filename = row
    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception:
        pass

    conn.execute("DELETE FROM redactions WHERE id=?", (redaction_id,))
    conn.commit()
    conn.close()

    return {"message": f"'{filename}' securely deleted.", "id": redaction_id}


@router.get("/{redaction_id}/download")
async def download_redacted_file(redaction_id: str):
    """Download a stored redacted file."""
    conn = _db()
    row  = conn.execute(
        "SELECT file_path, filename FROM redactions WHERE id=?",
        (redaction_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "Redaction not found")

    file_path, filename = row
    fpath = Path(file_path)

    if not fpath.exists():
        raise HTTPException(404, "File no longer exists on disk")

    return FileResponse(
        path=str(fpath),
        filename=filename,
        media_type="text/plain",
    )
