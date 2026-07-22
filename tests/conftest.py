"""
conftest.py — shared fixtures for all backend tests.

All tests run against the LIVE server (http://127.0.0.1:5003).
We do NOT import backend.demo1.main or use TestClient — on a 2GB VPS,
importing main.py loads torch/sentence-transformers/chromadb (~700MB)
which triggers the OOM killer and crashes uvicorn.
"""
import os
import pytest
import requests
from dotenv import load_dotenv

# ── Environment setup ─────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
os.environ['TESTING'] = '1'

load_dotenv(os.path.join(_ROOT, '.env'))

# ── Constants ─────────────────────────────────────────────────────────────────
BASE          = "http://127.0.0.1:5003"
DB_PATH       = 'backend/demo1/analyses.db'
TEST_USERNAME        = '_pytest_user_'
TEST_PASSWORD        = 'TestPass123!'
TEST_EMAIL           = '_pytest@test.internal'
SUPER_USERNAME       = '_pytest_super_'
SUPER_PASSWORD       = 'SuperPass123!'
SUPER_EMAIL          = '_pytest_super@test.internal'
API_KEY              = os.getenv('PARAIQ_API_KEY', '')


# ── Live-server HTTP client (drop-in replacement for TestClient) ──────────────
class LiveClient:
    """Wraps requests.Session with a base URL. Same API as fastapi.TestClient."""
    def __init__(self, base_url=BASE):
        self._base = base_url.rstrip('/')
        self._s = requests.Session()

    def _url(self, path):
        if path.startswith('http'):
            return path
        return f"{self._base}{path}"

    def get(self, path, **kw):
        return self._s.get(self._url(path), **kw)

    def post(self, path, **kw):
        return self._s.post(self._url(path), **kw)

    def put(self, path, **kw):
        return self._s.put(self._url(path), **kw)

    def delete(self, path, **kw):
        return self._s.delete(self._url(path), **kw)

    def patch(self, path, **kw):
        return self._s.patch(self._url(path), **kw)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope='session')
def client():
    return LiveClient()


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
    })
    assert r.status_code in (200, 201), f'Register failed: {r.text}'
    data = r.json()

    yield data

    # Teardown
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
def super_user(client):
    """Register a super-admin test user for monitor/admin endpoints.

    The public /auth/register endpoint only allows roles ('user','admin'),
    so we register as admin and then promote the row to paraiq_super directly
    in the DB. This keeps production auth restrictions intact while giving
    tests access to cross-tenant monitor endpoints.
    """
    try:
        import backend.demo1.pg as _pg
        _pg.init_pool()
        from backend.demo1.pg import get_conn as _get_conn
        with _get_conn('waw_vcf') as _conn:
            old = _conn.execute('SELECT id FROM users WHERE username=%s', (SUPER_USERNAME,)).fetchone()
            if old:
                _conn.execute('DELETE FROM role_assignments WHERE user_id=%s', (old['id'],))
                _conn.execute('DELETE FROM users WHERE id=%s', (old['id'],))
    except Exception as e:
        print(f'[conftest] super-user pre-cleanup warning: {e}')

    r = client.post('/auth/register', json={
        'username': SUPER_USERNAME,
        'password': SUPER_PASSWORD,
        'email':    SUPER_EMAIL,
        'role':     'admin',
    })
    assert r.status_code in (200, 201), f'Super register failed: {r.text}'
    data = r.json()
    uid = data.get('user_id')

    # Promote to paraiq_super; public register endpoint cannot assign this role.
    try:
        import backend.demo1.pg as _pg
        _pg.init_pool()
        from backend.demo1.pg import get_conn as _get_conn
        with _get_conn('waw_vcf') as _conn:
            _conn.execute(
                "UPDATE users SET role='paraiq_super' WHERE id=%s",
                (uid,),
            )
    except Exception as e:
        print(f'[conftest] super-user promotion warning: {e}')

    yield data

    try:
        import backend.demo1.pg as _pg
        _pg.init_pool()
        from backend.demo1.pg import get_conn as _get_conn
        with _get_conn('waw_vcf') as _conn:
            if uid:
                _conn.execute('DELETE FROM role_assignments WHERE user_id=%s', (uid,))
            _conn.execute('DELETE FROM users WHERE username=%s', (SUPER_USERNAME,))
    except Exception as e:
        print(f'[conftest] super-user teardown warning: {e}')


@pytest.fixture(scope='session')
def super_token(client, super_user):
    """Return a valid JWT for the super-admin test user."""
    r = client.post('/auth/login', json={
        'username': SUPER_USERNAME,
        'password': SUPER_PASSWORD,
    })
    assert r.status_code == 200, f'Super login failed: {r.text}'
    return r.json()['token']


@pytest.fixture(scope='session')
def super_auth_headers(super_token):
    """Full headers for super-admin."""
    return {
        'Authorization': f'Bearer {super_token}',
        'X-API-Key':     API_KEY,
    }


@pytest.fixture(scope='session')
def key_only_headers():
    """Headers with API key only — no JWT."""
    return {'X-API-Key': API_KEY}
