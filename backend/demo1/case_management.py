"""
case_management.py
==================
FastAPI APIRouter: Legal Case Management System — Postgres version

Endpoints:
  POST   /cases/                        - create new case
  GET    /cases/stats                   - dashboard stats
  GET    /cases/search                  - full-text cross-case search
  GET    /cases/{case_id}               - case detail + docs + notes
  PUT    /cases/{case_id}/status        - update status
  DELETE /cases/{case_id}              - soft-delete
  POST   /cases/{case_id}/documents     - add document to case
  GET    /cases/{case_id}/documents     - list documents
  GET    /cases/{case_id}/timeline      - auto-generated timeline
  POST   /cases/{case_id}/notes         - add note
  GET    /cases/{case_id}/notes         - list notes
  POST   /cases/{case_id}/timeline/extract - AI timeline extraction
  GET    /cases/{case_id}/contradictions - list contradictions
  PATCH  /cases/{case_id}/contradictions/{c_id}/review - mark reviewed
  POST   /cases/{case_id}/brief         - generate AI brief
"""

import json
import re
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import Depends, APIRouter, HTTPException, Query
from backend.demo1.auth import get_current_firm_id, get_current_user
from backend.demo1.pg import get_conn
from backend.demo1.intelligence import (
    run_case_contradiction_scan, get_case_contradictions,
    mark_reviewed, generate_case_brief,
)
from pydantic import BaseModel

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════

class CreateCaseBody(BaseModel):
    case_number:   str
    client_name:   str
    matter_number: Optional[str] = ""
    status:        Optional[str] = "open"
    court:         Optional[str] = ""
    judge:         Optional[str] = ""
    filing_date:   Optional[str] = ""
    description:   Optional[str] = ""
    tags:          Optional[List[str]] = []

class UpdateStatusBody(BaseModel):
    status: str
    author: Optional[str] = "System"

class AddDocumentBody(BaseModel):
    document_name:  str
    doc_text:       Optional[str] = ""
    sentiment:      Optional[str] = None
    risk_score:     Optional[float] = None
    events_json:    Optional[list] = None
    entities_json:  Optional[list] = None
    summary:        Optional[str] = ""
    language:       Optional[str] = "en"
    source:         Optional[str] = "uploaded"
    pacer_doc_id:   Optional[str] = ""
    pacer_seq_no:   Optional[str] = ""

class AddNoteBody(BaseModel):
    note:   str
    author: Optional[str] = "Counsel"
    pinned: Optional[int] = 0


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE INIT
# ══════════════════════════════════════════════════════════════════════════════

def init_case_db():
    """No-op — tables exist in Supabase Postgres."""
    print("[CaseDB] Tables initialized ✓")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def row_to_dict(row):
    return dict(row) if row else None

def ts_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def compute_case_risk(docs: list) -> str:
    scores = [d["risk_score"] for d in docs if d.get("risk_score") is not None]
    if not scores: return "unknown"
    avg = sum(scores) / len(scores)
    if avg >= 7: return "high"
    if avg >= 4: return "medium"
    return "low"

def extract_dates_from_text(text: str) -> list:
    patterns = [
        r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}\b",
    ]
    found, seen, unique = [], set(), []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            s = max(0, m.start()-60); e = min(len(text), m.end()+60)
            found.append({"date": m.group(),
                          "context": text[s:e].replace("\n"," ").strip(),
                          "pos": m.start()})
    for item in sorted(found, key=lambda x: x["pos"]):
        if item["date"] not in seen:
            seen.add(item["date"]); unique.append(item)
    return unique

