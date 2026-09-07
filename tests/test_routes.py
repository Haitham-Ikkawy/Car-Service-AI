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


def test_accessibility_tab_currently_disabled(auth_client):
    """The Accessibility tab is intentionally gated off (item 3) — its button and
    panel are commented out in settings.html, so neither should render."""
    html = auth_client.get("/settings").text
    assert 'data-tab="tab-a11y"' not in html
    assert 'id="tab-a11y"' not in html


def test_create_and_list_diag_session(auth_client):
    r = auth_client.post("/api/diag-sessions/new",
                         json={"vehicle": {"brand": "Audi", "model": "A4"}, "problem": "noise"})
    assert r.status_code == 200 and r.json()["ok"] is True
    listing = auth_client.get("/api/diag-sessions").json()
    assert listing["ok"] is True and len(listing["sessions"]) == 1


def test_vin_route_currently_disabled(auth_client):
    """VIN lookup is temporarily gated off (future work) — the route is commented
    out, so it 404s. The decoder logic (vehicle_api.decode_vin) is kept intact."""
    r = auth_client.get("/api/vehicles/vin?vin=1HGCM82633A004352")
    assert r.status_code == 404


def test_vin_decoder_logic_still_intact():
    """The underlying VIN validation still works (ready to re-enable)."""
    from src.car_database import vehicle_api as v
    assert v._valid_vin("1HGCM82633A004352") is True
    assert v._valid_vin("NOTAVIN") is False


def test_diagnose_complete_rejects_short_problem(auth_client):
    r = auth_client.post("/api/diagnose/complete", json={"problem": "x"})
    assert r.status_code == 400


def test_can_delete_diagnosing_session(auth_client):
    """A session left in 'diagnosing' (e.g. a failed run) must still be deletable (item 1)."""
    sid = auth_client.post("/api/diag-sessions/new", json={"problem": "p"}).json()["session"]["id"]
    auth_client.post(f"/api/diag-sessions/{sid}/update", json={"status": "diagnosing"})
    d = auth_client.post(f"/api/diag-sessions/{sid}/delete")
    assert d.status_code == 200 and d.json()["ok"] is True


def test_chat_shows_diagnosis_result_panel(auth_client):
    """Continuing chat from a completed diagnosis shows the result panel on the
    right, using the workspace .dz-ws-result-* layout."""
    from src.shared.store import store
    u = "tester@example.com"
    chat = store.new_chat(u, vehicle={"brand": "Honda", "model": "Civic"})
    sess = store.new_diag_session(u, vehicle={"brand": "Honda", "model": "Civic"}, problem="brakes")
    store.update_diag_session(u, sess["id"], {"diagnosis": {
        "problem": "Warped Front Brake Rotors", "urgency": "medium", "confidence": 80,
        "summary": "s", "causes": ["a"], "steps": ["b"], "parts": ["c"],
        "cost": "$250 - $350", "time": "1 - 2 hours", "center": "shop", "tips": ["t"]}})
    store.link_diag_session_chat(u, sess["id"], chat["id"])
    html = auth_client.get("/chat?chat_id=" + chat["id"]).text
    assert 'data-has-diagnosis="1"' in html
    assert "DIAGNOSIS RESULT" in html and "dz-sevmeter" in html
    assert "Warped Front Brake Rotors" in html
    assert "/static/ai_report/diagnose.css" in html


def test_chat_without_diagnosis_has_no_result_panel(auth_client):
    """A plain chat (not from a diagnosis) shows no result panel."""
    html = auth_client.get("/chat").text
    assert 'data-has-diagnosis="1"' not in html


def test_my_diagnoses_is_paginated(auth_client):
    """More than one page of history shows pagination controls; page 2 loads (item 1)."""
    for i in range(12):
        auth_client.post("/api/diag-sessions/new",
                         json={"vehicle": {"brand": "Honda", "model": "Civic"}, "problem": f"issue {i}"})
    html = auth_client.get("/my-diagnoses").text
    assert "md-pagination" in html and "Page 1 of 2" in html
    # Per-car photo (not a brand logo) is used for the card image (item 5).
    assert "/api/vehicles/image?make=Honda" in html
    assert auth_client.get("/my-diagnoses?page=2").status_code == 200


def test_service_locked_session_delete_still_blocked(auth_client):
    """The real safeguard remains: a session tied to an active service request can't be deleted."""
    sid = auth_client.post("/api/diag-sessions/new", json={"problem": "p"}).json()["session"]["id"]
    auth_client.post(f"/api/diag-sessions/{sid}/service-request", json={"active": True})
    d = auth_client.post(f"/api/diag-sessions/{sid}/delete")
    assert d.status_code == 409
