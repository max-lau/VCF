from fastapi import APIRouter, Request, HTTPException
from backend.demo1.pg import get_conn
from datetime import datetime

router = APIRouter()

@router.get("/vcf/cases/{case_id}/disbursement", tags=["VCF Disbursements"])
async def get_disbursement(case_id: int, request: Request):
    """Get or initialize the disbursement record for a VCF case."""
    firm_id = getattr(request.state, "firm_id", "default")
    try:
        with get_conn(firm_id) as conn:
            # Check if disbursement exists
            row = conn.execute("""
                SELECT * FROM vcf_disbursements WHERE case_id = %s
            """, (case_id,)).fetchone()
            
            if not row:
                # Initialize: pull gross award from cases table
                case = conn.execute("SELECT award_amount FROM cases WHERE id = %s", (case_id,)).fetchone()
                gross = float(case["award_amount"]) if case and case["award_amount"] else 0.0
                
                # Calculate default 10% fee
                fee_amount = gross * 0.10
                
                # Insert initial record
                row = conn.execute("""
                    INSERT INTO vcf_disbursements 
                    (case_id, gross_award, attorney_fee_amount, net_to_claimant)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                """, (case_id, gross, fee_amount, gross - fee_amount)).fetchone()
                conn.commit()
                
            return {"success": True, "disbursement": dict(row)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/vcf/cases/{case_id}/disbursement", tags=["VCF Disbursements"])
async def update_disbursement(case_id: int, request: Request):
    """Update liens, fees, and recalculate net payout."""
    firm_id = getattr(request.state, "firm_id", "default")
    body = await request.json()
    
    gross = float(body.get("gross_award", 0))
    fee_pct = float(body.get("attorney_fee_pct", 10.0))
    fee_amount = gross * (fee_pct / 100.0)
    
    medicare = float(body.get("medicare_lien", 0))
    medicaid = float(body.get("medicaid_lien", 0))
    workers_comp = float(body.get("workers_comp_lien", 0))
    other = float(body.get("other_lien", 0))
    
    total_liens = medicare + medicaid + workers_comp + other
    net_to_claimant = gross - fee_amount - total_liens
    
    status = body.get("status", "pending")
    
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute("""
                INSERT INTO vcf_disbursements 
                (case_id, gross_award, attorney_fee_pct, attorney_fee_amount, 
                 medicare_lien, medicaid_lien, workers_comp_lien, other_lien, other_lien_desc,
                 net_to_claimant, status, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (case_id) DO UPDATE SET
                  gross_award = EXCLUDED.gross_award,
                  attorney_fee_pct = EXCLUDED.attorney_fee_pct,
                  attorney_fee_amount = EXCLUDED.attorney_fee_amount,
                  medicare_lien = EXCLUDED.medicare_lien,
                  medicaid_lien = EXCLUDED.medicaid_lien,
                  workers_comp_lien = EXCLUDED.workers_comp_lien,
                  other_lien = EXCLUDED.other_lien,
                  other_lien_desc = EXCLUDED.other_lien_desc,
                  net_to_claimant = EXCLUDED.net_to_claimant,
                  status = EXCLUDED.status,
                  updated_at = now()
                RETURNING *
            """, (case_id, gross, fee_pct, fee_amount, medicare, medicaid, workers_comp, other, 
                  body.get("other_lien_desc", ""), net_to_claimant, status)).fetchone()
            conn.commit()
            
            return {"success": True, "disbursement": dict(row)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))