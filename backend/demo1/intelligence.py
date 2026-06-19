"""
intelligence.py  --  ParaIQ Case Intelligence Engine
=====================================================
Three proactive AI features:
  1. Contradiction Engine  -- auto-scan every time a new document is uploaded
  2. AI Case Brief         -- one-click 2-page structured legal memo via Claude
  3. Deadline Radar        -- surface upcoming dates across all open cases
"""

import json
import os
import re
import sqlite3
from datetime import datetime, date
from typing import Optional

import anthropic
from backend.demo1.observability.tracer import trace_claude_call
from backend.demo1.ab_testing.variants import assign_variant, build_brief_prompt, EXPERIMENT_ID
from backend.demo1.ab_testing.logger import log_experiment_result
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
DB_PATH = "analyses.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# TABLE INIT  (called automatically on import)
# ─────────────────────────────────────────────────────────────────────────────

def init_intelligence_db():
    conn = _get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS case_contradictions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id      INTEGER NOT NULL,
            doc_a_id     INTEGER NOT NULL,
            doc_b_id     INTEGER NOT NULL,
            doc_a_name   TEXT,
            doc_b_name   TEXT,
            severity     TEXT DEFAULT 'medium',
            c_type       TEXT,
            entity       TEXT,
            claim_a      TEXT,
            claim_b      TEXT,
            explanation  TEXT,
            reviewed     INTEGER DEFAULT 0,
            detected_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS case_briefs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id      INTEGER NOT NULL,
            brief_json   TEXT NOT NULL,
            generated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 1: CONTRADICTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def run_case_contradiction_scan(case_id: int, new_doc_id: int):
    """
    Runs in a background thread after every document upload.
    Compares the new document against all existing documents in the case.
    Writes detected contradictions to case_contradictions table.
    """
    try:
        conn = _get_db()
        new_doc = conn.execute(
            "SELECT id, document_name, doc_text FROM case_documents WHERE id=?",
            (new_doc_id,)
        ).fetchone()
        if not new_doc or not new_doc["doc_text"]:
            conn.close()
            return

        existing = conn.execute(
            """SELECT id, document_name, doc_text FROM case_documents
               WHERE case_id=? AND id!=? AND doc_text IS NOT NULL AND doc_text!=''""",
            (case_id, new_doc_id)
        ).fetchall()
        conn.close()

        if not existing:
            return

        doc_a = {
            "id":   new_doc["id"],
            "name": new_doc["document_name"],
            "text": new_doc["doc_text"],
        }
        for row in existing:
            doc_b = {
                "id":   row["id"],
                "name": row["document_name"],
                "text": row["doc_text"],
            }
            result = _detect_contradictions(doc_a, doc_b)
            if result.get("has_contradictions"):
                _save_contradictions(case_id, doc_a, doc_b,
                                     result.get("contradictions", []))
    except Exception as exc:
        print(f"[intelligence] Contradiction scan error: {exc}")


def _detect_contradictions(doc_a: dict, doc_b: dict) -> dict:
    prompt = (
        "You are a legal fact-checker. Compare these two case documents "
        "and identify factual contradictions.\n\n"
        "RESPOND ONLY WITH VALID JSON. No markdown, no backticks. "
        "Start with { and end with }.\n\n"
        'Document A -- "' + doc_a["name"] + '":\n'
        '"""' + doc_a["text"][:1200] + '"""\n\n'
        'Document B -- "' + doc_b["name"] + '":\n'
        '"""' + doc_b["text"][:1200] + '"""\n\n'
        "Return exactly this structure:\n"
        '{\n'
        '  "has_contradictions": true,\n'
        '  "contradictions": [\n'
        '    {\n'
        '      "type": "date|amount|fact|location|person|timeline",\n'
        '      "severity": "high|medium|low",\n'
        '      "entity": "what person/thing/event this is about",\n'
        '      "claim_a": "what Document A states",\n'
        '      "claim_b": "what Document B states",\n'
        '      "explanation": "plain-English explanation and legal significance"\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "Rules: max 3 contradictions. Only genuine factual conflicts, not "
        "differences in phrasing or perspective. "
        "If none exist, return has_contradictions: false and empty array."
    )
    try:
        msg, _tid = trace_claude_call(
            client=_client,
            name="contradiction_detection",
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
            tags=["paraiq", "haiku", "contradiction"]
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'^```\s*',     '', raw)
        raw = re.sub(r'\s*```$',     '', raw)
        return json.loads(raw)
    except Exception:
        return {"has_contradictions": False, "contradictions": []}


