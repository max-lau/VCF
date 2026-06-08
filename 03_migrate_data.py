#!/usr/bin/env python3
"""
ParaIQ — SQLite → Postgres migration (v2, patched)
Usage: python 03_migrate_data.py "postgresql://postgres:PASSWORD@db.XXXX.supabase.co:5432/postgres"
"""

import sqlite3
import json
import sys

try:
    import psycopg2
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg2-binary", "--break-system-packages", "-q"])
    import psycopg2

SQLITE_DBS = {
    "main":       "/root/nlp-portfolio/analyses.db",
    "demo":       "/root/nlp-portfolio/backend/demo1/analyses.db",
    "redactions": "/root/nlp-portfolio/backend/demo1/redactions.db",
}

DEFAULT_FIRM = "default"


# ── helpers ───────────────────────────────────────────────────────────────────

def sqlite_conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def to_json(val):
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    try:
        return json.dumps(json.loads(val))
    except (ValueError, TypeError):
        return val


def to_bool(val):
    if val is None:
        return None
    return bool(int(val)) if str(val).lstrip('-').isdigit() else bool(val)


def to_date(val):
    """Convert empty strings and None to NULL for Postgres DATE columns."""
    if val is None:
        return None
    if str(val).strip() == '':
        return None
    return val


def firm_or_default(val):
    """Return val if non-empty, else 'default'."""
    if val and str(val).strip():
        return str(val).strip()
    return DEFAULT_FIRM


def fetch_all(conn, table):
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {table}")
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError as e:
        print(f"  ⚠  {table} not found: {e}")
        return []


def bulk_insert(pg, table, columns, rows, on_conflict="DO NOTHING"):
    """Insert rows one at a time using savepoints so one bad row can't abort the batch."""
    if not rows:
        return 0
    cur = pg.cursor()
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT {on_conflict}"
    inserted = 0
    for row in rows:
        try:
            cur.execute("SAVEPOINT sp")
            cur.execute(sql, row)
            cur.execute("RELEASE SAVEPOINT sp")
            inserted += 1
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT sp")
            # Only print first unique error type to keep output clean
            print(f"  ⚠  skipped row in {table}: {str(e).splitlines()[0]}")
    pg.commit()
    return inserted


# ── Step 0: collect and pre-insert all firm_ids found in the data ─────────────

def collect_all_firm_ids(main, demo):
    """Scan every table for firm_id values and return the full set."""
    firm_ids = {DEFAULT_FIRM}
    tables_to_scan = [
        (main, ["cases", "case_documents", "case_notes", "correspondence",
                "calendar_events", "contacts", "research_notes", "reports",
                "ai_config", "client_portal_access", "discovery_runs"]),
        (demo, ["users", "role_assignments", "intake_scans", "discovery_files",
                "bates_configs", "bates_log", "privilege_log", "transcriptions",
                "parsed_messages", "discovery_runs"]),
    ]
    for conn, tables in tables_to_scan:
        for table in tables:
            rows = fetch_all(conn, table)
            for r in rows:
                fid = r.get("firm_id")
                if fid and str(fid).strip():
                    firm_ids.add(str(fid).strip())
    return firm_ids


def ensure_firms(pg, firm_ids):
    """Insert any firm_id that isn't already in the firms table."""
    cur = pg.cursor()
    cur.execute("SELECT id FROM firms")
    existing = {r[0] for r in cur.fetchall()}
    missing = firm_ids - existing
    for fid in sorted(missing):
        cur.execute(
            "INSERT INTO firms (id, name, plan) VALUES (%s, %s, 'free') ON CONFLICT DO NOTHING",
            (fid, fid.replace("_", " ").title())
        )
        print(f"  + inserted firm: {fid}")
    pg.commit()


# ── mappers ───────────────────────────────────────────────────────────────────

def map_cases(rows):
    cols = ["firm_id","case_number","client_name","matter_number","status",
            "court","judge","filing_date","description","risk_level","deleted",
            "created_at","updated_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r["case_number"], r["client_name"], r.get("matter_number"),
        r.get("status","open"), r.get("court"), r.get("judge"),
        to_date(r.get("filing_date")),          # ← empty string → NULL
        r.get("description"), r.get("risk_level","unknown"),
        to_bool(r.get("deleted",0)),
        r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_case_documents(rows):
    cols = ["firm_id","case_id","document_name","source","doc_text","sentiment",
            "risk_score","events_json","entities_json","summary","language",
            "upload_date","pacer_doc_id","pacer_seq_no"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r["case_id"], r["document_name"], r.get("source","uploaded"),
        r.get("doc_text"), r.get("sentiment"), r.get("risk_score"),
        to_json(r.get("events_json")), to_json(r.get("entities_json")),
        r.get("summary"), r.get("language","en"), r.get("upload_date"),
        r.get("pacer_doc_id"), r.get("pacer_seq_no"),
    ) for r in rows]


