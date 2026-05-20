"""
exports_router.py  — CSV / JSON bulk export of matter data
ai_config_router.py — Per-firm AI model and feature settings
client_portal_router.py — Read-only token-gated client views
legal_bert_router.py — Legal-BERT analysis endpoint (enclave or local fallback)
"""
import sqlite3, os, csv, io, json, secrets, hashlib
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel


DB_PATH = os.environ.get("DB_PATH", "/root/nlp-portfolio/analyses.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────
# EXPORTS ROUTER
# ─────────────────────────────────────────────
exports_router = APIRouter(prefix="/exports", tags=["exports"])

def _rows_to_csv(rows: list) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()

@exports_router.get("/matter/{matter_id}/csv")
def export_matter_csv(matter_id: int, table: str = "documents"):
    ALLOWED = {"documents", "correspondence", "calendar_events", "contacts",
               "research_notes", "case_contradictions", "privilege_log", "reports"}
    if table not in ALLOWED:
        raise HTTPException(400, f"Table must be one of: {ALLOWED}")
    col_map = {
        "documents":          "case_id",
        "correspondence":     "matter_id",
        "calendar_events":    "matter_id",
        "contacts":           "matter_id",
        "research_notes":     "matter_id",
        "case_contradictions":"case_id",
        "privilege_log":      "matter_id",
        "reports":            "matter_id",
    }
    fk = col_map.get(table, "matter_id")
    conn = get_db()
    rows = conn.execute(f"SELECT * FROM {table} WHERE {fk} = ?", (matter_id,)).fetchall()
    conn.close()
    csv_data = _rows_to_csv([dict(r) for r in rows])
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=matter_{matter_id}_{table}.csv"}
    )