def safe_json_dumps(val):
    """Serialize list/dict to JSON string for JSONB insert; pass None through."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return val


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/")
async def create_case(
    body: CreateCaseBody,
    firm_id: str = Depends(get_current_firm_id),
):
    try:
        with get_conn(firm_id) as conn:
            cur = conn.execute("""
                INSERT INTO cases
                  (firm_id, case_number, client_name, matter_number, status,
                   court, judge, filing_date, description)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (firm_id, body.case_number.strip(), body.client_name.strip(),
                  body.matter_number, body.status, body.court,
                  body.judge, body.filing_date or None, body.description))
            case_id = cur.fetchone()["id"]

            for tag in body.tags:
                conn.execute(
                    "INSERT INTO case_tags (firm_id, case_id, tag) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (firm_id, case_id, tag.lower().strip()))
            conn.execute(
                "INSERT INTO case_notes (firm_id, case_id, note) VALUES (%s,%s,%s)",
                (firm_id, case_id,
                 f"Case created: {body.case_number} for {body.client_name}"))

        return {"success": True, "case_id": case_id,
                "case_number": body.case_number}
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(409, "Case number already exists")
        raise HTTPException(500, str(e))


@router.get("/stats")
async def case_stats(firm_id: str = Depends(get_current_firm_id)):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM cases WHERE deleted = FALSE AND firm_id=%s GROUP BY status",
            (firm_id,)
        ).fetchall()
        by_status = {r["status"]: r["cnt"] for r in rows}
        rows = conn.execute(
            "SELECT risk_level, COUNT(*) AS cnt FROM cases WHERE deleted = FALSE AND firm_id=%s GROUP BY risk_level",
            (firm_id,)
        ).fetchall()
        by_risk = {r["risk_level"]: r["cnt"] for r in rows}
        total_docs = conn.execute(
            "SELECT COUNT(*) AS n FROM case_documents WHERE firm_id=%s",
            (firm_id,)
        ).fetchone()["n"]
        rows = conn.execute(
            "SELECT source, COUNT(*) AS cnt FROM case_documents WHERE firm_id=%s GROUP BY source",
            (firm_id,)
        ).fetchall()
        docs_by_source = {r["source"]: r["cnt"] for r in rows}

        rows = conn.execute("""
            SELECT c.case_number, c.client_name,
                   COUNT(cd.id) AS doc_count
            FROM cases c
            LEFT JOIN case_documents cd ON cd.case_id = c.id
            WHERE c.deleted = FALSE AND c.firm_id = %s
            GROUP BY c.id, c.case_number, c.client_name
            ORDER BY doc_count DESC LIMIT 5
        """, (firm_id,)).fetchall()
        most_active = [row_to_dict(r) for r in rows]

    total = sum(by_status.values())
    active = by_status.get("open", 0)
    return {
        "by_status":         by_status,
        "total_cases":       total,
        "total":             total,
        "active":            active,
        "by_risk":           by_risk,
        "total_documents":   total_docs,
        "docs_by_source":    docs_by_source,
        "most_active_cases": most_active,
    }


