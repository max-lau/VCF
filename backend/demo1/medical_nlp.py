"""
backend/demo1/medical_nlp.py
============================
Medical NLP assistant for VCF claims.
Analyzes medical text / questionnaires to surface WTC-related conditions
and possible additional illnesses that may increase claim value.
"""

import json
import logging
import os
import re
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.demo1.ai_client import get_client
from backend.demo1 import medical_bert

logger = logging.getLogger(__name__)
router = APIRouter()

LLM_FAST = os.getenv("LLM_FAST", "claude-haiku-4-5-20251001")

MEDICAL_SYSTEM_PROMPT = (
    "You are ACP-VCF Medical NLP, an expert clinical assistant helping WAW law firm "
    "process 9/11 Victim Compensation Fund claims. "
    "You review medical text and claimant questionnaires to identify diagnosed conditions, "
    "symptoms, and WTC-related illnesses that may be claimable. "
    "Always respond with valid JSON only — no markdown, no backticks, no preamble. "
    "Be rigorous, cite relevant facts from the provided text, and flag uncertainty explicitly."
)


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


class MedicalNlpInput(BaseModel):
    text: str
    case_id: int | None = None
    use_local_bert: bool = True


def _merge_conditions(claude_conditions: list, bert_conditions: list) -> list:
    """Merge Claude and BioClinicalBERT condition lists, deduplicating by name."""
    merged = {}
    for c in claude_conditions:
        name = c.get("name", "").lower().strip()
        if name:
            merged[name] = c
    for c in bert_conditions:
        name = c.get("name", "").lower().strip()
        if not name:
            continue
        if name in merged:
            # Boost relevance if both sources agree
            existing = merged[name]
            existing["relevance"] = round(max(existing.get("relevance", 0), c.get("relevance", 0)) + 0.05, 3)
            existing["relevance"] = min(existing["relevance"], 1.0)
            if "source" in existing and existing["source"] != c.get("source"):
                existing["source"] = "claude+bert"
        else:
            merged[name] = c
    return sorted(merged.values(), key=lambda x: x.get("relevance", 0), reverse=True)


@router.post("/medical-nlp/analyze")
def analyze_medical_text(body: MedicalNlpInput, request: Request):
    text = (body.text or "").strip()
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="Text too short (minimum 20 characters)")
    if len(text) > 4000:
        text = text[:4000]

    bert_conditions = []
    bert_available = False
    if body.use_local_bert:
        try:
            bert_conditions = medical_bert.extract_medical_conditions(text)
            bert_available = True
        except Exception as e:
            logger.warning(f"[MedicalNLP] Local BERT extraction failed: {e}")

    prompt = f"""Analyze the following medical text or questionnaire excerpt for a 9/11 VCF claim.

IMPORTANT: Your entire response must be ONLY a raw JSON object.
Do NOT use markdown. Do NOT use backticks. Do NOT add any explanation.
Start your response with {{ and end with }}.

Text:
{text}

Return exactly this structure:
{{
  "claim_relevance": 0.0,
  "conditions": [
    {{
      "name": "condition or illness name",
      "relevance": 0.0,
      "wtc_related": true|false,
      "certified": true|false,
      "actionable": true|false,
      "note": "one-sentence explanation with evidence from the text"
    }}
  ],
  "follow_up": [
    "concrete next step, e.g. Request pathology report for X",
    "Ask client about symptom onset date for Y"
  ],
  "source": "claude-medical-nlp"
}}

Rules:
- Only list conditions actually mentioned or strongly implied in the text.
- "wtc_related" should be true for illnesses recognized by the WTC Health Program / VCF.
- "certified" should be true if the text explicitly states the condition is certified by the WTC Health Program.
- "actionable" should be true if the condition is not yet claimed or needs documentation.
- Set claim_relevance to a score 0.0-1.0 reflecting how useful this text is for a VCF claim.
- Keep the response compact."""

    try:
        client = get_client()
        message = client.messages.create(
            model=LLM_FAST,
            max_tokens=1200,
            system=MEDICAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        cleaned = _clean_json(raw)
        parsed = json.loads(cleaned)

        # Normalize
        parsed.setdefault("claim_relevance", 0)
        parsed.setdefault("conditions", [])
        parsed.setdefault("follow_up", [])

        # Merge in local BERT conditions
        if bert_conditions:
            parsed["conditions"] = _merge_conditions(parsed["conditions"], bert_conditions)

        parsed["source"] = "claude+bert" if bert_available else "claude-medical-nlp"
        parsed["bert_available"] = bert_available
        return parsed
    except json.JSONDecodeError as e:
        logger.warning(f"[MedicalNLP] JSON parse error: {e}")
        # Fallback: return BERT-only results if Claude JSON parse fails
        if bert_conditions:
            return {
                "claim_relevance": 0.6,
                "conditions": bert_conditions,
                "follow_up": ["Review local BERT findings with an attorney."],
                "source": "bioclinicalbert-only",
                "bert_available": True,
            }
        raise HTTPException(status_code=500, detail="AI response could not be parsed. Please try again.")
    except Exception as e:
        logger.error(f"[MedicalNLP] Analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Medical NLP analysis failed. Please try again.")
