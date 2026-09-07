"""Store logic: unique/descriptive titles, session lifecycle, persistence."""
from __future__ import annotations

from src.shared import store as store_module


def test_new_sessions_get_distinct_titles(fresh_store):
    s = fresh_store
    v = {"brand": "Audi", "model": "A4"}
    a = s.new_diag_session("u@x.com", vehicle=v, problem="Overheating")
    b = s.new_diag_session("u@x.com", vehicle=v, problem="Overheating")
    assert a["title"] != b["title"]
    assert b["title"].endswith("(2)")


def test_title_from_diagnosis_is_descriptive(fresh_store):
    s = fresh_store
    sess = s.new_diag_session("u@x.com", vehicle={"brand": "Audi", "model": "A4"},
                              problem="noise")
    s.set_session_title_from_diagnosis("u@x.com", sess["id"], {"problem": "Worn brake pads"})
    updated = s.diag_session("u@x.com", sess["id"])
    assert updated["title"] == "Audi A4 — Worn brake pads"


def test_rename_marks_custom_and_survives_update(fresh_store):
    s = fresh_store
    sess = s.new_diag_session("u@x.com", vehicle={"brand": "Kia", "model": "Rio"}, problem="x")
    s.rename_diag_session("u@x.com", sess["id"], "My custom name")
    # A later vehicle/problem update must NOT overwrite the user's chosen name.
    s.update_diag_session("u@x.com", sess["id"], {"problem": "different problem"})
    assert s.diag_session("u@x.com", sess["id"])["title"] == "My custom name"


def test_delete_session(fresh_store):
    s = fresh_store
    sess = s.new_diag_session("u@x.com", problem="p")
    assert s.delete_diag_session("u@x.com", sess["id"]) is True
    assert s.diag_session("u@x.com", sess["id"]) is None


def test_persistence_roundtrip(tmp_path, monkeypatch):
    """Data written by one Store is reloaded by the next (survives 'restart')."""
    monkeypatch.setattr(store_module, "_DATA_FILE", tmp_path / "store.json")
    s1 = store_module.Store()
    s1.new_diag_session("u@x.com", vehicle={"brand": "Ford", "model": "Focus"}, problem="stalls")
    # A fresh instance pointed at the same file must see the session.
    s2 = store_module.Store()
    sessions = s2.diag_sessions("u@x.com")
    assert len(sessions) == 1
    assert sessions[0]["vehicle"]["brand"] == "Ford"


def test_ids_are_unique_and_increment(fresh_store):
    s = fresh_store
    ids = {s.new_diag_session("u@x.com", problem="p")["id"] for _ in range(5)}
    assert len(ids) == 5
