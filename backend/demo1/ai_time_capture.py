"""
ai_time_capture.py
==================
ParaIQ AI Time Capture (Phase 2, #3)

Analyzes recent user activity from the audit trail and uses the LLM to 
suggest billable time entries. This mimics Smokeball/MyCase's passive 
time capture to recover lost billable hours.

Features:
  - Fetches recent activity logs for a specific user
  - Groups activities intelligently
  - Uses model_router (fast model) for cheap, fast time-entry generation
  - Outputs structured JSON ready for the billing module
"""

import logging
import json
from typing import Dict, Any, List
from backend.demo1.prompt_guard import build_safe_messages
from backend.demo1.model_router import call_llm, TaskType

logger = logging.getLogger(__name__)

DEFAULT_TIME_CAPTURE_PROMPT = (
    "You are a legal billing assistant. Analyze the provided user activity logs. "
    "Your task is to group related activities into logical billable time entries. "
    "For each group, write a professional, concise billing description. "
    "Estimate the time spent in minutes based on the activities. "
    "Do not hallucinate activities not present in the logs.\n\n"
    "Return your response as a JSON object with this structure:\n"
    "{\n"
    '  "suggested_entries": [\n'
    '    {\n'
    '      "description": "Drafted motion to dismiss and reviewed opposing counsel\'s brief",\n'
    '      "estimated_minutes": 45,\n'
    '      "activities_grouped": ["Created document: Motion to Dismiss", "Viewed: Opposing Brief.pdf"]\n'
    '    }\n'
    '  ]\n'
    "}"
)

def suggest_time_entries(activity_logs: List[Dict[str, Any]], firm_id: str) -> Dict[str, Any]:
    """
    Analyzes a list of activity logs and suggests time entries.
    
    Args:
        activity_logs: A list of dictionaries containing audit trail events.
        firm_id: The tenant ID for AI isolation and routing.
        
    Returns:
        Dict containing suggested time entries or an error message.
    """
    if not activity_logs:
        return {"error": "No recent activities found to analyze."}
        
    try:
        # Format the logs into a clean string for the LLM
        log_text = "\n".join([
            f"- [{log.get('created_at', 'N/A')}] {log.get('action', 'Unknown action')}: {log.get('details', '')}"
            for log in activity_logs
        ])
        
        messages = build_safe_messages(
            system_prompt=DEFAULT_TIME_CAPTURE_PROMPT,
            user_content="Here are the recent activities:\n" + log_text,
            firm_id=firm_id,
        )
        
        response_text = call_llm(
            task_type=TaskType.TIME_CAPTURE,
            messages=messages,
            firm_id=firm_id,
            max_tokens=800,
        )
        
        if not response_text:
            return {"error": "LLM returned an empty response."}
            
        # Parse JSON response
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
            return {"raw_suggestions": response_text}
            
    except Exception as e:
        logger.error(f"Error during AI time capture for firm {firm_id}: {e}", exc_info=True)
        return {"error": f"Internal error during time capture: {str(e)}"}
