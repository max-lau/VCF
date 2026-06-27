"""
discovery_intake.py — ParaIQ Discovery Intake & Processing
All DB access now goes through pg.get_conn(firm_id) for RLS-based tenant isolation.
"""
import os, io, zipfile, hashlib, mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx

from backend.demo1.pg import get_conn

router = APIRouter(prefix="/discovery", tags=["discovery"])

UPLOAD_DIR = Path(os.environ.get("DISCOVERY_UPLOAD_DIR", str(Path(__file__).parent.parent.parent / "uploads" / "discovery")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def init_discovery_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Discovery] DB table initialized ✓")


def _require_auth(request: Request):
    """Raise 401 if no valid JWT was decoded by TenantMiddleware."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")


IMAGE_TYPES = {"image/jpeg","image/png","image/tiff","image/bmp","image/webp","image/gif"}
ZIP_TYPES   = {"application/zip","application/x-zip-compressed","application/x-zip"}
PDF_TYPES   = {"application/pdf"}
DOC_TYPES   = {
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain","text/csv","application/rtf"
}

def detect_route(filename: str, mime_type: str) -> str:
    ext = Path(filename).suffix.lower()
    if mime_type in IMAGE_TYPES or ext in {".jpg",".jpeg",".png",".tiff",".tif",".bmp",".webp"}:
        return "ocr"
    if mime_type in ZIP_TYPES or ext == ".zip":
        return "zip"
    if mime_type in PDF_TYPES or ext == ".pdf":
        return "digital"
    if mime_type in DOC_TYPES or ext in {".doc",".docx",".txt",".rtf",".csv"}:
        return "digital"
    if ext in {".mp3",".wav",".m4a",".ogg",".flac",".mp4",".mov",".avi"}:
        return "audio"
    return "unknown"

def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


# ── Privilege screening ────────────────────────────────────────────────────────

_PRIVILEGE_KEYWORDS = [
    "attorney-client", "privileged and confidential", "work product",
    "attorney eyes only", "legal advice", "without prejudice",
    "prepared by counsel", "settlement negotiation", "do not disclose",
    "confidential communication",
]

async def _screen_privilege(
    file_id: int,
    text: str,
    filename: str,
    firm_id: str = "default",
):
    """Background task — screen a file for privilege and write verdict to discovery_files."""
    privileged      = False
    priv_type       = "none"
    confidence      = 0.0
    requires_review = False

    try:
        from backend.demo1.db_enclaves import get_client_enclave, save_privilege_verdict
        enclave = get_client_enclave(firm_id)

        if enclave:
            async with httpx.AsyncClient(timeout=30) as hx:
                resp = await hx.post(
                    f"{enclave['enclave_url'].rstrip('/')}/screen",
                    json={
                        "doc_id":   str(file_id),
                        "text":     text[:5000],
                        "filename": filename,
                        "doc_type": "discovery",
                    },
                    headers={"X-Enclave-Key": enclave["api_key"]},
                )
            if resp.status_code == 200:
                r               = resp.json()
                privileged      = bool(r.get("privileged", False))
                priv_type       = r.get("privilege_type", "none")
                confidence      = float(r.get("confidence", 0.0))
                requires_review = bool(r.get("requires_review", False))
                save_privilege_verdict(
                    client_id=firm_id,
                    doc_id=str(file_id),
                    privileged=privileged,
                    privilege_type=priv_type,
                    confidence=confidence,
                    requires_review=requires_review,
                )
        else:
            t_lower = text.lower()
            hits    = sum(1 for kw in _PRIVILEGE_KEYWORDS if kw in t_lower)
            if hits >= 2:
                privileged      = True
                priv_type       = "attorney_client"
                confidence      = min(0.4 + hits * 0.1, 0.85)
                requires_review = True
            else:
                confidence = 0.05

    except Exception as exc:
        import logging
        logging.getLogger("paraiq.privilege").warning(
            f"Privilege screen failed file_id={file_id}: {exc}"
        )

    # Write verdict back to discovery_files (soft — never raises)
    try:
        with get_conn(firm_id) as conn:
            conn.execute(
                """UPDATE discovery_files
                   SET privilege_flag=%s, privilege_type=%s, privilege_confidence=%s, requires_review=%s
                   WHERE id=%s""",
                (int(privileged), priv_type, confidence, int(requires_review), file_id),
            )
    except Exception as exc:
        import logging
        logging.getLogger("paraiq.privilege").error(f"DB verdict write failed: {exc}")


def _get_doc_text(original_name: str, firm_id: str = "default", fallback: str = "") -> str:
    """Pull extracted text from case_documents. Returns fallback if not found."""
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT doc_text FROM case_documents WHERE document_name=%s LIMIT 1",
                (original_name,)
            ).fetchone()
            if row and row["doc_text"]:
                return row["doc_text"][:5000]
    except Exception:
        pass
    return fallback


# ── Upload / intake ───────────────────────────────────────────────────────────

@router.post("/intake")
@router.post("/upload")
async def intake_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    case_number: Optional[str] = Form(None),
    firm_id:     Optional[str] = Form(None),
):
    _require_auth(request)
    effective_firm = firm_id or getattr(request.state, "firm_id", "default")
    results = []

    for upload in files:
        data = await upload.read()
        mime  = upload.content_type or mimetypes.guess_type(upload.filename)[0] or "application/octet-stream"
        route = detect_route(upload.filename, mime)
        fhash = file_hash(data)
        size  = len(data)

        ts        = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = f"{ts}_{fhash}_{upload.filename}"
        dest      = UPLOAD_DIR / safe_name
        dest.write_bytes(data)

        zip_contents = []
        if route == "zip":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    zip_contents = [
                        {"name": n, "size": zf.getinfo(n).file_size}
                        for n in zf.namelist()
                        if not n.endswith("/")
                    ]
            except Exception:
                route = "unknown"

        with get_conn(effective_firm) as conn:
            cur = conn.execute(
                """INSERT INTO discovery_files
                   (filename, original_name, file_hash, file_size, mime_type, route, case_number, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (safe_name, upload.filename, fhash, size, mime, route, case_number, "queued"),
            )
            file_id = cur.fetchone()["id"]

        # Auto-link to case_documents if case_number provided
        if case_number:
            with get_conn(effective_firm) as conn:
                case_row = conn.execute(
                    "SELECT id FROM cases WHERE case_number=%s AND deleted=false LIMIT 1",
                    (case_number,)
                ).fetchone()
                if case_row:
                    stub = f"Intake route: {route} | Hash: {fhash}"
                    already = conn.execute(
                        "SELECT id FROM case_documents WHERE case_id=%s AND document_name=%s",
                        (case_row["id"], upload.filename)
                    ).fetchone()
                    if not already:
                        conn.execute(
                            "INSERT INTO case_documents (case_id, document_name, source, doc_text) VALUES (%s,%s,%s,%s)",
                            (case_row["id"], upload.filename, "discovery", stub)
                        )

        background_tasks.add_task(
            _screen_privilege, file_id, upload.filename, upload.filename, effective_firm
        )

        results.append({
            "id":            file_id,
            "original_name": upload.filename,
            "size":          size,
            "mime_type":     mime,
            "route":         route,
            "case_number":   case_number,
            "zip_contents":  zip_contents,
            "status":        "queued",
            "privilege_flag": None,
        })

    return {"success": True, "files": results, "total": len(results)}


# ── Queue / catalog / stats ───────────────────────────────────────────────────

@router.get("/queue")
def get_queue(request: Request, case_number: Optional[str] = None, limit: int = 50):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    limit = min(limit, 200)
    with get_conn(firm_id) as conn:
        if case_number:
            rows = conn.execute(
                "SELECT * FROM discovery_files WHERE case_number=%s ORDER BY created_at DESC LIMIT %s",
                (case_number, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM discovery_files ORDER BY created_at DESC LIMIT %s",
                (limit,)
            ).fetchall()
    return {"files": [dict(r) for r in rows]}


@router.delete("/queue/{file_id}")
def remove_from_queue(file_id: int, request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute("SELECT filename FROM discovery_files WHERE id=%s", (file_id,)).fetchone()
        if not row:
            raise HTTPException(404, "File not found")
        try:
            (UPLOAD_DIR / row["filename"]).unlink(missing_ok=True)
        except Exception:
            pass
        conn.execute("DELETE FROM discovery_files WHERE id=%s", (file_id,))
    return {"success": True}


@router.get("/stats")
def discovery_stats(request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows  = conn.execute(
            "SELECT route, COUNT(*) as cnt FROM discovery_files GROUP BY route"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM discovery_files").fetchone()[0]
    return {"total": total, "by_route": {r["route"]: r["cnt"] for r in rows}}


# ── Manual privilege screening endpoints ──────────────────────────────────────

@router.post("/screen/{file_id}")
async def screen_file_privilege(
    file_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute("SELECT * FROM discovery_files WHERE id=%s", (file_id,)).fetchone()
    if not row:
        raise HTTPException(404, "File not found")
    row = dict(row)
    text = _get_doc_text(row["original_name"], firm_id=firm_id, fallback=row["original_name"])
    background_tasks.add_task(_screen_privilege, file_id, text, row["original_name"], firm_id)
    return {"success": True, "file_id": file_id, "status": "screening_queued"}


@router.post("/screen-all")
async def screen_all_unscreened(
    request: Request,
    background_tasks: BackgroundTasks,
):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT id, original_name FROM discovery_files WHERE privilege_flag IS NULL"
        ).fetchall()
    for row in rows:
        text = _get_doc_text(row["original_name"], firm_id=firm_id, fallback=row["original_name"])
        background_tasks.add_task(_screen_privilege, row["id"], text, row["original_name"], firm_id)
    return {"success": True, "queued": len(rows), "firm_id": firm_id}


# ── OCR / ZIP / audio processing ─────────────────────────────────────────────

@router.post("/process/ocr/{file_id}")
async def process_ocr(file_id: int, request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM discovery_files WHERE id=%s AND route='ocr'", (file_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "File not found or not an OCR file")

    file_path = UPLOAD_DIR / row["filename"]
    if not file_path.exists():
        raise HTTPException(404, "File missing from disk")

    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                "http://localhost:5003/intake/scan",
                headers={"X-API-Key": os.environ.get("PARAIQ_API_KEY","")},
                files={"file": (row["original_name"], f, row["mime_type"])},
                data={"engine": "claude"}
            )

    result = resp.json()

    with get_conn(firm_id) as conn:
        conn.execute("UPDATE discovery_files SET status='processed' WHERE id=%s", (file_id,))

    return {
        "success":       True,
        "file_id":       file_id,
        "original_name": row["original_name"],
        "text":          result.get("text",""),
        "confidence":    result.get("confidence", 0),
        "word_count":    result.get("word_count", 0),
        "engine":        result.get("engine","")
    }


@router.post("/process/zip/{file_id}")
async def process_zip(file_id: int, request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM discovery_files WHERE id=%s AND route='zip'", (file_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "File not found or not a ZIP file")

    file_path = UPLOAD_DIR / row["filename"]
    if not file_path.exists():
        raise HTTPException(404, "ZIP file missing from disk")

    extracted = []
    errors    = []

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            entries = [e for e in zf.infolist() if not e.filename.endswith("/")]

            def zip_date(e):
                try:    return datetime(*e.date_time)
                except: return datetime.min
            entries.sort(key=zip_date)

            for entry in entries:
                try:
                    data      = zf.read(entry.filename)
                    flat_name = Path(entry.filename).name
                    fhash     = file_hash(data)
                    ts        = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    safe_name = f"{ts}_{fhash}_{flat_name}"
                    dest      = UPLOAD_DIR / safe_name
                    dest.write_bytes(data)

                    mime  = mimetypes.guess_type(flat_name)[0] or "application/octet-stream"
                    route = detect_route(flat_name, mime)

                    try:    doc_date = datetime(*entry.date_time).strftime("%Y-%m-%d")
                    except: doc_date = None

                    with get_conn(firm_id) as conn:
                        cur = conn.execute(
                            """INSERT INTO discovery_files
                               (filename, original_name, file_hash, file_size, mime_type,
                                route, case_number, doc_date, status)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                               RETURNING id""",
                            (safe_name, flat_name, fhash, len(data), mime,
                             route, row["case_number"], doc_date, "queued")
                        )
                        new_id = cur.fetchone()["id"]
                        conn.execute(
                            "UPDATE discovery_files SET status='extracted' WHERE id=%s", (file_id,)
                        )

                    extracted.append({
                        "id":       new_id,
                        "name":     flat_name,
                        "size":     len(data),
                        "route":    route,
                        "doc_date": doc_date,
                        "mime_type": mime,
                    })
                except Exception as e:
                    errors.append({"file": entry.filename, "error": "Processing failed"})

    except zipfile.BadZipFile:
        raise HTTPException(400, "Invalid or corrupted ZIP file")

    extracted.sort(key=lambda x: x["doc_date"] or "")

    return {
        "success":   True,
        "zip_id":    file_id,
        "zip_name":  row["original_name"],
        "extracted": extracted,
        "total":     len(extracted),
        "errors":    errors,
    }


@router.post("/assign")
async def assign_to_case(body: dict, request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    file_ids    = body.get("file_ids", [])
    case_number = body.get("case_number", "").strip()
    case_name   = body.get("case_name", case_number)

    if not file_ids or not case_number:
        raise HTTPException(400, "file_ids and case_number are required")

    API_KEY = os.environ.get("PARAIQ_API_KEY", "")

    with get_conn(firm_id) as conn:
        existing = conn.execute("SELECT id FROM cases WHERE case_number=%s", (case_number,)).fetchone()
        case_id  = existing["id"] if existing else None

    if not case_id:
        async with httpx.AsyncClient(timeout=15) as client:
            r2 = await client.post(
                "http://localhost:5003/cases/",
                headers={"X-API-Key": API_KEY, "Content-Type": "application/json",
                         "Authorization": request.headers.get("Authorization", "")},
                json={"case_number": case_number, "client_name": case_name, "status": "open"}
            )
        case_id = r2.json().get("id")

    if not case_id:
        raise HTTPException(500, "Could not create or find case")

    assigned = []
    with get_conn(firm_id) as conn:
        for fid in file_ids:
            row = conn.execute("SELECT * FROM discovery_files WHERE id=%s", (fid,)).fetchone()
            if not row:
                continue
            conn.execute("UPDATE discovery_files SET case_number=%s WHERE id=%s", (case_number, fid))
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    f"http://localhost:5003/cases/{case_id}/documents",
                    headers={"X-API-Key": API_KEY, "Content-Type": "application/json",
                             "Authorization": request.headers.get("Authorization", "")},
                    json={
                        "document_name": row["original_name"],
                        "doc_text":      f"Intake route: {row['route']} | Hash: {row['file_hash']}",
                    }
                )
            assigned.append({"id": fid, "name": row["original_name"]})

    return {
        "success":     True,
        "case_id":     case_id,
        "case_number": case_number,
        "assigned":    assigned,
        "total":       len(assigned),
    }


@router.get("/catalog")
def get_catalog(request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """SELECT case_number, route,
                      COUNT(*) as cnt,
                      COALESCE(SUM(file_size), 0) as total_size,
                      MIN(created_at) as first_added,
                      MAX(created_at) as last_added
               FROM discovery_files
               GROUP BY case_number, route
               ORDER BY case_number, route"""
        ).fetchall()

    catalog = {}
    for r in rows:
        cn = r["case_number"] or "Unassigned"
        if cn not in catalog:
            catalog[cn] = {"case_number": cn, "routes": {}, "total_files": 0, "total_size": 0}
        catalog[cn]["routes"][r["route"]] = {"count": r["cnt"], "size": r["total_size"]}
        catalog[cn]["total_files"] += r["cnt"]
        catalog[cn]["total_size"]  += r["total_size"] or 0

    return {"catalog": list(catalog.values()), "total_cases": len(catalog)}


import re as _re

DATE_PATTERNS = [
    (_re.compile(r'\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b'), "%Y-%m-%d"),
    (_re.compile(r'\b(0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])[-/](20\d{2})\b'), "%m-%d-%Y"),
    (_re.compile(r'\b(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b'), "%Y%m%d"),
    (_re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{2})\b'), "%B %d %Y"),
    (_re.compile(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{2})\b'), "%b %d %Y"),
]

def extract_date_from_text(text: str):
    from datetime import datetime as _dt
    for pattern, fmt in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(0).replace(",", "").replace("/", "-")
            for candidate in [raw, " ".join(g for g in m.groups() if g)]:
                try:    return _dt.strptime(candidate, fmt).strftime("%Y-%m-%d")
                except: continue
    return None


@router.post("/extract-dates")
async def extract_dates(request: Request, body: dict = None):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    file_ids = (body or {}).get("file_ids", None)
    with get_conn(firm_id) as conn:
        if file_ids:
            rows = conn.execute(
                "SELECT * FROM discovery_files WHERE id = ANY(%s)",
                (file_ids,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM discovery_files WHERE doc_date IS NULL").fetchall()

    updated = []
    skipped = []

    for row in rows:
        doc_date = extract_date_from_text(row["original_name"])
        if not doc_date and row["mime_type"] and row["mime_type"].startswith("text/"):
            try:
                fp = UPLOAD_DIR / row["filename"]
                if fp.exists():
                    text     = fp.read_text(errors="ignore")[:3000]
                    doc_date = extract_date_from_text(text)
            except Exception:
                pass

        if doc_date:
            with get_conn(firm_id) as conn:
                conn.execute("UPDATE discovery_files SET doc_date=%s WHERE id=%s", (doc_date, row["id"]))
            updated.append({"id": row["id"], "name": row["original_name"], "doc_date": doc_date})
        else:
            skipped.append({"id": row["id"], "name": row["original_name"]})

    return {"success": True, "updated": updated, "skipped": skipped,
            "total_updated": len(updated), "total_skipped": len(skipped)}


@router.get("/sorted")
def get_sorted_queue(request: Request, case_number: str = None):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if case_number:
            rows = conn.execute(
                "SELECT * FROM discovery_files WHERE case_number=%s ORDER BY COALESCE(doc_date,'9999') ASC, created_at ASC",
                (case_number,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM discovery_files ORDER BY COALESCE(doc_date,'9999') ASC, created_at ASC"
            ).fetchall()
    return {"files": [dict(r) for r in rows], "total": len(rows)}


@router.get("/duplicates")
def find_duplicates(request: Request):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        dupes = conn.execute("""
            SELECT file_hash, COUNT(*) as cnt
            FROM discovery_files
            WHERE file_hash IS NOT NULL
            GROUP BY file_hash
            HAVING COUNT(*) > 1
        """).fetchall()

        groups = []
        for d in dupes:
            rows = conn.execute(
                "SELECT * FROM discovery_files WHERE file_hash=%s ORDER BY created_at ASC",
                (d["file_hash"],)
            ).fetchall()
            files = [dict(r) for r in rows]
            groups.append({
                "hash":       d["file_hash"],
                "count":      d["cnt"],
                "keep":       files[0]["id"],
                "duplicates": files,
            })

    return {
        "total_groups":     len(groups),
        "total_duplicates": sum(g["count"] - 1 for g in groups),
        "groups":           groups,
    }


@router.post("/extract-text/{file_id}")
async def extract_text_to_case(file_id: int, request: Request, background_tasks: BackgroundTasks):
    _require_auth(request)
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute("SELECT * FROM discovery_files WHERE id=%s", (file_id,)).fetchone()
    if not row:
        raise HTTPException(404, "File not found")

    row       = dict(row)
    route     = row.get("route", "")
    file_path = UPLOAD_DIR / row["filename"]
    extracted_text = ""

    if route == "ocr":
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "http://localhost:5003/discovery/process/ocr/" + str(file_id),
                headers={"X-API-Key": os.environ.get("PARAIQ_API_KEY", ""),
                         "Authorization": request.headers.get("Authorization", "")}
            )
        extracted_text = resp.json().get("text", "")

    elif route == "digital":
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            extracted_text = pdf_extract(str(file_path))
            extracted_text = " ".join(extracted_text.split())[:10000]
        except Exception as e:
            import logging; logging.getLogger(__name__).error(f"[discovery_intake] PDF extraction error: {e}")
        raise HTTPException(500, "PDF extraction failed. Please try again.")

    elif route == "audio":
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "http://localhost:5003/media/transcribe/discovery/" + str(file_id),
                headers={"X-API-Key": os.environ.get("PARAIQ_API_KEY", ""),
                         "Authorization": request.headers.get("Authorization", "")}
            )
        extracted_text = resp.json().get("transcript", "")

    else:
        raise HTTPException(400, f"No text extraction available for route: {route}")

    if not extracted_text.strip():
        return {"success": False, "file_id": file_id, "message": "No text extracted"}

    with get_conn(firm_id) as conn:
        updated = conn.execute(
            "UPDATE case_documents SET doc_text=%s WHERE document_name=%s",
            (extracted_text, row["original_name"])
        ).rowcount
        conn.execute("UPDATE discovery_files SET status='text_extracted' WHERE id=%s", (file_id,))

    # Re-screen with real text now that extraction is complete
    background_tasks.add_task(
        _screen_privilege, file_id, extracted_text[:5000], row["original_name"], firm_id
    )

    return {
        "success":                True,
        "file_id":                file_id,
        "original_name":          row["original_name"],
        "route":                  route,
        "word_count":             len(extracted_text.split()),
        "preview":                extracted_text[:200],
        "case_documents_updated": updated,
    }

# ─────────────────────────────────────────────────────────────────────────────

from backend.demo1.discovery_agent_guard import GuardedDiscoveryRunner, AgentLimits

@router.post("/run-guarded")
async def run_guarded_discovery(request: Request, body: dict):
    """
    Guarded batch discovery run.
    Accepts file_ids already uploaded via /discovery/intake.
    Runs all 7 pipeline stages with hard compute guards.
    """
    _require_auth(request)
    firm_id      = getattr(request.state, "firm_id", "default")
    file_ids     = body.get("file_ids", [])
    case_number  = body.get("case_number", "").strip()
    bates_prefix = body.get("bates_prefix", "PROD")
    bates_start  = int(body.get("bates_start", 1))
    output_dir   = body.get("output_dir", "/tmp")

    if not file_ids:
        raise HTTPException(400, "file_ids is required")
    if not case_number:
        raise HTTPException(400, "case_number is required")

    limits = AgentLimits(
        max_llm_calls_per_run     = int(body.get("max_llm_calls",     8)),
        max_total_tokens_per_run  = int(body.get("max_total_tokens",  12000)),
        max_docs_per_run          = int(body.get("max_docs",          30)),
        max_ocr_pages_per_run     = int(body.get("max_ocr_pages",     150)),
        max_estimated_cost_usd    = float(body.get("max_cost_usd",    0.25)),
        timeout_seconds_per_stage = int(body.get("timeout_per_stage", 90)),
        timeout_seconds_total     = int(body.get("timeout_total",     600)),
    )

    runner = GuardedDiscoveryRunner(
        case_id      = case_number,
        firm_id      = firm_id,
        limits       = limits,
        bates_prefix = bates_prefix,
        bates_start  = bates_start,
    )

    result = await runner.run_from_ids(file_ids=file_ids, output_dir=output_dir)
    return result
