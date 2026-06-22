"""
conftest.py — shared fixtures for all backend tests
"""
import os
import sys
import pytest

# ── Environment setup (must happen before app import) ─────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
os.environ['TESTING'] = '1'          # disables APScheduler in risk_watcher

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, '.env'))

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
    try:
        import backend.demo1.pg as _pg
        _pg.init_pool()
        from backend.demo1.pg import get_conn as _get_conn
        with _get_conn('default') as _conn:
            old = _conn.execute('SELECT id FROM users WHERE username=%s', (TEST_USERNAME,)).fetchone()
            if old:
                _conn.execute('DELETE FROM role_assignments WHERE user_id=%s', (old['id'],))
                _conn.execute('DELETE FROM users WHERE id=%s', (old['id'],))
    except Exception as e:
        print(f'[conftest] pre-cleanup warning: {e}')

    r = client.post('/auth/register', json={
        'username': TEST_USERNAME,
        'password': TEST_PASSWORD,
        'email':    TEST_EMAIL,
        'role':     'user',
        'firm_id':  'default',
    })
    assert r.status_code in (200, 201), f'Register failed: {r.text}'
    data = r.json()

    yield data

    # Teardown — use Supabase pg connection
    uid = data.get('user_id')
    try:
        import backend.demo1.pg as _pg
        _pg.init_pool()
        from backend.demo1.pg import get_conn as _get_conn
        with _get_conn('default') as _conn:
            if uid:
                _conn.execute('DELETE FROM role_assignments WHERE user_id=%s', (uid,))
            _conn.execute('DELETE FROM users WHERE username=%s', (TEST_USERNAME,))
    except Exception as e:
        print(f'[conftest] teardown warning: {e}')

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
