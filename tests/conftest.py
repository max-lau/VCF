"""
conftest.py — shared fixtures for all backend tests
"""
import os
import sys
import sqlite3
import pytest

# ── Environment setup (must happen before app import) ─────────────────────────
os.chdir('/root/nlp-portfolio')
os.environ['TESTING'] = '1'          # disables APScheduler in risk_watcher

from dotenv import load_dotenv
load_dotenv('/root/nlp-portfolio/.env')

from fastapi.testclient import TestClient
from backend.demo1.main import app

# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH       = 'backend/demo1/analyses.db'
TEST_USERNAME = '_pytest_user_'
TEST_PASSWORD = 'TestPass123!'
TEST_EMAIL    = '_pytest@test.internal'
API_KEY       = os.getenv('PARAIQ_API_KEY', '')

# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope='session')
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope='session')
def test_user(client):
    """Register a test user, yield its data, then clean up."""
    # Clean up any leftover from a previous failed run
    conn = sqlite3.connect(DB_PATH)
    old = conn.execute('SELECT id FROM users WHERE username=?', (TEST_USERNAME,)).fetchone()
    if old:
        conn.execute('DELETE FROM role_assignments WHERE user_id=?', (old[0],))
        conn.execute('DELETE FROM users WHERE id=?',                 (old[0],))
        conn.commit()
    conn.close()

    r = client.post('/auth/register', json={
        'username': TEST_USERNAME,
        'password': TEST_PASSWORD,
        'email':    TEST_EMAIL,
        'role':     'user',
        'firm_id':  'test',
    })
    assert r.status_code in (200, 201), f'Register failed: {r.text}'
    data = r.json()

    yield data

    # Teardown
    uid = data.get('user_id')
    conn = sqlite3.connect(DB_PATH)
    if uid:
        conn.execute('DELETE FROM role_assignments WHERE user_id=?', (uid,))
    conn.execute('DELETE FROM users WHERE username=?', (TEST_USERNAME,))
    conn.commit()
    conn.close()

@pytest.fixture(scope='session')
def auth_token(client, test_user):
    """Return a valid JWT for the test user."""
    r = client.post('/auth/login', json={
        'username': TEST_USERNAME,
        'password': TEST_PASSWORD,
    })
    assert r.status_code == 200, f'Login failed: {r.text}'
    return r.json()['token']

@pytest.fixture(scope='session')
def auth_headers(auth_token):
    """Full headers: Bearer JWT + API key."""
    return {
        'Authorization': f'Bearer {auth_token}',
        'X-API-Key':     API_KEY,
    }

@pytest.fixture(scope='session')
def key_only_headers():
    """Headers with API key only — no JWT."""
    return {'X-API-Key': API_KEY}