@router.get("/search")
async def search_cases(
    q:            Optional[str] = Query(None),
    firm_id:      str           = Depends(get_current_firm_id),
    current_user: dict          = Depends(get_current_user),
    status:       Optional[str] = Query(None),
    case_id:      Optional[int] = Query(None),
    limit:        int           = Query(50, le=100),
):
    with get_conn(firm_id) as conn:
        # No query — list all cases
        if not q or not q.strip():
            sql = """
                SELECT c.id, c.case_number, c.client_name, c.matter_number,
                       c.court, c.filing_date, c.status, c.risk_level, c.created_at,
                       COUNT(cd.id) AS doc_count
                FROM cases c
                LEFT JOIN case_documents cd ON cd.case_id = c.id
                WHERE c.deleted = FALSE AND c.firm_id = %s
            """
            params = [firm_id]
            if status:
                sql += " AND c.status = %s"
                params.append(status)
            sql += " GROUP BY c.id ORDER BY c.created_at DESC LIMIT %s"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            results = [row_to_dict(r) for r in rows]
            return {"query": "", "cases": results,
                    "results": results, "count": len(results)}

        # Full-text search via tsvector GIN index
        try:
            sql = """
                SELECT cd.case_id,
                       cd.document_name,
                       ts_headline('english', COALESCE(cd.doc_text,''),
                           plainto_tsquery('english', %s),
                           'MaxFragments=1, MaxWords=20') AS snippet,
                       c.case_number, c.client_name, c.status,
                       c.matter_number, c.court, c.filing_date,
                       c.risk_level, c.id, c.created_at
                FROM case_documents cd
                JOIN cases c ON c.id = cd.case_id
                WHERE cd.doc_tsv @@ plainto_tsquery('english', %s)
                  AND c.deleted = FALSE
            """
            params = [q.strip(), q.strip()]
            if case_id:
                sql += " AND cd.case_id = %s"
                params.append(case_id)
            if status:
                sql += " AND c.status = %s"
                params.append(status)
            sql += (
                " ORDER BY ts_rank(cd.doc_tsv, plainto_tsquery('english', %s)) DESC"
                " LIMIT %s"
            )
            params += [q.strip(), limit]
            rows = conn.execute(sql, params).fetchall()
        except Exception:
            # Fallback to ILIKE search
            rows = conn.execute("""
                SELECT id, case_number, client_name, matter_number, court,
                       filing_date, status, risk_level, created_at
                FROM cases
                WHERE deleted = FALSE
                  AND (case_number ILIKE %s OR client_name ILIKE %s
                       OR matter_number ILIKE %s)
                ORDER BY created_at DESC LIMIT %s
            """, (f"%{q}%", f"%{q}%", f"%{q}%", limit)).fetchall()

    results = [row_to_dict(r) for r in rows]
    return {"query": q, "cases": results,
            "results": results, "count": len(results)}


@router.get("/{case_id}")
async def get_case(
    case_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        case = row_to_dict(conn.execute(
            "SELECT * FROM cases WHERE id = %s AND deleted = FALSE",
            (case_id,)).fetchone())
        if not case:
            raise HTTPException(404, "Case not found")

        docs = [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM case_documents WHERE case_id = %s ORDER BY upload_date DESC",
            (case_id,)).fetchall()]

        notes = [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM case_notes WHERE case_id = %s ORDER BY pinned DESC, created_at DESC",
            (case_id,)).fetchall()]

        tags = [r["tag"] for r in conn.execute(
            "SELECT tag FROM case_tags WHERE case_id = %s", (case_id,)).fetchall()]

    # JSONB columns already parsed — convert any stray strings just in case
    for d in docs:
        for f in ["events_json", "entities_json"]:
            if isinstance(d.get(f), str):
                try: d[f] = json.loads(d[f])
                except: pass

    case.update({"documents": docs, "notes": notes,
                 "tags": tags, "doc_count": len(docs)})
    return case


@router.put("/{case_id}/status")
async def update_status(
    case_id: int,
    body:    UpdateStatusBody,
    firm_id: str = Depends(get_current_firm_id),
):
    if body.status not in ("open", "pending", "closed", "archived"):
        raise HTTPException(400, "Invalid status")
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE cases SET status = %s, updated_at = %s WHERE id = %s",
            (body.status, ts_now(), case_id))
        conn.execute(
            "INSERT INTO case_notes (firm_id, case_id, author, note) VALUES (%s,%s,%s,%s)",
            (firm_id, case_id, body.author, f"Status changed to: {body.status}"))
    return {"success": True, "case_id": case_id, "status": body.status}


@router.delete("/{case_id}")
async def delete_case(
    case_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE cases SET deleted = TRUE, updated_at = %s WHERE id = %s",
            (ts_now(), case_id))
    return {"success": True, "message": "Case soft-deleted"}


