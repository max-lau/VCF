#!/usr/bin/env python3
"""
seed_waw.py — Seed the WaW LLP demo tenant (firm_id 'waw') into ParaIQ.

Schema confirmed against seed_guest.py and prior session output — NOT guessed:
  firms         (id, name, plan)                                    <- id IS the firm_id string
  public.users  (id, username, email, password_hash, role, plan,
                 firm_id, active, invited_at, created_at, last_login) <- schema-qualify: there is
                                                                          ALSO an auth.users (Supabase)
  cases         (id, firm_id, case_number, client_name, matter_number,
                 status, court, judge, filing_date, description,
                 risk_level, deleted, created_at, updated_at)
  case_documents(firm_id, case_id, document_name, source, doc_text,
                 sentiment, risk_score, events_json, entities_json,
                 summary, language, upload_date, pacer_doc_id, pacer_seq_no)
  case_notes    (firm_id, case_id, author, note, pinned, created_at)
  kanban_cards  (case_id, firm_id, title, card_type, column_id, due_date,
                 assignee_id, notes, position, moved_by_hermes)

IMPORTANT CORRECTION (discovered live against the real app, not assumed):
  `cases.status` is NOT the Kanban board — it's a coarse lifecycle flag with a
  CHECK constraint limited to {'open','pending','closed','archived'}. The real
  Kanban board (CaseKanban.vue) is a SEPARATE per-case table, `kanban_cards`,
  with 6 hardcoded columns: intake / research / discovery / motions /
  trial_prep / closed (litigation-oriented labels — cosmetically odd for a VCF
  claims practice, but that's a global relabeling decision outside this script's
  scope, not something to quietly change here).
  This script therefore:
    1. Maps each client's rich 8-stage VCF pipeline label down to a valid
       `cases.status` value (see STATUS_MAP below), and keeps the full label
       visible as a "[Stage: ...]" prefix on `description`.
    2. Populates real `kanban_cards` rows — one per timeline event — spread
       across the 6 real columns, so the Kanban board actually has content.
    3. Still writes the full 8-stage narrative into case_notes (unchanged),
       which is the authoritative "well-formed timeline" the spec asked for.

Design choices (mirroring seed_guest.py conventions):
  * RLS context set with literal `SET app.current_firm_id = %s` (psycopg2 mogrifies
    this client-side into a literal before sending, so it works even though SET
    doesn't accept wire-protocol parameters).
  * No `clients` table exists, so each VCF claimant = one `case`; full demographic /
    exposure / WTC-HP detail goes into a pinned "Client Intake Summary" case_note
    (author = assigned paralegal) rather than being split across tables that don't exist.
  * Each timeline event -> one case_note (unchanged narrative history), AND one
    kanban_cards row (actionable board view) — same data, two presentations.
    case_notes pinned=True for milestone event types (award_letter, claim_filed,
    wtchp_certification, case_closed, etc).
  * Each intake image / medical-record PDF -> one case_documents row. For the two
    Vision-demo intake images, `doc_text` is pre-filled with the structured English
    extraction a Claude Vision pass would produce — so the case looks complete even
    before you run the live Vision demo, and you can diff live output against it.
  * kanban_cards.assignee_id left NULL: column is nullable with NO foreign-key
    constraint (verified), but the fictional paralegal names (D. Kim, M. Torres)
    don't correspond to real rows in `users`, so NULL is the honest choice —
    paralegal name is still fully preserved as case_notes.author and in the
    pinned intake summary.

Usage on VPS (from /root/nlp-portfolio):
    source .venv/bin/activate
    export DATABASE_URL="$(grep '^DATABASE_URL' .env | cut -d= -f2-)"
    python3 demo_docs/waw/seed_waw.py --dry-run      # preview, commits nothing
    python3 demo_docs/waw/seed_waw.py                # seed
    python3 demo_docs/waw/seed_waw.py --reset         # wipe firm 'waw' rows first, then seed

!! CONFIRMED against live schema + auth.py + frontend + kanban_router.py on 2026-07-08:
!!   - users.role = 'firm_admin' is correct: ROLE_TIER_MAP contains "firm_admin": 1
!!     as a literal key, so auth.py line 143 resolves it directly (tier 1), no
!!     fallback-to-associate risk.
!!   - firms.id / users.firm_id / cases.firm_id all accept arbitrary text (default
!!     firm_id is the literal string 'default'), so the non-UUID slug 'waw' is fine.
!!   - firms.plan / users.plan CHECK constraint allows only {'free','starter','pro',
!!     'enterprise'} — using 'free' (users.plan has no CHECK constraint at all, but
!!     'free' matches the column default there too).
!!   - case_documents.source CHECK allows only {'uploaded','pacer','email','manual'}
!!     — using 'uploaded' for both intake scans and medical records.
!!   - cases.status CHECK allows only {'open','pending','closed','archived'} — see
!!     STATUS_MAP below for the mapping from the 8-stage VCF pipeline label.
!!   - cases.assigned_attorney IS a real column but is an integer FK to users(id),
!!     NOT a free-text name — left unset (NULL) since our paralegals aren't real
!!     users; name is preserved in notes/description instead.
!!   - kanban_cards.column_id CHECK allows only {'intake','research','discovery',
!!     'motions','trial_prep','closed'}; card_type CHECK allows only {'task',
!!     'deadline','motion','depo','filing'}.
!! Remaining unverified: whether users.username/email carry a UNIQUE constraint.
!! The script uses a bare ON CONFLICT DO NOTHING, safe regardless of the constraint
!! name, but it silently no-ops on a second run instead of updating — use --reset
!! if you rerun after fixing a mistake.
"""
import argparse
import json
import os
import sys

