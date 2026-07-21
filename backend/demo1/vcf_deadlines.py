from fastapi import APIRouter, Request, HTTPException
from backend.demo1.pg import get_conn
from datetime import date, datetime

router = APIRouter()

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