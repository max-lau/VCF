"""
backfill_vcf_emails.py
======================
Assign a dedicated VCF email to every case that doesn't have one.
Safe to run multiple times — it skips cases that already have a vcf_email.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill missing VCF emails")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be assigned without writing")
    args = parser.parse_args()

    load_env()

    domain = os.environ.get("VCF_DEDICATED_EMAIL_DOMAIN", "").strip()
    if not domain:
        print("ERROR: VCF_DEDICATED_EMAIL_DOMAIN is not set in .env")
        return 1

    from backend.demo1.pg import init_pool, get_conn
    from backend.demo1.case_management import generate_vcf_email

    init_pool()

    with get_conn("default") as conn:
        rows = conn.execute(
            "SELECT id, case_number, client_name FROM cases WHERE vcf_email IS NULL OR vcf_email = '' ORDER BY id"
        ).fetchall()

        if not rows:
            print("No cases need a VCF email. Done.")
            return 0

        mode = "Would assign" if args.dry_run else "Assigning"
        print(f"{mode} VCF emails to {len(rows)} case(s)...")
        for r in rows:
            email = generate_vcf_email(conn)
            print(f"  {r['case_number']} ({r['client_name']}): {email}")
            if not args.dry_run:
                conn.execute(
                    "UPDATE cases SET vcf_email = %s, updated_at = NOW() WHERE id = %s",
                    (email, r["id"]),
                )

        if args.dry_run:
            print("\nDry-run complete. No changes were made.")
            conn.rollback()
        else:
            conn.commit()
            print("\nDone. Hard-refresh the prep sheet to see the email.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
