"""
ai_output_validation.py
=======================
ParaIQ AI Output Validation & Sanitization (Phase 3, #10)

Validates LLM responses *before* returning them to the user. This prevents
PII leakage, ensures formatting compliance, and blocks harmful content.

Features:
  - PII Detection (Emails, Phone Numbers, SSNs)
  - JSON Schema validation (if expected output is JSON)
  - Harmful content pattern matching
  - Audit logging to ai_output_validation_log table
"""

import re
import logging
import json
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── PII & Sensitive Patterns ──────────────────────────────────────────────────

PII_PATTERNS = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone": re.compile(r'\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
    "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
}

HARMFUL_PATTERNS = {
    "sql_injection": re.compile(r'(?:DROP TABLE|INSERT INTO|UPDATE .* SET|DELETE FROM)', re.IGNORECASE),
    "script_injection": re.compile(r'(?:<script.*?>|javascript:)', re.IGNORECASE),
}

def validate_output(
    response_text: str, 
    firm_id: str, 
    expect_json: bool = False
) -> Tuple[str, Dict[str, Any]]:
    """
    Validates and sanitizes an LLM response.
    
    Args:
        response_text: The raw text returned by the LLM.
        firm_id: The tenant ID for logging.
        expect_json: If True, validates that the response is parseable JSON.
        
    Returns:
        Tuple of (sanitized_response, validation_report)
    """
    report = {
        "passed": True,
        "pii_detected": [],
        "harmful_content_detected": [],
        "json_valid": None,
        "sanitized": False
    }
    
    sanitized_text = response_text

    # 1. Check for PII
    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(response_text)
        if matches:
            report["pii_detected"].append({"type": pii_type, "count": len(matches)})
            report["passed"] = False
            # Redact PII
            sanitized_text = pattern.sub(f"[REDACTED_{pii_type.upper()}]", sanitized_text)
            report["sanitized"] = True

    # 2. Check for harmful content
    for harm_type, pattern in HARMFUL_PATTERNS.items():
        if pattern.search(response_text):
            report["harmful_content_detected"].append(harm_type)
            report["passed"] = False

    # 3. Check JSON validity if expected
    if expect_json:
        try:
            # Strip code fences if present before parsing
            clean = sanitized_text.strip()
            if clean.startswith("```json"): clean = clean[7:]
            if clean.startswith("```"): clean = clean[3:]
            if clean.endswith("```"): clean = clean[:-3]
            json.loads(clean.strip())
            report["json_valid"] = True
        except json.JSONDecodeError:
            report["json_valid"] = False
            report["passed"] = False

    # Log the validation event (fire and forget)
    try:
        from backend.demo1.pg import get_conn
        with get_conn(firm_id) as conn:
            conn.execute(
                """INSERT INTO ai_output_validation_log 
                   (firm_id, passed, pii_detected, harmful_detected, json_valid, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    firm_id, 
                    report["passed"], 
                    json.dumps(report["pii_detected"]),
                    json.dumps(report["harmful_content_detected"]),
                    report["json_valid"],
                    datetime.now(timezone.utc)
                )
            )
    except Exception as e:
        logger.warning(f"Could not log output validation event: {e}")

    return sanitized_text, report

def init_validation_tables():
    """Creates the output validation log table if it doesn't exist."""
    try:
        from backend.demo1.pg import get_conn
        # Need superuser/admin connection to create table across all tenants
        # In a real RLS setup, this might be in a central schema. Assuming 'public' for demo.
        import os
        from dotenv import load_dotenv
        load_dotenv("/root/nlp-portfolio/.env")
        import psycopg2
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS public.ai_output_validation_log (
                id BIGSERIAL PRIMARY KEY,
                firm_id TEXT NOT NULL,
                passed BOOLEAN NOT NULL,
                pii_detected JSONB,
                harmful_detected JSONB,
                json_valid BOOLEAN,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE public.ai_output_validation_log ENABLE ROW LEVEL SECURITY;
        """)
        cursor.close()
        conn.close()
        print("[AI Output Validation] Table initialized [OK]")
    except Exception as e:
        print(f"Error initializing output validation table: {e}")

