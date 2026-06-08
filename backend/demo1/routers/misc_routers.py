"""
misc_routers.py
===============
exports_router      — CSV / JSON bulk export of matter data
ai_config_router    — Per-firm AI model and feature settings
client_portal_router — Read-only token-gated client views
legal_bert_router   — Legal-BERT analysis endpoint
"""
import csv, io, json, secrets, os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from backend.demo1.pg import get_conn
from backend.demo1.auth import get_current_firm_id


# ─────────────────────────────────────────────
# EXPORTS ROUTER
# ─────────────────────────────────────────────
exports_router = APIRouter(prefix="/exports", tags=["exports"])

# Map table → FK column name (as stored in Postgres)
_TABLE_FK = {
    "case_documents":     "case_id",
    "correspondence":     "matter_id",
    "calendar_events":    "matter_id",
    "contacts":           "matter_id",
    "research_notes":     "matter_id",
    "case_contradictions": "case_id",
    "privilege_log":      "matter_id",
    "reports":            "matter_id",
}

# Public alias → actual table name
_TABLE_ALIAS = {
    "documents":           "case_documents",
    "case_documents":      "case_documents",
    "correspondence":      "correspondence",
    "calendar_events":     "calendar_events",
    "contacts":            "contacts",
    "research_notes":      "research_notes",
    "case_contradictions": "case_contradictions",
    "privilege_log":       "privilege_log",
    "reports":             "reports",
}


def _rows_to_csv(rows: list) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


@exports_router.get("/matter/{matter_id}/csv")
def export_matter_csv(
    matter_id: int,
    table:     str = "case_documents",
    firm_id:   str = Depends(get_current_firm_id),
):
    if table not in _TABLE_ALIAS:
        raise HTTPException(400, f"Table must be one of: {list(_TABLE_ALIAS)}")
    actual = _TABLE_ALIAS[table]
    fk     = _TABLE_FK[actual]
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            f"SELECT * FROM {actual} WHERE {fk} = %s", (matter_id,)
        ).fetchall()
    csv_data = _rows_to_csv([dict(r) for r in rows])
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=matter_{matter_id}_{actual}.csv"}
    )


@exports_router.get("/matter/{matter_id}/json")
def export_matter_json(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        case = conn.execute(
            "SELECT * FROM cases WHERE id = %s AND deleted = FALSE", (matter_id,)
        ).fetchone()
        if not case:
            raise HTTPException(404, "Matter not found")

        def fetch(table, fk):
            try:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE {fk} = %s", (matter_id,)
                ).fetchall()
                return [dict(r) for r in rows]
            except Exception:
                return []

        payload = {
            "exported_at":   datetime.now().isoformat(),
            "matter":        dict(case),
            "documents":     fetch("case_documents", "case_id"),
            "correspondence": fetch("correspondence", "matter_id"),
            "calendar_events": fetch("calendar_events", "matter_id"),
            "contacts":      fetch("contacts", "matter_id"),
            "research_notes": fetch("research_notes", "matter_id"),
            "contradictions": fetch("case_contradictions", "case_id"),
            "privilege_log": fetch("privilege_log", "matter_id"),
            "reports":       fetch("reports", "matter_id"),
        }

    return JSONResponse(
        content=json.loads(json.dumps(payload, default=str)),
        headers={"Content-Disposition": f"attachment; filename=matter_{matter_id}_full.json"}
    )


