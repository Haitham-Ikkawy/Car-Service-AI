"""Shared pytest fixtures for Car Service AI.

Tests are isolated from the real on-disk store: every fixture points the store's
persistence file at a per-test tmp path, so runs never touch ``data/store.json``.
No test makes live network calls (vPIC / Wikipedia) — only pure logic is covered.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

# Make ``import src.*`` work regardless of where pytest is invoked from.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.shared import store as store_module  # noqa: E402


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    """A brand-new, empty Store persisting to an isolated tmp file."""
    monkeypatch.setattr(store_module, "_DATA_FILE", tmp_path / "store.json")
    return store_module.Store()


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """A TestClient authenticated as a fixed user, with an isolated store.

    Clears the app's singleton store, forces the auth gate to pass, and redirects
    persistence to a tmp file.
    """
    monkeypatch.setattr(store_module, "_DATA_FILE", tmp_path / "store.json")
    s = store_module.store
    for attr, _key in s._PERSIST:
        getattr(s, attr).clear()

    import src.shared.utils.templating as tmpl
    monkeypatch.setattr(tmpl, "user", lambda request: "tester@example.com")
    s.login("tester@example.com", "Tester")

    from starlette.testclient import TestClient
    from src.app import app
    return TestClient(app)
