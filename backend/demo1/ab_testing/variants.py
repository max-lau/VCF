"""
A/B testing framework for ParaIQ prompt variants.
Deterministic hash-based assignment — same case_id always gets same variant.
"""
import hashlib
from enum import Enum
from typing import Dict

class PromptVariant(str, Enum):
    CONTROL   = "control"
    VARIANT_A = "variant_a"
    VARIANT_B = "variant_b"

EXPERIMENT_ID = "case_brief_prompt_v1"

def assign_variant(case_id: int, experiment_id: str = EXPERIMENT_ID) -> PromptVariant:
    """
    Deterministic assignment — same case always gets same variant.
    Uses MD5 hash of case_id + experiment_id for reproducibility.
    """
    hash_input = f"{case_id}:{experiment_id}".encode()
    hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
    variants   = list(PromptVariant)
    return variants[hash_value % len(variants)]

def build_brief_prompt(variant: PromptVariant, case: dict, doc_context: str,
                        events_ctx: str, notes_text: str, entities_str: str,
                        avg_risk, today_str: str) -> str:
    """Returns the prompt string for the given variant."""
    schema = (
        "RESPOND ONLY WITH VALID JSON. No markdown, no backticks.\n\n"
        "{\n"
        f"  \"case_number\": \"{case['case_number']}\",\n"
        f"  \"matter\": \"{case['client_name']}\",\n"
        f'  "generated_at": "{today_str}",\n'
        f'  "risk_score": {avg_risk},\n'
        '  "sections": {\n'
        '    "parties":      {"title": "I. PARTIES",                 "content": "2-3 sentences identifying all parties and their roles."},\n'
        '    "facts":        {"title": "II. STATEMENT OF FACTS",     "content": "4-6 sentences summarizing key facts."},\n'
        '    "legal_issues": {"title": "III. LEGAL ISSUES",          "content": "Numbered list of 2-4 primary legal issues."},\n'
        '    "key_evidence": {"title": "IV. KEY EVIDENCE",           "content": "3-5 items of significant evidence and relevance."},\n'
        '    "risk":         {"title": "V. RISK ASSESSMENT",         "content": "2-3 sentences on strengths, weaknesses, risk posture."},\n'
        '    "next_steps":   {"title": "VI. RECOMMENDED NEXT STEPS", "content": "3-5 numbered concrete action items for counsel."},\n'
        '    "deadlines":    {"title": "VII. CRITICAL DEADLINES",    "content": "Date-sensitive items or: No imminent deadlines identified."}\n'
        '  }\n'
        '}'
    )
    context = (
        f"CASE: {case['case_number']} | {case['client_name']}\n"
        f"Court: {case['court'] or 'Not specified'} | Judge: {case['judge'] or 'Not specified'}\n"
        f"Filing Date: {case['filing_date'] or 'Not specified'} | Status: {case['status']}\n"
        f"Aggregate Risk Score: {avg_risk}/10\n\n"
        f"DOCUMENTS IN FILE:\n{doc_context}\n\n"
        f"KEY EVENTS:\n{events_ctx}\n\n"
        f"COUNSEL NOTES:\n{notes_text}\n\n"
        f"KEY ENTITIES: {entities_str}\n\n"
    )
    if variant == PromptVariant.CONTROL:
        # Original prompt — baseline
        return (
            "You are a senior litigation paralegal at a U.S. law firm. "
            "Generate a complete, structured case brief based on the data below.\n\n"
            + context + schema
        )
    elif variant == PromptVariant.VARIANT_A:
        # Chain-of-thought framing before JSON output
        return (
            "You are a senior litigation paralegal with 15 years of U.S. federal court experience. "
            "Before generating the case brief, internally reason through: (1) the core legal theory, "
            "(2) the strongest evidence, (3) the biggest risk to the client. "
            "Then produce the structured brief as JSON.\n\n"
            + context + schema
        )
    elif variant == PromptVariant.VARIANT_B:
        # Minimal framing — let the schema do the work
        return (
            "Generate a structured legal case brief as JSON from the case data below. "
            "Be precise and cite specific facts from the documents provided.\n\n"
            + context + schema
        )
    raise ValueError(f"Unknown variant: {variant}")