@exports_router.get("/matter/{matter_id}/json")
def export_matter_json(matter_id: int):
    conn = get_db()
    case = conn.execute("SELECT * FROM cases WHERE id = ?", (matter_id,)).fetchone()
    if not case:
        raise HTTPException(404, "Matter not found")

    def fetch(table, fk):
        try:
            rows = conn.execute(f"SELECT * FROM {table} WHERE {fk} = ?", (matter_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    payload = {
        "exported_at": datetime.now().isoformat(),
        "matter": dict(case),
        "documents":       fetch("documents", "case_id"),
        "correspondence":  fetch("correspondence", "matter_id"),
        "calendar_events": fetch("calendar_events", "matter_id"),
        "contacts":        fetch("contacts", "matter_id"),
        "research_notes":  fetch("research_notes", "matter_id"),
        "contradictions":  fetch("case_contradictions", "case_id"),
        "privilege_log":   fetch("privilege_log", "matter_id"),
        "reports":         fetch("reports", "matter_id"),
    }
    conn.close()
    return JSONResponse(content=payload, headers={
        "Content-Disposition": f"attachment; filename=matter_{matter_id}_full.json"
    })

@exports_router.get("/matter/{matter_id}/summary")
def export_matter_summary(matter_id: int):
    """Returns table-row counts for quick export preview."""
    conn = get_db()
    counts = {}
    for table, fk in [("documents","case_id"), ("correspondence","matter_id"),
                       ("calendar_events","matter_id"), ("contacts","matter_id"),
                       ("research_notes","matter_id"), ("reports","matter_id")]:
        try:
            row = conn.execute(f"SELECT COUNT(*) as c FROM {table} WHERE {fk}=?", (matter_id,)).fetchone()
            counts[table] = row["c"] if row else 0
        except Exception:
            counts[table] = 0
    conn.close()
    return counts


# ─────────────────────────────────────────────
# AI CONFIG ROUTER
# ─────────────────────────────────────────────
ai_config_router = APIRouter(prefix="/ai-config", tags=["ai_config"])

DEFAULT_CONFIG = {
    "ai_model":             "claude-opus-4-5",
    "brief_model":          "claude-opus-4-5",
    "contradiction_model":  "claude-opus-4-5",
    "timeline_model":       "claude-opus-4-5",
    "enable_legal_bert":    "true",
    "enable_auto_brief":    "true",
    "enable_contradictions":"true",
    "enable_deadline_radar":"true",
    "privilege_threshold":  "0.7",
    "max_tokens":           "4000",
    "temperature":          "0.3",
    "enclave_enabled":      "false",
    "enclave_url":          "",
}

def _init_ai_config_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firm_id INTEGER NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(firm_id, setting_key)
        )
    """)
    conn.commit()
    conn.close()

_init_ai_config_table()

class ConfigUpdate(BaseModel):
    settings: dict  # {key: value}

@ai_config_router.get("/{firm_id}")
def get_ai_config(firm_id: int):
    conn = get_db()
    rows = conn.execute("SELECT setting_key, setting_value FROM ai_config WHERE firm_id = ?",
                        (firm_id,)).fetchall()
    conn.close()
    config = dict(DEFAULT_CONFIG)
    for r in rows:
        config[r["setting_key"]] = r["setting_value"]
    return config

@ai_config_router.put("/{firm_id}")
def update_ai_config(firm_id: int, body: ConfigUpdate):
    conn = get_db()
    for key, value in body.settings.items():
        conn.execute("""
            INSERT INTO ai_config (firm_id, setting_key, setting_value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(firm_id, setting_key) DO UPDATE SET setting_value=excluded.setting_value, updated_at=excluded.updated_at
        """, (firm_id, key, str(value), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return get_ai_config(firm_id)

@ai_config_router.post("/{firm_id}/reset")
def reset_ai_config(firm_id: int):
    conn = get_db()
    conn.execute("DELETE FROM ai_config WHERE firm_id = ?", (firm_id,))
    conn.commit()
    conn.close()
    return DEFAULT_CONFIG


# ─────────────────────────────────────────────
# CLIENT PORTAL ROUTER
# ─────────────────────────────────────────────
client_portal_router = APIRouter(prefix="/client-portal", tags=["client_portal"])

def _init_portal_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_portal_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER NOT NULL,
            firm_id INTEGER,
            client_name TEXT,
            client_email TEXT,
            access_token TEXT UNIQUE NOT NULL,
            permissions TEXT DEFAULT 'timeline,documents,correspondence',
            expires_at TEXT,
            last_accessed TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

_init_portal_table()

class PortalAccessCreate(BaseModel):
    matter_id: int
    firm_id: Optional[int] = None
    client_name: str
    client_email: str
    permissions: Optional[str] = "timeline,documents,correspondence"
    expires_days: Optional[int] = 30

@client_portal_router.post("/grant")
def grant_portal_access(body: PortalAccessCreate):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=body.expires_days)).isoformat()
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO client_portal_access (matter_id, firm_id, client_name, client_email,
            access_token, permissions, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (body.matter_id, body.firm_id, body.client_name, body.client_email,
          token, body.permissions, expires))
    conn.commit()
    row = conn.execute("SELECT * FROM client_portal_access WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return {**dict(row), "portal_url": f"/client-portal/view/{token}"}

@client_portal_router.get("/view/{token}")
def view_portal(token: str):
    conn = get_db()
    access = conn.execute(
        "SELECT * FROM client_portal_access WHERE access_token = ? AND is_active = 1",
        (token,)
    ).fetchone()
    if not access:
        raise HTTPException(403, "Invalid or expired portal link")
    a = dict(access)
    if a.get("expires_at") and a["expires_at"] < datetime.now().isoformat():
        conn.close()
        raise HTTPException(403, "Portal link has expired")
    # Update last accessed
    conn.execute("UPDATE client_portal_access SET last_accessed = ? WHERE id = ?",
                 (datetime.now().isoformat(), a["id"]))
    conn.commit()

    matter_id = a["matter_id"]
    perms = set(a.get("permissions", "").split(","))
    payload = {"access": a, "matter": {}}

    case = conn.execute("SELECT id, case_name, case_number, status, created_at FROM cases WHERE id = ?",
                        (matter_id,)).fetchone()
    if case:
        payload["matter"] = dict(case)

    if "timeline" in perms:
        rows = conn.execute("SELECT * FROM timeline_events WHERE case_id = ? ORDER BY event_date ASC",
                            (matter_id,)).fetchall()
        payload["timeline"] = [dict(r) for r in rows]

    if "documents" in perms:
        rows = conn.execute("SELECT id, filename, doc_type, created_at FROM documents WHERE case_id = ?",
                            (matter_id,)).fetchall()
        payload["documents"] = [dict(r) for r in rows]

    if "correspondence" in perms:
        rows = conn.execute("SELECT id, subject, date, direction, from_party, to_party FROM correspondence WHERE matter_id = ?",
                            (matter_id,)).fetchall()
        payload["correspondence"] = [dict(r) for r in rows]

    conn.close()
    return payload

@client_portal_router.get("/matter/{matter_id}/accesses")
def list_portal_accesses(matter_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, client_name, client_email, permissions, expires_at, last_accessed, is_active, created_at "
        "FROM client_portal_access WHERE matter_id = ? ORDER BY created_at DESC",
        (matter_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@client_portal_router.delete("/access/{access_id}")
def revoke_portal_access(access_id: int):
    conn = get_db()
    conn.execute("UPDATE client_portal_access SET is_active = 0 WHERE id = ?", (access_id,))
    conn.commit()
    conn.close()
    return {"revoked": access_id}


# ─────────────────────────────────────────────
# LEGAL-BERT ROUTER
# ─────────────────────────────────────────────
legal_bert_router = APIRouter(prefix="/legal-bert", tags=["legal_bert"])

def _init_bert_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS legal_bert_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id INTEGER,
            document_id INTEGER,
            text_snippet TEXT,
            analysis_type TEXT DEFAULT 'classification',
            result TEXT,
            confidence REAL,
            labels TEXT,
            source TEXT DEFAULT 'local',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

_init_bert_table()

class BertAnalysisRequest(BaseModel):
    text: str
    analysis_type: Optional[str] = "classification"
    matter_id: Optional[int] = None
    document_id: Optional[int] = None

LEGAL_CATEGORIES = [
    "contract_dispute", "employment", "tort", "criminal", "IP",
    "real_estate", "family_law", "bankruptcy", "securities", "other"
]

@legal_bert_router.post("/analyze")
def analyze_text(req: BertAnalysisRequest):
    """
    Attempts to call the enclave Legal-BERT endpoint if configured;
    falls back to keyword-based heuristic classification.
    """
    enclave_url = os.environ.get("ENCLAVE_LEGAL_BERT_URL", "")
    result = None
    source = "heuristic"

    if enclave_url:
        try:
            import httpx
            resp = httpx.post(
                f"{enclave_url}/analyze",
                json={"text": req.text, "type": req.analysis_type},
                timeout=10.0
            )
            if resp.status_code == 200:
                result = resp.json()
                source = "legal_bert_enclave"
        except Exception:
            pass

    if result is None:
        # Heuristic keyword fallback
        text_lower = req.text.lower()
        scores = {}
        keywords = {
            "employment":      ["wrongful termination","hostile workplace","discrimination","harassment","FMLA","ADA","Title VII"],
            "contract_dispute":["breach","material term","consideration","damages","specific performance","indemnification"],
            "tort":            ["negligence","duty of care","damages","injury","causation","liability"],
            "IP":              ["trademark","patent","copyright","trade secret","infringement","license"],
            "real_estate":     ["easement","deed","zoning","title","foreclosure","lease"],
            "criminal":        ["felony","misdemeanor","indictment","probable cause","Miranda","bail"],
        }
        for cat, kws in keywords.items():
            scores[cat] = sum(1 for kw in kws if kw.lower() in text_lower)
        best = max(scores, key=scores.get) if any(scores.values()) else "other"
        confidence = min(scores.get(best, 0) / 3.0, 1.0)
        result = {
            "label": best,
            "confidence": round(confidence, 3),
            "all_scores": {k: round(v/3.0, 3) for k, v in scores.items()}
        }

    # Persist
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO legal_bert_analyses (matter_id, document_id, text_snippet, analysis_type, result, confidence, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (req.matter_id, req.document_id, req.text[:500],
          req.analysis_type, json.dumps(result),
          result.get("confidence", 0), source))
    conn.commit()
    row = conn.execute("SELECT * FROM legal_bert_analyses WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return {**dict(row), "result": result, "source": source}

@legal_bert_router.get("/matter/{matter_id}/history")
def get_bert_history(matter_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM legal_bert_analyses WHERE matter_id = ? ORDER BY created_at DESC LIMIT 50",
        (matter_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@legal_bert_router.get("/status")
def bert_status():
    enclave_url = os.environ.get("ENCLAVE_LEGAL_BERT_URL", "")
    if enclave_url:
        try:
            import httpx
            resp = httpx.get(f"{enclave_url}/health", timeout=5.0)
            if resp.status_code == 200:
                return {"mode": "enclave", "url": enclave_url, "status": "online"}
        except Exception:
            pass
    return {"mode": "heuristic", "status": "online",
            "note": "Set ENCLAVE_LEGAL_BERT_URL env var to enable Legal-BERT enclave"}
