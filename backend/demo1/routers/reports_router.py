from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json
from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

router = APIRouter(prefix="/reports", tags=["reports"])

REPORT_TYPES = [
    "case_summary", "timeline_report", "privilege_log", "discovery_index",
    "contradiction_report", "deadline_report", "correspondence_log",
    "contact_sheet", "research_memo", "custom"
]


def init_table():
    """No-op — table exists in Supabase Postgres."""
    pass


init_table()


class ReportCreate(BaseModel):
    matter_id:    Optional[int]  = None
    report_type:  str
    title:        str
    content:      Optional[str]  = ""
    metadata:     Optional[dict] = None
    generated_by: Optional[str]  = "manual"
    created_by:   Optional[str]  = ""


class ReportUpdate(BaseModel):
    title:    Optional[str]  = None
    content:  Optional[str]  = None
    status:   Optional[str]  = None
    metadata: Optional[dict] = None


def _build_report_content(matter_id: int, report_type: str, conn) -> str:
    """Assemble report content from existing Postgres data."""
    try:
        if report_type == "case_summary":
            case = conn.execute(
                "SELECT * FROM cases WHERE id = %s", (matter_id,)
            ).fetchone()
            if not case:
                return "Case not found."
            doc_count = conn.execute(
                "SELECT COUNT(*) AS c FROM case_documents WHERE case_id = %s",
                (matter_id,)
            ).fetchone()["c"]
            return json.dumps({
                "case": dict(case),
                "document_count": doc_count,
                "generated_at": datetime.now().isoformat()
            }, indent=2, default=str)

        elif report_type == "deadline_report":
            rows = conn.execute(
                "SELECT * FROM calendar_events WHERE matter_id = %s ORDER BY due_date ASC",
                (matter_id,)
            ).fetchall()
            return json.dumps([dict(r) for r in rows], indent=2, default=str)

        elif report_type == "privilege_log":
            rows = conn.execute(
                "SELECT * FROM privilege_log WHERE case_number IN "
                "(SELECT case_number FROM cases WHERE id = %s) ORDER BY withheld_at DESC",
                (matter_id,)
            ).fetchall()
            return json.dumps([dict(r) for r in rows], indent=2, default=str)

        elif report_type == "discovery_index":
            rows = conn.execute(
                "SELECT * FROM case_documents WHERE case_id = %s ORDER BY upload_date DESC",
                (matter_id,)
            ).fetchall()
            return json.dumps([dict(r) for r in rows], indent=2, default=str)

        elif report_type == "correspondence_log":
            rows = conn.execute(
                "SELECT * FROM correspondence WHERE matter_id = %s ORDER BY date DESC",
                (matter_id,)
            ).fetchall()
            return json.dumps([dict(r) for r in rows], indent=2, default=str)

        elif report_type == "contact_sheet":
            rows = conn.execute(
                "SELECT * FROM contacts WHERE matter_id = %s ORDER BY name ASC",
                (matter_id,)
            ).fetchall()
            return json.dumps([dict(r) for r in rows], indent=2, default=str)

        elif report_type == "contradiction_report":
            rows = conn.execute(
                "SELECT * FROM case_contradictions WHERE case_id = %s ORDER BY severity DESC",
                (matter_id,)
            ).fetchall()
            return json.dumps([dict(r) for r in rows], indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": "Internal error occurred"})
    return ""


@router.get("/matter/{matter_id}")
def list_matter_reports(
    matter_id:   int,
    report_type: Optional[str] = None,
    firm_id:     str           = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        sql = """
            SELECT id, matter_id, report_type, title, status,
                   generated_by, created_by, created_at
            FROM reports WHERE matter_id = %s
        """
        params = [matter_id]
        if report_type:
            sql += " AND report_type = %s"
            params.append(report_type)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/{report_id}")
def get_report(
    report_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = %s", (report_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@router.post("/generate/{matter_id}/{report_type}")
def generate_report(
    matter_id:   int,
    report_type: str,
    created_by:  Optional[str] = "",
    firm_id:     str           = Depends(get_current_firm_id),
):
    if report_type not in REPORT_TYPES:
        raise HTTPException(400, f"Invalid report type. Valid: {REPORT_TYPES}")
    title = f"{report_type.replace('_', ' ').title()} — Matter #{matter_id}"
    with get_conn(firm_id) as conn:
        content = _build_report_content(matter_id, report_type, conn)
        cur = conn.execute("""
            INSERT INTO reports
              (firm_id, matter_id, report_type, title, status, content, generated_by, created_by)
            VALUES (%s,%s,%s,%s,'complete',%s,'system',%s)
            RETURNING id
        """, (firm_id, matter_id, report_type, title, content, created_by))
        new_id = cur.fetchone()["id"]
        row    = conn.execute(
            "SELECT * FROM reports WHERE id = %s", (new_id,)
        ).fetchone()
    return dict(row)


@router.post("/")
def create_manual_report(
    report:  ReportCreate,
    firm_id: str = Depends(get_current_firm_id),
):
    meta = json.dumps(report.metadata) if report.metadata else None
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO reports
              (firm_id, matter_id, report_type, title, status, content,
               metadata, generated_by, created_by)
            VALUES (%s,%s,%s,%s,'complete',%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, report.matter_id, report.report_type, report.title,
              report.content, meta, report.generated_by, report.created_by))
        new_id = cur.fetchone()["id"]
        row    = conn.execute(
            "SELECT * FROM reports WHERE id = %s", (new_id,)
        ).fetchone()
    return dict(row)


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute("DELETE FROM reports WHERE id = %s", (report_id,))
    return {"deleted": report_id}


@router.get("/types/list")
def get_report_types():
    return {"types": REPORT_TYPES}
