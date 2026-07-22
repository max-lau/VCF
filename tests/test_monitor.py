"""
test_monitor.py — /monitor/health, /monitor/api-stats, /monitor/events
"""
import pytest


class TestMonitorHealth:
    def test_health_valid_auth(self, client, super_auth_headers):
        r = client.get('/monitor/health', headers=super_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert 'cpu'       in data
        assert 'memory'    in data
        assert 'disk'      in data
        assert 'processes' in data

    def test_health_cpu_is_number(self, client, super_auth_headers):
        r = client.get('/monitor/health', headers=super_auth_headers)
        cpu = r.json().get('cpu')
        assert isinstance(cpu, (int, float))
        assert 0 <= cpu <= 100

    def test_health_memory_has_expected_keys(self, client, super_auth_headers):
        r = client.get('/monitor/health', headers=super_auth_headers)
        mem = r.json().get('memory', {})
        assert 'percent'  in mem
        assert 'used_gb'  in mem
        assert 'total_gb' in mem

    def test_health_no_auth_rejected(self, client):
        r = client.get('/monitor/health')
        assert r.status_code in (401, 403)

    def test_health_wrong_api_key(self, client, super_auth_headers):
        bad = {**super_auth_headers, 'X-API-Key': 'wrong-key'}
        r = client.get('/monitor/health', headers=bad)
        # Should still work if JWT is valid (middleware accepts either)
        assert r.status_code in (200, 401)


class TestMonitorApiStats:
    def test_api_stats_default(self, client, super_auth_headers):
        r = client.get('/monitor/api-stats', headers=super_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert 'total_requests'  in data
        assert 'server_errors'   in data
        assert 'error_rate_pct'  in data
        assert 'avg_response_ms' in data
        assert 'top_endpoints'   in data

    def test_api_stats_custom_hours(self, client, super_auth_headers):
        r = client.get('/monitor/api-stats?hours=6', headers=super_auth_headers)
        assert r.status_code == 200
        assert r.json()['period_hours'] == 6

    def test_api_stats_invalid_hours(self, client, super_auth_headers):
        r = client.get('/monitor/api-stats?hours=9999', headers=super_auth_headers)
        assert r.status_code == 422   # gt validator rejects > 168

    def test_api_stats_no_auth(self, client):
        r = client.get('/monitor/api-stats')
        assert r.status_code in (401, 403)


class TestMonitorEvents:
    def test_events_default(self, client, super_auth_headers):
        r = client.get('/monitor/events', headers=super_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert 'total'    in data
        assert 'page'     in data
        assert 'per_page' in data
        assert 'events'   in data
        assert isinstance(data['events'], list)

    def test_events_pagination(self, client, super_auth_headers):
        r = client.get('/monitor/events?page=1&per_page=10', headers=super_auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data['page']     == 1
        assert data['per_page'] == 10
        assert len(data['events']) <= 10

    def test_events_filter_errors_only(self, client, super_auth_headers):
        r = client.get('/monitor/events?status=errors', headers=super_auth_headers)
        assert r.status_code == 200
        for ev in r.json()['events']:
            assert ev['status_code'] >= 400

    def test_events_filter_ok_only(self, client, super_auth_headers):
        r = client.get('/monitor/events?status=ok', headers=super_auth_headers)
        assert r.status_code == 200
        for ev in r.json()['events']:
            assert ev['status_code'] < 400

    def test_events_no_auth(self, client):
        r = client.get('/monitor/events')
        assert r.status_code in (401, 403)
