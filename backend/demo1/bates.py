import os
import io, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/bates", tags=["Bates Numbering"])

DB_PATH    = os.environ.get("PARAIQ_DB", str(Path(__file__).parent / "analyses.db"))
UPLOAD_DIR = Path(os.environ.get("DISCOVERY_UPLOAD_DIR", str(Path(__file__).parent.parent.parent / "uploads" / "discovery")))
BATES_DIR  = Path(os.environ.get("BATES_DIR", str(Path(__file__).parent.parent.parent / "uploads" / "bates")))
BATES_DIR.mkdir(parents=True, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_bates_tables():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bates_configs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id      TEXT NOT NULL UNIQUE,
            prefix      TEXT NOT NULL DEFAULT '',
            start_num   INTEGER NOT NULL DEFAULT 1,
            padding     INTEGER NOT NULL DEFAULT 6,
            case_number TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bates_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id       TEXT NOT NULL,
            doc_id       INTEGER,
            filename     TEXT NOT NULL,
            bates_start  TEXT NOT NULL,
            bates_end    TEXT NOT NULL,
            page_count   INTEGER NOT NULL DEFAULT 1,
            stamped_path TEXT,
            stamped_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_bates_tables()

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt(prefix: str, num: int, padding: int) -> str:
    return f"{prefix}{str(num).zfill(padding)}"

def stamp_pdf(src: Path, dest: Path, labels: list) -> int:
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas as rl_canvas

    reader = PdfReader(str(src))
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        label = labels[i] if i < len(labels) else labels[-1]
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)

        # Build stamp overlay
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(w, h))
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(w - 20, 18, label)
        c.save()
        buf.seek(0)

        from pypdf import PdfReader as PR
        overlay = PR(buf).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        writer.write(f)

    return len(reader.pages)

# ── Models ────────────────────────────────────────────────────────────────────

class BatesConfigIn(BaseModel):
    set_id:      str
    prefix:      str = ""
    start_num:   int = 1
    padding:     int = 6
    case_number: Optional[str] = None

class BatesStampIn(BaseModel):
    set_id:   str
    file_ids: Optional[List[int]] = None  # None = all PDFs in the configured case

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/configure")
def configure(body: BatesConfigIn):
    if not (1 <= body.padding <= 12):
        raise HTTPException(400, "padding must be 1–12")
    prefix = body.prefix.upper().strip()
    conn = get_conn()
    conn.execute("""
        INSERT INTO bates_configs (set_id, prefix, start_num, padding, case_number)
        VALUES (?,?,?,?,?)
        ON CONFLICT(set_id) DO UPDATE SET
            prefix=excluded.prefix, start_num=excluded.start_num,
            padding=excluded.padding, case_number=excluded.case_number
    """, (body.set_id, prefix, body.start_num, body.padding, body.case_number))
    conn.commit()
    conn.close()
    return {
        "success": True,
        "set_id": body.set_id,
        "sample": fmt(prefix, body.start_num, body.padding)
    }

@router.post("/stamp")
def stamp(body: BatesStampIn):
    conn = get_conn()
    cfg = conn.execute("SELECT * FROM bates_configs WHERE set_id=?", (body.set_id,)).fetchone()
    if not cfg:
        conn.close()
        raise HTTPException(404, f"No config for set_id='{body.set_id}'. Call /bates/configure first.")

    prefix   = cfg["prefix"]
    padding  = cfg["padding"]
    case_num = cfg["case_number"]

    # Resume counter from where this set left off
    last = conn.execute(
        "SELECT bates_end FROM bates_log WHERE set_id=? ORDER BY id DESC LIMIT 1",
        (body.set_id,)
    ).fetchone()
    counter = (int(last["bates_end"][len(prefix):]) + 1) if last else cfg["start_num"]

    # Fetch target PDFs
    if body.file_ids:
        ph   = ",".join("?" * len(body.file_ids))
        rows = conn.execute(
            f"SELECT * FROM discovery_files WHERE id IN ({ph}) AND mime_type='application/pdf'",
            body.file_ids
        ).fetchall()
    elif case_num:
        rows = conn.execute(
            """SELECT * FROM discovery_files WHERE case_number=? AND mime_type='application/pdf'
               ORDER BY COALESCE(doc_date,'9999') ASC, created_at ASC""",
            (case_num,)
        ).fetchall()
    else:
        conn.close()
        raise HTTPException(400, "Provide file_ids or set case_number in /bates/configure")

    conn.close()

    if not rows:
        raise HTTPException(404, "No PDF files found to stamp")

    stamped, errors = [], []

    for row in rows:
        src = UPLOAD_DIR / row["filename"]
        if not src.exists():
            errors.append({"id": row["id"], "name": row["original_name"], "error": "missing from disk"})
            continue

        try:
            from pypdf import PdfReader
            pages = len(PdfReader(str(src)).pages)
        except Exception as e:
            errors.append({"id": row["id"], "name": row["original_name"], "error": f"read: {e}"})
            continue

        labels      = [fmt(prefix, counter + j, padding) for j in range(pages)]
        bates_start = labels[0]
        bates_end   = labels[-1]
        out_name    = f"BATES_{body.set_id}_{bates_start}_{bates_end}_{row['original_name']}"
        out_path    = BATES_DIR / body.set_id / out_name

        try:
            stamp_pdf(src, out_path, labels)
        except Exception as e:
            errors.append({"id": row["id"], "name": row["original_name"], "error": f"stamp: {e}"})
            continue

        conn = get_conn()
        conn.execute("""
            INSERT INTO bates_log (set_id, doc_id, filename, bates_start, bates_end, page_count, stamped_path)
            VALUES (?,?,?,?,?,?,?)
        """, (body.set_id, row["id"], row["original_name"],
              bates_start, bates_end, pages, str(out_path)))
        conn.execute("UPDATE discovery_files SET status='bates_stamped' WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()

        stamped.append({
            "id": row["id"], "filename": row["original_name"],
            "pages": pages, "bates_start": bates_start, "bates_end": bates_end,
        })
        counter += pages

    return {
        "success":    True,
        "set_id":     body.set_id,
        "stamped":    len(stamped),
        "errors":     len(errors),
        "range":      {"start": stamped[0]["bates_start"], "end": stamped[-1]["bates_end"]} if stamped else None,
        "documents":  stamped,
        "error_detail": errors,
    }

@router.get("/log")
def get_log(set_id: Optional[str] = None):
    conn = get_conn()
    if set_id:
        rows = conn.execute(
            "SELECT * FROM bates_log WHERE set_id=? ORDER BY id ASC", (set_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM bates_log ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()
    return {"log": [dict(r) for r in rows], "total": len(rows)}

@router.get("/configs")
def list_configs():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bates_configs ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"configs": [dict(r) for r in rows]}

@router.delete("/log/{set_id}")
def clear_log(set_id: str):
    """Reset a set so it can be re-stamped from its original start number."""
    conn = get_conn()
    conn.execute("DELETE FROM bates_log WHERE set_id=?", (set_id,))
    conn.commit()
    conn.close()
    return {"success": True, "cleared": set_id}
