"""Boot an embedded Postgres (via pgserver) and run the pytest suite against it.

This script:
  1. Starts a pgserver Postgres instance in a temp data dir.
  2. Exports DATABASE_URL and PARAIQ_API_KEY.
  3. Initializes the pg pool and the app's tables as main.py would at startup.
  4. Invokes pytest programmatically.
  5. Tears down on exit.
"""
import os
import sys
import tempfile

os.environ["PARAIQ_API_KEY"] = "test_dummy_key_for_pytest"

# Start embedded postgres
import pgserver

data_dir = tempfile.mkdtemp(prefix="pgserver_")
print(f"[boot] pgserver data dir: {data_dir}", flush=True)
pg = pgserver.get_server(data_dir, cleanup_mode="delete")
pg.ensure_pgdata_inited()
pg.ensure_postgres_running()
# get_uri() returns a libpq connection URI string
db_url = pg.get_uri()
os.environ["DATABASE_URL"] = db_url
print("[boot] DATABASE_URL set", flush=True)

# Init the pg pool and app tables
import backend.demo1.pg as _pg
_pg.init_pool()
print("[boot] pg pool initialized", flush=True)

# Initialize the same tables that main.py creates at startup.
# Note: case_management.init_case_db() is currently a no-op; the cases table
# must already exist from a base-schema migration or manual setup.
from backend.demo1.database import init_db
from backend.demo1.audit_trail import init_audit_table
from backend.demo1.webhook import init_webhook_table
from backend.demo1.custom_entities import init_custom_entity_table
from backend.demo1.auth import init_auth_table
from backend.demo1.slack_teams import init_notify_table
from backend.demo1.fine_tune import init_model_table
from backend.demo1.ocr_intake import init_intake_table
from backend.demo1.intake_jobs import init_intake_jobs_table
from backend.demo1.redaction import init_redaction_table
from backend.demo1.media_transcription import init_transcription_table
from backend.demo1.message_parser import init_messages_table
from backend.demo1.vcf_account import init_vcf_account_table
from backend.demo1.db_enclaves import init_enclave_tables
from backend.demo1.esignature import init_esign_tables
from backend.demo1.client_portal import init_tables as init_portal_tables
from backend.demo1.prompt_guard import init_guard_table
from backend.demo1.ai_isolation import init_isolation_tables
from backend.demo1.ai_output_validation import init_validation_tables
from backend.demo1.lead_crm import init_crm_tables
from backend.demo1.communications import init_communications_tables

init_db()
init_audit_table()
init_webhook_table()
init_custom_entity_table()
init_auth_table()
init_notify_table()
init_model_table()
init_intake_table()
init_intake_jobs_table()
init_redaction_table()
init_transcription_table()
init_messages_table()
init_vcf_account_table()
init_enclave_tables()
init_esign_tables()
init_portal_tables()
init_guard_table()
init_isolation_tables()
init_validation_tables()
init_crm_tables()
init_communications_tables()
print("[boot] App tables initialized", flush=True)

# Run pytest
import pytest

rc = pytest.main(["tests/", "-x", "--tb=short", "-q"])
print(f"[boot] pytest rc={rc}", flush=True)

# Stop server
try:
    pg.cleanup()
except Exception:
    pass
sys.exit(rc)