import bcrypt
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv("/root/nlp-portfolio/.env")

TARGET_FIRM = "waw"
DOCS_DIR = "/root/nlp-portfolio/demo_docs/waw"   # where you scp the PNG/PDF files alongside this script

MILESTONE_TYPES = {
    "award_letter", "claim_filed", "wtchp_certification", "case_closed",
    "retainer_signed", "vcf_registration", "payment_received", "disbursement",
}

# cases.status CHECK constraint only allows these 4 — map the 8-stage narrative down.
STATUS_MAP = {
    "Intake": "open",
    "Documentation": "open",
    "WTC-HP Certification": "pending",
    "Claim Filed": "pending",
    "Under Review": "pending",
    "Award / Decision": "pending",
    "Disbursement": "pending",
    "Closed": "closed",
}

# kanban_cards.column_id CHECK only allows these 6 (litigation-oriented labels —
# cosmetically mismatched for a VCF practice, but relabeling is a global frontend
# change, not something to do inside a data-seeding script).
EVENT_TO_COLUMN = {
    "intake_call": "intake", "questionnaire_sent": "intake",
    "questionnaire_received": "intake", "retainer_signed": "intake",
    "missing_info_request": "intake",
    "records_requested": "research", "follow_up": "research",
    "records_received": "discovery", "medical_exam": "discovery",
    "wtchp_appointment": "discovery", "wtchp_certification": "discovery",
    "vcf_registration": "discovery",
    "claim_filed": "motions", "deficiency_letter": "motions",
    "deficiency_response": "motions",
    "client_meeting": "trial_prep", "award_letter": "trial_prep",
    "decision_discussion": "trial_prep", "financial_arrangement": "trial_prep",
    "payment_received": "closed", "disbursement": "closed", "case_closed": "closed",
}

# kanban_cards.card_type CHECK only allows: task, deadline, motion, depo, filing.
EVENT_TO_CARD_TYPE = {
    "claim_filed": "filing", "deficiency_response": "filing",
    "vcf_registration": "filing", "wtchp_appointment": "filing",
    "medical_exam": "depo",
    "award_letter": "motion", "decision_discussion": "motion",
    "wtchp_certification": "motion",
}

# ---------------------------------------------------------------------------

def load_data():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "waw_seed_data.json"), encoding="utf-8") as f:
        return json.load(f)


def card_type_for(event):
    if event["title"].startswith("Upcoming"):
        return "deadline"
    return EVENT_TO_CARD_TYPE.get(event["type"], "task")


def risk_level_for(client):
    conds = " ".join(c["condition"].lower() for c in client["conditions"])
    if "cancer" in conds or "carcinoma" in conds or "lymphoma" in conds or "myeloma" in conds:
        return "High"
    if "sarcoidosis" in conds or "severe" in conds:
        return "High"
    if "asthma" in conds or "copd" in conds or "lymphedema" in conds:
        return "Medium"
    return "Low"