def map_case_notes(rows):
    cols = ["firm_id","case_id","author","note","pinned","created_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r["case_id"], r.get("author","System"), r["note"],
        to_bool(r.get("pinned",0)), r.get("created_at"),
    ) for r in rows]


def map_correspondence(rows):
    cols = ["firm_id","matter_id","type","direction","subject","body","from_party",
            "to_party","cc_party","date","status","attachments","created_at","updated_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r["matter_id"], r.get("type","email"), r.get("direction","outbound"),
        r["subject"], r.get("body"), r.get("from_party"), r.get("to_party"),
        r.get("cc_party"), to_date(r.get("date")), r.get("status","draft"),
        to_json(r.get("attachments")), r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_calendar_events(rows):
    cols = ["firm_id","matter_id","title","event_type","due_date","due_time",
            "location","description","attendees","status","reminder_days",
            "is_court_date","created_at","updated_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r.get("matter_id"), r["title"], r.get("event_type","deadline"),
        to_date(r["due_date"]), r.get("due_time"), r.get("location"),
        r.get("description"), to_json(r.get("attendees")),
        r.get("status","upcoming"), r.get("reminder_days",3),
        to_bool(r.get("is_court_date",0)),
        r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_contacts(rows):
    cols = ["firm_id","matter_id","name","role","organization","email","phone",
            "address","notes","is_adverse","tags","created_at","updated_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r.get("matter_id"), r["name"], r.get("role","other"),
        r.get("organization"), r.get("email"), r.get("phone"),
        r.get("address"), r.get("notes"), to_bool(r.get("is_adverse",0)),
        to_json(r.get("tags")), r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_research_notes(rows):
    cols = ["firm_id","matter_id","title","research_type","citation","jurisdiction",
            "summary","body","relevance","url","tags","is_favorable","created_by",
            "created_at","updated_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r.get("matter_id"), r["title"], r.get("research_type","case_law"),
        r.get("citation"), r.get("jurisdiction"), r.get("summary"), r.get("body"),
        r.get("relevance"), r.get("url"), to_json(r.get("tags")),
        to_bool(r.get("is_favorable",1)), r.get("created_by"),
        r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_reports(rows):
    cols = ["firm_id","matter_id","report_type","title","status","content",
            "metadata","generated_by","created_by","created_at","updated_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r.get("matter_id"), r["report_type"], r["title"],
        r.get("status","generating"), r.get("content"),
        to_json(r.get("metadata")), r.get("generated_by","manual"),
        r.get("created_by"), r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_ai_config(rows):
    cols = ["firm_id","setting_key","setting_value","updated_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r["setting_key"], r.get("setting_value"), r.get("updated_at"),
    ) for r in rows]


def map_client_portal_access(rows):
    cols = ["firm_id","matter_id","client_name","client_email","access_token",
            "permissions","expires_at","last_accessed","is_active","created_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r["matter_id"], r.get("client_name"), r.get("client_email"),
        r["access_token"],
        r.get("permissions","timeline,documents,correspondence"),
        r.get("expires_at"), r.get("last_accessed"),
        to_bool(r.get("is_active",1)), r.get("created_at"),
    ) for r in rows]


def map_discovery_runs(rows):
    cols = ["firm_id","case_id","status","docs_processed","flagged_docs",
            "llm_calls","estimated_cost","elapsed_seconds","zip_path",
            "aborted","abort_reason","created_at"]
    return cols, [(
        firm_or_default(r.get("firm_id")),
        r.get("case_id"), r.get("status"), r.get("docs_processed"),
        r.get("flagged_docs"), r.get("llm_calls"), r.get("estimated_cost"),
        r.get("elapsed_seconds"), r.get("zip_path"),
        to_bool(r.get("aborted",0)), r.get("abort_reason"), r.get("created_at"),
    ) for r in rows]


def map_depositions(rows):
    cols = ["firm_id","case_number","witness_name","witness_role","depo_date",
            "location","status","notes","created_at","updated_at"]
    return cols, [(
        DEFAULT_FIRM, r["case_number"], r["witness_name"], r.get("witness_role"),
        to_date(r.get("depo_date")), r.get("location"),
        r.get("status","scheduled"), r.get("notes"),
        r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_motions(rows):
    cols = ["firm_id","case_number","title","motion_type","filed_date",
            "hearing_date","status","notes","created_at","updated_at"]
    return cols, [(
        DEFAULT_FIRM, r["case_number"], r["title"], r.get("motion_type"),
        to_date(r.get("filed_date")), to_date(r.get("hearing_date")),
        r.get("status","draft"), r.get("notes"),
        r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_contracts(rows):
    cols = ["firm_id","case_number","contract_name","contract_type","parties",
            "execution_date","expiry_date","status","notes","created_at","updated_at"]
    return cols, [(
        DEFAULT_FIRM, r["case_number"], r["contract_name"], r.get("contract_type"),
        r.get("parties"), to_date(r.get("execution_date")), to_date(r.get("expiry_date")),
        r.get("status","draft"), r.get("notes"),
        r.get("created_at"), r.get("updated_at"),
    ) for r in rows]


def map_client_enclaves(rows):
    cols = ["client_id","firm_id","enclave_url","api_key","firm_name","active",
            "created_at","updated_at"]
    return cols, [(
        r["client_id"], DEFAULT_FIRM, r["enclave_url"], r["api_key"],
        r.get("firm_name"), to_bool(r.get("active",1)),
        r["created_at"], r["updated_at"],
    ) for r in rows]


def map_privilege_verdicts(rows):
    cols = ["id","firm_id","client_id","doc_id","privileged","privilege_type",
            "confidence","requires_review","enclave_log_id","created_at"]
    return cols, [(
        r["id"], DEFAULT_FIRM, r["client_id"], r["doc_id"],
        to_bool(r["privileged"]), r["privilege_type"], r["confidence"],
        to_bool(r["requires_review"]), r.get("enclave_log_id"), r["created_at"],
    ) for r in rows]


def map_users(rows):
    cols = ["username","email","password_hash","role","plan","firm_id",
            "active","created_at","last_login"]
    return cols, [(
        r["username"], r["email"], r["password_hash"], r.get("role","user"),
        r.get("plan","free"), firm_or_default(r.get("firm_id")),
        to_bool(r.get("active",1)), r["created_at"], r.get("last_login"),
    ) for r in rows]


def map_roles(rows):
    cols = ["name","tier","default_open"]
    return cols, [(r["name"], r["tier"], to_bool(r.get("default_open",1))) for r in rows]


def map_module_permissions(rows):
    cols = ["role_id","module","can_read","can_write","can_delete","can_export","can_admin"]
    return cols, [(
        r["role_id"], r["module"],
        to_bool(r.get("can_read",0)), to_bool(r.get("can_write",0)),
        to_bool(r.get("can_delete",0)), to_bool(r.get("can_export",0)),
        to_bool(r.get("can_admin",0)),
    ) for r in rows]


def map_role_assignments(rows):
    cols = ["user_id","role_id","firm_id","assigned_at"]
    return cols, [(
        r["user_id"], r["role_id"],
        firm_or_default(r.get("firm_id")), r.get("assigned_at"),
    ) for r in rows]


def map_analyses(rows):
    cols = ["created_at","text","word_count","sentiment","score","tone",
            "entities","keywords","summary"]
    return cols, [(
        r["created_at"], r["text"], r.get("word_count"), r.get("sentiment"),
        r.get("score"), r.get("tone"), to_json(r.get("entities")),
        to_json(r.get("keywords")), r.get("summary"),
    ) for r in rows]


def map_intake_scans(rows):
    cols = ["firm_id","filename","raw_text","word_count","confidence","sentiment",
            "risk_score","risk_level","entities_json","form_fields","ocr_engine","created_at"]
    return cols, [(
        DEFAULT_FIRM, r.get("filename"), r.get("raw_text"), r.get("word_count"),
        r.get("confidence"), r.get("sentiment"), r.get("risk_score"),
        r.get("risk_level"), to_json(r.get("entities_json")),
        to_json(r.get("form_fields")), r.get("ocr_engine"), r.get("created_at"),
    ) for r in rows]


def map_discovery_files(rows):
    cols = ["firm_id","filename","original_name","file_hash","file_size","mime_type",
            "route","case_number","doc_date","status","privilege_flag","privilege_type",
            "privilege_confidence","requires_review","created_at"]
    return cols, [(
        DEFAULT_FIRM, r["filename"], r["original_name"], r.get("file_hash"),
        r.get("file_size"), r.get("mime_type"), r["route"], r.get("case_number"),
        to_date(r.get("doc_date")), r.get("status","queued"),
        to_bool(r.get("privilege_flag")) if r.get("privilege_flag") is not None else None,
        r.get("privilege_type"), r.get("privilege_confidence"),
        to_bool(r.get("requires_review")) if r.get("requires_review") is not None else None,
        r.get("created_at"),
    ) for r in rows]


def map_bates_configs(rows):
    cols = ["firm_id","set_id","prefix","start_num","padding","case_number","created_at"]
    return cols, [(
        DEFAULT_FIRM, r["set_id"], r.get("prefix",""), r.get("start_num",1),
        r.get("padding",6), r.get("case_number"), r.get("created_at"),
    ) for r in rows]


def map_bates_log(rows):
    cols = ["firm_id","set_id","doc_id","filename","bates_start","bates_end",
            "page_count","stamped_path","stamped_at"]
    return cols, [(
        DEFAULT_FIRM, r["set_id"], r.get("doc_id"), r["filename"],
        r["bates_start"], r["bates_end"], r.get("page_count",1),
        r.get("stamped_path"), r.get("stamped_at"),
    ) for r in rows]


def map_privilege_log(rows):
    cols = ["firm_id","case_number","doc_id","file_id","filename","bates","doc_date",
            "author","recipients","privilege_type","basis","is_privileged","confidence",
            "requires_review","risk_score","risk_label","ai_summary","ocr_pages","withheld_at"]
    return cols, [(
        DEFAULT_FIRM, r["case_number"], r.get("doc_id"), r.get("file_id"),
        r["filename"], r.get("bates"), to_date(r.get("doc_date")),
        r.get("author"), r.get("recipients"),
        r["privilege_type"], r["basis"],
        to_bool(r.get("is_privileged")) if r.get("is_privileged") is not None else None,
        r.get("confidence"),
        to_bool(r.get("requires_review")) if r.get("requires_review") is not None else None,
        r.get("risk_score"), r.get("risk_label"), r.get("ai_summary"),
        r.get("ocr_pages"), r.get("withheld_at"),
    ) for r in rows]


def map_transcriptions(rows):
    cols = ["firm_id","filename","file_type","duration_s","case_number","language",
            "transcript","segments","word_count","created_at"]
    return cols, [(
        DEFAULT_FIRM, r["filename"], r["file_type"], r.get("duration_s"),
        r.get("case_number"), r.get("language"), r.get("transcript"),
        to_json(r.get("segments")), r.get("word_count"), r.get("created_at"),
    ) for r in rows]


def map_parsed_messages(rows):
    cols = ["firm_id","source_file","format","case_number","thread_count",
            "msg_count","parsed_json","created_at"]
    return cols, [(
        DEFAULT_FIRM, r["source_file"], r["format"], r.get("case_number"),
        r.get("thread_count",0), r.get("msg_count",0),
        to_json(r.get("parsed_json")), r.get("created_at"),
    ) for r in rows]


def map_risk_assessments(rows):
    cols = ["assessed_at","risk_level","summary","signals","prediction","actions","alerted"]
    return cols, [(
        r["assessed_at"], r["risk_level"], r["summary"],
        to_json(r.get("signals","[]")), r.get("prediction"),
        to_json(r.get("actions")), to_bool(r.get("alerted",0)),
    ) for r in rows]


def map_webhook_subscriptions(rows):
    cols = ["event","url","label","active","created_at","last_fired","fire_count","last_status"]
    return cols, [(
        r["event"], r["url"], r.get("label",""), to_bool(r.get("active",1)),
        r["created_at"], r.get("last_fired"), r.get("fire_count",0), r.get("last_status"),
    ) for r in rows]


def map_notify_config(rows):
    cols = ["platform","label","webhook_url","active","created_at","last_used","send_count"]
    return cols, [(
        r["platform"], r.get("label",""), r["webhook_url"],
        to_bool(r.get("active",1)), r["created_at"],
        r.get("last_used"), r.get("send_count",0),
    ) for r in rows]


def map_redactions(rows):
    cols = ["id","firm_id","filename","original_filename","size_kb","style",
            "total_redactions","confidence_score","file_path","created_at"]
    return cols, [(
        r["id"], DEFAULT_FIRM, r.get("filename"), r.get("original_filename"),
        r.get("size_kb"), r.get("style"), r.get("total_redactions"),
        r.get("confidence_score"), r.get("file_path"), r.get("created_at"),
    ) for r in rows]


# ── main ──────────────────────────────────────────────────────────────────────

def run(pg_url):
    print(f"\n{'='*60}")
    print("  ParaIQ — SQLite → Postgres migration (v2)")
    print(f"{'='*60}\n")

    pg = psycopg2.connect(pg_url)

    def migrate(table, rows, mapper):
        if not rows:
            print(f"  {table}: empty")
            return
        cols, data = mapper(rows)
        n = bulk_insert(pg, table, cols, data)
        status = "✓" if n == len(rows) else "⚠"
        print(f"  {status} {table}: {n}/{len(rows)} rows")

    main = sqlite_conn(SQLITE_DBS["main"])
    demo = sqlite_conn(SQLITE_DBS["demo"])

    # Step 0 — ensure all firm_ids exist before FK constraints fire
    print("▶  Pre-flight: seeding firms table")
    firm_ids = collect_all_firm_ids(main, demo)
    ensure_firms(pg, firm_ids)

    # Step 1 — main analyses.db
    print("\n▶  analyses.db (main)")
    migrate("cases",                fetch_all(main, "cases"),                map_cases)
    migrate("case_documents",       fetch_all(main, "case_documents"),       map_case_documents)
    migrate("case_notes",           fetch_all(main, "case_notes"),           map_case_notes)
    migrate("correspondence",       fetch_all(main, "correspondence"),       map_correspondence)
    migrate("calendar_events",      fetch_all(main, "calendar_events"),      map_calendar_events)
    migrate("contacts",             fetch_all(main, "contacts"),             map_contacts)
    migrate("research_notes",       fetch_all(main, "research_notes"),       map_research_notes)
    migrate("reports",              fetch_all(main, "reports"),              map_reports)
    migrate("ai_config",            fetch_all(main, "ai_config"),            map_ai_config)
    migrate("client_portal_access", fetch_all(main, "client_portal_access"), map_client_portal_access)
    migrate("discovery_runs",       fetch_all(main, "discovery_runs"),       map_discovery_runs)
    migrate("depositions",          fetch_all(main, "depositions"),          map_depositions)
    migrate("motions",              fetch_all(main, "motions"),              map_motions)
    migrate("contracts",            fetch_all(main, "contracts"),            map_contracts)
    migrate("client_enclaves",      fetch_all(main, "client_enclaves"),      map_client_enclaves)
    migrate("privilege_verdicts",   fetch_all(main, "privilege_verdicts"),   map_privilege_verdicts)
    main.close()

    # Step 2 — demo1/analyses.db
    print("\n▶  backend/demo1/analyses.db")
    migrate("roles",                 fetch_all(demo, "roles"),                 map_roles)
    migrate("users",                 fetch_all(demo, "users"),                 map_users)
    migrate("module_permissions",    fetch_all(demo, "module_permissions"),    map_module_permissions)
    migrate("role_assignments",      fetch_all(demo, "role_assignments"),      map_role_assignments)
    migrate("analyses",              fetch_all(demo, "analyses"),              map_analyses)
    migrate("intake_scans",          fetch_all(demo, "intake_scans"),          map_intake_scans)
    migrate("discovery_files",       fetch_all(demo, "discovery_files"),       map_discovery_files)
    migrate("bates_configs",         fetch_all(demo, "bates_configs"),         map_bates_configs)
    migrate("bates_log",             fetch_all(demo, "bates_log"),             map_bates_log)
    migrate("privilege_log",         fetch_all(demo, "privilege_log"),         map_privilege_log)
    migrate("transcriptions",        fetch_all(demo, "transcriptions"),        map_transcriptions)
    migrate("parsed_messages",       fetch_all(demo, "parsed_messages"),       map_parsed_messages)
    migrate("risk_assessments",      fetch_all(demo, "risk_assessments"),      map_risk_assessments)
    migrate("webhook_subscriptions", fetch_all(demo, "webhook_subscriptions"), map_webhook_subscriptions)
    migrate("notify_config",         fetch_all(demo, "notify_config"),         map_notify_config)
    migrate("discovery_runs",        fetch_all(demo, "discovery_runs"),        map_discovery_runs)
    demo.close()

    # Step 3 — redactions.db
    print("\n▶  backend/demo1/redactions.db")
    red = sqlite_conn(SQLITE_DBS["redactions"])
    migrate("redactions", fetch_all(red, "redactions"), map_redactions)
    red.close()

    pg.close()
    print(f"\n{'='*60}")
    print("  ✅  Migration complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 03_migrate_data.py 'postgresql://...'")
        sys.exit(1)
    run(sys.argv[1])
