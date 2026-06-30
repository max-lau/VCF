"""
ai_agents.py
============
ParaIQ Firm-Wide AI Agents (Phase 3, #7)

Executes complex, multi-step legal work autonomously across matters.
This mimics Filevine's LOIS by having an "Agent" take an objective and
generate actionable work products (strategies, task lists, risk plans).

Features:
  - Autonomous task execution
  - Structured action plan generation
  - Deep reasoning using the strong model
  - Output validation applied to all agent responses
"""

import logging
import json
from typing import Dict, Any
from backend.demo1.prompt_guard import build_safe_messages, guard_prompt
from backend.demo1.model_router import call_llm, TaskType
from backend.demo1.ai_output_validation import validate_output

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = (
    "You are an expert legal AI Agent. Your job is to execute complex legal tasks autonomously. "
    "Analyze the provided objective and case context, then generate a comprehensive action plan. "
    "Do not just summarize—create actionable, specific tasks and strategic recommendations.\n\n"
    "Return your response as a JSON object with this structure:\n"
    "{\n"
    '  "executive_strategy": "High-level strategic approach",\n'
    '  "immediate_tasks": [\n'
    '    {\n'
    '      "task": "Specific action to take",\n'
    '      "priority": "High|Medium|Low",\n'
    '      "assignee_role": "Paralegal|Associate|Partner"\n'
    '    }\n'
    '  ],\n'
    '  "discovery_plan": ["Specific discovery requests or targets"],\n'
    '  "risk_mitigation": ["Strategies to mitigate identified risks"]\n'
    "}"
)

def execute_agent_task(
    objective: str, 
    context: str, 
    firm_id: str, 
    max_tokens: int = 2500
) -> Dict[str, Any]:
    """
    Executes a complex task using the AI Agent.
    
    Args:
        objective: What the agent needs to accomplish (e.g., "Develop an early case assessment strategy").
        context: The case facts and background data.
        firm_id: The tenant ID.
        max_tokens: Max output tokens.
        
    Returns:
        Dict containing the agent's executed work product.
    """
    if not objective:
        return {"error": "Agent objective is required."}
        
    try:
        # 1. Prompt injection defense
        guard_result = guard_prompt(objective + " " + context)
        if guard_result.blocked:
            logger.warning(f"Prompt guard blocked agent task for firm {firm_id}")
            return {"error": "Input blocked by security filter.", "threats": guard_result.threat_summary}

        # 2. Build safe messages
        user_content = f"Agent Objective: {objective}\n\nCase Context: {context}"
        messages = build_safe_messages(
            system_prompt=AGENT_SYSTEM_PROMPT,
            user_content=user_content,
            firm_id=firm_id,
        )
        
        # 3. Route to LLM (Agents use the strong model)
        response_text = call_llm(
            task_type=TaskType.ANALYSIS,
            messages=messages,
            firm_id=firm_id,
            max_tokens=max_tokens,
        )
        
        if not response_text:
            return {"error": "Agent returned an empty response."}
            
        # 4. Validate output (Check for PII leakage, harmful content)
        sanitized_response, validation_report = validate_output(
            response_text=response_text,
            firm_id=firm_id,
            expect_json=True
        )
        
        if not validation_report["passed"] and validation_report.get("json_valid") is False:
             return {"raw_agent_output": sanitized_response, "validation_report": validation_report}
             
        try:
            return json.loads(sanitized_response.strip())
        except json.JSONDecodeError:
            return {"raw_agent_output": sanitized_response}
            
    except Exception as e:
        logger.error(f"Error during AI agent execution for firm {firm_id}: {e}", exc_info=True)
        return {"error": f"Internal error during agent execution: {str(e)}"}
