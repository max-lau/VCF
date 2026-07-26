from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, field_validator
from backend.demo1.pg import get_conn
from datetime import datetime

router = APIRouter()


class DisbursementUpdate(BaseModel):
    gross_award: float = Field(default=0.0, ge=0)
    attorney_fee_pct: float = Field(default=10.0, ge=0, le=100)
    medicare_lien: float = Field(default=0.0, ge=0)
    medicaid_lien: float = Field(default=0.0, ge=0)
    workers_comp_lien: float = Field(default=0.0, ge=0)
    other_lien: float = Field(default=0.0, ge=0)
    other_lien_desc: str = Field(default="")
    status: str = Field(default="pending")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = {"pending", "approved", "paid", "on_hold"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


def _verify_case_ownership(conn, firm_id: str, case_id: int):
    """Raise 404 if the case does not exist or does not belong to the firm."""
    row = conn.execute(
        "SELECT id FROM cases WHERE id = %s AND firm_id = %s AND deleted = FALSE",
        (case_id, firm_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")


@router.get("/vcf/cases/{case_id}/disbursement", tags=["VCF Disbursements"])
async def get_disbursement(case_id: int, request: Request):
    """Get or initialize the disbursement record for a VCF case."""
    firm_id = getattr(request.state, "firm_id", "default")
    try:
        with get_conn(firm_id) as conn:
            _verify_case_ownership(conn, firm_id, case_id)

            row = conn.execute(
                "SELECT * FROM vcf_disbursements WHERE firm_id = %s AND case_id = %s",
                (firm_id, case_id),
            ).fetchone()

            if not row:
                case = conn.execute(
                    "SELECT award_amount FROM cases WHERE id = %s AND firm_id = %s",
                    (case_id, firm_id),
                ).fetchone()
                gross = float(case["award_amount"]) if case and case["award_amount"] else 0.0
                fee_amount = round(gross * 0.10, 2)

                row = conn.execute(
                    """
                    INSERT INTO vcf_disbursements
                        (firm_id, case_id, gross_award, attorney_fee_amount, net_to_claimant)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (firm_id, case_id, gross, fee_amount, round(gross - fee_amount, 2)),
                ).fetchone()
                conn.commit()

            return {"success": True, "disbursement": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load disbursement: {e}")


@router.put("/vcf/cases/{case_id}/disbursement", tags=["VCF Disbursements"])
async def update_disbursement(case_id: int, request: Request):
    """Update liens, fees, and recalculate net payout."""
    firm_id = getattr(request.state, "firm_id", "default")
    try:
        body = await request.json()
        data = DisbursementUpdate(**body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed JSON: {e}")

    fee_amount = round(data.gross_award * (data.attorney_fee_pct / 100.0), 2)
    total_liens = data.medicare_lien + data.medicaid_lien + data.workers_comp_lien + data.other_lien
    net_to_claimant = round(data.gross_award - fee_amount - total_liens, 2)

    try:
        with get_conn(firm_id) as conn:
            _verify_case_ownership(conn, firm_id, case_id)

            row = conn.execute(
                """
                INSERT INTO vcf_disbursements
                    (firm_id, case_id, gross_award, attorney_fee_pct, attorney_fee_amount,
                     medicare_lien, medicaid_lien, workers_comp_lien, other_lien, other_lien_desc,
                     net_to_claimant, status, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (case_id) DO UPDATE SET
                  firm_id = EXCLUDED.firm_id,
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
                """,
                (firm_id, case_id, data.gross_award, data.attorney_fee_pct, fee_amount,
                 data.medicare_lien, data.medicaid_lien, data.workers_comp_lien, data.other_lien,
                 data.other_lien_desc, net_to_claimant, data.status),
            ).fetchone()
            conn.commit()

            return {"success": True, "disbursement": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not update disbursement: {e}")
