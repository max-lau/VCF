from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id
from datetime import date, datetime, timedelta
import logging
import os

router = APIRouter()
logger = logging.getLogger(__name__)


class DeadlineBody(BaseModel):
    deadline_type: str = "missing_info_response"
    due_date: str
    description: str = ""


def _send_deadline_reminder(firm_id: str, deadline: dict, days_left: int):
    """Create an in-app notification and optionally log an email alert."""
    case_id = deadline["case_id"]
    deadline_type = deadline["deadline_type"]
    due_date = deadline["due_date"]
    case_number = deadline.get("case_number", "Unknown")
    client_name = deadline.get("client_name", "Unknown")

    urgency = "overdue" if days_left < 0 else "today" if days_left == 0 else f"in {days_left} day{'s' if days_left != 1 else ''}"
    title = f"VCF deadline {urgency}: {deadline_type}"
    body = (f"{deadline_type} for {client_name} (claim #{case_number}) is due {urgency} "
            f"({due_date}).")
    link = f"/matters/{case_id}"

    try:
        with get_conn(firm_id) as conn:
            conn.execute(
                """INSERT INTO notifications (firm_id, type, title, body, link)
                   VALUES (%s, %s, %s, %s, %s)""",
                (firm_id, "vcf_deadline", title, body, link)
            )
    except Exception as e:
        logger.warning(f"[VCF deadlines] Could not create in-app notification: {e}")

    notify_email = os.getenv("VCF_DEADLINE_NOTIFY_EMAIL")
    if notify_email:
        logger.info(f"[VCF deadlines] Would email {notify_email}: {title} — {body}")

    print(f"[VCF deadline reminder] {days_left} days left: {deadline_type} "
          f"for claim #{case_number} ({client_name})")


@router.post("/vcf/deadlines/notify", tags=["VCF Deadlines"])
async def notify_upcoming_deadlines(
    days_ahead: int = 7,
    firm_id: str = Depends(get_current_firm_id),
):
    """Send reminders for deadlines due within N days. Idempotent."""
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute("""
                SELECT d.id, d.case_id, d.deadline_type, d.due_date,
                       c.case_number, c.client_name
                FROM vcf_deadlines d
                JOIN cases c ON c.id = d.case_id
                WHERE d.firm_id = %s
                  AND d.status = 'pending'
                  AND d.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '%s days'
                ORDER BY d.due_date ASC
            """, (firm_id, days_ahead)).fetchall()

        today = date.today()
        notified = []
        for d in rows:
            days_left = (d["due_date"] - today).days
            _send_deadline_reminder(firm_id, dict(d), days_left)
            notified.append({"deadline_id": d["id"], "case_number": d["case_number"],
                             "days_left": days_left})

        return {"success": True, "notified": len(notified), "reminders": notified}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vcf/deadlines", tags=["VCF Deadlines"])
async def get_upcoming_deadlines(
    days_ahead: int = 30,
    firm_id: str = Depends(get_current_firm_id),
):
    """Fetch all upcoming/pending VCF deadlines across all cases."""
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute("""
                SELECT d.id, d.case_id, d.deadline_type, d.due_date, d.status,
                       c.case_number, c.client_name
                FROM vcf_deadlines d
                JOIN cases c ON c.id = d.case_id
                WHERE d.firm_id = %s
                  AND d.status = 'pending'
                  AND d.due_date >= CURRENT_DATE
                  AND d.due_date <= CURRENT_DATE + INTERVAL '%s days'
                ORDER BY d.due_date ASC
            """, (firm_id, days_ahead)).fetchall()

            return {"success": True, "count": len(rows), "deadlines": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vcf/cases/{case_id}/deadlines", tags=["VCF Deadlines"])
async def get_case_deadlines(case_id: int, firm_id: str = Depends(get_current_firm_id)):
    """Fetch all deadlines for a specific VCF case."""
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute("""
                SELECT * FROM vcf_deadlines
                WHERE case_id = %s AND firm_id = %s
                ORDER BY due_date DESC
            """, (case_id, firm_id)).fetchall()

            return {"success": True, "count": len(rows), "deadlines": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vcf/cases/{case_id}/deadlines", tags=["VCF Deadlines"])
async def create_case_deadline(
    case_id: int,
    body: DeadlineBody,
    firm_id: str = Depends(get_current_firm_id),
):
    """Manually add a deadline to a VCF case (e.g., 30-day missing info letter)."""
    if not body.due_date:
        raise HTTPException(status_code=400, detail="due_date is required (YYYY-MM-DD)")

    try:
        due_date = datetime.strptime(body.due_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        with get_conn(firm_id) as conn:
            # Verify case exists and belongs to this firm
            case = conn.execute(
                "SELECT id FROM cases WHERE id = %s AND firm_id = %s",
                (case_id, firm_id)
            ).fetchone()
            if not case:
                raise HTTPException(status_code=404, detail="Case not found")

            row = conn.execute("""
                INSERT INTO vcf_deadlines (firm_id, case_id, deadline_type, due_date, status, description)
                VALUES (%s, %s, %s, %s, 'pending', %s)
                RETURNING id, case_id, deadline_type, due_date, status, created_at
            """, (firm_id, case_id, body.deadline_type, due_date, body.description)).fetchone()
            conn.commit()

            return {"success": True, "deadline": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vcf/deadlines/dashboard", tags=["VCF Deadlines"])
async def get_deadlines_dashboard(firm_id: str = Depends(get_current_firm_id)):
    """Return VCF deadline counts by urgency."""
    try:
        with get_conn(firm_id) as conn:
            today = date.today()
            week_end = today + timedelta(days=7)

            overdue = conn.execute(
                """SELECT COUNT(*) AS n FROM vcf_deadlines
                   WHERE firm_id = %s AND status = 'pending' AND due_date < %s""",
                (firm_id, today)
            ).fetchone()["n"]

            today_count = conn.execute(
                """SELECT COUNT(*) AS n FROM vcf_deadlines
                   WHERE firm_id = %s AND status = 'pending' AND due_date = %s""",
                (firm_id, today)
            ).fetchone()["n"]

            this_week = conn.execute(
                """SELECT COUNT(*) AS n FROM vcf_deadlines
                   WHERE firm_id = %s AND status = 'pending'
                     AND due_date > %s AND due_date <= %s""",
                (firm_id, today, week_end)
            ).fetchone()["n"]

            later = conn.execute(
                """SELECT COUNT(*) AS n FROM vcf_deadlines
                   WHERE firm_id = %s AND status = 'pending' AND due_date > %s""",
                (firm_id, week_end)
            ).fetchone()["n"]

        return {
            "success": True,
            "counts": {
                "overdue": overdue,
                "today": today_count,
                "this_week": this_week,
                "later": later,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