@exports_router.get("/matter/{matter_id}/summary")
def export_matter_summary(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    counts = {}
    with get_conn(firm_id) as conn:
        for table, fk in [
            ("case_documents", "case_id"),
            ("correspondence", "matter_id"),
            ("calendar_events", "matter_id"),
            ("contacts", "matter_id"),
            ("research_notes", "matter_id"),
            ("reports", "matter_id"),
        ]:
            try:
                row = conn.execute(
                    f"SELECT COUNT(*) AS c FROM {table} WHERE {fk} = %s", (matter_id,)
                ).fetchone()
                counts[table] = row["c"] if row else 0
            except Exception:
                counts[table] = 0
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
    pass  # No-op — table exists in Supabase


_init_ai_config_table()


class ConfigUpdate(BaseModel):
    settings: dict


@ai_config_router.get("/{firm_id_path}")
def get_ai_config(
    firm_id_path: str,
    firm_id:      str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT setting_key, setting_value FROM ai_config WHERE firm_id = %s",
            (firm_id,)
        ).fetchall()
    config = dict(DEFAULT_CONFIG)
    for r in rows:
        config[r["setting_key"]] = r["setting_value"]
    return config


@ai_config_router.put("/{firm_id_path}")
def update_ai_config(
    firm_id_path: str,
    body:         ConfigUpdate,
    firm_id:      str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        for key, value in body.settings.items():
            conn.execute("""
                INSERT INTO ai_config (firm_id, setting_key, setting_value, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (firm_id, setting_key)
                DO UPDATE SET setting_value = EXCLUDED.setting_value,
                              updated_at    = EXCLUDED.updated_at
            """, (firm_id, key, str(value), datetime.now().isoformat()))
    return get_ai_config(firm_id_path, firm_id)


@ai_config_router.post("/{firm_id_path}/reset")
def reset_ai_config(
    firm_id_path: str,
    firm_id:      str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute("DELETE FROM ai_config WHERE firm_id = %s", (firm_id,))
    return DEFAULT_CONFIG


# ─────────────────────────────────────────────
# CLIENT PORTAL ROUTER
# Note: client_portal_access uses a public token — RLS is disabled
# on this table so unauthenticated token lookups work.
# Run in Supabase SQL editor once:
#   ALTER TABLE client_portal_access DISABLE ROW LEVEL SECURITY;
# ─────────────────────────────────────────────
client_portal_router = APIRouter(prefix="/client-portal", tags=["client_portal"])


def _init_portal_table():
    pass  # No-op


_init_portal_table()


class PortalAccessCreate(BaseModel):
    matter_id:    int
    client_name:  str
    client_email: str
    permissions:  Optional[str] = "timeline,documents,correspondence"
    expires_days: Optional[int] = 30


@client_portal_router.post("/grant")
def grant_portal_access(
    body:    PortalAccessCreate,
    firm_id: str = Depends(get_current_firm_id),
):
    token   = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=body.expires_days)).isoformat()
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO client_portal_access
              (firm_id, matter_id, client_name, client_email,
               access_token, permissions, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, body.matter_id, body.client_name, body.client_email,
              token, body.permissions, expires))
        new_id = cur.fetchone()["id"]
        row    = conn.execute(
            "SELECT * FROM client_portal_access WHERE id = %s", (new_id,)
        ).fetchone()
    return {**dict(row), "portal_url": f"/client-portal/view/{token}"}


@client_portal_router.get("/view/{token}")
def view_portal(token: str):
    # Use "default" firm to do token lookup — RLS must be disabled on this table
    with get_conn("default") as conn:
        access = conn.execute(
            "SELECT * FROM client_portal_access WHERE access_token = %s AND is_active = TRUE",
            (token,)
        ).fetchone()
        if not access:
            raise HTTPException(403, "Invalid or expired portal link")
        a = dict(access)
        if a.get("expires_at") and str(a["expires_at"]) < datetime.now().isoformat():
            raise HTTPException(403, "Portal link has expired")
        conn.execute(
            "UPDATE client_portal_access SET last_accessed = %s WHERE id = %s",
            (datetime.now().isoformat(), a["id"])
        )

    matter_id  = a["matter_id"]
    portal_firm = a.get("firm_id", "default")
    perms       = set(a.get("permissions", "").split(","))
    payload     = {"access": a, "matter": {}}

    with get_conn(portal_firm) as conn:
        case = conn.execute(
            "SELECT id, client_name, case_number, status, created_at FROM cases WHERE id = %s",
            (matter_id,)
        ).fetchone()
        if case:
            payload["matter"] = dict(case)

        if "documents" in perms:
            rows = conn.execute(
                "SELECT id, document_name, source, upload_date FROM case_documents WHERE case_id = %s",
                (matter_id,)
            ).fetchall()
            payload["documents"] = [dict(r) for r in rows]

        if "correspondence" in perms:
            rows = conn.execute(
                "SELECT id, subject, date, direction, from_party, to_party FROM correspondence WHERE matter_id = %s",
                (matter_id,)
            ).fetchall()
            payload["correspondence"] = [dict(r) for r in rows]

        if "timeline" in perms:
            try:
                docs = conn.execute(
                    "SELECT events_json FROM case_documents WHERE case_id = %s",
                    (matter_id,)
                ).fetchall()
                all_events = []
                for d in docs:
                    ev_json = dict(d).get("events_json")
                    if ev_json:
                        try:
                            items = ev_json if isinstance(ev_json, list) else __import__('json').loads(ev_json)
                            all_events.extend(items[:5])
                        except: pass
                payload["timeline"] = all_events[:20]
            except:
                payload["timeline"] = []

    return payload


