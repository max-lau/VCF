"""
backend/demo1/vcf_reports.py
────────────────────────────
VCFClaimsIQ reporting endpoints.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.demo1.pg import get_conn

router = APIRouter(tags=["VCF Reports"])


@router.get("/reports/claims-by-stage")
async def claims_by_stage(request: Request):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            """SELECT claim_stage, COUNT(*) AS cnt
               FROM cases WHERE firm_id = %s AND deleted = FALSE
               GROUP BY claim_stage ORDER BY claim_stage""",
            (firm_id,)
        ).fetchall()
    return {"success": True, "data": [dict(r) for r in rows]}


@router.get("/reports/overdue-deadlines")
async def overdue_deadlines(
    request: Request,
    days_ahead: int = Query(30, ge=1, le=365),
    include_resolved: bool = False,
):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    with get_conn(firm_id) as conn:
        status_filter = "" if include_resolved else "AND d.status = 'pending'"
        rows = conn.execute(f"""
            SELECT d.id, d.case_id, d.deadline_type, d.due_date, d.status,
                   c.case_number, c.client_name
            FROM vcf_deadlines d
            JOIN cases c ON c.id = d.case_id
            WHERE d.firm_id = %s
              AND d.due_date <= CURRENT_DATE + INTERVAL '%s days'
              {status_filter}
            ORDER BY d.due_date ASC
        """, (firm_id, days_ahead)).fetchall()
    return {"success": True, "count": len(rows), "deadlines": [dict(r) for r in rows]}


@router.get("/reports/disbursements")
async def disbursements_report(request: Request, format: str = Query("json", pattern="^(json|csv)$")):
    firm_id = getattr(request.state, "firm_id", "waw_vcf")
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT d.*, c.case_number, c.client_name
            FROM vcf_disbursements d
            JOIN cases c ON c.id = d.case_id
            WHERE d.firm_id = %s
            ORDER BY d.created_at DESC
        """, (firm_id,)).fetchall()
    data = [dict(r) for r in rows]

    if format == "json":
        return {"success": True, "count": len(data), "disbursements": data}

    # CSV export
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "case_id", "case_number", "client_name", "gross_award", "attorney_fee_pct",
        "attorney_fee_amount", "medicare_lien", "medicaid_lien", "workers_comp_lien",
        "other_lien", "net_to_claimant", "status"
    ])
    writer.writeheader()
    for row in data:
        writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=disbursements-{date.today()}.csv"}
    )
