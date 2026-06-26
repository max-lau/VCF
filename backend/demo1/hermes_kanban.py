"""
hermes_kanban.py  -  Hermes auto-move intelligence for the Kanban board
"""

import logging
import httpx
from backend.demo1.pg import get_conn

log = logging.getLogger(__name__)

API_BASE = "http://localhost:5003"

ADVANCE_RULES = [
    ("intake",     "has_complaint_filed",    "research",   0.95, "complaint_filed"),
    ("research",   "has_discovery_opened",   "discovery",  0.90, "discovery_opened"),
    ("discovery",  "production_complete",    "motions",    0.85, "document_production_complete"),
    ("motions",    "all_motions_ruled",      "trial_prep", 0.88, "all_motions_decided"),
    ("trial_prep", "verdict_entered",        "closed",     0.99, "verdict_or_settlement"),
]

def has_complaint_filed(conn, case_id, firm_id):
    row = conn.execute(
        "SELECT 1 FROM kanban_cards WHERE case_id=%s AND firm_id=%s AND card_type='filing' AND LOWER(title) LIKE '%%complaint%%' AND column_id='intake' LIMIT 1",
        (case_id, firm_id)).fetchone()
    return row is not None

def has_discovery_opened(conn, case_id, firm_id):
    row = conn.execute(
        "SELECT 1 FROM kanban_cards WHERE case_id=%s AND firm_id=%s AND card_type IN ('depo','deadline') LIMIT 1",
        (case_id, firm_id)).fetchone()
    return row is not None

def production_complete(conn, case_id, firm_id):
    row = conn.execute(
        "SELECT 1 FROM kanban_cards WHERE case_id=%s AND firm_id=%s AND column_id='discovery' AND card_type='deadline' AND LOWER(title) LIKE '%%production%%' AND due_date < NOW() LIMIT 1",
        (case_id, firm_id)).fetchone()
    return row is not None

def all_motions_ruled(conn, case_id, firm_id):
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM kanban_cards WHERE case_id=%s AND firm_id=%s AND column_id='motions' AND card_type='motion'",
        (case_id, firm_id)).fetchone()
    return row["cnt"] == 0

def verdict_entered(conn, case_id, firm_id):
    row = conn.execute(
        "SELECT 1 FROM kanban_cards WHERE case_id=%s AND firm_id=%s AND column_id='trial_prep' AND (LOWER(title) LIKE '%%verdict%%' OR LOWER(title) LIKE '%%settlement%%') LIMIT 1",
        (case_id, firm_id)).fetchone()
    return row is not None

CONDITION_MAP = {
    "has_complaint_filed":  has_complaint_filed,
    "has_discovery_opened": has_discovery_opened,
    "production_complete":  production_complete,
    "all_motions_ruled":    all_motions_ruled,
    "verdict_entered":      verdict_entered,
}

def check_case_for_advances(case_id: int, firm_id: str, jwt_token: str):
    with get_conn(firm_id) as conn:
        for (from_col, condition_fn_name, to_col, confidence, label) in ADVANCE_RULES:
            condition_fn = CONDITION_MAP[condition_fn_name]
            cards = conn.execute(
                "SELECT id FROM kanban_cards WHERE case_id=%s AND firm_id=%s AND column_id=%s AND moved_by_hermes=false LIMIT 5",
                (case_id, firm_id, from_col)).fetchall()
            if not cards:
                continue
            triggered = condition_fn(conn, case_id, firm_id)
            if not triggered:
                continue
            for card_row in cards:
                try:
                    with httpx.Client() as client:
                        client.post(
                            f"{API_BASE}/kanban/hermes/signal",
                            json={"case_id": case_id, "card_id": card_row["id"],
                                  "detected_event": label, "suggested_column": to_col,
                                  "confidence": confidence},
                            headers={"Authorization": f"Bearer {jwt_token}"},
                            timeout=5.0)
                except Exception as e:
                    log.warning("Hermes signal failed for card %d: %s", card_row["id"], e)

async def run_hermes_kanban(jwt_token: str):
    with get_conn("default") as conn:  # noqa: intentional — background task scans all firms' kanban boards
        rows = conn.execute(
            "SELECT DISTINCT case_id, firm_id FROM kanban_cards WHERE column_id NOT IN ('closed') LIMIT 200"
        ).fetchall()
    for row in rows:
        check_case_for_advances(row["case_id"], row["firm_id"], jwt_token)
