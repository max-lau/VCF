"""
cleanup_duplicate_scans.py
──────────────────────────
Remove duplicate intake-scan rows and their linked case_documents.

Duplicate groups are identified by:
  • content_hash (when not null) — exact file duplicates
  • filename     (when content_hash is null) — legacy scans uploaded before
    the content_hash column was populated

In each group the scan linked to a case is preferred; otherwise the earliest
scan (MIN id) is kept. Newer/unlinked duplicates are deleted.

Usage:
    venv/Scripts/python scripts/cleanup_duplicate_scans.py
    venv/Scripts/python scripts/cleanup_duplicate_scans.py --execute
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from backend.demo1.pg import init_pool, get_conn


def _delete_group(conn, firm_id, ids_to_delete):
    doc_rows = conn.execute(
        "SELECT id, file_url FROM case_documents WHERE firm_id=%s AND scan_id = ANY(%s)",
        (firm_id, ids_to_delete)
    ).fetchall()
    doc_ids = [r["id"] for r in doc_rows]
    storage_paths = [r["file_url"] for r in doc_rows if r["file_url"]]

    if doc_ids:
        conn.execute("DELETE FROM case_documents WHERE id = ANY(%s)", (doc_ids,))

    scan_rows = conn.execute(
        "SELECT file_url FROM intake_scans WHERE id = ANY(%s)", (ids_to_delete,)
    ).fetchall()
    storage_paths.extend([r["file_url"] for r in scan_rows if r["file_url"]])

    conn.execute("DELETE FROM intake_scans WHERE id = ANY(%s)", (ids_to_delete,))
    conn.commit()
    return len(doc_ids), storage_paths


def _process_groups(conn, firm_id, groups, key_name, dry_run):
    scans_deleted = 0
    docs_deleted = 0
    storage_paths = []

    for g in groups:
        key_value = g[key_name]
        rows = conn.execute(
            """SELECT id, case_id, file_url FROM intake_scans
               WHERE firm_id = %s AND {} = %s
               ORDER BY (case_id IS NULL), id""".format(key_name),
            (firm_id, key_value)
        ).fetchall()

        if len(rows) <= 1:
            continue

        keep_id = rows[0]["id"]
        ids_to_delete = [r["id"] for r in rows[1:]]

        if dry_run:
            print(f"[DRY-RUN] firm={firm_id} {key_name}={key_value} keep={keep_id} scans={len(ids_to_delete)}")
        else:
            d, paths = _delete_group(conn, firm_id, ids_to_delete)
            docs_deleted += d
            storage_paths.extend(paths)
            print(f"[EXECUTED] firm={firm_id} {key_name}={key_value} keep={keep_id} scans={len(ids_to_delete)} docs={d}")

        scans_deleted += len(ids_to_delete)

    return scans_deleted, docs_deleted, storage_paths


def cleanup(dry_run: bool = True):
    init_pool()

    with get_conn("default") as conn:
        firms = [r["firm_id"] if hasattr(r, "keys") else r[0]
                 for r in conn.execute("SELECT DISTINCT firm_id FROM intake_scans").fetchall()]

    total_scans_deleted = 0
    total_docs_deleted = 0
    all_storage_paths = []

    for firm_id in firms:
        firm_id = str(firm_id)
        with get_conn(firm_id) as conn:
            # Phase 1: exact duplicates by content_hash
            hash_groups = conn.execute("""
                SELECT content_hash FROM intake_scans
                WHERE firm_id = %s AND content_hash IS NOT NULL
                GROUP BY content_hash
                HAVING COUNT(*) > 1
            """, (firm_id,)).fetchall()

            s, d, p = _process_groups(conn, firm_id, hash_groups, "content_hash", dry_run)
            total_scans_deleted += s
            total_docs_deleted += d
            all_storage_paths.extend(p)

            # Phase 2: legacy duplicates with NULL content_hash
            file_groups = conn.execute("""
                SELECT filename FROM intake_scans
                WHERE firm_id = %s AND content_hash IS NULL
                GROUP BY filename
                HAVING COUNT(*) > 1
            """, (firm_id,)).fetchall()

            s, d, p = _process_groups(conn, firm_id, file_groups, "filename", dry_run)
            total_scans_deleted += s
            total_docs_deleted += d
            all_storage_paths.extend(p)

    if not dry_run and all_storage_paths:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        if supabase_url and supabase_key:
            try:
                from supabase import create_client
                supabase = create_client(supabase_url, supabase_key)
                for i in range(0, len(all_storage_paths), 100):
                    chunk = all_storage_paths[i:i+100]
                    try:
                        supabase.storage.from_("vcf-documents").remove(chunk)
                    except Exception as e:
                        print(f"[WARN] Storage cleanup chunk failed: {e}")
            except Exception as e:
                print(f"[WARN] Could not clean up Supabase storage: {e}")
        else:
            print("[WARN] SUPABASE_URL/SUPABASE_SERVICE_KEY not set; skipping storage cleanup")

    print(f"\nSummary: {'dry-run' if dry_run else 'executed'}")
    print(f"  Firms checked: {len(firms)}")
    print(f"  Intake scans to delete: {total_scans_deleted}")
    if not dry_run:
        print(f"  Case documents deleted: {total_docs_deleted}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deduplicate intake scans")
    parser.add_argument("--execute", action="store_true", help="Actually delete duplicates (default is dry-run)")
    args = parser.parse_args()
    cleanup(dry_run=not args.execute)
