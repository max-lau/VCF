"""
test_ai_smoke.py - Smoke tests for AI-powered endpoints.
Catches NameErrors, import bugs, and broken Claude wiring that
py_compile and tenant isolation tests would miss.

Run: cd /root/nlp-portfolio && .venv/bin/python3 -m pytest tests/test_ai_smoke.py -v
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, "..", ".env"))

BASE    = "http://localhost:5003"
API_KEY = os.environ.get("PARAIQ_API_KEY", "")

# Unique test user per CI run to avoid collisions
_TS = str(int(time.time()))
TEST_USERNAME = f"_smoke_{_TS}"
TEST_PASSWORD = "SmokeTest123!"
TEST_EMAIL    = f"_smoke_{_TS}@test.internal"


def _headers(token):
    return {"Authorization": f"Bearer {token}", "X-API-Key": API_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def auth_token():
    """Register a test user and return a JWT."""
    r = requests.post(f"{BASE}/auth/register", json={
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
        "email":    TEST_EMAIL,
        "role":     "user",
        "firm_id":  "default",
    })
    assert r.status_code in (200, 201), f"Register failed: {r.text}"
    r = requests.post(f"{BASE}/auth/login", json={
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
    })
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


class TestAnalyzeEndpoint:
    """POST /analyze — the core NLP endpoint. Must not crash with NameError."""

    def test_analyze_returns_success(self, auth_token):
        r = requests.post(
            f"{BASE}/analyze",
            headers=_headers(auth_token),
            json={"text": "The defendant, John Smith, breached the contract on January 15, 2024 by failing to deliver the agreed-upon goods worth $50,000."},
        )
        assert r.status_code == 200, f"/analyze returned {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "success", f"/analyze status was '{data.get('status')}' — expected 'success'. Error: {data.get('error', '')}"
        assert "sentiment" in data, "Missing 'sentiment' key in /analyze response"
        assert "entities" in data, "Missing 'entities' key in /analyze response"
        assert "summary" in data, "Missing 'summary' key in /analyze response"


class TestTimelineEndpoint:
    """POST /timeline — must persist work product and return valid JSON."""

    def test_timeline_returns_events(self, auth_token):
        r = requests.post(
            f"{BASE}/timeline",
            headers=_headers(auth_token),
            json={"text": "On March 3, 2024, the plaintiff filed a complaint. On April 10, 2024, the court denied the motion to dismiss. On May 20, 2024, the parties reached a settlement of $75,000."},
        )
        assert r.status_code == 200, f"/timeline returned {r.status_code}: {r.text}"
        data = r.json()
        assert "events" in data, "Missing 'events' key in /timeline response"
        assert isinstance(data["events"], list), "Expected 'events' to be a list"
        assert len(data["events"]) > 0, "Timeline should have at least 1 event"


class TestHealthEndpoint:
    """GET /health — server must be up and responding."""

    def test_health_returns_ok(self):
        r = requests.get(f"{BASE}/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
