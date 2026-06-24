import os
import io, csv, zipfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.demo1.pg import get_conn

router = APIRouter(prefix="/production", tags=["Production Bundler"])

BATES_DIR = Path(os.environ.get("BATES_DIR",
    str(Path(__file__).parent.parent.parent / "uploads" / "bates")))


@router.get("/sets")
def list_sets(request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT set_id, COUNT(*) as doc_count,
                   SUM(page_count) as total_pages,
                   MIN(bates_start) as range_start,
                   MAX(bates_end)   as range_end,
                   MAX(stamped_at)  as last_stamped
            FROM bates_log WHERE firm_id=%s
            GROUP BY set_id ORDER BY last_stamped DESC
        """, (firm_id,)).fetchall()
    return {"sets": [dict(r) for r in rows]}


@router.get("/bundle/{set_id}")
def download_bundle(set_id: str, request: Request, max_mb: int = 100):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM bates_log WHERE set_id=%s AND firm_id=%s ORDER BY id ASC",
            (set_id, firm_id)
        ).fetchall()

    if not rows:
        raise HTTPException(404, f"No stamped documents found for set '{set_id}'")

    set_dir = BATES_DIR / set_id
    if not set_dir.exists():
        raise HTTPException(404, f"Production set directory not found: {set_dir}")

    max_bytes    = max_mb * 1024 * 1024
    catalog_rows = []
    file_entries = []

    for r in rows:
        p = Path(r["stamped_path"]) if r["stamped_path"] else None
        if not p or not p.exists():
            matches = list(set_dir.glob(f"*{r['filename']}"))
            p = matches[0] if matches else None
        size = p.stat().st_size if p else 0
        catalog_rows.append({
            "bates_start": r["bates_start"], "bates_end": r["bates_end"],
            "pages": r["page_count"], "filename": r["filename"],
            "stamped_at": r["stamped_at"], "size_bytes": size,
        })
        file_entries.append((r, p, size))

    def make_catalog_csv(entries):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["#","Bates Start","Bates End","Pages","Filename","Size (bytes)","Stamped At"])
        for i, e in enumerate(entries, 1):
            w.writerow([i, e["bates_start"], e["bates_end"], e["pages"],
                        e["filename"], e["size_bytes"], e["stamped_at"]])
        return buf.getvalue().encode()

    total_size = sum(e[2] for e in file_entries)
    zip_buf    = io.BytesIO()

    if total_size <= max_bytes:
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("production_catalog.csv", make_catalog_csv(catalog_rows))
            for r, p, size in file_entries:
                if p and p.exists():
                    zf.write(p, p.name)
        filename = f"Production_{set_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.zip"
    else:
        batch_catalog, batch_size = [], 0
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for r, p, size in file_entries:
                if batch_size + size > max_bytes and batch_catalog:
                    break
                if p and p.exists():
                    zf.write(p, p.name)
                    batch_catalog.append({
                        "bates_start": dict(r)["bates_start"], "bates_end": dict(r)["bates_end"],
                        "pages": dict(r)["page_count"], "filename": dict(r)["filename"],
                        "size_bytes": size, "stamped_at": dict(r)["stamped_at"],
                    })
                    batch_size += size
            zf.writestr("production_catalog.csv", make_catalog_csv(batch_catalog))
            zf.writestr("SPLIT_NOTICE.txt",
                f"Batch 1 of split production set '{set_id}'.\n"
                f"Total: {total_size/1024/1024:.1f} MB exceeds {max_mb} MB limit.")
        filename = f"Production_{set_id}_Part1_{datetime.now(timezone.utc).strftime('%Y%m%d')}.zip"

    zip_buf.seek(0)
    return StreamingResponse(zip_buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/catalog/{set_id}")
def get_catalog(set_id: str, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM bates_log WHERE set_id=%s AND firm_id=%s ORDER BY id ASC",
            (set_id, firm_id)
        ).fetchall()
    if not rows:
        raise HTTPException(404, f"No documents found for set '{set_id}'")
    total_pages = sum(r["page_count"] for r in rows)
    return {
        "set_id":      set_id,
        "doc_count":   len(rows),
        "total_pages": total_pages,
        "range_start": rows[0]["bates_start"],
        "range_end":   rows[-1]["bates_end"],
        "documents":   [dict(r) for r in rows],
    }
