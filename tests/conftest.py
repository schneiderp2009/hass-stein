"""Shared fixtures for STEIN tests."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/stein in every test."""
    yield


def make_report(rid=1, finished=False, bu_id=19, **extra):
    """Build a report dict shaped like STEIN /reports/full (schema 2.0)."""
    report = {
        "id": rid,
        "schemaVersion": "2.0",
        "finished": finished,
        "einsatzStichwort": "THL Unwetter",
        "schadenort": "Schwäbisch Gmünd, Remsstraße 1",
        "schaden": "Baum auf Fahrbahn",
        "einsatzbeginn": "2026-11-17T10:00:00Z",
        "einsatzende": None,
        "anzahlEk1": 2,
        "anzahlEk2": 5,
        "anzahlEk3": None,
        "assets": [{"id": 340, "name": "GKW"}, {"id": 341, "name": "MTW"}],
        "bu": {"id": bu_id, "code": "SGD", "name": "OV Schwäbisch Gmünd"},
        "lastModified": "2026-11-17T10:05:00Z",
    }
    report.update(extra)
    return report
