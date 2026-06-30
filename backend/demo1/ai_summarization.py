"""
ai_summarization.py
===================
ParaIQ AI Case Summarization (Phase 2, #1)

Leverages the Phase 1 model_router to generate concise, accurate summaries
of legal cases, documents, and matter contexts. 

Features:
  - Task-specific routing (summarization -> fast model)
  - Prompt injection defense applied to all input text
  - Structured JSON output parsing for programmatic use
  - Tenant-aware system prompts

Usage:
    from backend.demo1.ai_summarization import summarize_text
    
    summary = summarize_text(
        text="Long legal document text...",
        firm_id="acme_law",
        context="This is regarding the Smith v. Jones discovery phase."
    )
"""

import logging
import json
from typing import Dict, Any, Optional
from backend.demo1.prompt_guard import build_safe_messages, guard_prompt
from backend.demo1.model_router import call_llm, TaskType

logger = logging.getLogger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "You are an expert legal AI assistant. Your task is to summarize the provided "
    "text accurately and concisely. Focus on key facts, legal arguments, deadlines, "
    "and actionable items. Do not hallucinate information. If the text is incomplete "
    "or ambiguous, state that in your summary.\n\n"
    "Return your response as a JSON object with the following structure:\n"
    "{\n"
    '  "executive_summary": "1-2 sentence high-level overview",\n'
    '  "key_facts": ["List of critical facts"],\n'
    '  "action_items": ["List of next steps or deadlines"],\n'
    '  "risk_flags": ["Any potential legal risks or compliance issues noted"]\n'
    "}"
)

# ── Core Function ─────────────────────────────────────────────────────────────

def summarize_text(
    text: str,
    firm_id: str,
    context: str = "",
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """
    Summarizes a block of legal text using the routed LLM.
    
    Args:
        text: The raw text to summarize (case notes, document content, etc.)
        firm_id: The tenant ID for AI isolation and tracking.
        context: Optional additional context (e.g., "This is for the Acme merger").
        max_tokens: Max output tokens for the response.
        
    Returns:
        Dict containing the parsed summary JSON, or raw text if parsing fails.
    """
    if not text or len(text.strip()) < 10:
        return {"error": "Input text too short to summarize."}

    try:
        # 1. Build safe messages with prompt injection defense
        messages = build_safe_messages(
            system_prompt=DEFAULT_SUMMARY_SYSTEM_PROMPT,
            user_content=text,
            additional_context=context,
            firm_id=firm_id,
        )
        
        # Check if prompt_guard blocked the input
        guard_result = guard_prompt(text)
        if guard_result.blocked:
            logger.warning(f"Prompt guard blocked summarization for firm {firm_id}")
            return {"error": "Input blocked by security filter.", "threats": guard_result.threat_summary}

        # 2. Route to LLM via model_router (uses Haiku by default for summarization)
        response_text = call_llm(
            task_type=TaskType.SUMMARIZATION,
            messages=messages,
            firm_id=firm_id,
            max_tokens=max_tokens,
        )
        
        if not response_text:
            return {"error": "LLM returned an empty response."}

        # 3. Parse JSON response
        try:
            # Strip markdown code fences if present
            clean_response = response_text.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
                
            return json.loads(clean_response.strip())
        except json.JSONDecodeError:
            # Fallback to raw text if LLM didn't return valid JSON
            return {"raw_summary": response_text}

    except Exception as e:
        logger.error(f"Error during AI summarization for firm {firm_id}: {e}", exc_info=True)
        return {"error": f"Internal error during summarization: {str(e)}"}
