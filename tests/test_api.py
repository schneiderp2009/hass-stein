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


async def test_get_reports_sends_buids_as_json_array_and_bearer():
    session = _FakeSession(body=[{"id": 1}])
    api = SteinApi("API-TOKEN", session)

    result = await api.get_reports([19], 0)

    assert result == [{"id": 1}]
    call = session.calls[0]
    assert call["url"] == "https://stein.app/api/api/ext/reports/full"
    assert call["headers"]["Authorization"] == "Bearer API-TOKEN"
    assert call["params"]["buIds"] == "[19]"
    assert call["params"]["updatedSince"] == "1970-01-01T00:00:00Z"


async def test_get_reports_multiple_bus_without_since():
    session = _FakeSession()
    api = SteinApi("t", session)

    await api.get_reports([19, 20])

    params = session.calls[0]["params"]
    assert params == {"buIds": "[19,20]"}


async def test_get_reports_400_carries_status_and_body():
    session = _FakeSession(status=400, body={"message": "JSON array expected"})
    api = SteinApi("t", session)

    with pytest.raises(SteinApiError) as exc:
        await api.get_reports([19], 0)
    assert exc.value.status == 400
    assert "JSON array expected" in str(exc.value)


async def test_get_reports_401_is_auth_error():
    session = _FakeSession(status=401, body={"message": "Fehlerhafte Zugangsdaten"})
    api = SteinApi("t", session)

    with pytest.raises(SteinAuthError):
        await api.get_reports([19], 0)
