"""
document_annotations.py
========================
ParaIQ — Inline AI annotations for document viewing.

Returns document text with entity highlights, privilege flags, date/deadline
markers, and PII detection — all positioned inline so the frontend can render
them as overlays on the document text.

Endpoint:
  GET  /documents/{doc_id}/annotated  — Get document text + inline annotations
  POST /documents/{doc_id}/annotate   — Force re-annotation of a document
"""
import os
import re
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_user, get_current_firm_id

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Annotation Types ─────────────────────────────────────────────────────────

ANNOTATION_TYPES = {
    "person":       { "label": "Person",       "color": "#4a9eff", "icon": "👤" },
    "organization": { "label": "Organization", "color": "#b377ff", "icon": "🏢" },
    "date":         { "label": "Date",         "color": "#ffb74d", "icon": "📅" },
    "deadline":     { "label": "Deadline",     "color": "#ff7070", "icon": "⏰" },
    "money":        { "label": "Money",        "color": "#c9a84c", "icon": "💰" },
    "citation":     { "label": "Citation",     "color": "#ff7070", "icon": "⚖" },
    "jurisdiction": { "label": "Jurisdiction", "color": "#4caf79", "icon": "🏛" },
    "pii":          { "label": "PII",          "color": "#e03131", "icon": "🔒" },
    "privileged":   { "label": "Privileged",   "color": "#9f7aea", "icon": "🛡" },
    "obligation":   { "label": "Obligation",   "color": "#48bb78", "icon": "📝" },
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> Dict[str, Any]:
    return dict(row) if hasattr(row, "keys") else dict(row._mapping)


def _find_occurrences(text: str, pattern: str, ann_type: str, metadata: Dict = None) -> List[Dict]:
    """Find all occurrences of pattern in text and return annotation ranges."""
    annotations = []
    for match in re.finditer(re.escape(pattern), text, re.IGNORECASE):
        annotations.append({
            "start": match.start(),
            "end": match.end(),
            "text": match.group(),
            "type": ann_type,
            "metadata": metadata or {},
        })
    return annotations


def _extract_dates(text: str) -> List[Dict]:
    """Find date patterns in text."""
    annotations = []
    date_patterns = [
        # "January 15, 2025" or "Jan 15, 2025"
        (r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', "date"),
        # "01/15/2025" or "1/15/25"
        (r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', "date"),
        # "2025-01-15"
        (r'\b\d{4}-\d{2}-\d{2}\b', "date"),
        # "on or before [date]"
        (r'(?:on or before|no later than|by|before|deadline:?)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})', "deadline"),
    ]

    for pattern, ann_type in date_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group(1) if match.lastindex else match.group()
            start = match.start(1) if match.lastindex else match.start()
            end = match.end(1) if match.lastindex else match.end()
            annotations.append({
                "start": start,
                "end": end,
                "text": matched_text,
                "type": ann_type,
                "metadata": {"pattern": pattern[:30]},
            })

    return annotations


def _extract_money(text: str) -> List[Dict]:
    """Find monetary amounts."""
    annotations = []
    for match in re.finditer(r'\$[\d,]+(?:\.\d{2})?(?:\s?(?:million|billion|M|B))?', text):
        annotations.append({
            "start": match.start(),
            "end": match.end(),
            "text": match.group(),
            "type": "money",
            "metadata": {},
        })
    return annotations


def _extract_citations(text: str) -> List[Dict]:
    """Find legal citations."""
    annotations = []
    # Case citations: "123 F.3d 456" or "123 U.S. 456 (1995)"
    for match in re.finditer(r'\b\d+\s+(?:U\.S\.|F\.\d*d|F\.Supp\.\d*|S\.Ct\.|L\.Ed\.2d)\s+\d+\b', text):
        annotations.append({
            "start": match.start(),
            "end": match.end(),
            "text": match.group(),
            "type": "citation",
            "metadata": {"citation_type": "case_law"},
        })
    # Statute citations: "42 U.S.C. § 1983" or "18 U.S.C. § 1343"
    for match in re.finditer(r'\b\d+\s+U\.S\.C\.?\s*§?\s*\d+', text):
        annotations.append({
            "start": match.start(),
            "end": match.end(),
            "text": match.group(),
            "type": "citation",
            "metadata": {"citation_type": "statute"},
        })
    return annotations


def _detect_privilege_keywords(text: str) -> List[Dict]:
    """Find privilege-related keywords in context."""
    annotations = []
    keywords = [
        "attorney-client privilege",
        "privileged and confidential",
        "attorney work product",
        "without prejudice",
        "settlement negotiations",
        "confidential communication",
    ]
    for kw in keywords:
        for match in re.finditer(re.escape(kw), text, re.IGNORECASE):
            annotations.append({
                "start": match.start(),
                "end": match.end(),
                "text": match.group(),
                "type": "privileged",
                "metadata": {"keyword": kw},
            })
    return annotations


def _detect_pii(text: str) -> List[Dict]:
    """Detect obvious PII patterns."""
    annotations = []
    # SSN: XXX-XX-XXXX
    for match in re.finditer(r'\b\d{3}-\d{2}-\d{4}\b', text):
        annotations.append({
            "start": match.start(), "end": match.end(), "text": match.group(),
            "type": "pii", "metadata": {"pii_type": "ssn"}
        })
    # Email
    for match in re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text):
        annotations.append({
            "start": match.start(), "end": match.end(), "text": match.group(),
            "type": "pii", "metadata": {"pii_type": "email"}
        })
    # Phone: (XXX) XXX-XXXX or XXX-XXX-XXXX
    for match in re.finditer(r'\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', text):
        annotations.append({
            "start": match.start(), "end": match.end(), "text": match.group(),
            "type": "pii", "metadata": {"pii_type": "phone"}
        })
    # Credit card: XXXX XXXX XXXX XXXX
    for match in re.finditer(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', text):
        annotations.append({
            "start": match.start(), "end": match.end(), "text": match.group(),
            "type": "pii", "metadata": {"pii_type": "credit_card"}
        })
    return annotations


def _merge_annotations(annotations: List[Dict]) -> List[Dict]:
    """Merge overlapping annotations, preferring more specific types."""
    if not annotations:
        return []

    # Sort by start position
    annotations.sort(key=lambda a: (a["start"], -(a["end"] - a["start"])))

    # Priority: deadline > privileged > pii > citation > money > date > person > org
    priority = {"deadline": 8, "privileged": 7, "pii": 6, "citation": 5,
                "money": 4, "date": 3, "person": 2, "organization": 2, "obligation": 1, "jurisdiction": 1}

    merged = []
    occupied = []  # list of (start, end) ranges already claimed

    for ann in annotations:
        # Check if this range overlaps with an existing annotation
        overlaps = False
        for (s, e) in occupied:
            if ann["start"] < e and ann["end"] > s:
                # Check priority — higher priority can override
                existing_idx = next((i for i, m in enumerate(merged)
                                     if m["start"] == s and m["end"] == e), None)
                if existing_idx is not None:
                    existing = merged[existing_idx]
                    if priority.get(ann["type"], 0) > priority.get(existing["type"], 0):
                        # Replace existing with higher priority annotation
                        merged[existing_idx] = ann
                        occupied[existing_idx] = (ann["start"], ann["end"])
                overlaps = True
                break
        if not overlaps:
            merged.append(ann)
            occupied.append((ann["start"], ann["end"]))

    return sorted(merged, key=lambda a: a["start"])


def _annotate_text(text: str, llm_entities: Dict = None, privilege_info: Dict = None) -> Dict:
    """
    Run all annotation extractors on document text.
    Returns: { text, annotations: [{start, end, text, type, metadata}] }
    """
    if not text:
        return {"text": "", "annotations": []}

    annotations = []

    # 1. Regex-based annotations (fast, always available)
    annotations.extend(_extract_dates(text))
    annotations.extend(_extract_money(text))
    annotations.extend(_extract_citations(text))
    annotations.extend(_detect_privilege_keywords(text))
    annotations.extend(_detect_pii(text))

    # 2. LLM entity annotations (if available from /entities/legal)
    if llm_entities:
        # Parties
        for party in llm_entities.get("parties", []):
            name = party.get("name", "")
            if name and len(name) > 2:
                ann_type = "person" if party.get("role") not in ("Other",) else "person"
                annotations.extend(_find_occurrences(text, name, ann_type, {
                    "role": party.get("role", ""),
                    "organization": party.get("organization", ""),
                }))

        # Organizations from party data
        for party in llm_entities.get("parties", []):
            org = party.get("organization", "")
            if org and len(org) > 2:
                annotations.extend(_find_occurrences(text, org, "organization", {}))

        # Jurisdictions
        for jur in llm_entities.get("jurisdictions", []):
            name = jur.get("name", "")
            if name and len(name) > 2:
                annotations.extend(_find_occurrences(text, name, "jurisdiction", {
                    "type": jur.get("type", ""),
                }))

        # Obligations — highlight the party name in obligation text
        for obl in llm_entities.get("key_obligations", []):
            party = obl.get("party", "")
            if party and len(party) > 2:
                annotations.extend(_find_occurrences(text, party, "obligation", {
                    "obligation": obl.get("obligation", ""),
                    "deadline": obl.get("deadline", ""),
                }))

    # 3. Privilege info from discovery screening
    if privilege_info and privilege_info.get("privileged"):
        # Add a document-level privilege annotation at the start
        annotations.append({
            "start": 0,
            "end": min(50, len(text)),
            "text": text[:min(50, len(text))],
            "type": "privileged",
            "metadata": {
                "privilege_type": privilege_info.get("privilege_type", ""),
                "confidence": privilege_info.get("confidence", 0),
                "document_level": True,
            },
        })

    # Merge overlapping annotations
    merged = _merge_annotations(annotations)

    return {
        "text": text,
        "annotations": merged,
        "annotation_types": ANNOTATION_TYPES,
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/{doc_id}/annotated")
async def get_annotated_document(
    doc_id: int,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """
    Get document text with inline AI annotations.

    Combines:
    - Regex-based: dates, deadlines, money, citations, PII, privilege keywords
    - LLM entities (if previously extracted via /entities/legal)
    - Privilege screening results from discovery pipeline

    Returns document text + array of annotation spans with positions.
    """
    try:
        with get_conn(firm_id) as conn:
            # Get document from case_documents
            row = conn.execute(
                """
                SELECT id, case_id, document_name, source, doc_text,
                       risk_level, risk_score, created_at
                FROM case_documents
                WHERE id = %s AND firm_id = %s
                """,
                (doc_id, firm_id)
            ).fetchone()

            if not row:
                raise HTTPException(404, "Document not found")

            doc = _row_to_dict(row)
            doc_text = doc.get("doc_text") or ""

            if not doc_text.strip():
                return {
                    "doc_id": doc_id,
                    "document_name": doc.get("document_name", ""),
                    "case_id": doc.get("case_id"),
                    "text": "",
                    "annotations": [],
                    "annotation_types": ANNOTATION_TYPES,
                    "message": "No extractable text in this document. Run OCR first.",
                }

            # Check for privilege info in discovery_files
            privilege_info = None
            try:
                priv_row = conn.execute(
                    """
                    SELECT privilege_flag, privilege_type, privilege_confidence, requires_review
                    FROM discovery_files
                    WHERE original_name = %s AND firm_id = %s
                    LIMIT 1
                    """,
                    (doc.get("document_name"), firm_id)
                ).fetchone()
                if priv_row:
                    privilege_info = _row_to_dict(priv_row)
            except Exception:
                pass  # discovery_files table may not have this doc

            # Check for previously extracted entities (stored as work product)
            llm_entities = None
            try:
                from backend.demo1.case_management import get_work_product
                wp = get_work_product("/entities/legal", firm_id, doc.get("case_id"))
                if wp:
                    llm_entities = wp
            except Exception:
                pass  # work product may not exist yet

            result = _annotate_text(doc_text, llm_entities, privilege_info)

            return {
                "doc_id": doc_id,
                "document_name": doc.get("document_name", ""),
                "case_id": doc.get("case_id"),
                "source": doc.get("source", ""),
                "risk_level": doc.get("risk_level", ""),
                "risk_score": doc.get("risk_score"),
                "text": result["text"],
                "annotations": result["annotations"],
                "annotation_types": result["annotation_types"],
                "privilege": privilege_info,
                "stats": {
                    "total_annotations": len(result["annotations"]),
                    "by_type": _count_by_type(result["annotations"]),
                },
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DocAnnotations] Failed to annotate doc {doc_id}: {e}")
        raise HTTPException(500, f"Annotation failed: {e}")


@router.post("/{doc_id}/annotate")
async def re_annotate_document(
    doc_id: int,
    firm_id: str = Depends(get_current_firm_id),
    current_user: dict = Depends(get_current_user),
):
    """Force re-annotation of a document (re-runs LLM entity extraction + annotation)."""
    # This endpoint triggers the /entities/legal endpoint internally,
    # then re-runs the annotation pipeline.
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT doc_text FROM case_documents WHERE id = %s AND firm_id = %s",
                (doc_id, firm_id)
            ).fetchone()

            if not row:
                raise HTTPException(404, "Document not found")

            doc_text = row["doc_text"] or ""
            if not doc_text.strip():
                raise HTTPException(400, "No text to annotate. Run OCR first.")

        # Run LLM entity extraction
        llm_entities = None
        try:
            from backend.demo1.ai_client import get_client
            from backend.demo1.main import claude_with_retry, LLM_FAST, LEGAL_SYSTEM_PROMPT

            client = get_client()
            prompt = f"""You are a legal NLP specialist. Extract all legally significant entities from this document.

Return ONLY valid JSON, no markdown:
{{
  "parties": [{{"name": "full name", "role": "Plaintiff|Defendant|Counsel|Judge|Witness|Other", "organization": "firm or company if applicable"}}],
  "amounts": [{{"value": "$X,XXX", "context": "what the amount refers to", "type": "damages|settlement|fee|penalty|other"}}],
  "dates_and_deadlines": [{{"date": "YYYY-MM-DD or as written", "event": "what happens on this date", "is_deadline": true}}],
  "jurisdictions": [{{"name": "court or jurisdiction name", "type": "federal|state|arbitration|other"}}],
  "legal_citations": [{{"citation": "case or statute citation", "type": "case_law|statute|regulation|contract"}}],
  "key_obligations": [{{"party": "who must act", "obligation": "what they must do", "deadline": "by when if stated"}}]
}}

Document:
{doc_text[:5000]}"""

            msg = claude_with_retry(
                client.messages.create,
                model=LLM_FAST,
                max_tokens=2000,
                system=LEGAL_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                firm_id=firm_id,
            )
            raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
            llm_entities = json.loads(raw)
        except Exception as e:
            logger.warning(f"[DocAnnotations] LLM entity extraction failed, using regex only: {e}")

        result = _annotate_text(doc_text, llm_entities, None)

        return {
            "doc_id": doc_id,
            "text": result["text"],
            "annotations": result["annotations"],
            "annotation_types": result["annotation_types"],
            "llm_entities": llm_entities,
            "stats": {
                "total_annotations": len(result["annotations"]),
                "by_type": _count_by_type(result["annotations"]),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DocAnnotations] Re-annotation failed for doc {doc_id}: {e}")
        raise HTTPException(500, f"Re-annotation failed: {e}")


def _count_by_type(annotations: List[Dict]) -> Dict[str, int]:
    """Count annotations by type."""
    counts = {}
    for ann in annotations:
        t = ann["type"]
        counts[t] = counts.get(t, 0) + 1
    return counts
