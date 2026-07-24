#!/usr/bin/env python3
"""
bulk_cleanup_duplicate_scans.py
===============================
One-off / reusable cleanup for the VCF intake document tables.

Identifies duplicate intake_scans and case_documents rows and removes the
later copies, plus their linked records and Supabase storage objects.

Logic
-----
- intake_scans:     keep earliest id per (firm_id, case_id, filename)
- case_documents:   keep earliest id per (firm_id, case_id, document_name)
- test files:       any filename/document_name starting with 'test_' is removed

Safety
------
- Always run with --dry-run first.
- intake_scan rows are only deleted if no remaining case_document references
  them.
- Storage removal is best-effort; database rows are deleted regardless.

Usage
-----
    python scripts/cleanup_duplicate_scans.py --dry-run
    python scripts/cleanup_duplicate_scans.py --execute
"""

import os
import sys
import argparse
from typing import List, Dict
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv(".env")

DSN = os.environ.get("DATABASE_URL")
if not DSN:
    print("DATABASE_URL not set in environment", file=sys.stderr)
    sys.exit(1)

TEST_PREFIXES = ("test_",)


def connect():
    return psycopg2.connect(DSN, cursor_factory=RealDictCursor)


def find_intake_scan_dups(cur) -> List[Dict]:
    cur.execute(
        """
        SELECT id, firm_id, case_id, filename, content_hash, file_url,
               ROW_NUMBER() OVER (
                   PARTITION BY firm_id, COALESCE(case_id, 0), filename
                   ORDER BY id ASC
               ) AS rn
        FROM intake_scans
        """
    )
    rows = cur.fetchall()
    return [r for r in rows if r["rn"] > 1 or r["filename"].lower().startswith(TEST_PREFIXES)]


def find_case_document_dups(cur) -> List[Dict]:
    cur.execute(
        """
        SELECT id, firm_id, case_id, document_name, content_hash, scan_id, file_url,
               ROW_NUMBER() OVER (
                   PARTITION BY firm_id, COALESCE(case_id, 0), document_name
                   ORDER BY id ASC
               ) AS rn
        FROM case_documents
        """
    )
    rows = cur.fetchall()
    return [r for r in rows if r["rn"] > 1 or r["document_name"].lower().startswith(TEST_PREFIXES)]


def protected_scan_ids(cur, doc_ids: List[int]) -> set:
    if not doc_ids:
        return set()
    cur.execute(
        "SELECT scan_id FROM case_documents WHERE id <> ALL(%s) AND scan_id IS NOT NULL",
        (doc_ids,),
    )
    return {r["scan_id"] for r in cur.fetchall()}


def delete_records(cur, scan_ids: List[int], doc_ids: List[int]) -> None:
    if doc_ids:
        cur.execute("DELETE FROM case_documents WHERE id = ANY(%s)", (doc_ids,))
    if scan_ids:
        cur.execute("DELETE FROM intake_scans WHERE id = ANY(%s)", (scan_ids,))


def remove_storage(file_urls: List[str]) -> int:
    removed = 0
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key or not file_urls:
        return 0
    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
        for url in set(file_urls):
            try:
                supabase.storage.from_("vcf-documents").remove([url])
                removed += 1
            except Exception as e:
                print(f"  Could not remove storage object {url}: {e}")
    except Exception as e:
        print(f"  Supabase storage client failed: {e}")
    return removed


def main():
    parser = argparse.ArgumentParser(description="Bulk cleanup duplicate VCF intake scans/documents")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted")
    parser.add_argument("--execute", action="store_true", help="Actually delete the rows")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.print_help()
        sys.exit(1)

    conn = connect()
    cur = conn.cursor()

    scan_dups = find_intake_scan_dups(cur)
    doc_dups = find_case_document_dups(cur)

    scan_ids_to_delete = [r["id"] for r in scan_dups]
    doc_ids_to_delete = [r["id"] for r in doc_dups]

    # Do not delete a scan that is still referenced by a kept case_document.
    protected = protected_scan_ids(cur, doc_ids_to_delete)
    safe_scan_ids = [sid for sid in scan_ids_to_delete if sid not in protected]

    # Gather storage URLs from records we are deleting.
    storage_urls = []
    for r in scan_dups:
        if r["id"] in safe_scan_ids and r["file_url"]:
            storage_urls.append(r["file_url"])
    for r in doc_dups:
        if r["file_url"]:
            storage_urls.append(r["file_url"])

    print(f"Intake scan duplicates to delete: {len(safe_scan_ids)}")
    for r in scan_dups:
        if r["id"] in safe_scan_ids:
            print(f"  scan id={r['id']} case={r['case_id']} {r['filename']}")

    print(f"\nCase document duplicates to delete: {len(doc_ids_to_delete)}")
    for r in doc_dups:
        print(f"  doc id={r['id']} case={r['case_id']} {r['document_name']}")

    print(f"\nStorage objects to remove: {len(set(storage_urls))}")

    if args.dry_run:
        print("\n--dry-run: no rows deleted.")
        cur.close()
        conn.close()
        return

    if args.execute:
        delete_records(cur, safe_scan_ids, doc_ids_to_delete)
        conn.commit()
        removed = remove_storage(storage_urls)
        print(f"\nDeleted {len(safe_scan_ids)} intake scans, {len(doc_ids_to_delete)} case documents.")
        print(f"Removed {removed} storage objects.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
