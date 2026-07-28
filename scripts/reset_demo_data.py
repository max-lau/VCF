"""
reset_demo_data.py
==================
One-command reset of all client/case/demo data for VCFClaimsIQ.

Keeps:
  - firm, user, role, permission, and auth tables
  - audit logs (so the reset itself is auditable)
  - AI config and notification configs

Deletes:
  - all cases, case documents, intake scans, and linked records
  - email intake history and communications
  - redactions, disbursements, deadlines, stage history
  - litigation-leftover tables still on disk
  - local upload files (uploads/*)
  - Supabase Storage objects in the vcf-documents bucket (optional)

Usage:
  C:\vcf> . venv/Scripts/activate
  (venv) PS C:\vcf> python scripts/reset_demo_data.py
"""
import os
import sys
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def get_db_conn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not found in environment or .env")
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


# Tables to truncate. Order does not matter because we use CASCADE,
# but child-before-parent is listed for clarity.
TABLES_TO_TRUNCATE = [
    # case-linked detail
    "case_documents",
    "case_notes",
    "case_tags",
    "case_briefs",
    "case_contradictions",
    "claim_stage_history",
    "claim_checklists",
    "vcf_account_prep",
    "vcf_deadlines",
    "vcf_disbursements",
    "contact_matters",
    "contacts",
    "communications",
    # intake / documents
    "intake_scans",
    "intake_jobs",
    "redactions",
    "transcriptions",
    "parsed_messages",
    "discovery_files",
    "discovery_runs",
    "bates_log",
    "bates_configs",
    # email
    "email_intakes",
    "email_processing_log",
    # portal / comms
    "client_portal_access",
    "client_messages",
    "client_enclaves",
    # workflow / kanban
    "kanban_card_logs",
    "kanban_cards",
    "kanban_boards",
    # esign
    "esign_signers",
    "esign_requests",
    # misc VCF
    "leads",
    "analyses",
    "feedback",
    "ai_work_product",
    "ai_drafts",
    "custom_entity_types",
    # litigation leftovers
    "correspondence",
    "depositions",
    "docketing_chains",
    "docketing_confirmations",
    "docketing_events",
    "invoices",
    "invoice_items",
    "legal_bert_analyses",
    "morning_briefs",
    "motions",
    "payments",
    "privilege_log",
    "privilege_verdicts",
    "reports",
    "research_notes",
    "risk_assessments",
    "contracts",
    "approval_queue",
    "attorney_review_gates",
    "webhook_subscriptions",
    "webhook_log",
    # time / voice
    "time_entries",
    "time_heartbeats",
    "time_sessions",
    "voice_audit_log",
    "voice_shortcuts",
    "notifications",
    # parent tables last
    "cases",
    "billing_rates",
]


def get_counts(cur):
    counts = {}
    for table in TABLES_TO_TRUNCATE:
        try:
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            counts[table] = cur.fetchone()["n"]
        except Exception as e:
            counts[table] = f"error: {e}"
    return counts


def truncate_tables(cur):
    for table in TABLES_TO_TRUNCATE:
        try:
            cur.execute(f"TRUNCATE TABLE {table} CASCADE")
        except Exception as e:
            print(f"  ⚠ could not truncate {table}: {e}")


def reset_sequences(cur):
    """Restart serial sequences so the next case starts from 1."""
    cur.execute("""
        SELECT c.relname AS table_name, a.attname AS col_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND n.nspname = 'public'
          AND a.attidentity != '' OR a.attgenerated != ''
    """)
    # Simpler: find serial columns via pg_get_serial_sequence
    cur.execute("""
        SELECT t.table_name, c.column_name
        FROM information_schema.tables t
        JOIN information_schema.columns c
          ON c.table_name = t.table_name AND c.table_schema = t.table_schema
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
          AND c.column_default LIKE 'nextval%'
    """)
    rows = cur.fetchall()
    for row in rows:
        seq = f"{row['table_name']}_{row['column_name']}_seq"
        try:
            cur.execute(f"ALTER SEQUENCE IF EXISTS {seq} RESTART WITH 1")
        except Exception:
            pass


def clear_local_uploads():
    upload_root = ROOT / "uploads"
    if not upload_root.exists():
        return
    cleared = 0
    for sub in upload_root.iterdir():
        if sub.is_dir():
            for f in sub.iterdir():
                if f.is_file():
                    f.unlink()
                    cleared += 1
                elif f.is_dir():
                    shutil.rmtree(f)
                    cleared += 1
    print(f"  ✓ Cleared {cleared} local upload item(s) under uploads/")


def clear_supabase_storage():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        print("  ⚠ SUPABASE_URL or SUPABASE_SERVICE_KEY missing — skipping Supabase Storage cleanup")
        return
    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)
        bucket = "vcf-documents"
        # List objects in batches and remove
        removed = 0
        page = 0
        while True:
            # supabase-py list API varies; use the storage client directly
            res = client.storage.from_(bucket).list()
            if not res or len(res) == 0:
                break
            paths = [item["name"] for item in res if "name" in item]
            if not paths:
                break
            client.storage.from_(bucket).remove(paths)
            removed += len(paths)
            page += 1
            if page > 100:
                print("  ⚠ Stopped Supabase cleanup after 100 pages as a safety limit")
                break
        print(f"  ✓ Removed {removed} object(s) from Supabase Storage bucket '{bucket}'")
    except Exception as e:
        print(f"  ⚠ Supabase Storage cleanup failed: {e}")


def main():
    load_env()
    firm_id = os.environ.get("FIRM_ID", "waw_vcf")

    print("VCFClaimsIQ — Demo data reset")
    print("=" * 50)
    print(f"Database: {mask_dsn(os.environ.get('DATABASE_URL', ''))}")
    print(f"Firm ID:  {firm_id}")
    print()

    conn = get_db_conn()
    cur = conn.cursor()

    # Set tenant context for RLS
    cur.execute("SELECT set_config('app.current_firm_id', %s, false)", (firm_id,))

    counts = get_counts(cur)
    total_rows = sum(v for v in counts.values() if isinstance(v, int))

    print(f"Tables that will be truncated ({len(TABLES_TO_TRUNCATE)} tables, ~{total_rows} rows):")
    for table in TABLES_TO_TRUNCATE:
        n = counts.get(table, 0)
        print(f"  {table:<36} {n}")
    print()
    print("Local uploads/ and Supabase Storage objects will also be removed.")
    print("User accounts, firm config, roles, and audit logs are preserved.")
    print()

    answer = input("Type DELETE DEMO DATA to proceed, or press Enter to cancel: ")
    if answer.strip() != "DELETE DEMO DATA":
        print("Cancelled. No changes were made.")
        return 0

    print("\nTruncating tables...")
    truncate_tables(cur)

    print("Restarting serial sequences...")
    reset_sequences(cur)

    print("Clearing local uploads...")
    clear_local_uploads()

    print("Clearing Supabase Storage...")
    clear_supabase_storage()

    conn.commit()
    cur.close()
    conn.close()

    print("\n✓ Demo reset complete. You can now record with a clean slate.")
    return 0


def mask_dsn(dsn: str) -> str:
    if not dsn:
        return "(not set)"
    try:
        p = urlparse(dsn)
        if p.password:
            return dsn.replace(p.password, "***")
    except Exception:
        pass
    return dsn


if __name__ == "__main__":
    sys.exit(main())
