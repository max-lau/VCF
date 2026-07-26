"""
test_vcf_smoke.py - End-to-end smoke tests for VCFClaimsIQ core flows.

Run with the backend server on http://127.0.0.1:5003:
    venv/Scripts/python -m pytest tests/test_vcf_smoke.py -v
"""
import hashlib
import json
import os
import time
import pytest
import requests
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, "..", ".env"))

# Light-weight DB access for fixtures that bypass the OCR pipeline.
import backend.demo1.pg as _pg
_pg.init_pool()
from backend.demo1.pg import get_conn

BASE    = "http://127.0.0.1:5003"
API_KEY = os.environ.get("PARAIQ_API_KEY", "")

# Unique per test-run so repeated smoke runs do not collide on case_number.
CASE_NUMBER = f"VCF-SMOKE-{int(time.time())}"


def _headers(token):
    return {"Authorization": f"Bearer {token}", "X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def admin_token():
    """Register and log in a test admin user."""
    username = "_vcf_smoke_admin_"
    password = "SmokePass123!"
    email    = "vcf_smoke@test.internal"

    # Register (idempotent-ish: previous run may leave user behind)
    r = requests.post(f"{BASE}/auth/register", json={
        "username": username,
        "password": password,
        "email":    email,
        "role":     "admin",
    })
    assert r.status_code in (200, 201, 409), f"Register failed: {r.text}"

    # Login
    r = requests.post(f"{BASE}/auth/login", json={
        "username": username,
        "password": password,
    })
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def case_id(admin_token):
    """Create a VCF claim and return its id."""
    r = requests.post(f"{BASE}/cases/", headers=_headers(admin_token), json={
        "case_number": CASE_NUMBER,
        "client_name": "Smoke Test Client",
        "client_email": "smoke@test.internal",
        "claim_stage": "intake",
        "vcf_status": "pending",
        "exposure_location": "World Trade Center",
        "presence_dates": "2001-09-11",
        "wtc_health_program": True,
    })
    assert r.status_code in (200, 201), f"Create case failed: {r.text}"
    data = r.json()
    assert "vcf_email" in data
    assert data["vcf_email"].endswith("@wawvcf.com")
    return data["case_id"]


class TestVCFClaimLifecycle:
    def test_get_case_detail(self, admin_token, case_id):
        r = requests.get(f"{BASE}/cases/{case_id}", headers=_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["case_number"] == CASE_NUMBER
        assert data["client_name"] == "Smoke Test Client"
        assert data["firm_id"] == "waw_vcf"
        assert data.get("vcf_email", "").endswith("@wawvcf.com")

    def test_get_case_checklist(self, admin_token, case_id):
        r = requests.get(f"{BASE}/vcf/cases/{case_id}/checklist", headers=_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "intake"
        assert len(data["items"]) > 0

    def test_transition_stage(self, admin_token, case_id):
        r = requests.post(
            f"{BASE}/vcf/cases/{case_id}/stage",
            headers=_headers(admin_token),
            json={"to_stage": "eligibility_review", "note": "Intake complete"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["from_stage"] == "intake"
        assert data["to_stage"] == "eligibility_review"

    def test_stage_transition_seeds_checklist(self, admin_token, case_id):
        r = requests.get(f"{BASE}/vcf/cases/{case_id}/checklist", headers=_headers(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "eligibility_review"
        item_keys = {item["item_key"] for item in data["items"]}
        assert "presence_proof" in item_keys
        assert "medical_record" in item_keys


class TestVCFCommunications:
    def test_create_communication(self, admin_token, case_id):
        r = requests.post(
            f"{BASE}/communications",
            headers=_headers(admin_token),
            json={
                "case_id": case_id,
                "direction": "inbound",
                "channel": "email",
                "party_type": "client",
                "party_name": "Smoke Test Client",
                "sender": "smoke@test.internal",
                "recipient": "intake@wawvcf.com",
                "subject": "Medical records",
                "body": "Please send records.",
            },
        )
        assert r.status_code == 200, f"Create communication failed: {r.text}"
        data = r.json()
        assert "communication_id" in data

    def test_list_case_communications(self, admin_token, case_id):
        r = requests.get(
            f"{BASE}/cases/{case_id}/communications",
            headers=_headers(admin_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1


class TestVCFDeadlines:
    def test_create_deadline(self, admin_token, case_id):
        r = requests.post(
            f"{BASE}/vcf/cases/{case_id}/deadlines",
            headers=_headers(admin_token),
            json={
                "deadline_type": "missing_info_response",
                "due_date": "2026-12-31",
                "description": "Respond to VCF request",
            },
        )
        assert r.status_code == 200, f"Create deadline failed: {r.text}"
        data = r.json()
        assert data["deadline"]["case_id"] == case_id

    def test_list_case_deadlines(self, admin_token, case_id):
        r = requests.get(
            f"{BASE}/vcf/cases/{case_id}/deadlines",
            headers=_headers(admin_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1


class TestVCFHealth:
    def test_health_returns_ok(self):
        r = requests.get(f"{BASE}/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"


class TestVCFIntakeToPrepFlow:
    """OCR intake scan → /vcf/from-scan → prep sheet → status sync."""

    def test_scan_bridges_to_prep_sheet(self, admin_token):
        # 1. Create a VCF case with identity signals the scanner would extract.
        case_number = f"VCF-SCAN-{int(time.time())}"
        r = requests.post(f"{BASE}/cases/", headers=_headers(admin_token), json={
            "case_number": case_number,
            "client_name": "Smoke Scan Client",
            "client_email": "smokescan@test.internal",
            "date_of_birth": "1960-04-15",
            "ssn_last4": "9876",
            "claim_stage": "intake",
            "vcf_status": "pending",
        })
        assert r.status_code in (200, 201), f"Create case failed: {r.text}"
        case = r.json()
        case_id = case["case_id"]

        # 2. Seed an intake_scans row with Vision-structured form_fields.
        #    This bypasses the actual OCR/AI call while exercising the bridge code.
        form_fields = {
            "client_name": "Smoke Scan Client",
            "date_of_birth": "1960-04-15",
            "ssn_last4": "9876",
            "phone": "718-555-0199",
            "email": "smokescan@test.internal",
            "address": "100 Test St, New York, NY",
            "preferred_language": "English",
            "exposure_location": "World Trade Center",
            "presence_dates": "2001-09-11 to 2001-09-12",
            "medical_conditions": ["asthma"],
            "doc_type": "intake_form",
            "name_order": "given_first",
            "key_facts": ["Worked near WTC on 9/11."],
        }
        content_hash = hashlib.sha256(os.urandom(32)).hexdigest()
        with get_conn("waw_vcf") as conn:
            scan_row = conn.execute(
                """INSERT INTO intake_scans
                   (firm_id, filename, raw_text, confidence, ocr_engine, form_fields, content_hash)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                ("waw_vcf", "smoke_intake.pdf", "Smoke Scan Client DOB 1960-04-15",
                 0.95, "claude-vision", json.dumps(form_fields), content_hash),
            ).fetchone()
            scan_id = scan_row["id"]

        try:
            # 3. Bridge the scan to a ClientData payload.
            r = requests.post(
                f"{BASE}/vcf/from-scan/{scan_id}",
                headers=_headers(admin_token),
            )
            assert r.status_code == 200, f"from-scan failed: {r.text}"
            data = r.json()
            assert data["success"] is True
            assert data["source"] == "vision_form_fields"
            client = data["client"]
            assert client["first_name"] == "Smoke Scan"
            assert client["last_name"] == "Client"
            assert client["date_of_birth"] == "1960-04-15"

            # 4. Create a VCF prep sheet from the bridged client data.
            r = requests.post(
                f"{BASE}/vcf/prep",
                headers=_headers(admin_token),
                json={
                    "case_id": case_id,
                    "client": client,
                    "demo_mode": True,
                },
            )
            assert r.status_code == 200, f"prep create failed: {r.text}"
            prep = r.json()
            assert prep["success"] is True
            prep_id = prep["prep_id"]
            assert prep["prep"]["account_information"]["email"].endswith("@wawvcf.com")

            # 5. Mark the prep sheet as account-created and verify case sync.
            r = requests.patch(
                f"{BASE}/vcf/prep/{prep_id}/status",
                headers=_headers(admin_token),
                json={"status": "account_created", "vcf_username": "smoke.scan.client"},
            )
            assert r.status_code == 200, f"prep status update failed: {r.text}"
            assert r.json()["status"] == "account_created"

            r = requests.get(
                f"{BASE}/vcf/cases/{case_id}/prep-status",
                headers=_headers(admin_token),
            )
            assert r.status_code == 200, f"prep-status failed: {r.text}"
            status_data = r.json()
            assert status_data["status"] == "account_created"
            assert status_data["case_vcf_account_created"] is True
        finally:
            # Best-effort cleanup so repeated runs stay tidy.
            with get_conn("waw_vcf") as conn:
                conn.execute("DELETE FROM vcf_account_prep WHERE firm_id=%s AND case_id=%s", ("waw_vcf", case_id))
                conn.execute("DELETE FROM vcf_deadlines WHERE firm_id=%s AND case_id=%s", ("waw_vcf", case_id))
                conn.execute("DELETE FROM case_notes WHERE firm_id=%s AND case_id=%s", ("waw_vcf", case_id))
                conn.execute("DELETE FROM intake_scans WHERE firm_id=%s AND id=%s", ("waw_vcf", scan_id))
                conn.execute("DELETE FROM cases WHERE firm_id=%s AND id=%s", ("waw_vcf", case_id))


class TestVCFEmailEndpoints:
    """Smoke checks for the email intake/OCR loop endpoints."""

    def test_email_intake_list(self, admin_token):
        r = requests.get(f"{BASE}/email/intake", headers=_headers(admin_token))
        assert r.status_code == 200, f"email/intake failed: {r.text}"
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_email_log_list(self, admin_token):
        r = requests.get(f"{BASE}/email/log", headers=_headers(admin_token))
        assert r.status_code == 200, f"email/log failed: {r.text}"
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_email_poll_now_is_reachable(self, admin_token):
        # Without a connected account this may report "no accounts", but it must
        # not crash with a 500.
        r = requests.post(f"{BASE}/email/poll-now", headers=_headers(admin_token))
        assert r.status_code in (200, 202, 400, 404), f"poll-now crashed: {r.text}"