def vision_extraction_stub(client, form_language):
    """Pre-filled structured extraction, as if Claude Vision had already scanned the
    handwritten intake form. Lets the case look complete pre-demo; live Vision output
    can be compared against this during the pitch."""
    c = client
    lines = [
        f"[Claude Vision structured extraction — source: handwritten intake, {form_language}]",
        f"Name: {c['name']}" + (f" ({c['name_native']})" if c.get("name_native") else ""),
        f"DOB: {c['dob']}  |  Gender: {c['gender']}  |  Age: {c['age']}",
        f"Address: {c['address']}",
        f"Phone: {c['phone']}",
        f"Exposure: {c['exposure_narrative']}",
        f"Employer: {c['exposure_category']}",
        "Diagnosed conditions: " + "; ".join(x["condition"] for x in c["conditions"]),
        f"WTC-HP enrolled: {c['wtc_hp'].get('enrolled') or 'not yet'}",
        f"Prior VCF filing: {'No — first filing' if not c.get('vcf_registration') else 'Registered ' + c['vcf_registration']}",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete all firm 'waw' rows first")
    ap.add_argument("--dry-run", action="store_true", help="print planned inserts, commit nothing")
    args = ap.parse_args()

    data = load_data()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL not set — see usage note at top of this file.")

    conn = psycopg2.connect(dsn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SET app.current_firm_id = %s", (TARGET_FIRM,))

    if args.reset:
        print(f"Resetting firm '{TARGET_FIRM}' ...")
        if not args.dry_run:
            cur.execute("DELETE FROM kanban_cards WHERE firm_id = %s", (TARGET_FIRM,))
            cur.execute("DELETE FROM case_documents WHERE firm_id = %s", (TARGET_FIRM,))
            cur.execute("DELETE FROM case_notes WHERE firm_id = %s", (TARGET_FIRM,))
            cur.execute("DELETE FROM cases WHERE firm_id = %s", (TARGET_FIRM,))
            cur.execute("DELETE FROM public.users WHERE firm_id = %s", (TARGET_FIRM,))
            cur.execute("DELETE FROM firms WHERE id = %s", (TARGET_FIRM,))
            conn.commit()
            print("  cleared existing waw rows")
        else:
            print("  [dry] would DELETE from kanban_cards, case_documents, case_notes, cases, public.users, firms")

    # ── firm ──────────────────────────────────────────────────────────────
    f = data["firm"]
    print(f"Seeding firm '{TARGET_FIRM}' ({f['name']}) ...")
    if not args.dry_run:
        cur.execute(
        "INSERT INTO firms (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (TARGET_FIRM, f["name"]),
    )

    # ── user ──────────────────────────────────────────────────────────────
    u = data["user"]
    demo_pw = os.environ["WAW_DEMO_PASSWORD"]  # from env, never commit plaintext
    pw_hash = bcrypt.hashpw(demo_pw.encode(), bcrypt.gensalt()).decode()
    print(f"Seeding user '{u['username']}' (role='{u['role']}' — VERIFY against auth.py) ...")
    if not args.dry_run:
        cur.execute(
            """INSERT INTO public.users
                   (username, email, password_hash, role, plan, firm_id, active, created_at)
               VALUES (%s, %s, %s, %s, 'free', %s, TRUE, NOW())
               ON CONFLICT DO NOTHING""",
            (u["username"], u["email"], pw_hash, u["role"], TARGET_FIRM),
        )

    # ── cases (+ notes, + documents) ─────────────────────────────────────
    doc_index = {}
    for d in data["documents"]:
        doc_index.setdefault(d["client_key"], []).append(d)

    for i, c in enumerate(data["clients"], start=1):
        display = c["name"] + (f" ({c['name_native']})" if c.get("name_native") else "")
        print(f"[{i}/8] {display}  —  {c['kanban_stage']}")

        case_number = f"VCF-2026-{i:03d}"
        matter_number = f"WAW-{c['client_key'].upper()}"
        filing_events = [e for e in c["timeline"] if e["type"] == "claim_filed"]
        filing_date = filing_events[0]["date"] if filing_events else c["timeline"][0]["date"]
        status = STATUS_MAP[c["kanban_stage"]]
        description = (
            f"[Stage: {c['kanban_stage']}] {c['claim_type']}. "
            f"Claimant: {c['age']}yo {c['gender']}, {c['race_ethnicity']}. "
            f"Exposure: {c['exposure_category']}. "
            f"Conditions: {'; '.join(x['condition'] for x in c['conditions'])}."
        )

        if args.dry_run:
            print(f"    [dry] INSERT cases: {case_number}, status={status} "
                  f"(stage='{c['kanban_stage']}'), risk={risk_level_for(c)}")
            case_id = None
        else:
            cur.execute(
                """INSERT INTO cases
                       (firm_id, case_number, client_name, matter_number, status, court,
                        judge, filing_date, description, risk_level,
                        deleted, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, FALSE, NOW(), NOW())
                   RETURNING id""",
                (TARGET_FIRM, case_number, display, matter_number, status,
                 "U.S. Department of Justice — September 11th VCF Claims Unit",
                 "N/A — Special Master review (VCF is not a court proceeding)",
                 filing_date, description, risk_level_for(c)),
            )
            case_id = cur.fetchone()["id"]

        # pinned intake summary note (stands in for the missing "clients" table)
        intake_summary = (
            f"CLIENT INTAKE SUMMARY\n"
            f"DOB: {c['dob']}  |  Age: {c['age']}  |  Gender: {c['gender']}  |  "
            f"Ethnicity: {c['race_ethnicity']}\n"
            f"Address: {c['address']}\nPhone: {c['phone']}"
            + (f"\nEmail: {c['email']}" if c.get("email") else "")
            + (f"\nPreferred language: {c['preferred_language']}" if c.get("preferred_language") else "")
            + (f"\nEmergency contact: {c['emergency_contact']}" if c.get("emergency_contact") else "")
            + f"\n\nExposure: {c['exposure_narrative']}\n"
            f"WTC-HP enrolled: {c['wtc_hp'].get('enrolled') or 'not yet'}; "
            f"certified: {', '.join(c['wtc_hp']['certified']) or 'none yet'}\n"
            f"VCF registration: {c.get('vcf_registration') or 'not yet registered'}\n"
            f"Assigned paralegal: {c['assigned_paralegal']}\n\n"
            f"Case notes: {c['notes']}"
        )
        if args.dry_run:
            print(f"    [dry] INSERT case_notes: intake summary (pinned)")
            print(f"    [dry] INSERT case_notes: {len(c['timeline'])} timeline events")
        else:
            cur.execute(
                """INSERT INTO case_notes (firm_id, case_id, author, note, pinned, created_at)
                   VALUES (%s,%s,%s,%s, TRUE, %s)""",
                (TARGET_FIRM, case_id, c["assigned_paralegal"], intake_summary, c["timeline"][0]["date"]),
            )
            for ev in c["timeline"]:
                pinned = ev["type"] in MILESTONE_TYPES
                note_text = f"[{ev['type']}] {ev['title']}" + (f"\n{ev['detail']}" if ev["detail"] else "")
                cur.execute(
                    """INSERT INTO case_notes (firm_id, case_id, author, note, pinned, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (TARGET_FIRM, case_id, c["assigned_paralegal"], note_text, pinned, ev["date"]),
                )

        # kanban cards — same timeline events, real board columns, actionable view
        if args.dry_run:
            print(f"    [dry] INSERT kanban_cards: {len(c['timeline'])} cards across "
                  f"{len(set(EVENT_TO_COLUMN.get(e['type'], 'intake') for e in c['timeline']))} columns")
        else:
            col_position = {}
            for ev in c["timeline"]:
                col = EVENT_TO_COLUMN.get(ev["type"], "intake")
                col_position[col] = col_position.get(col, 0) + 1
                card_type = card_type_for(ev)
                title = ev["title"]
                cur.execute(
                    """INSERT INTO kanban_cards
                           (case_id, firm_id, title, card_type, column_id, due_date,
                            assignee_id, notes, position, moved_by_hermes)
                       VALUES (%s,%s,%s,%s,%s,%s, NULL, %s, %s, FALSE)""",
                    (case_id, TARGET_FIRM, title, card_type, col, ev["date"],
                     ev["detail"] or None, col_position[col]),
                )

        # documents
        for d in doc_index.get(c["client_key"], []):
            is_intake_image = d["doc_type"] == "intake_form_scan"
            doc_text = vision_extraction_stub(c, d.get("language", "en")) if is_intake_image else \
                f"[Medical record on file: {d['description']}. Full text available in source PDF at " \
                f"{DOCS_DIR}/{d['filename']}]"
            if args.dry_run:
                print(f"    [dry] INSERT case_documents: {d['filename']}")
            else:
                cur.execute(
                    """INSERT INTO case_documents
                           (firm_id, case_id, document_name, source, doc_text, sentiment, risk_score,
                            events_json, entities_json, summary, language, upload_date,
                            pacer_doc_id, pacer_seq_no)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)""",
                    (TARGET_FIRM, case_id, d["filename"],
                     "uploaded",
                     doc_text, None, None,
                     json.dumps([]), json.dumps({}),
                     d["description"], d.get("language", "en"),
                     c["timeline"][0]["date"]),
                )

    if args.dry_run:
        print("\nDry run complete — nothing committed.")
        conn.rollback()
    else:
        conn.commit()
        print("\nCommitted. Verify tenant isolation:")
        print("  1) Log in as WaW (password from WAW_DEMO_PASSWORD env) -> should see exactly 8 cases.")
        print("  2) Log in as maxwell (firm 'default') -> should see ZERO waw rows.")
        print("  3) Add firm 'waw' as a third tenant in the cross-tenant CI test matrix.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
