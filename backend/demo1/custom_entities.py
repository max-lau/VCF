import os
import re
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id

router = APIRouter()

BUILTIN_ENTITIES = [
    {"type": "STATUTE", "label": "US Code Statute",
     "pattern": r'\b\d+\s+U\.?S\.?C\.?\s*[§§\s]*\d+[\w\-]*',
     "examples": ["18 U.S.C. § 1343", "18 USC 1341", "42 U.S.C. § 1983"], "builtin": True},
    {"type": "STATUTE", "label": "Federal Rules",
     "pattern": r'\bRule\s+\d+[\w\(\)\.]*\b',
     "examples": ["Rule 12(b)(6)", "Rule 56", "Rule 11"], "builtin": True},
    {"type": "COURT", "label": "Federal District Court",
     "pattern": r'\b(?:United States District Court|U\.S\. District Court)[^\n,]{0,60}',
     "examples": ["United States District Court for the Southern District of New York"], "builtin": True},
    {"type": "JUDGE", "label": "Federal Judge",
     "pattern": r'\b(?:Judge|Justice|Magistrate Judge|Chief Judge)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',
     "examples": ["Judge Rakoff", "Justice Sotomayor"], "builtin": True},
    {"type": "DOCKET", "label": "Case Docket Number",
     "pattern": r'\b\d{2}[\s\-](?:CR|CV|CIV|CRIM|MDL|MJ)[\s\.\-]*\d+(?:[\s\-]\w+)*',
     "examples": ["12 CR. 99 SHS", "21-CV-1234"], "builtin": True},
    {"type": "LEGAL_TERM", "label": "Legal Term of Art",
     "pattern": r'\b(?:habeas corpus|mens rea|actus reus|voir dire|in limine|prima facie|res judicata|stare decisis|pro se|amicus curiae|certiorari|mandamus|subpoena duces tecum|wire fraud|money laundering)\b',
     "examples": ["habeas corpus", "mens rea", "in limine"], "builtin": True},
]


def init_custom_entity_table():
    """No-op -- table exists in Supabase Postgres."""
    print("[CustomEntities] Table initialized OK")


def extract_custom_entities(text: str, types: list = None, firm_id: str = "default") -> list:
    with get_conn(firm_id) as conn:
        query  = "SELECT * FROM custom_entity_types WHERE active=TRUE"
        params = []
        if types:
            ph = ",".join(["%s"] * len(types))
            query += f" AND type IN ({ph})"
            params.extend(types)
        patterns = conn.execute(query, params).fetchall()

    found = []
    seen  = set()
    for p in patterns:
        try:
            for m in re.finditer(p["pattern"], text, re.IGNORECASE):
                raw = m.group(0).strip()
                key = (raw.lower(), p["type"])
                if key in seen:
                    continue
                seen.add(key)
                found.append({
                    "text":       raw,
                    "type":       p["type"],
                    "label":      p["label"],
                    "span":       [m.start(), m.end()],
                    "builtin":    bool(p["builtin"]),
                    "pattern_id": p["id"],
                })
        except re.error:
            continue
    found.sort(key=lambda x: x["span"][0])
    return found


class AddEntityType(BaseModel):
    type:     str
    label:    str
    pattern:  str
    examples: Optional[list] = []

class ExtractBody(BaseModel):
    text:  str
    types: Optional[list] = None


@router.post("/extract")
def extract_entities(body: ExtractBody, firm_id: str = Depends(get_current_firm_id)):
    if not body.text.strip():
        raise HTTPException(400, "Text is required")
    entities = extract_custom_entities(body.text, types=body.types, firm_id=firm_id)
    by_type  = {}
    for e in entities:
        by_type.setdefault(e["type"], []).append(e)
    return {"success": True, "total_found": len(entities),
            "by_type": by_type, "entities": entities,
            "text_preview": body.text[:200]}


@router.get("/types")
def list_types(firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM custom_entity_types WHERE active=TRUE ORDER BY builtin DESC, type ASC"
        ).fetchall()
    types = {}
    for r in rows:
        t = r["type"]
        if t not in types:
            types[t] = {"type": t, "patterns": [], "builtin": bool(r["builtin"])}
        types[t]["patterns"].append({
            "id": r["id"], "label": r["label"], "pattern": r["pattern"],
            "examples": json.loads(r["examples"] or "[]"), "builtin": bool(r["builtin"]),
        })
    return {"success": True, "type_count": len(types),
            "total_patterns": sum(len(v["patterns"]) for v in types.values()),
            "types": list(types.values())}


@router.post("/types")
def add_entity_type(body: AddEntityType, firm_id: str = Depends(get_current_firm_id)):
    try:
        re.compile(body.pattern)
    except re.error as e:
        raise HTTPException(400, f"Invalid regex pattern: {e}")
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO custom_entity_types
              (type, label, pattern, examples, builtin, active, created_at)
            VALUES (%s,%s,%s,%s,FALSE,TRUE,%s)
            RETURNING id
        """, (body.type.upper(), body.label, body.pattern,
              json.dumps(body.examples), datetime.now(timezone.utc).isoformat()))
        new_id = cur.fetchone()["id"]
    return {"success": True, "id": new_id, "type": body.type.upper(), "label": body.label}


@router.delete("/types/{pattern_id}")
def delete_entity_type(pattern_id: int, firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT builtin FROM custom_entity_types WHERE id=%s", (pattern_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Pattern {pattern_id} not found")
        if row["builtin"]:
            raise HTTPException(400, "Built-in patterns cannot be deleted")
        conn.execute(
            "UPDATE custom_entity_types SET active=FALSE WHERE id=%s", (pattern_id,)
        )
    return {"success": True, "message": f"Pattern {pattern_id} deactivated"}


@router.post("/types/test")
def test_pattern(body: AddEntityType):
    try:
        compiled = re.compile(body.pattern, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(400, f"Invalid regex: {e}")
    matches = []
    for example in body.examples:
        found = compiled.findall(example)
        matches.append({"input": example, "matches": found, "matched": len(found) > 0})
    return {"success": True, "pattern": body.pattern, "test_results": matches,
            "all_matched": all(m["matched"] for m in matches)}
