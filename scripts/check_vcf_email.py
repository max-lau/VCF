"""
check_vcf_email.py
==================
Diagnostic: verify VCF dedicated email configuration and sequence.
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
    load_env()

    domain = os.environ.get("VCF_DEDICATED_EMAIL_DOMAIN", "").strip()
    prefix = os.environ.get("VCF_DEDICATED_EMAIL_PREFIX", "vcfclaim").strip()

    print("VCF dedicated email diagnostic")
    print("=" * 40)
    print(f"VCF_DEDICATED_EMAIL_DOMAIN : {domain or '(NOT SET)'}")
    print(f"VCF_DEDICATED_EMAIL_PREFIX : {prefix or '(default: vcfclaim)'}")

    if not domain:
        print("\nERROR: domain is not set. Add VCF_DEDICATED_EMAIL_DOMAIN=wawvcf.com to .env and restart backend.")
        return 1

    from backend.demo1.pg import init_pool, get_conn
    from backend.demo1.case_management import generate_vcf_email

    init_pool()

    with get_conn("default") as conn:
        # Check sequence
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname='vcf_email_seq' AND relkind='S') AS exists"
        ).fetchone()
        seq_exists = row["exists"] if row else False
        print(f"vcf_email_seq exists       : {seq_exists}")

        if not seq_exists:
            print("\nERROR: sequence vcf_email_seq is missing.")
            print("Run in Supabase SQL Editor: CREATE SEQUENCE IF NOT EXISTS vcf_email_seq START 1;")
            return 1

        # Try generating one
        sample = generate_vcf_email(conn)
        print(f"Sample generated email     : {sample}")

        # Cases with missing vcf_email
        rows = conn.execute(
            "SELECT id, case_number, client_name FROM cases WHERE vcf_email IS NULL OR vcf_email = '' ORDER BY id"
        ).fetchall()
        print(f"\nCases with empty vcf_email : {len(rows)}")
        for r in rows:
            print(f"  id={r['id']}  {r['case_number']}  {r['client_name']}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
