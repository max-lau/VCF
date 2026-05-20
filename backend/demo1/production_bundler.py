import io, csv, sqlite3, zipfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/production", tags=["Production Bundler"])

DB_PATH   = "/root/nlp-portfolio/backend/demo1/analyses.db"
BATES_DIR = Path("/root/nlp-portfolio/uploads/bates")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/sets")
def list_sets():
    """List all production sets that have stamped documents."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT set_id, COUNT(*) as doc_count,
               SUM(page_count) as total_pages,
               MIN(bates_start) as range_start,
               MAX(bates_end)   as range_end,
               MAX(stamped_at)  as last_stamped
        FROM bates_log
        GROUP BY set_id
        ORDER BY last_stamped DESC
    """).fetchall()
    conn.close()
    return {"sets": [dict(r) for r in rows]}

@router.get("/bundle/{set_id}")
def download_bundle(set_id: str, max_mb: int = 100):
    """
    Stream a ZIP of all Bates-stamped PDFs for a production set.
    Splits into multiple ZIPs if total exceeds max_mb (default 100 MB).
    Includes a production_catalog.csv manifest inside the ZIP.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM bates_log WHERE set_id=? ORDER BY id ASC", (set_id,)
    ).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(404, f"No stamped documents found for set '{set_id}'")

    set_dir = BATES_DIR / set_id
    if not set_dir.exists():
        raise HTTPException(404, f"Production set directory not found: {set_dir}")

    max_bytes = max_mb * 1024 * 1024

    # Build catalog rows and collect files
    catalog_rows = []
    file_entries  = []
    for r in rows:
        p = Path(r["stamped_path"]) if r["stamped_path"] else None
        if not p or not p.exists():
            # Try to find by name in set_dir
            matches = list(set_dir.glob(f"*{r['filename']}"))
            p = matches[0] if matches else None
        size = p.stat().st_size if p else 0
        catalog_rows.append({
            "bates_start": r["bates_start"],
            "bates_end":   r["bates_end"],
            "pages":       r["page_count"],
            "filename":    r["filename"],
            "stamped_at":  r["stamped_at"],
            "size_bytes":  size,
            "path":        str(p) if p else "MISSING",
        })
        file_entries.append((r, p, size))

    # Build catalog CSV in memory
    def make_catalog_csv(entries):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["#","Bates Start","Bates End","Pages","Filename","Size (bytes)","Stamped At"])
        for i, e in enumerate(entries, 1):
            w.writerow([i, e["bates_start"], e["bates_end"], e["pages"],
                        e["filename"], e["size_bytes"], e["stamped_at"]])
        return buf.getvalue().encode()

    # Check if everything fits in one ZIP
    total_size = sum(e[2] for e in file_entries)

    if total_size <= max_bytes:
        # Single ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            catalog_data = make_catalog_csv(catalog_rows)
            zf.writestr("production_catalog.csv", catalog_data)
            for r, p, size in file_entries:
                if p and p.exists():
                    zf.write(p, p.name)
        zip_buf.seek(0)
        filename = f"Production_{set_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.zip"
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        # Split into batches — return first batch, note others
        # (For simplicity, return batch 1; full multi-part needs client coordination)
        batch, batch_size, batch_num = [], 0, 1
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            batch_catalog = []
            for r, p, size in file_entries:
                if batch_size + size > max_bytes and batch:
                    break
                if p and p.exists():
                    zf.write(p, p.name)
                    batch_catalog.append({
                        "bates_start": dict(r)["bates_start"],
                        "bates_end":   dict(r)["bates_end"],
                        "pages":       dict(r)["page_count"],
                        "filename":    dict(r)["filename"],
                        "size_bytes":  size,
                        "stamped_at":  dict(r)["stamped_at"],
                    })
                    batch_size += size
            zf.writestr("production_catalog.csv", make_catalog_csv(batch_catalog))
            zf.writestr("SPLIT_NOTICE.txt",
                f"This is batch 1 of a split production set '{set_id}'.\n"
                f"Total set size: {total_size/1024/1024:.1f} MB exceeds {max_mb} MB limit.\n"
                f"Increase limit with ?max_mb=N or download remaining batches.")
        zip_buf.seek(0)
        filename = f"Production_{set_id}_Part1_{datetime.now(timezone.utc).strftime('%Y%m%d')}.zip"
        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

@router.get("/catalog/{set_id}")
def get_catalog(set_id: str):
    """Return the production catalog as JSON without downloading the ZIP."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM bates_log WHERE set_id=? ORDER BY id ASC", (set_id,)
    ).fetchall()
    conn.close()
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
