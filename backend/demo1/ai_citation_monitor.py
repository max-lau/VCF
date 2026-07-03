"""
backend/demo1/ai_citation_monitor.py
====================================
Independent Monitor Agent that red-teams the Case Researcher's output.
Prevents hallucinated or mislabeled citations from being trusted.
"""
import json
import logging
from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

def verify_citations(text: str, firm_id: str = None) -> dict:
    """
    Independent Monitor Agent: extracts legal citations from AI-generated
    text (e.g. a case brief) and resolves case citations against
    CourtListener to catch hallucinated or mislabeled citations before
    they reach an attorney.
    """
    from backend.demo1.citation_resolver import extract_citations, resolve_citation

    citations = extract_citations(text)
    resolved_count = 0
    unresolved_count = 0
    error_count = 0

    for c in citations:
        if c["type"] == "case":
            result = resolve_citation(c["raw"])
            c["resolved"] = result
            c["resolve_status"] = result.get("status", "error")
            if c["resolve_status"] == "resolved":
                resolved_count += 1
            elif c["resolve_status"] == "not_found":
                unresolved_count += 1
            else:
                error_count += 1

    total_case_citations = sum(1 for c in citations if c["type"] == "case")
    if total_case_citations == 0:
        overall_status = "no_case_citations"
    elif unresolved_count > 0 or error_count > 0:
        overall_status = "high_risk_of_hallucination"
    else:
        overall_status = "verified"

    return {
        "overall_status": overall_status,
        "total_citations": len(citations),
        "case_citations_checked": total_case_citations,
        "resolved": resolved_count,
        "unresolved": unresolved_count,
        "errors": error_count,
        "citations": citations,
    }



def log_attorney_review(doc_id: int, attorney_id: str, firm_id: str) -> bool:
    """
    Logs that an attorney has formally reviewed and approved an AI-generated document.
    This is the malpractice shield.
    """
    with get_conn(firm_id) as conn:
        # Check if already reviewed
        row = conn.execute(
            "SELECT reviewed FROM attorney_review_gates WHERE doc_id = %s AND firm_id = %s",
            (doc_id, firm_id)
        ).fetchone()
        
        if row and row["reviewed"]:
            return True
            
        if row:
            conn.execute(
                "UPDATE attorney_review_gates SET reviewed = TRUE, attorney_id = %s, reviewed_at = NOW() WHERE doc_id = %s",
                (attorney_id, doc_id)
            )
        else:
            conn.execute(
                "INSERT INTO attorney_review_gates (firm_id, doc_id, attorney_id, reviewed, reviewed_at) VALUES (%s, %s, %s, TRUE, NOW())",
                (firm_id, doc_id, attorney_id)
            )
    return True

def is_document_reviewed(doc_id: int, firm_id: str) -> bool:
    """Checks if a document has passed the attorney review gate."""
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT reviewed FROM attorney_review_gates WHERE doc_id = %s AND firm_id = %s",
            (doc_id, firm_id)
        ).fetchone()
    return bool(row and row["reviewed"])
