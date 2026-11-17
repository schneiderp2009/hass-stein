"""Tests for SteinApi.get_reports (no network, fake aiohttp session)."""
import json

import pytest

from custom_components.stein.api import SteinApi, SteinApiError, SteinAuthError


class _FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return self._body

    async def text(self):
        return json.dumps(self._body)


class _FakeSession:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body if body is not None else []
        self.calls = []

    def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return _FakeResp(self.status, self.body)


async def test_get_reports_sends_unix_timestamp_and_bearer():
    session = _FakeSession(body=[{"id": 1}])
    api = SteinApi("API-TOKEN", session)

    result = await api.get_reports(1700000000)

    assert result == [{"id": 1}]
    call = session.calls[0]
    assert call["url"] == "https://stein.app/api/api/ext/reports/full"
    assert call["headers"]["Authorization"] == "Bearer API-TOKEN"
    assert call["params"] == {"updatedSince": 1700000000}


async def test_get_reports_403_carries_status():
    session = _FakeSession(status=403, body={"detail": "Forbidden"})
    api = SteinApi("t", session)

    with pytest.raises(SteinApiError) as exc:
        await api.get_reports(0)
    assert exc.value.status == 403


async def test_get_reports_400_carries_status_and_body():
    session = _FakeSession(status=400, body={"message": "invalid updatedSince"})
    api = SteinApi("t", session)

    with pytest.raises(SteinApiError) as exc:
        await api.get_reports(0)
    assert exc.value.status == 400
    assert "invalid updatedSince" in str(exc.value)


async def test_get_reports_401_is_auth_error():
    session = _FakeSession(status=401, body={"message": "Fehlerhafte Zugangsdaten"})
    api = SteinApi("t", session)

    with pytest.raises(SteinAuthError):
        await api.get_reports(0)