@router.post("/{case_id}/documents")
async def add_document(
    case_id: int,
    body:    AddDocumentBody,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        if not conn.execute(
            "SELECT id FROM cases WHERE id = %s AND deleted = FALSE",
            (case_id,)).fetchone():
            raise HTTPException(404, "Case not found")

        cur = conn.execute("""
            INSERT INTO case_documents
              (firm_id, case_id, document_name, source, doc_text, sentiment,
               risk_score, events_json, entities_json, summary, language,
               pacer_doc_id, pacer_seq_no)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            firm_id, case_id, body.document_name, body.source, body.doc_text,
            body.sentiment, body.risk_score,
            safe_json_dumps(body.events_json),
            safe_json_dumps(body.entities_json),
            body.summary, body.language, body.pacer_doc_id, body.pacer_seq_no,
        ))
        new_doc_id = cur.fetchone()["id"]

        docs     = conn.execute(
            "SELECT risk_score FROM case_documents WHERE case_id = %s",
            (case_id,)).fetchall()
        new_risk = compute_case_risk([row_to_dict(d) for d in docs])
        conn.execute(
            "UPDATE cases SET risk_level = %s, updated_at = %s WHERE id = %s",
            (new_risk, ts_now(), case_id))

    # Fire contradiction scan in background — non-blocking
    if body.doc_text:
        import threading as _th
        _th.Thread(
            target=run_case_contradiction_scan,
            args=(case_id, new_doc_id),
            daemon=True
        ).start()

    return {"success": True, "case_id": case_id,
            "document_id": new_doc_id,
            "document_name": body.document_name, "new_risk_level": new_risk}


@router.get("/{case_id}/documents")
async def list_documents(
    case_id: int,
    source:  Optional[str] = Query(None),
    firm_id: str           = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        sql    = "SELECT * FROM case_documents WHERE case_id = %s"
        params = [case_id]
        if source:
            sql += " AND source = %s"
            params.append(source)
        rows = conn.execute(sql + " ORDER BY upload_date DESC", params).fetchall()

    docs = [row_to_dict(r) for r in rows]
    for d in docs:
        for f in ["events_json", "entities_json"]:
            if isinstance(d.get(f), str):
                try: d[f] = json.loads(d[f])
                except: pass
    return {"case_id": case_id, "documents": docs, "count": len(docs)}


@router.get("/{case_id}/timeline")
async def case_timeline(
    case_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        docs = [row_to_dict(r) for r in conn.execute(
            "SELECT document_name, doc_text, events_json FROM case_documents WHERE case_id = %s",
            (case_id,)).fetchall()]

    all_events = []
    for doc in docs:
        ev_json = doc.get("events_json")
        if ev_json:
            items = ev_json if isinstance(ev_json, list) else []
            try:
                if isinstance(ev_json, str):
                    items = json.loads(ev_json)
            except: pass
            for ev in items:
                ev["source_doc"] = doc["document_name"]
                ev["source"]     = "nlp_extractor"
                all_events.append(ev)
        if doc.get("doc_text"):
            for rd in extract_dates_from_text(doc["doc_text"]):
                all_events.append({**rd, "source_doc": doc["document_name"],
                                   "source": "regex_scan"})

    def sort_key(ev):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%B %d %Y"):
            try: return datetime.strptime((ev.get("date","")).strip(), fmt)
            except: pass
        return datetime.min

    all_events.sort(key=sort_key)
    return {"case_id": case_id, "event_count": len(all_events),
            "timeline": all_events}


@router.post("/{case_id}/notes")
async def add_note(
    case_id: int,
    body:    AddNoteBody,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "INSERT INTO case_notes (firm_id, case_id, author, note, pinned) VALUES (%s,%s,%s,%s,%s)",
            (firm_id, case_id, body.author, body.note, bool(body.pinned)))
    return {"success": True}


@router.get("/{case_id}/notes")
async def list_notes(
    case_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM case_notes WHERE case_id = %s ORDER BY pinned DESC, created_at DESC",
            (case_id,)).fetchall()
    return {"case_id": case_id, "notes": [row_to_dict(r) for r in rows]}


# Auto-init on import
init_case_db()


# ── AI Timeline Extraction ────────────────────────────────────────────────────

@router.post("/{case_id}/timeline/extract")
async def extract_timeline_ai(
    case_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    """Call Claude to extract timeline events from all linked case documents."""
    with get_conn(firm_id) as conn:
        docs = [row_to_dict(r) for r in conn.execute(
            "SELECT id, document_name, doc_text FROM case_documents WHERE case_id = %s AND doc_text IS NOT NULL",
            (case_id,)).fetchall()]

    texts = []
    for doc in docs:
        text = (doc.get("doc_text") or "").strip()
        if len(text) > 4 and not text.startswith("Intake route:"):
            texts.append("[Document: " + doc["document_name"] + "]\n" + text)

    if not texts:
        return {"case_id": case_id, "event_count": 0, "timeline": [],
                "message": "No text content found — transcribe or analyze documents first"}

    combined = "\n\n".join(texts)[:8000]

    import anthropic as _ant, os as _os, json as _json, re as _re
    _client = _ant.Anthropic(api_key=_os.getenv("ANTHROPIC_API_KEY"))

    prompt = (
        "Extract a chronological timeline from these legal case documents.\n"
        "Return ONLY valid JSON, no markdown, no backticks:\n"
        '{"events": [{"date": "date as written", "date_normalized": "YYYY-MM-DD",'
        '"event": "description", "parties": ["people"], "significance": "high|medium|low",'
        '"source_doc": "document name"}]}\n\n'
        "Documents:\n" + combined
    )

    try:
        msg = _ant.Anthropic(api_key=_os.getenv("ANTHROPIC_API_KEY")).messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw    = msg.content[0].text.strip()
        raw    = _re.sub(r'^```json\s*', '', raw)
        raw    = _re.sub(r'\s*```$', '', raw)
        parsed = _json.loads(raw)
        events = parsed.get("events", [])

        # Persist events back to case_documents
        with get_conn(firm_id) as conn:
            for ev in events:
                src_doc = ev.get("source_doc", "")
                if src_doc:
                    existing = conn.execute(
                        "SELECT id, events_json FROM case_documents WHERE case_id = %s AND document_name = %s",
                        (case_id, src_doc)).fetchone()
                    if existing:
                        prev = existing["events_json"] or []
                        if isinstance(prev, str):
                            try: prev = _json.loads(prev)
                            except: prev = []
                        prev.append(ev)
                        conn.execute(
                            "UPDATE case_documents SET events_json = %s WHERE id = %s",
                            (_json.dumps(prev), existing["id"]))

        # Auto-score risk
        try:
            from backend.demo1.risk_scorer import score_text as _score_txt
            _risk  = _score_txt(combined[:3000])
            _level = _risk.get("level", "unknown")
            _score = _risk.get("score", 0)
            with get_conn(firm_id) as conn:
                conn.execute(
                    "UPDATE cases SET risk_level = %s WHERE id = %s",
                    (_level, case_id))
        except Exception:
            _level = "unknown"
            _score = 0

        return {"case_id": case_id, "event_count": len(events),
                "timeline": events, "docs_scanned": len(texts),
                "risk_level": _level, "risk_score": round(_score, 1)}
    except Exception as e:
        raise HTTPException(500, "AI extraction failed: " + str(e))


# ══════════════════════════════════════════════════════════════════════════════
# INTELLIGENCE ENGINE ENDPOINTS
# Note: get_case_contradictions / mark_reviewed / generate_case_brief
# are in intelligence.py which still uses SQLite — migrate separately.
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{case_id}/contradictions")
async def list_contradictions(case_id: int):
    items = get_case_contradictions(case_id)
    return {
        "case_id":        case_id,
        "count":          len(items),
        "unreviewed":     sum(1 for i in items if not i["reviewed"]),
        "contradictions": items,
    }


@router.patch("/{case_id}/contradictions/{c_id}/review")
async def review_contradiction(case_id: int, c_id: int):
    mark_reviewed(c_id)
    return {"success": True}


@router.post("/{case_id}/brief")
async def case_brief(case_id: int):
    try:
        brief = generate_case_brief(case_id)
        return {"success": True, "case_id": case_id, "brief": brief}
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail=f"Brief generation failed: {str(exc)}")

# ── Case Binder ───────────────────────────────────────────────────────────────
@router.get("/{case_id}/binder")
async def case_binder(
    case_id: int,
    firm_id: str = Depends(get_current_firm_id),
):
    """Return all materials linked to a case in a unified chronological feed."""
    with get_conn(firm_id) as conn:
        # 1. Uploaded documents + email-linked records
        docs = conn.execute("""
            SELECT
                cd.id,
                cd.document_name,
                cd.source,
                cd.source_type,
                cd.source_ref,
                cd.summary,
                cd.risk_score,
                cd.sentiment,
                cd.entities_json,
                cd.upload_date,
                cd.source_url,
                ei.from_address,
                ei.priority          AS email_priority,
                ei.extracted_entities AS email_entities,
                ei.deadline_dates    AS email_deadlines,
                el.stage4_final_score AS email_score
            FROM case_documents cd
            LEFT JOIN email_intakes ei
                ON ei.id::text = cd.source_ref
                AND cd.source_type = 'email'
            LEFT JOIN email_processing_log el
                ON el.intake_id = ei.id
                AND cd.source_type = 'email'
            WHERE cd.case_id = %s
            ORDER BY cd.upload_date DESC
        """, (case_id,)).fetchall()

        # 2. AI drafts
        drafts = conn.execute("""
            SELECT id, doc_type, doc_label, created_at, created_by
            FROM ai_drafts
            WHERE case_id = %s
            ORDER BY created_at DESC
        """, (case_id,)).fetchall()

        # 3. Research notes
        notes = conn.execute("""
            SELECT id, title, summary, created_at
            FROM research_notes
            WHERE matter_id = %s
            ORDER BY created_at DESC
        """, (case_id,)).fetchall()

    # Build unified feed
    items = []

    for d in docs:
        row = dict(d)
        items.append({
            "binder_type": row.get("source_type") or "upload",
            "id":          row["id"],
            "title":       row["document_name"],
            "source":      row.get("from_address") or row.get("source") or "upload",
            "date":        row["upload_date"].isoformat() if row.get("upload_date") else None,
            "risk_score":  row.get("risk_score"),
            "sentiment":   row.get("sentiment"),
            "summary":     row.get("summary"),
            "email_priority": row.get("email_priority"),
            "email_score": row.get("email_score"),
            "entities":    row.get("email_entities") or row.get("entities_json"),
            "deadlines":   row.get("email_deadlines"),
            "source_ref":  row.get("source_ref"),
            "source_url":  row.get("source_url"),
        })

    for d in drafts:
        row = dict(d)
        items.append({
            "binder_type": "ai_draft",
            "id":          row["id"],
            "title":       row.get("doc_label") or row.get("doc_type", "AI Draft"),
            "source":      row.get("created_by") or "AI",
            "date":        row["created_at"].isoformat() if row.get("created_at") else None,
            "risk_score":  None,
            "sentiment":   None,
            "summary":     None,
            "email_priority": None,
            "email_score": None,
            "entities":    None,
            "deadlines":   None,
            "source_ref":  None,
        })

    for n in notes:
        row = dict(n)
        items.append({
            "binder_type": "research",
            "id":          row["id"],
            "title":       f"Research: {row.get('title', '')[:80]}",
            "source":      "CourtListener",
            "date":        row["created_at"].isoformat() if row.get("created_at") else None,
            "risk_score":  None,
            "sentiment":   None,
            "summary":     row.get("summary"),
            "email_priority": None,
            "email_score": None,
            "entities":    None,
            "deadlines":   None,
            "source_ref":  None,
        })

    # Sort all items newest first
    items.sort(key=lambda x: x["date"] or "", reverse=True)

    return {"case_id": case_id, "total": len(items), "items": items}
