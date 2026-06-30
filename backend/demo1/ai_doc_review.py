"""
ai_doc_review.py
================
ParaIQ AI Document Review & Risk Analysis (Phase 2, #6)

Analyzes legal documents to identify potential risks, missing clauses,
and compliance issues. Uses the strong model (Opus/Sonnet) for deep
analysis and applies prompt injection defense.

Features:
  - Risk identification and severity scoring
  - Missing clause detection
  - Compliance flagging
  - Structured JSON output
"""

import logging
import json
from typing import Dict, Any
from backend.demo1.prompt_guard import build_safe_messages, guard_prompt
from backend.demo1.model_router import call_llm, TaskType

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = (
    "You are an expert legal document reviewer. Analyze the provided document text for "
    "potential legal risks, missing standard clauses, and compliance issues. "
    "Do not provide legal advice, but objectively identify areas of concern.\n\n"
    "Return your response as a JSON object with this structure:\n"
    "{\n"
    '  "overall_risk_level": "Low|Medium|High",\n'
    '  "identified_risks": [\n'
    '    {\n'
    '      "risk": "Description of the risk",\n'
    '      "severity": "Low|Medium|High",\n'
    '      "location_or_clause": "Where it was found"\n'
    '    }\n'
    '  ],\n'
    '  "missing_clauses": ["List of standard clauses that appear to be missing"],\n'
    '  "compliance_flags": ["Any regulatory or compliance concerns"]\n'
    "}"
)

def review_document(text: str, firm_id: str, max_tokens: int = 1500) -> Dict[str, Any]:
    """
    Reviews a legal document for risks and missing clauses.
    
    Args:
        text: The raw text of the document to review.
        firm_id: The tenant ID for AI isolation.
        max_tokens: Max output tokens.
        
    Returns:
        Dict containing the structured review or an error.
    """
    if not text or len(text.strip()) < 50:
        return {"error": "Document text too short to review."}
        
    try:
        guard_result = guard_prompt(text)
        if guard_result.blocked:
            logger.warning(f"Prompt guard blocked doc review for firm {firm_id}")
            return {"error": "Input blocked by security filter.", "threats": guard_result.threat_summary}

        messages = build_safe_messages(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_content=text,
            firm_id=firm_id,
        )
        
        # Use the strong model for deep analysis
        response_text = call_llm(
            task_type=TaskType.ANALYSIS,
            messages=messages,
            firm_id=firm_id,
            max_tokens=max_tokens,
        )
        
        if not response_text:
            return {"error": "LLM returned an empty response."}
            
        try:
            clean_response = response_text.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
                
            return json.loads(clean_response.strip())
        except json.JSONDecodeError:
            return {"raw_review": response_text}
            
    except Exception as e:
        logger.error(f"Error during AI doc review for firm {firm_id}: {e}", exc_info=True)
        return {"error": f"Internal error during document review: {str(e)}"}
