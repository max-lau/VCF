"""Boot an embedded Postgres (via pgserver) and run the pytest suite against it.

This script:
  1. Starts a pgserver Postgres instance in a temp data dir.
  2. Exports DATABASE_URL and PARAIQ_API_KEY.
  3. Initializes the pg pool and the app's schema as main.py would.
  4. Invokes pytest programmatically.
  5. Tears down on exit.
"""
import os
import sys
import logging
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
print(f"[boot] DATABASE_URL set", flush=True)

# Init the pg pool and app schema
import backend.demo1.pg as _pg
_pg.init_pool()
print("[boot] pg pool initialized", flush=True)

# Initialize the app schema (tables). The app expects tables to exist.
try:
    from backend.demo1.casedb import CaseDB
    CaseDB()
    print("[boot] CaseDB initialized", flush=True)
except Exception as e:
    print(f"[boot] CaseDB init note: {e}", flush=True)

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
