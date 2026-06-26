"""
test_auth.py — POST /auth/login and GET /auth/me/permissions
"""
import pytest
from tests.conftest import TEST_USERNAME, TEST_PASSWORD, API_KEY


class TestLogin:
    def test_login_success(self, client, test_user):
        r = client.post('/auth/login', json={
            'username': TEST_USERNAME,
            'password': TEST_PASSWORD,
        })
        assert r.status_code == 200
        data = r.json()
        assert data['success'] is True
        assert 'token' in data
        assert data['username'] == TEST_USERNAME
        assert 'role' in data
        assert 'tier' in data
        assert 'permissions' in data

    def test_login_wrong_password(self, client, test_user):
        r = client.post('/auth/login', json={
            'username': TEST_USERNAME,
            'password': 'definitely_wrong_password',
        })
        assert r.status_code == 401
        assert 'Invalid' in r.json().get('detail', '')

    def test_login_unknown_user(self, client):
        r = client.post('/auth/login', json={
            'username': 'no_such_user_xyz',
            'password': 'anything',
        })
        assert r.status_code == 401

    def test_login_missing_password(self, client):
        r = client.post('/auth/login', json={'username': TEST_USERNAME})
        assert r.status_code == 422   # Pydantic validation

    def test_login_missing_username(self, client):
        r = client.post('/auth/login', json={'password': TEST_PASSWORD})
        assert r.status_code == 422

    def test_login_empty_body(self, client):
        r = client.post('/auth/login', json={})
        assert r.status_code == 422

    def test_login_returns_firm_id(self, client, test_user):
        r = client.post('/auth/login', json={
            'username': TEST_USERNAME,
            'password': TEST_PASSWORD,
        })
        assert 'firm_id' in r.json()

    def test_login_permissions_snapshot_in_response(self, client, test_user):
        r = client.post('/auth/login', json={
            'username': TEST_USERNAME,
            'password': TEST_PASSWORD,
        })
        perms = r.json().get('permissions', {})
        assert 'role'    in perms
        assert 'tier'    in perms
        assert 'modules' in perms


class TestPermissions:
    def test_permissions_valid_jwt(self, client, auth_headers):
        r = client.get('/auth/me/permissions', headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert 'role'    in data
        assert 'tier'    in data
        assert 'modules' in data

    def test_permissions_no_auth(self, client):
        r = client.get('/auth/me/permissions')
        assert r.status_code in (401, 403)

    def test_permissions_invalid_jwt(self, client, key_only_headers):
        headers = {**key_only_headers, 'Authorization': 'Bearer not.a.real.token'}
        r = client.get('/auth/me/permissions', headers=headers)
        assert r.status_code in (401, 403)

    def test_permissions_malformed_bearer(self, client, key_only_headers):
        headers = {**key_only_headers, 'Authorization': 'NotBearer token'}
        r = client.get('/auth/me/permissions', headers=headers)
        assert r.status_code in (401, 403)


class TestLogout:
    def test_logout_success(self, client, test_user, key_only_headers):
        """Login, logout — should return success."""
        from tests.conftest import TEST_USERNAME, TEST_PASSWORD
        r = client.post('/auth/login', json={
            'username': TEST_USERNAME,
            'password': TEST_PASSWORD,
        })
        assert r.status_code == 200
        token = r.json()['token']
        headers = {**key_only_headers, 'Authorization': f'Bearer {token}'}
        r2 = client.post('/auth/logout', headers=headers)
        assert r2.status_code == 200
        assert r2.json().get('success') is True

    def test_blocklisted_token_rejected(self, client, test_user, key_only_headers):
        """Login, logout, then reuse the same token — must be rejected with 401."""
        from tests.conftest import TEST_USERNAME, TEST_PASSWORD
        r = client.post('/auth/login', json={
            'username': TEST_USERNAME,
            'password': TEST_PASSWORD,
        })
        assert r.status_code == 200
        token = r.json()['token']
        headers = {**key_only_headers, 'Authorization': f'Bearer {token}'}

        # Logout invalidates the token
        r2 = client.post('/auth/logout', headers=headers)
        assert r2.status_code == 200

        # Reuse the same token — must now be rejected
        r3 = client.get('/auth/me/permissions', headers=headers)
        assert r3.status_code in (401, 403), (
            f"Expected 401/403 for blocklisted token, got {r3.status_code}: {r3.text}"
        )

    def test_logout_without_auth_rejected(self, client, key_only_headers):
        """Logout with no JWT should fail."""
        r = client.post('/auth/logout', headers=key_only_headers)
        assert r.status_code in (401, 403)

    def test_logout_with_invalid_token_rejected(self, client, key_only_headers):
        """Logout with a malformed token should fail."""
        headers = {**key_only_headers, 'Authorization': 'Bearer not.a.valid.token'}
        r = client.post('/auth/logout', headers=headers)
        assert r.status_code in (401, 403)
