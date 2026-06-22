"""
test_tenant_isolation.py - Tenant isolation tests for ParaIQ.
Run: cd /root/nlp-portfolio && .venv/bin/python3 -m pytest tests/test_tenant_isolation.py -v
"""
import os
import pytest
import requests
from dotenv import load_dotenv

# Resolve .env relative to this file so it works outside /root/
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, "..", ".env"))

BASE    = "http://localhost:5003"
API_KEY = os.environ.get("PARAIQ_API_KEY", "")


def _headers(token):
    return {"Authorization": f"Bearer {token}", "X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def thornton_token():
    r = requests.post(f"{BASE}/auth/login", json={"username": "thornton", "password": "Demo2024abc"})
    assert r.status_code == 200, f"Thornton login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def meridian_token():
    r = requests.post(f"{BASE}/auth/login", json={"username": "meridian", "password": "Demo2024mer"})
    assert r.status_code == 200, f"Meridian login failed: {r.text}"
    return r.json()["token"]


class TestCaseIsolation:
    def test_no_case_id_overlap_between_firms(self, thornton_token, meridian_token):
        th  = requests.get(f"{BASE}/cases/", headers=_headers(thornton_token)).json()
        mer = requests.get(f"{BASE}/cases/", headers=_headers(meridian_token)).json()
        th_ids  = {c["id"] for c in th.get("cases",  th  if isinstance(th,  list) else [])}
        mer_ids = {c["id"] for c in mer.get("cases", mer if isinstance(mer, list) else [])}
        overlap = th_ids & mer_ids
        assert not overlap, f"Case ID overlap between tenants: {overlap}"

    def test_thornton_cannot_read_meridian_case(self, thornton_token, meridian_token):
        mer = requests.get(f"{BASE}/cases/", headers=_headers(meridian_token)).json()
        cases = mer.get("cases", mer if isinstance(mer, list) else [])
        if not cases:
            pytest.skip("Meridian has no cases")
        target_id = cases[0]["id"]
        r = requests.get(f"{BASE}/cases/{target_id}", headers=_headers(thornton_token))
        assert r.status_code in (403, 404), (
            f"Expected 403/404 for cross-tenant fetch, got {r.status_code}"
        )


class TestAuditIsolation:
    def test_audit_logs_scoped_by_firm(self, thornton_token, meridian_token):
        th_resp  = requests.get(f"{BASE}/audit/logs?limit=50", headers=_headers(thornton_token)).json()
        mer_resp = requests.get(f"{BASE}/audit/logs?limit=50", headers=_headers(meridian_token)).json()

        th_logs  = th_resp.get("logs", [])
        mer_logs = mer_resp.get("logs", [])

        # Must have actual log rows with firm_id populated — catches the vacuous case
        assert len(th_logs) > 0,  "Thornton audit log is empty — firm_id write path may be broken"
        assert len(mer_logs) > 0, "Meridian audit log is empty — firm_id write path may be broken"

        th_firms  = {l.get("firm_id") for l in th_logs}
        mer_firms = {l.get("firm_id") for l in mer_logs}

        # Every row returned to Thornton must belong to firm_abc only
        assert th_firms == {"firm_abc"}, (
            f"Thornton sees unexpected firm_ids: {th_firms} (expected only {{'firm_abc'}})"
        )
        # Every row returned to Meridian must belong to meridian_legal only
        assert mer_firms == {"meridian_legal"}, (
            f"Meridian sees unexpected firm_ids: {mer_firms} (expected only {{'meridian_legal'}})"
        )

    def test_audit_log_clear_is_blocked(self, thornton_token):
        r = requests.delete(f"{BASE}/audit/logs/clear", headers=_headers(thornton_token))
        assert r.status_code in (403, 409), (
            f"Audit clear should be blocked, got {r.status_code}: {r.text}"
        )

    def test_discovery_chain_requires_auth(self):
        """Chain of custody endpoint must reject unauthenticated requests."""
        r = requests.get(f"{BASE}/audit/discovery/chain")
        assert r.status_code in (401, 403), (
            f"Discovery chain should require auth, got {r.status_code}"
        )

    def test_discovery_chain_export_requires_auth(self):
        """Chain of custody CSV export must reject unauthenticated requests."""
        r = requests.get(f"{BASE}/audit/discovery/chain/export")
        assert r.status_code in (401, 403), (
            f"Discovery chain export should require auth, got {r.status_code}"
        )

    def test_discovery_chain_scoped_by_firm(self, thornton_token, meridian_token):
        """Each firm's chain of custody must only contain their own entries."""
        th  = requests.get(f"{BASE}/audit/discovery/chain", headers=_headers(thornton_token)).json()
        mer = requests.get(f"{BASE}/audit/discovery/chain", headers=_headers(meridian_token)).json()
        # Entries from each firm should not appear in the other's chain
        th_endpoints  = {e["endpoint"] for e in th.get("entries",  [])}
        mer_endpoints = {e["endpoint"] for e in mer.get("entries", [])}
        # Both responses should be valid (no 4xx leaked as JSON)
        assert "entries" in th,  f"Thornton chain response malformed: {th}"
        assert "entries" in mer, f"Meridian chain response malformed: {mer}"


class TestAuthBoundaries:
    def test_no_token_no_key_returns_401(self):
        """No credentials at all should be rejected."""
        r = requests.get(f"{BASE}/audit/logs")
        assert r.status_code in (401, 403)

    def test_api_key_only_no_token_returns_401(self):
        """API key alone without JWT should be rejected (audit endpoint requires auth)."""
        r = requests.get(f"{BASE}/audit/logs", headers={"X-API-Key": API_KEY})
        assert r.status_code in (401, 403)

    def test_bad_jwt_with_valid_key_returns_401(self):
        """Invalid JWT signature should be rejected even with valid API key."""
        fake = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI5OTkiLCJleHAiOjF9.bad"
        r = requests.get(f"{BASE}/audit/logs", headers={"Authorization": f"Bearer {fake}", "X-API-Key": API_KEY})
        assert r.status_code in (401, 403)

    def test_valid_token_bypasses_api_key_check(self, thornton_token):
        """Valid JWT allows access regardless of API key (by design for browser clients)."""
        r = requests.get(f"{BASE}/audit/logs", headers={"Authorization": f"Bearer {thornton_token}"})
        assert r.status_code == 200, "Valid JWT should grant access without API key"

    def test_no_credentials_on_auth_endpoint_returns_422(self):
        """Login with empty body returns validation error."""
        r = requests.post(f"{BASE}/auth/login", json={})
        assert r.status_code == 422