def _save_contradictions(case_id, doc_a, doc_b, items):
    if not items:
        return
    conn = _get_db()
    for item in items:
        conn.execute(
            """INSERT INTO case_contradictions
               (case_id, doc_a_id, doc_b_id, doc_a_name, doc_b_name,
                severity, c_type, entity, claim_a, claim_b, explanation)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                case_id,
                doc_a["id"], doc_b["id"],
                doc_a["name"], doc_b["name"],
                item.get("severity", "medium"),
                item.get("type", "fact"),
                item.get("entity", ""),
                item.get("claim_a", ""),
                item.get("claim_b", ""),
                item.get("explanation", ""),
            )
        )
    conn.commit()
    conn.close()


def get_case_contradictions(case_id: int) -> list:
    conn = _get_db()
    rows = conn.execute(
        """SELECT * FROM case_contradictions WHERE case_id=?
           ORDER BY severity DESC, detected_at DESC""",
        (case_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unreviewed_count(case_id: int) -> int:
    conn = _get_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM case_contradictions WHERE case_id=? AND reviewed=0",
        (case_id,)
    ).fetchone()[0]
    conn.close()
    return n


def mark_reviewed(contradiction_id: int):
    conn = _get_db()
    conn.execute("UPDATE case_contradictions SET reviewed=1 WHERE id=?",
                 (contradiction_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 2: AI CASE BRIEF
# ─────────────────────────────────────────────────────────────────────────────

def generate_case_brief(case_id: int) -> dict:
    """
    Aggregates all case data (documents, timeline, notes, risk scores)
    and generates a 2-page structured legal memo via Claude Sonnet.
    Saves the brief to case_briefs table and returns the dict.
    """
    conn = _get_db()
    case = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not case:
        conn.close()
        raise ValueError(f"Case {case_id} not found")

    docs = conn.execute(
        """SELECT document_name, doc_text, summary, risk_score,
                  events_json, entities_json
           FROM case_documents WHERE case_id=? ORDER BY upload_date ASC""",
        (case_id,)
    ).fetchall()

    notes = conn.execute(
        "SELECT note, author FROM case_notes WHERE case_id=? ORDER BY created_at ASC",
        (case_id,)
    ).fetchall()
    conn.close()

    doc_blocks, all_events, all_entities, risk_scores = [], [], [], []
    for d in docs:
        snippet = d["summary"] or (d["doc_text"] or "")[:400]
        doc_blocks.append(f"* {d['document_name']}: {snippet}")
        if d["risk_score"]:
            risk_scores.append(d["risk_score"])
        if d["events_json"]:
            try:
                all_events.extend(json.loads(d["events_json"])[:5])
            except Exception:
                pass
        if d["entities_json"]:
            try:
                all_entities.extend(
                    e.get("text", "") for e in json.loads(d["entities_json"])[:5]
                )
            except Exception:
                pass

    avg_risk     = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else "N/A"
    notes_text   = "\n".join(f"* [{n['author']}] {n['note']}" for n in notes) or "None."
    doc_context  = "\n".join(doc_blocks[:8])
    events_ctx   = json.dumps(all_events[:8], indent=2) if all_events else "None extracted yet."
    entities_str = ", ".join(set(filter(None, all_entities)))[:300] or "None identified."
    today_str    = datetime.now().strftime("%B %d, %Y")
    risk_json    = json.dumps(avg_risk)

    # A/B test: deterministic variant assignment per case_id
    variant = assign_variant(case_id, EXPERIMENT_ID)
    prompt  = build_brief_prompt(
        variant=variant,
        case=dict(case),
        doc_context=doc_context,
        events_ctx=events_ctx,
        notes_text=notes_text,
        entities_str=entities_str,
        avg_risk=risk_json,
        today_str=today_str,
    )

    import time as _time
    _t0 = _time.time()
    msg, _tid = trace_claude_call(
        client=_client,
        name=f"matter_intelligence_{variant.value}",
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        tags=["paraiq", "sonnet", "intelligence", variant.value]
    )
    _latency_ms = (_time.time() - _t0) * 1000
    log_experiment_result(
        experiment_id=EXPERIMENT_ID,
        case_id=case_id,
        variant=variant,
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
        latency_ms=_latency_ms,
        output_text=msg.content[0].text,
        trace_id=_tid,
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'^```\s*',     '', raw)
    raw = re.sub(r'\s*```$',     '', raw)
    brief = json.loads(raw)

    conn = _get_db()
    conn.execute("INSERT INTO case_briefs (case_id, brief_json) VALUES (?,?)",
                 (case_id, json.dumps(brief)))
    conn.commit()
    conn.close()
    return brief


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 3: DEADLINE RADAR
# ─────────────────────────────────────────────────────────────────────────────

_MONTHS = {
    "january": 1, "february": 2, "march": 3,     "april": 4,
    "may": 5,     "june": 6,     "july": 7,      "august": 8,
    "september": 9,"october": 10, "november": 11, "december": 12,
}

_DEADLINE_KW = [
    "deadline", "due date", "filing", "must be filed", "not later than",
    "on or before", "respond by", "discovery cutoff", "hearing", "trial",
    "motion due", "brief due", "expires", "statute of limitations",
    "deposition", "conference", "scheduling order", "answer due",
    "response due", "objection due", "reply due",
]

_DATE_RE = [
    re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b'),
    re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'),
    re.compile(
        r'\b(January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b',
        re.IGNORECASE
    ),
]


def _parse_date_match(m, idx: int):
    try:
        if idx == 0:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if idx == 1:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if idx == 2:
            mo = _MONTHS.get(m.group(1).lower(), 0)
            return date(int(m.group(3)), mo, int(m.group(2).rstrip(",")))
    except Exception:
        return None


def _scan_text_for_dates(text: str) -> list:
    results, today = [], date.today()
    for line in text.split("\n"):
        ll = line.lower()
        has_kw = any(kw in ll for kw in _DEADLINE_KW)
        for idx, pat in enumerate(_DATE_RE):
            for m in pat.finditer(line):
                d = _parse_date_match(m, idx)
                if d and d > today:
                    s = max(0, m.start() - 60)
                    e = min(len(line), m.end() + 60)
                    results.append({
                        "date":         d.isoformat(),
                        "date_display": d.strftime("%B %d, %Y"),
                        "context":      line[s:e].strip(),
                        "is_deadline":  has_kw,
                    })
    return results


def get_deadline_radar() -> dict:
    """Scan all open cases for upcoming dates extracted from documents."""
    try:
        conn = sqlite3.connect("/root/nlp-portfolio/analyses.db")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Get all open cases
        cur.execute("""
            SELECT id, case_number, client_name, description
            FROM cases WHERE status='open' AND deleted=0
        """)
        cases = cur.fetchall()

        deadlines = []
        today = date.today()

        for case in cases:
            case_id, case_number, client_name, matter = case[0], case[1], case[2], case[3]

            # Pull dates extracted from documents (stored in case_documents doc_text JSON or entities)
            cur.execute("""
                SELECT doc_text FROM case_documents
                WHERE case_id=? AND doc_text IS NOT NULL AND doc_text!=''
            """, (case_id,))
            docs = cur.fetchall()

            for (doc_text,) in docs:
                # Try to find ISO dates in doc text
                import re
                found = re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', doc_text)
                for ds in found:
                    try:
                        dl_date = datetime.strptime(ds, "%Y-%m-%d").date()
                        diff = (dl_date - today).days
                        if 0 <= diff <= 30:
                            deadlines.append({
                                "date": ds,
                                "case_number": case_number,
                                "case_title": client_name or matter or case_number,
                                "label": case_number,
                                "days_away": diff
                            })
                    except Exception:
                        pass

            # Also check filing_date + 30 days as a basic deadline
            cur.execute("SELECT filing_date FROM cases WHERE id=?", (case_id,))
            row = cur.fetchone()
            if row and row[0]:
                try:
                    fd = datetime.strptime(row[0][:10], "%Y-%m-%d").date()
                    # 30-day answer deadline (civil default)
                    answer_dl = date(fd.year, fd.month, fd.day)
                    from datetime import timedelta
                    answer_dl = fd + timedelta(days=30)
                    diff = (answer_dl - today).days
                    if 0 <= diff <= 30:
                        deadlines.append({
                            "date": answer_dl.isoformat(),
                            "case_number": case_number,
                            "case_title": client_name or case_number,
                            "label": case_number,
                            "days_away": diff,
                            "event": "30-day answer deadline"
                        })
                except Exception:
                    pass

        conn.close()

        # Deduplicate by date+case
        seen = set()
        unique = []
        for d in deadlines:
            k = (d["date"], d["case_number"])
            if k not in seen:
                seen.add(k)
                unique.append(d)

        unique.sort(key=lambda x: x["date"])
        return {"deadlines": unique, "count": len(unique)}

    except Exception as e:
        return {"deadlines": [], "count": 0, "error": str(e)}

    """
    Scans all open case documents for future dates within 30 days.
    Classifies by urgency: CRITICAL (<=7d), WARNING (<=14d), WATCH (<=30d).
    """
    conn  = _get_db()
    today = date.today()
    rows  = conn.execute(
        """SELECT c.id as case_id, c.case_number, c.client_name,
                  cd.document_name, cd.doc_text, cd.events_json
           FROM cases c
           JOIN case_documents cd ON cd.case_id = c.id
           WHERE c.deleted = 0
             AND c.status NOT IN ('closed', 'archived')
             AND (cd.doc_text IS NOT NULL OR cd.events_json IS NOT NULL)"""
    ).fetchall()
    conn.close()

    deadlines, seen = [], set()

    for row in rows:
        # Scan free text
        if row["doc_text"]:
            for df in _scan_text_for_dates(row["doc_text"]):
                key = (row["case_id"], df["date"])
                if key in seen:
                    continue
                seen.add(key)
                d    = date.fromisoformat(df["date"])
                days = (d - today).days
                if days < 0 or days > 30:
                    continue
                urgency = ("CRITICAL" if days <= 7 else
                           "WARNING"  if days <= 14 else "WATCH")
                deadlines.append({
                    "case_id":      row["case_id"],
                    "case_number":  row["case_number"],
                    "client_name":  row["client_name"],
                    "doc_name":     row["document_name"],
                    "date":         df["date"],
                    "date_display": df["date_display"],
                    "days_away":    days,
                    "urgency":      urgency,
                    "context":      df["context"],
                    "is_deadline":  df["is_deadline"],
                })

        # Scan structured events_json
        if row["events_json"]:
            try:
                for ev in json.loads(row["events_json"]):
                    ds = ev.get("date", "")
                    if not ds:
                        continue
                    d = None
                    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
                        try:
                            d = datetime.strptime(ds, fmt).date()
                            break
                        except Exception:
                            pass
                    if not d or d <= today:
                        continue
                    days = (d - today).days
                    if days > 30:
                        continue
                    key = (row["case_id"], d.isoformat())
                    if key in seen:
                        continue
                    seen.add(key)
                    urgency = ("CRITICAL" if days <= 7 else
                               "WARNING"  if days <= 14 else "WATCH")
                    deadlines.append({
                        "case_id":      row["case_id"],
                        "case_number":  row["case_number"],
                        "client_name":  row["client_name"],
                        "doc_name":     row["document_name"],
                        "date":         d.isoformat(),
                        "date_display": d.strftime("%B %d, %Y"),
                        "days_away":    days,
                        "urgency":      urgency,
                        "context":      ev.get("description", ev.get("event", "")),
                        "is_deadline":  True,
                    })
            except Exception:
                pass

    pri = {"CRITICAL": 0, "WARNING": 1, "WATCH": 2}
    deadlines.sort(key=lambda x: (pri.get(x["urgency"], 3), x["days_away"]))

    return {
        "total":     len(deadlines),
        "critical":  sum(1 for d in deadlines if d["urgency"] == "CRITICAL"),
        "warning":   sum(1 for d in deadlines if d["urgency"] == "WARNING"),
        "watch":     sum(1 for d in deadlines if d["urgency"] == "WATCH"),
        "deadlines": deadlines,
    }


# Auto-init DB tables on import
init_intelligence_db()
