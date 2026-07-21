"""
backend/demo1/intake_jobs.py
────────────────────────────
Async / batch OCR intake job queue for VCFClaimsIQ.

Keeps the synchronous /intake/scan path fast while allowing bulk uploads
(5+ new claims/day, 10k+ backlog) to run in the background.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Intake Jobs"])


class JobStatusResponse(BaseModel):
    id: int
    status: str
    filename: str
    result_json: Optional[dict] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


def init_intake_jobs_table():
    """Create intake_jobs table if it doesn't exist."""
    try:
        from backend.demo1.pg import get_conn
        with get_conn("waw_vcf") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intake_jobs (
                    id          SERIAL PRIMARY KEY,
                    firm_id     TEXT NOT NULL,
                    filename    TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    result_json JSONB,
                    error       TEXT,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intake_jobs_firm_status ON intake_jobs(firm_id, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intake_jobs_created_at ON intake_jobs(firm_id, created_at DESC)")
            conn.execute("ALTER TABLE intake_jobs ENABLE ROW LEVEL SECURITY")
            conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE schemaname = 'public' AND tablename = 'intake_jobs'
                          AND policyname = 'intake_jobs_tenant_isolation'
                    ) THEN
                        CREATE POLICY intake_jobs_tenant_isolation ON intake_jobs
                            USING (firm_id = current_setting('app.current_firm_id', true))
                            WITH CHECK (firm_id = current_setting('app.current_firm_id', true));
                    END IF;
                END
                $$
            """)
            conn.commit()
        print("[IntakeJobs] Table initialized ✓")
    except Exception as e:
        print(f"[IntakeJobs] init failed: {e}")


def _run_ocr_job(job_id: int, firm_id: str, filename: str, contents: bytes,
                 content_type: str, lang: str, engine: str):
    """Background worker: run OCR and update the job record."""
    try:
        from backend.demo1.ocr_intake import extract_text, clean_ocr_text, _prep_upload
        pages, mime_type = _prep_upload(contents, content_type)
        result = extract_text(pages, lang=lang, engine=engine,
                              mime_type=mime_type, firm_id=firm_id)
        result["text"] = clean_ocr_text(result["text"])

        # Persist a scan row so it appears in intake history too.
        from backend.demo1.ocr_intake import get_conn as _get_conn
        with _get_conn(firm_id) as conn:
            conn.execute(
                """INSERT INTO intake_scans
                   (firm_id, filename, raw_text, word_count, confidence, ocr_engine, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (firm_id, filename, result["text"], result["word_count"],
                 result["confidence"], result["engine"],
                 datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

        # Mark job completed.
        with _get_conn(firm_id) as conn:
            conn.execute(
                """UPDATE intake_jobs
                   SET status = 'completed',
                       result_json = %s,
                       completed_at = NOW()
                   WHERE id = %s AND firm_id = %s""",
                (json.dumps(result), job_id, firm_id)
            )
            conn.commit()
    except Exception as e:
        logger.exception(f"[intake_jobs] job {job_id} failed")
        from backend.demo1.ocr_intake import get_conn as _get_conn
        try:
            with _get_conn(firm_id) as conn:
                conn.execute(
                    "UPDATE intake_jobs SET status='failed', error=%s, completed_at=NOW() WHERE id=%s AND firm_id=%s",
                    (str(e)[:500], job_id, firm_id)
                )
                conn.commit()
        except Exception as inner:
            logger.error(f"[intake_jobs] could not mark job {job_id} failed: {inner}")


@router.post("/intake/jobs")
async def create_intake_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    lang: str = Form(default="eng"),
    engine: str = Form(default="auto"),
):
    """Enqueue a single file for async OCR. Returns a job ID to poll."""
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    contents = await file.read()

    with get_conn(firm_id) as conn:
        row = conn.execute(
            """INSERT INTO intake_jobs (firm_id, filename, status)
               VALUES (%s, %s, 'pending') RETURNING id, created_at""",
            (firm_id, file.filename)
        ).fetchone()
        conn.commit()
        job_id = row["id"]

    background_tasks.add_task(_run_ocr_job, job_id, firm_id, file.filename,
                              contents, file.content_type, lang, engine)

    return {"success": True, "job_id": job_id, "status": "pending",
            "created_at": row["created_at"]}


@router.post("/intake/batch")
async def batch_intake(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    lang: str = Form(default="eng"),
    engine: str = Form(default="auto"),
):
    """Upload multiple files; each gets its own background OCR job."""
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    if len(files) > 50:
        raise HTTPException(400, "Maximum 50 files per batch")

    job_ids = []
    for file in files:
        contents = await file.read()
        with get_conn(firm_id) as conn:
            row = conn.execute(
                """INSERT INTO intake_jobs (firm_id, filename, status)
                   VALUES (%s, %s, 'pending') RETURNING id""",
                (firm_id, file.filename)
            ).fetchone()
            conn.commit()
            job_id = row["id"]
        job_ids.append(job_id)
        background_tasks.add_task(_run_ocr_job, job_id, firm_id, file.filename,
                                  contents, file.content_type, lang, engine)

    return {"success": True, "count": len(job_ids), "job_ids": job_ids}


@router.get("/intake/jobs/{job_id}")
async def get_intake_job(job_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    with get_conn(firm_id) as conn:
        row = conn.execute(
            """SELECT id, firm_id, filename, status, result_json, error,
                      created_at, completed_at
               FROM intake_jobs WHERE id = %s AND firm_id = %s""",
            (job_id, firm_id)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    data = dict(row)
    data["result_json"] = data["result_json"] if isinstance(data["result_json"], dict) else {}
    return {"success": True, "job": data}


@router.get("/intake/jobs")
async def list_intake_jobs(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    with get_conn(firm_id) as conn:
        if status:
            rows = conn.execute(
                """SELECT id, filename, status, created_at, completed_at
                   FROM intake_jobs WHERE firm_id = %s AND status = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (firm_id, status, min(limit, 200))
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, filename, status, created_at, completed_at
                   FROM intake_jobs WHERE firm_id = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (firm_id, min(limit, 200))
            ).fetchall()
    return {"success": True, "count": len(rows), "jobs": [dict(r) for r in rows]}
