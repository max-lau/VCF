"""
intelligence.py  --  ACP-VCF Case Intelligence Engine
=====================================================
Proactive AI features for claims processing:
  1. Contradiction Engine  -- auto-scan every time a new document is uploaded
  2. Deadline Radar        -- surface upcoming dates across all open cases
"""

import json
import logging
import os
import re
from backend.demo1.pg import get_conn as _pg_get_conn
from datetime import datetime, date
from typing import Optional

import anthropic
from backend.demo1.observability.tracer import trace_claude_call

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Claude client — lazily imported from main at call time to avoid circular import
_client = None

def _get_client():
    global _client
    if _client is None:
        from backend.demo1.main import client as _c
        _client = _c
    return _client


def _get_db(firm_id="default"):
    return _pg_get_conn(firm_id)


# ─────────────────────────────────────────────────────────────────────────────
# TABLE INIT  (called automatically on import)
# ─────────────────────────────────────────────────────────────────────────────

def init_intelligence_db():
    """No-op -- tables exist in Supabase Postgres."""
    pass


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
            "SELECT id, document_name, doc_text FROM case_documents WHERE id=%s",
            (new_doc_id,)
        ).fetchone()
        if not new_doc or not new_doc["doc_text"]:
            conn.close()
            return

        existing = conn.execute(
            """SELECT id, document_name, doc_text FROM case_documents
               WHERE case_id=%s AND id!=%s AND doc_text IS NOT NULL AND doc_text!=''""",
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
    except (KeyError, ValueError, TypeError, OSError) as exc:
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
            client=_get_client(),
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
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning(f"[intelligence] contradiction detection parse failed: {e}")
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
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
        """SELECT * FROM case_contradictions WHERE case_id=%s
           ORDER BY severity DESC, detected_at DESC""",
        (case_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unreviewed_count(case_id: int) -> int:
    conn = _get_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM case_contradictions WHERE case_id=%s AND reviewed=FALSE",
        (case_id,)
    ).fetchone()[0]
    conn.close()
    return n


def mark_reviewed(contradiction_id: int):
    conn = _get_db()
    conn.execute("UPDATE case_contradictions SET reviewed=1 WHERE id=%s",
                 (contradiction_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 2: DEADLINE RADAR
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
    except (ValueError, TypeError) as e:
        logger.debug(f"[intelligence] date match parse failed: {e}")
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
        with _pg_get_conn("default") as conn:  # noqa: intentional — deadline radar scans all firms' cases
            cases = conn.execute("""
                SELECT id, case_number, client_name, description
                FROM cases WHERE status='open' AND deleted=FALSE
            """).fetchall()

        deadlines = []
        today = date.today()

        for case in cases:
            case_id, case_number, client_name, matter = case[0], case[1], case[2], case[3]

            # Pull dates extracted from documents
            with _pg_get_conn("default") as conn2:  # noqa: intentional — deadline radar, cross-firm case scan
                docs = conn2.execute("""
                    SELECT doc_text FROM case_documents
                    WHERE case_id=%s AND doc_text IS NOT NULL AND doc_text!=''
                """, (case_id,)).fetchall()
                filing_row = conn2.execute(
                    "SELECT filing_date FROM cases WHERE id=%s", (case_id,)
                ).fetchone()

            for doc in docs:
                doc_text = doc["doc_text"] if hasattr(doc, "keys") else doc[0]
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
                    except (ValueError, TypeError) as e:
                        logger.debug(f"[intelligence] deadline radar date parse failed for '{ds}': {e}")

            # Also check filing_date + 30 days as a basic deadline
            row = filing_row
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
                except (ValueError, TypeError) as e:
                    logger.debug(f"[intelligence] filing_date answer deadline parse failed: {e}")

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

    except (KeyError, ValueError, TypeError, OSError) as e:
        return {"deadlines": [], "count": 0, "error": "Internal error occurred"}

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
                        except (ValueError, TypeError):
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
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.debug(f"[intelligence] events_json scan failed: {e}")

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