@client_portal_router.get("/matter/{matter_id}/accesses")
def list_portal_accesses(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT id, client_name, client_email, permissions,
                   expires_at, last_accessed, is_active, created_at, access_token
            FROM client_portal_access
            WHERE matter_id = %s ORDER BY created_at DESC
        """, (matter_id,)).fetchall()
    return [dict(r) for r in rows]


@client_portal_router.delete("/access/{access_id}")
def revoke_portal_access(
    access_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE client_portal_access SET is_active = FALSE WHERE id = %s",
            (access_id,)
        )
    return {"revoked": access_id}


# ─────────────────────────────────────────────
# LEGAL-BERT ROUTER
# ─────────────────────────────────────────────
legal_bert_router = APIRouter(prefix="/legal-bert", tags=["legal_bert"])

LEGAL_CATEGORIES = [
    "contract_dispute", "employment", "tort", "criminal", "IP",
    "real_estate", "family_law", "bankruptcy", "securities", "other"
]


def _init_bert_table():
    pass  # No-op


_init_bert_table()


class BertAnalysisRequest(BaseModel):
    text:          str
    analysis_type: Optional[str] = "classification"
    matter_id:     Optional[int] = None
    document_id:   Optional[int] = None


@legal_bert_router.post("/analyze")
def analyze_text(
    req:     BertAnalysisRequest,
    firm_id: str = Depends(get_current_firm_id),
):
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
        text_lower = req.text.lower()
        scores = {}
        keywords = {
            "employment":       ["wrongful termination","hostile workplace","discrimination","harassment","FMLA","ADA","Title VII"],
            "contract_dispute": ["breach","material term","consideration","damages","specific performance","indemnification"],
            "tort":             ["negligence","duty of care","damages","injury","causation","liability"],
            "IP":               ["trademark","patent","copyright","trade secret","infringement","license"],
            "real_estate":      ["easement","deed","zoning","title","foreclosure","lease"],
            "criminal":         ["felony","misdemeanor","indictment","probable cause","Miranda","bail"],
        }
        for cat, kws in keywords.items():
            scores[cat] = sum(1 for kw in kws if kw.lower() in text_lower)
        best       = max(scores, key=scores.get) if any(scores.values()) else "other"
        confidence = min(scores.get(best, 0) / 3.0, 1.0)
        result = {
            "label":      best,
            "confidence": round(confidence, 3),
            "all_scores": {k: round(v / 3.0, 3) for k, v in scores.items()},
        }

    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO legal_bert_analyses
              (firm_id, matter_id, document_id, text_snippet, analysis_type,
               result, confidence, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, req.matter_id, req.document_id, req.text[:500],
              req.analysis_type, json.dumps(result),
              result.get("confidence", 0), source))
        new_id = cur.fetchone()["id"]
        row    = conn.execute(
            "SELECT * FROM legal_bert_analyses WHERE id = %s", (new_id,)
        ).fetchone()

    return {**dict(row), "result": result, "source": source}


@legal_bert_router.get("/matter/{matter_id}/history")
def get_bert_history(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
):
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT * FROM legal_bert_analyses
            WHERE matter_id = %s ORDER BY created_at DESC LIMIT 50
        """, (matter_id,)).fetchall()
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
