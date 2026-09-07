"""Route-level tests via Starlette TestClient (no live network)."""
from __future__ import annotations


def test_diagnose_requires_auth():
    """Unauthenticated page routes redirect to /login."""
    from starlette.testclient import TestClient
    from src.app import app
    c = TestClient(app)
    r = c.get("/diagnose", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_authed_pages_render(auth_client):
    for path in ("/diagnose", "/my-diagnoses", "/settings", "/chat", "/maintenance"):
        assert auth_client.get(path).status_code == 200, path


def test_settings_shows_accessibility_tab(auth_client):
    """The Accessibility tab button must be present (was previously commented out)."""
    html = auth_client.get("/settings").text
    assert 'data-tab="tab-a11y"' in html
    assert 'id="tab-a11y"' in html


def test_create_and_list_diag_session(auth_client):
    r = auth_client.post("/api/diag-sessions/new",
                         json={"vehicle": {"brand": "Audi", "model": "A4"}, "problem": "noise"})
    assert r.status_code == 200 and r.json()["ok"] is True
    listing = auth_client.get("/api/diag-sessions").json()
    assert listing["ok"] is True and len(listing["sessions"]) == 1


def test_vin_route_rejects_invalid_without_network(auth_client):
    """An invalid VIN is rejected by format check before any upstream call."""
    r = auth_client.get("/api/vehicles/vin?vin=NOTAVIN")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and "VIN" in body["message"]


def test_diagnose_complete_rejects_short_problem(auth_client):
    r = auth_client.post("/api/diagnose/complete", json={"problem": "x"})
    assert r.status_code == 400
