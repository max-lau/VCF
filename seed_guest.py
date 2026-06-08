#!/usr/bin/env python3
"""
seed_guest.py — copies demo data from 'default' firm into guest trial workspaces.
Usage: python3 seed_guest.py trial_14 trial_15 ...
Run from: /root/nlp-portfolio
"""

import sys, os, json, psycopg2, psycopg2.extras
from dotenv import load_dotenv
load_dotenv("/root/nlp-portfolio/.env")

SOURCE_FIRM = "default"

def seed_firm(conn, target_firm):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── Ensure trial firm exists ───────────────────────────────────────────────
    cur.execute("SET app.current_firm_id = 'default'")
    cur.execute("""
        INSERT INTO firms (id, name, plan) VALUES (%s, %s, 'free')
        ON CONFLICT DO NOTHING
    """, (target_firm, target_firm.replace("_", " ").title()))

    # ── Check if already seeded ────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) AS n FROM cases WHERE firm_id = %s", (target_firm,))
    if cur.fetchone()["n"] > 0:
        print(f"  ⚠  {target_firm} already has cases — skipping")
        return

    # ── Read ALL source data first (context = default) ────────────────────────
    cur.execute("""
        SELECT id, case_number, client_name, matter_number, status, court, judge,
               filing_date, description, risk_level, deleted, created_at, updated_at
        FROM cases WHERE firm_id = %s AND deleted = FALSE
    """, (SOURCE_FIRM,))
    source_cases = cur.fetchall()

    source_case_ids = [c["id"] for c in source_cases]

    source_docs = []
    source_notes = []
    if source_case_ids:
        placeholders = ",".join(["%s"] * len(source_case_ids))
        cur.execute(f"""
            SELECT case_id, document_name, source, doc_text, sentiment, risk_score,
                   events_json, entities_json, summary, language, upload_date,
                   pacer_doc_id, pacer_seq_no
            FROM case_documents WHERE firm_id = %s AND case_id IN ({placeholders})
        """, [SOURCE_FIRM] + source_case_ids)
        source_docs = cur.fetchall()

        cur.execute(f"""
            SELECT case_id, author, note, pinned, created_at
            FROM case_notes WHERE firm_id = %s AND case_id IN ({placeholders})
        """, [SOURCE_FIRM] + source_case_ids)
        source_notes = cur.fetchall()

    # ── Switch context to target for all writes ───────────────────────────────
    cur.execute("SET app.current_firm_id = %s", (target_firm,))

    case_id_map = {}
    for c in source_cases:
        cur.execute("""
            INSERT INTO cases
                (firm_id, case_number, client_name, matter_number, status, court,
                 judge, filing_date, description, risk_level, deleted, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (target_firm, c["case_number"], c["client_name"], c["matter_number"],
              c["status"], c["court"], c["judge"], c["filing_date"],
              c["description"], c["risk_level"], c["deleted"],
              c["created_at"], c["updated_at"]))
        case_id_map[c["id"]] = cur.fetchone()["id"]

    print(f"  ✓ {len(source_cases)} cases copied")

    doc_count = 0
    for d in source_docs:
        new_case_id = case_id_map.get(d["case_id"])
        if not new_case_id:
            continue
        cur.execute("""
            INSERT INTO case_documents
                (firm_id, case_id, document_name, source, doc_text, sentiment,
                 risk_score, events_json, entities_json, summary, language,
                 upload_date, pacer_doc_id, pacer_seq_no)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (target_firm, new_case_id, d["document_name"], d["source"],
              d["doc_text"], d["sentiment"], d["risk_score"],
              json.dumps(d["events_json"]) if isinstance(d["events_json"], (dict,list)) else d["events_json"],
              json.dumps(d["entities_json"]) if isinstance(d["entities_json"], (dict,list)) else d["entities_json"],
              d["summary"],
              d["language"], d["upload_date"], d["pacer_doc_id"], d["pacer_seq_no"]))
        doc_count += 1
    print(f"  ✓ {doc_count} documents copied")

    note_count = 0
    for n in source_notes:
        new_case_id = case_id_map.get(n["case_id"])
        if not new_case_id:
            continue
        cur.execute("""
            INSERT INTO case_notes (firm_id, case_id, author, note, pinned, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (target_firm, new_case_id, n["author"], n["note"], n["pinned"], n["created_at"]))
        note_count += 1
    if note_count:
        print(f"  ✓ {note_count} notes copied")

    conn.commit()
    print(f"  ✅ {target_firm} seeded successfully\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 seed_guest.py trial_14 [trial_15 ...]")
        sys.exit(1)
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    print(f"\nSeeding {len(sys.argv)-1} workspace(s) from '{SOURCE_FIRM}'...\n")
    for firm_id in sys.argv[1:]:
        print(f"▶  {firm_id}")
        try:
            seed_firm(conn, firm_id)
        except Exception as e:
            conn.rollback()
            print(f"  ✗ Failed: {e}\n")
    conn.close()

if __name__ == "__main__":
    main()
