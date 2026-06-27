import os
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.demo1.pg import get_conn

router = APIRouter(prefix="/bates", tags=["Bates Numbering"])
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(os.environ.get("DISCOVERY_UPLOAD_DIR",
    str(Path(__file__).parent.parent.parent / "uploads" / "discovery")))
BATES_DIR  = Path(os.environ.get("BATES_DIR",
    str(Path(__file__).parent.parent.parent / "uploads" / "bates")))
BATES_DIR.mkdir(parents=True, exist_ok=True)


def init_bates_tables():
    """No-op -- tables exist in Supabase Postgres."""
    print("[Bates] Tables initialized OK")


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


class BatesConfigIn(BaseModel):
    set_id:      str
    prefix:      str = ""
    start_num:   int = 1
    padding:     int = 6
    case_number: Optional[str] = None

class BatesStampIn(BaseModel):
    set_id:   str
    file_ids: Optional[List[int]] = None


@router.post("/configure")
def configure(body: BatesConfigIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    if not (1 <= body.padding <= 12):
        raise HTTPException(400, "padding must be 1-12")
    prefix = body.prefix.upper().strip()
    with get_conn(firm_id) as conn:
        conn.execute("""
            INSERT INTO bates_configs (firm_id, set_id, prefix, start_num, padding, case_number)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (set_id) DO UPDATE SET
                prefix=EXCLUDED.prefix, start_num=EXCLUDED.start_num,
                padding=EXCLUDED.padding, case_number=EXCLUDED.case_number
        """, (firm_id, body.set_id, prefix, body.start_num, body.padding, body.case_number))
    return {"success": True, "set_id": body.set_id, "sample": fmt(prefix, body.start_num, body.padding)}


@router.post("/stamp")
def stamp(body: BatesStampIn, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        cfg = conn.execute(
            "SELECT * FROM bates_configs WHERE set_id=%s AND firm_id=%s",
            (body.set_id, firm_id)
        ).fetchone()
        if not cfg:
            raise HTTPException(404, f"No config for set_id='{body.set_id}'")

        prefix   = cfg["prefix"]
        padding  = cfg["padding"]
        case_num = cfg["case_number"]

        last = conn.execute(
            "SELECT bates_end FROM bates_log WHERE set_id=%s AND firm_id=%s ORDER BY id DESC LIMIT 1",
            (body.set_id, firm_id)
        ).fetchone()
        counter = (int(last["bates_end"][len(prefix):]) + 1) if last else cfg["start_num"]

        if body.file_ids:
            ph   = ",".join(["%s"] * len(body.file_ids))
            rows = conn.execute(
                f"SELECT * FROM discovery_files WHERE id IN ({ph}) AND firm_id=%s AND mime_type='application/pdf'",
                body.file_ids + [firm_id]
            ).fetchall()
        elif case_num:
            rows = conn.execute(
                """SELECT * FROM discovery_files WHERE case_number=%s AND firm_id=%s
                   AND mime_type='application/pdf'
                   ORDER BY COALESCE(doc_date,'9999') ASC, created_at ASC""",
                (case_num, firm_id)
            ).fetchall()
        else:
            raise HTTPException(400, "Provide file_ids or set case_number in /bates/configure")

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
            errors.append({"id": row["id"], "name": row["original_name"], "error": "read failed"})
            continue

        labels      = [fmt(prefix, counter + j, padding) for j in range(pages)]
        bates_start = labels[0]
        bates_end   = labels[-1]
        out_name    = f"BATES_{body.set_id}_{bates_start}_{bates_end}_{row['original_name']}"
        out_path    = BATES_DIR / body.set_id / out_name

        try:
            stamp_pdf(src, out_path, labels)
        except Exception as e:
            logger.warning(f"[Bates] stamp failed for {row['original_name']}: {e}")
            errors.append({"id": row["id"], "name": row["original_name"], "error": "stamp failed"})
            continue

        with get_conn(firm_id) as conn:
            conn.execute("""
                INSERT INTO bates_log
                  (firm_id, set_id, doc_id, filename, bates_start, bates_end, page_count, stamped_path, stamped_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (firm_id, body.set_id, row["id"], row["original_name"],
                  bates_start, bates_end, pages, str(out_path),
                  datetime.now(timezone.utc).isoformat()))
            conn.execute(
                "UPDATE discovery_files SET status='bates_stamped' WHERE id=%s AND firm_id=%s",
                (row["id"], firm_id)
            )

        stamped.append({"id": row["id"], "filename": row["original_name"],
                        "pages": pages, "bates_start": bates_start, "bates_end": bates_end})
        counter += pages

    return {
        "success":      True,
        "set_id":       body.set_id,
        "stamped":      len(stamped),
        "errors":       len(errors),
        "range":        {"start": stamped[0]["bates_start"], "end": stamped[-1]["bates_end"]} if stamped else None,
        "documents":    stamped,
        "error_detail": errors,
    }


@router.get("/log")
def get_log(request: Request, set_id: Optional[str] = None):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if set_id:
            rows = conn.execute(
                "SELECT * FROM bates_log WHERE set_id=%s AND firm_id=%s ORDER BY id ASC",
                (set_id, firm_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bates_log WHERE firm_id=%s ORDER BY id DESC LIMIT 200",
                (firm_id,)
            ).fetchall()
    return {"log": [dict(r) for r in rows], "total": len(rows)}


@router.get("/configs")
def list_configs(request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM bates_configs WHERE firm_id=%s ORDER BY created_at DESC",
            (firm_id,)
        ).fetchall()
    return {"configs": [dict(r) for r in rows]}


@router.delete("/log/{set_id}")
def clear_log(set_id: str, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        conn.execute(
            "DELETE FROM bates_log WHERE set_id=%s AND firm_id=%s", (set_id, firm_id)
        )
    return {"success": True, "cleared": set_id}
