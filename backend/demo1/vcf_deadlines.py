from fastapi import APIRouter, Request, HTTPException
from backend.demo1.pg import get_conn
from datetime import date, datetime, timedelta

router = APIRouter()


def _send_deadline_reminder(firm_id: str, deadline: dict, days_left: int):
    """Placeholder for notification channel (email/Slack/in-app)."""
    # TODO: wire to notifications_router / email / Slack once channel is chosen.
    print(f"[VCF deadline reminder] {days_left} days left: {deadline['deadline_type']} "
          f"for claim #{deadline['case_number']} ({deadline['client_name']})")


@router.post("/vcf/deadlines/notify", tags=["VCF Deadlines"])
async def notify_upcoming_deadlines(request: Request, days_ahead: int = 7):
    """Send reminders for deadlines due within N days. Idempotent."""
    firm_id = getattr(request.state, "firm_id", "default")
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
async def get_upcoming_deadlines(request: Request, days_ahead: int = 30):
    """Fetch all upcoming/pending VCF deadlines across all cases."""
    firm_id = getattr(request.state, "firm_id", "default")
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute("""
                SELECT d.id, d.case_id, d.deadline_type, d.due_date, d.status,
                       c.case_number, c.client_name
                FROM vcf_deadlines d
                JOIN cases c ON c.id = d.case_id
                WHERE d.status = 'pending'
                  AND d.due_date >= CURRENT_DATE
                  AND d.due_date <= CURRENT_DATE + INTERVAL '%s days'
                ORDER BY d.due_date ASC
            """, (days_ahead,)).fetchall()
            
            return {"success": True, "count": len(rows), "deadlines": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/vcf/cases/{case_id}/deadlines", tags=["VCF Deadlines"])
async def get_case_deadlines(case_id: int, request: Request):
    """Fetch all deadlines for a specific VCF case."""
    firm_id = getattr(request.state, "firm_id", "default")
    try:
        with get_conn(firm_id) as conn:
            rows = conn.execute("""
                SELECT * FROM vcf_deadlines 
                WHERE case_id = %s 
                ORDER BY due_date DESC
            """, (case_id,)).fetchall()
            
            return {"success": True, "count": len(rows), "deadlines": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vcf/cases/{case_id}/deadlines", tags=["VCF Deadlines"])
async def create_case_deadline(case_id: int, request: Request):
    """Manually add a deadline to a VCF case (e.g., 30-day missing info letter)."""
    firm_id = getattr(request.state, "firm_id", "default")
    body = await request.json()
    
    deadline_type = body.get("deadline_type", "missing_info_response")
    due_date_str = body.get("due_date")
    
    if not due_date_str:
        raise HTTPException(status_code=400, detail="due_date is required (YYYY-MM-DD)")
        
    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        with get_conn(firm_id) as conn:
            # Verify case exists
            case = conn.execute("SELECT id FROM cases WHERE id = %s", (case_id,)).fetchone()
            if not case:
                raise HTTPException(status_code=404, detail="Case not found")
                
            row = conn.execute("""
                INSERT INTO vcf_deadlines (case_id, deadline_type, due_date, status)
                VALUES (%s, %s, %s, 'pending')
                RETURNING id, case_id, deadline_type, due_date, status, created_at
            """, (case_id, deadline_type, due_date)).fetchone()
            conn.commit()
            
            return {"success": True, "deadline": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))