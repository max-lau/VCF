"""
db_enclaves.py
Add to the ParaIQ cloud database.py (or import standalone).

Two new tables:
  client_enclaves     — registry of client_id → enclave URL + key
  privilege_verdicts  — cloud-side verdict log (NO document content, counts only)
"""

import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional

CLOUD_DB = os.getenv("ANALYSES_DB_PATH", "/root/nlp-portfolio/analyses.db")

def _now():
    return datetime.now(timezone.utc).isoformat()


def _conn():
    c = sqlite3.connect(CLOUD_DB)
    c.row_factory = sqlite3.Row
    return c


def init_enclave_tables():
    """Call this once from the cloud app's startup (alongside init_db())."""
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS client_enclaves (
                client_id    TEXT PRIMARY KEY,
                enclave_url  TEXT NOT NULL,
                api_key      TEXT NOT NULL,
                firm_name    TEXT,
                active       INTEGER DEFAULT 1,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS privilege_verdicts (
                id               TEXT PRIMARY KEY,
                client_id        TEXT NOT NULL,
                doc_id           TEXT NOT NULL,
                privileged       INTEGER NOT NULL,
                privilege_type   TEXT NOT NULL,
                confidence       REAL NOT NULL,
                requires_review  INTEGER NOT NULL,
                enclave_log_id   TEXT,
                created_at       TEXT NOT NULL,
                FOREIGN KEY(client_id) REFERENCES client_enclaves(client_id)
            );

            CREATE INDEX IF NOT EXISTS idx_pv_client  ON privilege_verdicts(client_id);
            CREATE INDEX IF NOT EXISTS idx_pv_doc     ON privilege_verdicts(doc_id);
            CREATE INDEX IF NOT EXISTS idx_pv_flagged ON privilege_verdicts(privileged);
        """)


# ── Enclave registry ──────────────────────────────────────────────────────────

def register_client_enclave(
    client_id: str,
    enclave_url: str,
    api_key: str,
    firm_name: str = "",
):
    with _conn() as c:
        c.execute("""
            INSERT INTO client_enclaves (client_id, enclave_url, api_key, firm_name, active, created_at, updated_at)
            VALUES (?,?,?,?,1,?,?)
            ON CONFLICT(client_id) DO UPDATE SET
                enclave_url=excluded.enclave_url,
                api_key=excluded.api_key,
                firm_name=excluded.firm_name,
                active=1,
                updated_at=excluded.updated_at
        """, (client_id, enclave_url, api_key, firm_name, _now(), _now()))


def get_client_enclave(client_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM client_enclaves WHERE client_id=? AND active=1",
            (client_id,)
        ).fetchone()
    return dict(row) if row else None


def deactivate_client_enclave(client_id: str):
    with _conn() as c:
        c.execute(
            "UPDATE client_enclaves SET active=0, updated_at=? WHERE client_id=?",
            (_now(), client_id)
        )


def list_client_enclaves() -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT client_id, enclave_url, firm_name, active, created_at FROM client_enclaves"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Verdict log (cloud side, NO document content) ────────────────────────────

def save_privilege_verdict(
    client_id: str,
    doc_id: str,
    privileged: bool,
    privilege_type: str,
    confidence: float,
    requires_review: bool,
    log_entry_id: str = "",
):
    import uuid
    with _conn() as c:
        c.execute("""
            INSERT INTO privilege_verdicts
            (id, client_id, doc_id, privileged, privilege_type,
             confidence, requires_review, enclave_log_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            str(uuid.uuid4()), client_id, doc_id,
            int(privileged), privilege_type, confidence,
            int(requires_review), log_entry_id, _now()
        ))


def get_privilege_summary(client_id: str) -> dict:
    """
    Returns aggregate counts only — no document content.
    Used by the cloud dashboard to show privilege stats per client.
    """
    with _conn() as c:
        total    = c.execute("SELECT COUNT(*) FROM privilege_verdicts WHERE client_id=?", (client_id,)).fetchone()[0]
        flagged  = c.execute("SELECT COUNT(*) FROM privilege_verdicts WHERE client_id=? AND privileged=1", (client_id,)).fetchone()[0]
        review_q = c.execute("SELECT COUNT(*) FROM privilege_verdicts WHERE client_id=? AND requires_review=1", (client_id,)).fetchone()[0]
        by_type  = c.execute("""
            SELECT privilege_type, COUNT(*) as cnt
            FROM privilege_verdicts WHERE client_id=? AND privileged=1
            GROUP BY privilege_type
        """, (client_id,)).fetchall()

    return {
        "client_id":       client_id,
        "total_screened":  total,
        "total_flagged":   flagged,
        "review_queue":    review_q,
        "by_type":         {r["privilege_type"]: r["cnt"] for r in by_type},
        "note":            "Document content is never stored in the cloud DB.",
    }
