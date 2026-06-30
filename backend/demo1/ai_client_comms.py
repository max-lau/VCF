"""
ai_client_comms.py
==================
ParaIQ AI Client Communication Drafting (Phase 2, #5)

Helps attorneys quickly draft professional emails, updates, or messages
to clients. Uses the strong model (Sonnet/Opus) for high-quality writing
and applies prompt guards to prevent sensitive data leakage in instructions.

Features:
  - Context-aware drafting based on matter details
  - Adjustable tone (formal, reassuring, urgent)
  - Prompt injection defense on user inputs
  - Multi-model routing (uses drafting task type)
"""

import logging
from typing import Dict, Any
from backend.demo1.prompt_guard import build_safe_messages, guard_prompt
from backend.demo1.model_router import call_llm, TaskType

logger = logging.getLogger(__name__)

def draft_communication(
    topic: str, 
    context: str, 
    tone: str, 
    firm_id: str,
    max_tokens: int = 1000
) -> Dict[str, Any]:
    """
    Drafts a client communication based on the provided topic and context.
    
    Args:
        topic: The main subject or instruction (e.g., "Update them on the court date delay").
        context: Background information or case details.
        tone: The desired tone (e.g., "formal", "reassuring", "urgent").
        firm_id: The tenant ID for AI isolation.
        max_tokens: Max output tokens.
        
    Returns:
        Dict containing the drafted message or an error.
    """
    if not topic:
        return {"error": "Topic is required to draft communication."}
        
    try:
        # 1. Check for prompt injection in the topic/context
        guard_result = guard_prompt(topic + " " + context)
        if guard_result.blocked:
            logger.warning(f"Prompt guard blocked comms drafting for firm {firm_id}")
            return {"error": "Input blocked by security filter.", "threats": guard_result.threat_summary}

        system_prompt = (
            "You are an expert legal communications assistant. Draft a professional "
            f"email to a client with a {tone} tone. Use the provided context to inform "
            "the details. Be concise, clear, and empathetic. Do not invent legal advice "
            "or facts not present in the context. Format it as a standard email."
        )
        
        # 2. Build safe messages
        user_content = f"Topic/Goal: {topic}\n\nContext/Case Details: {context}"
        messages = build_safe_messages(
            system_prompt=system_prompt,
            user_content=user_content,
            firm_id=firm_id,
        )
        
        # 3. Route to LLM (Drafting tasks use the strong model)
        response_text = call_llm(
            task_type=TaskType.DRAFTING,
            messages=messages,
            firm_id=firm_id,
            max_tokens=max_tokens,
        )
        
        if not response_text:
            return {"error": "LLM returned an empty response."}
            
        return {"draft": response_text.strip()}
        
    except Exception as e:
        logger.error(f"Error during AI comms drafting for firm {firm_id}: {e}", exc_info=True)
        return {"error": f"Internal error during drafting: {str(e)}"}
