"""
test_vcf_smoke.py - End-to-end smoke tests for VCFClaimsIQ core flows.

Run with the backend server on http://127.0.0.1:5003:
    venv/Scripts/python -m pytest tests/test_vcf_smoke.py -v
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, "..", ".env"))

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
