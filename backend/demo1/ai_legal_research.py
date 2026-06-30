"""
ai_legal_research.py
====================
ParaIQ AI Legal Research (Phase 3, #4)

Provides AI-assisted legal research by analyzing queries and generating
structured legal analysis. While a full RAG implementation requires an
ingested case law database, this module provides the analytical layer
and structures the output for future RAG integration.

Features:
  - Legal issue identification
  - Analytical framework generation
  - Citation formatting structure
  - Uses strong model for deep reasoning
"""

import logging
import json
from typing import Dict, Any
from backend.demo1.prompt_guard import build_safe_messages, guard_prompt
from backend.demo1.model_router import call_llm, TaskType

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM_PROMPT = (
    "You are an expert legal research assistant. Analyze the user's legal query and "
    "provide a structured legal analysis. Identify the core legal issues, apply relevant "
    "legal principles, and suggest areas for further research. "
    "Do not provide definitive legal advice, but provide a thorough analytical framework.\n\n"
    "Return your response as a JSON object with this structure:\n"
    "{\n"
    '  "issue_identification": ["List of core legal issues identified"],\n'
    '  "legal_framework": "Discussion of relevant legal principles, statutes, or precedent categories",\n'
    '  "analytical_application": "Application of the law to the facts presented",\n'
    '  "potential_arguments": ["Arguments for the requesting party", "Arguments against"],\n'
    '  "research_recommendations": ["Specific areas or types of authority to research further"],\n'
    '  "disclaimer": "Standard legal research disclaimer"\n'
    "}"
)

def conduct_research(query: str, firm_id: str, jurisdiction: str = "", max_tokens: int = 2000) -> Dict[str, Any]:
    """
    Conducts AI-assisted legal research.
    
    Args:
        query: The legal question or fact pattern to research.
        firm_id: The tenant ID for AI isolation.
        jurisdiction: Optional jurisdiction context (e.g., "California state law").
        max_tokens: Max output tokens for the response.
        
    Returns:
        Dict containing structured legal research analysis.
    """
    if not query or len(query.strip()) < 10:
        return {"error": "Query is too short to conduct research."}
        
    try:
        # 1. Prompt injection defense
        guard_result = guard_prompt(query)
        if guard_result.blocked:
            logger.warning(f"Prompt guard blocked legal research for firm {firm_id}")
            return {"error": "Input blocked by security filter.", "threats": guard_result.threat_summary}

        # 2. Build safe messages with optional jurisdiction context
        user_content = query
        if jurisdiction:
            user_content = f"Jurisdiction Context: {jurisdiction}\n\nQuery: {query}"
            
        messages = build_safe_messages(
            system_prompt=RESEARCH_SYSTEM_PROMPT,
            user_content=user_content,
            firm_id=firm_id,
        )
        
        # 3. Route to LLM (Research uses the strong model)
        response_text = call_llm(
            task_type=TaskType.LEGAL_RESEARCH,
            messages=messages,
            firm_id=firm_id,
            max_tokens=max_tokens,
        )
        
        if not response_text:
            return {"error": "LLM returned an empty response."}
            
        # 4. Parse JSON response
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
            return {"raw_research": response_text}
            
    except Exception as e:
        logger.error(f"Error during AI legal research for firm {firm_id}: {e}", exc_info=True)
        return {"error": f"Internal error during legal research: {str(e)}"}
