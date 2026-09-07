"""In-memory data store for Car Service AI.

No database is used on purpose (graduation project requirement): all temporary
data lives in process memory and is keyed by the logged-in user's session.

NOTE: data is lost on server restart. This is fine for the project scope.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("car_ai.store")

# Per-user data is persisted here so diagnoses, sessions and progress survive a
# server restart (item: "continue diagnosis" must be saved per user). The file
# lives outside the source tree layout under a gitignored ``data/`` folder.
_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "store.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _now_iso() -> str:
    """ISO timestamp with seconds — used for chat message timestamps."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _relative_time(dt_str: str) -> str:
    """Convert a datetime string to a human-readable relative time."""
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        now = datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()
        if seconds < 60:
            return "Just now"
        if seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins} min ago" if mins > 1 else "1 min ago"
        if seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hours ago" if hours > 1 else "1 hour ago"
        days = int(seconds / 86400)
        if days == 1:
            return "Yesterday"
        if days < 7:
            return f"{days} days ago"
        return dt.strftime("%b %d, %Y")
    except Exception:
        return dt_str


class Store:
    """Thread-safe in-memory store. One instance is shared app-wide."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[str, dict[str, Any]] = {}          # user -> profile
        self._vehicles: dict[str, dict[str, Any]] = {}       # user -> vehicle
        self._chats: dict[str, list[dict[str, Any]]] = {}    # user -> chat threads
        self._active: dict[str, str] = {}                    # user -> active chat id
        self._diagnoses: dict[str, list[dict[str, Any]]] = {}  # user -> diagnosis reports
        self._maintenance: dict[str, list[dict[str, Any]]] = {}  # user -> reminders
        self._settings: dict[str, dict[str, Any]] = {}       # user -> settings
        self._twin: dict[str, dict[str, Any]] = {}           # user -> digital twin analysis
        self._diag_sessions: dict[str, list[dict[str, Any]]] = {}  # user -> diagnosis sessions
        self._diag_active: dict[str, str] = {}               # user -> active diagnosis session id
        self._seq = 0
        self._load()

    # ---------- persistence ----------
    # Snapshot of every per-user collection. Written after each mutation and
    # reloaded on startup so a user can resume exactly where they left off.
    _PERSIST = (
        ("_users", "users"), ("_vehicles", "vehicles"), ("_chats", "chats"),
        ("_active", "active"), ("_diagnoses", "diagnoses"),
        ("_maintenance", "maintenance"), ("_settings", "settings"),
        ("_diag_sessions", "diag_sessions"), ("_diag_active", "diag_active"),
    )

    def _load(self) -> None:
        """Load the persisted snapshot on startup (best-effort)."""
        try:
            if not _DATA_FILE.exists():
                return
            data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
            for attr, key in self._PERSIST:
                if key in data and isinstance(data[key], dict):
                    setattr(self, attr, data[key])
            self._seq = int(data.get("seq", 0))
            log.info("Store: restored persisted data for %d user(s).", len(self._users))
        except Exception as exc:  # noqa: BLE001 — never let bad data block startup
            log.warning("Store: could not load persisted data: %s: %s",
                        type(exc).__name__, exc)

    def _save(self) -> None:
        """Persist the current snapshot atomically (best-effort).

        Called while ``self._lock`` is already held by the calling thread, so the
        dicts are read consistently. Failures are swallowed — persistence is a
        convenience, never a hard dependency.
        """
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {key: getattr(self, attr) for attr, key in self._PERSIST}
            data["seq"] = self._seq
            tmp = _DATA_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(_DATA_FILE)
        except Exception as exc:  # noqa: BLE001
            log.warning("Store: could not persist data: %s: %s", type(exc).__name__, exc)

    # ---------- helpers ----------
    def _new_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{datetime.now():%Y%m%d}-{self._seq:04d}"

    def _unique_title(self, user: str, base: str, exclude_id: str | None = None) -> str:
        """Return ``base`` made unique among this user's sessions.

        Duplicate diagnosis names are confusing, so a numeric suffix is added
        (``"… (2)"``) when the base title already exists. Caller must hold the lock.
        """
        base = (base or "New Diagnosis").strip()
        existing = {s.get("title") for s in self._diag_sessions.get(user, [])
                    if s.get("id") != exclude_id}
        if base not in existing:
            return base
        i = 2
        while f"{base} ({i})" in existing:
            i += 1
        return f"{base} ({i})"

    def _default_settings(self) -> dict[str, Any]:
        return {
            "theme": "dark",
            "accent": "",
            "language": "en",
            "gemini_key": "",
            "model": "",
            "streaming": True,
            "notifications": {"reminders": True, "reports": True, "tips": False},
            "a11y": {"reduce_motion": False, "high_contrast": False, "font_size": "normal"},
        }

    # ---------- users ----------
    def login(self, email: str, name: str, *, provider: str = "",
              provider_id: str = "", picture: str = "") -> dict[str, Any]:
        """Create the user if new, otherwise return the existing profile.

        ``provider`` / ``provider_id`` / ``picture`` are only stored when the
        account is first created or when the existing profile is missing them —
        email/password accounts have empty provider fields.
        """
        key = email.lower()
        with self._lock:
            if key not in self._users:
                self._users[key] = {
                    "email": email,
                    "name": name or email.split("@")[0],
                    "provider": provider,
                    "provider_id": provider_id,
                    "picture": picture,
                }
            else:
                profile = self._users[key]
                if picture and not profile.get("picture"):
                    profile["picture"] = picture
                if provider and not profile.get("provider"):
                    profile["provider"] = provider
                if provider_id and not profile.get("provider_id"):
                    profile["provider_id"] = provider_id
            self._users[key]["last_login"] = _now()
            self._save()
            return self._users[key]

    def user(self, email: str) -> dict[str, Any] | None:
        return self._users.get(email.lower())

    # ---------- vehicle ----------
    def set_vehicle(self, user: str, vehicle: dict[str, Any]) -> None:
        with self._lock:
            vehicle = dict(vehicle)
            vehicle["updated"] = _now()
            self._vehicles[user] = vehicle
            # The stored AI analysis is stale once the vehicle data changes.
            self._twin.pop(user, None)
            self._save()

    def vehicle(self, user: str) -> dict[str, Any] | None:
        return self._vehicles.get(user)

    # ---------- digital twin ----------
    def twin(self, user: str) -> dict[str, Any] | None:
        return self._twin.get(user)

    def set_twin(self, user: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._twin[user] = data

    def invalidate_twin(self, user: str) -> None:
        with self._lock:
            self._twin.pop(user, None)

    # ---------- settings ----------
    def settings(self, user: str) -> dict[str, Any]:
        with self._lock:
            if user not in self._settings:
                self._settings[user] = self._default_settings()
            return self._settings[user]

    def save_settings(self, user: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self._settings.get(user, self._default_settings())
            for key in ("theme", "accent", "language", "gemini_key", "model", "streaming"):
                if key in data:
                    current[key] = data[key]
            if isinstance(data.get("notifications"), dict):
                current["notifications"].update(data["notifications"])
            if isinstance(data.get("a11y"), dict):
                current["a11y"].update(data["a11y"])
            self._settings[user] = current
            self._save()
            return current

    def get_lang(self, user: str) -> str:
        """The user's preferred UI language (falls back to 'en')."""
        lang = self.settings(user).get("language")
        return lang if lang in ("en", "ar") else "en"

    def set_lang(self, user: str, code: str) -> str:
        """Persist the UI language choice for the user."""
        code = code if code in ("en", "ar") else "en"
        with self._lock:
            current = self._settings.get(user, self._default_settings())
            current["language"] = code
            self._settings[user] = current
        return code

    # ---------- chat ----------
    def ensure_chat(self, user: str) -> dict[str, Any]:
        with self._lock:
            chats = self._chats.setdefault(user, [])
            active = self._active.get(user)
            if active:
                for c in chats:
                    if c["id"] == active:
                        return c
            chat = {"id": self._new_id("CHAT"), "title": "New conversation",
                    "messages": [], "created": _now(), "updated": _now(),
                    "vehicle": {"brand": "", "model": ""}, "diag_id": None}
            chats.insert(0, chat)
            self._active[user] = chat["id"]
            self._save()
            return chat

    def new_chat(self, user: str, vehicle: dict | None = None,
                 diag_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            chat = {"id": self._new_id("CHAT"), "title": "New conversation",
                    "messages": [], "created": _now(), "updated": _now(),
                    "vehicle": vehicle or {"brand": "", "model": ""},
                    "diag_id": diag_id}
            self._chats.setdefault(user, []).insert(0, chat)
            self._active[user] = chat["id"]
            self._save()
            return chat

    def set_active_chat(self, user: str, chat_id: str) -> dict[str, Any] | None:
        with self._lock:
            for c in self._chats.get(user, []):
                if c["id"] == chat_id:
                    self._active[user] = chat_id
                    return c
        return None

    def chat(self, user: str, chat_id: str) -> dict[str, Any] | None:
        with self._lock:
            for c in self._chats.get(user, []):
                if c["id"] == chat_id:
                    return c
        return None

    def chats(self, user: str) -> list[dict[str, Any]]:
        return list(self._chats.get(user, []))

    def active_chat(self, user: str) -> dict[str, Any]:
        return self.ensure_chat(user)

    def append_message(self, user: str, chat_id: str, role: str, content: str) -> None:
        with self._lock:
            for c in self._chats.get(user, []):
                if c["id"] == chat_id:
                    c["messages"].append({"role": role, "content": content,
                                          "ts": _now_iso()})
                    c["updated"] = _now()
                    # Smart auto-title: use vehicle + first user message
                    if role == "user" and len(c["messages"]) == 1:
                        vehicle = c.get("vehicle", {})
                        brand = (vehicle or {}).get("brand", "")
                        model = (vehicle or {}).get("model", "")
                        vehicle_str = " ".join(filter(None, [brand, model])).strip()
                        # Extract a short topic from the message
                        topic = content.strip()
                        if len(topic) > 50:
                            topic = topic[:50] + "..."
                        if vehicle_str:
                            c["title"] = f"{vehicle_str} — {topic}" if topic else vehicle_str
                        else:
                            c["title"] = topic if topic else "New conversation"
                    self._save()
                    return

    def clear_messages(self, user: str, chat_id: str) -> bool:
        """Remove every message in a conversation (keeps the thread itself)."""
        with self._lock:
            for c in self._chats.get(user, []):
                if c["id"] == chat_id:
                    c["messages"] = []
                    c["updated"] = _now()
                    return True
        return False

    def search_chats(self, user: str, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search conversation titles and message text; returns {id, title, snippet}."""
        q = (query or "").strip().lower()
        if not q:
            return []
        hits: list[dict[str, Any]] = []
        with self._lock:
            for c in self._chats.get(user, []):
                title = (c.get("title") or "").lower()
                if q in title:
                    hits.append({"id": c["id"], "title": c.get("title", ""),
                                 "snippet": ""})
                    continue
                for m in c["messages"]:
                    content = str(m.get("content") or "")
                    if q in content.lower():
                        start = max(0, content.lower().index(q) - 40)
                        snippet = ("…" if start > 0 else "") + content[start:start + 120] + "…"
                        hits.append({"id": c["id"], "title": c.get("title", ""),
                                     "snippet": snippet})
                        break
        return hits[:limit]

    def delete_chat(self, user: str, chat_id: str) -> None:
        with self._lock:
            chats = self._chats.get(user, [])
            self._chats[user] = [c for c in chats if c["id"] != chat_id]
            if self._active.get(user) == chat_id:
                self._active.pop(user, None)
            self._save()

    def rename_chat(self, user: str, chat_id: str, title: str) -> dict[str, Any] | None:
        with self._lock:
            for c in self._chats.get(user, []):
                if c["id"] == chat_id:
                    c["title"] = title.strip() or c["title"]
                    c["updated"] = _now()
                    return c
        return None

    def set_chat_vehicle(self, user: str, chat_id: str,
                         vehicle: dict[str, Any]) -> None:
        with self._lock:
            for c in self._chats.get(user, []):
                if c["id"] == chat_id:
                    c["vehicle"] = vehicle
                    c["updated"] = _now()
                    return

    def chats_meta(self, user: str) -> list[dict[str, Any]]:
        """Return chat metadata for the history sidebar (no full messages)."""
        with self._lock:
            result = []
            for c in self._chats.get(user, []):
                msgs = c.get("messages", [])
                last_msg = msgs[-1].get("content", "") if msgs else ""
                # Truncate last message preview
                if len(last_msg) > 80:
                    last_msg = last_msg[:80] + "..."
                result.append({
                    "id": c["id"],
                    "title": c.get("title", "New conversation"),
                    "vehicle": c.get("vehicle", {"brand": "", "model": ""}),
                    "message_count": len(msgs),
                    "last_message": last_msg,
                    "created": c.get("created", ""),
                    "updated": c.get("updated", c.get("created", "")),
                    "diag_id": c.get("diag_id"),
                })
            return result

    def history_payload(self, user: str, chat_id: str, max_messages: int = 24) -> list[dict[str, str]]:
        """Recent messages formatted for the Gemini API."""
        chat = self.chat(user, chat_id)
        if not chat:
            return []
        msgs = [{"role": m["role"], "content": m["content"]} for m in chat["messages"] if m["content"]]
        return msgs[-max_messages:]

    # ---------- diagnoses / reports ----------
    def add_diagnosis(self, user: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = dict(data)
            record["id"] = record.get("id") or self._new_id("DIA")
            record.setdefault("date", _now())
            self._diagnoses.setdefault(user, []).insert(0, record)
            self._twin.pop(user, None)
            self._save()
            return record

    def diagnoses(self, user: str) -> list[dict[str, Any]]:
        return list(self._diagnoses.get(user, []))

    def diagnosis(self, user: str, diag_id: str) -> dict[str, Any] | None:
        with self._lock:
            for d in self._diagnoses.get(user, []):
                if d["id"] == diag_id:
                    return d
        return None

    # ---------- diagnosis sessions ----------
    def _generate_session_title(self, vehicle: dict, problem: str) -> str:
        """Generate a default title from vehicle + problem."""
        brand = (vehicle or {}).get("brand", "")
        model = (vehicle or {}).get("model", "")
        vehicle_str = " ".join(filter(None, [brand, model])).strip()
        problem_str = (problem or "").strip()
        if vehicle_str and problem_str:
            if len(problem_str) > 40:
                problem_str = problem_str[:40] + "..."
            return f"{vehicle_str} — {problem_str}"
        if vehicle_str:
            return vehicle_str
        if problem_str:
            if len(problem_str) > 50:
                problem_str = problem_str[:50] + "..."
            return problem_str
        return "New Diagnosis"

    def new_diag_session(self, user: str, vehicle: dict = None,
                         problem: str = "") -> dict[str, Any]:
        """Create a new diagnosis session."""
        with self._lock:
            now = _now()
            session = {
                "id": self._new_id("DXS"),
                "title": self._unique_title(user, self._generate_session_title(vehicle, problem)),
                "status": "in_progress",  # in_progress, ready, diagnosing, completed
                "created_at": now,
                "updated_at": now,
                "vehicle": vehicle or {"brand": "", "model": ""},
                "problem": problem,
                "notice": "",
                "category": "",
                "when": "",
                "where": "",
                "answers": {},
                "questions": [],
                "question_index": 0,
                "image": None,
                "step": "welcome",
                "diagnosis": None,  # filled after AI diagnosis completes
                "chat_id": None,  # linked chat thread id
                "locked": False,  # true when tied to an active service request
                "service_request": None,  # {active, requested_at} when a service is booked
            }
            self._diag_sessions.setdefault(user, []).insert(0, session)
            self._diag_active[user] = session["id"]
            self._save()
            return session

    def set_session_title_from_diagnosis(self, user: str, session_id: str,
                                         diagnosis: dict[str, Any] | None) -> dict[str, Any] | None:
        """Rename a session to a short, descriptive title based on the detected fault.

        e.g. ``"Audi A4 — Worn front brake pads"``. Kept unique so no two
        diagnoses share a name (item: distinct, descriptive names).
        """
        with self._lock:
            for s in self._diag_sessions.get(user, []):
                if s["id"] == session_id:
                    problem = (diagnosis or {}).get("problem") or s.get("problem") or "Diagnosis"
                    problem = str(problem).strip()
                    vehicle = s.get("vehicle") or {}
                    vstr = " ".join(filter(None, [vehicle.get("brand", ""),
                                                  vehicle.get("model", "")])).strip()
                    base = f"{vstr} — {problem}" if vstr else problem
                    if len(base) > 60:
                        base = base[:60].rstrip() + "…"
                    s["title"] = self._unique_title(user, base, exclude_id=session_id)
                    s["updated_at"] = _now()
                    self._save()
                    return s
        return None

    def diag_session(self, user: str, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            for s in self._diag_sessions.get(user, []):
                if s["id"] == session_id:
                    return s
        return None

    def diag_sessions(self, user: str) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._diag_sessions.get(user, []))
        # Attach relative time for display
        for s in sessions:
            s["time_ago"] = _relative_time(s.get("updated_at", ""))
        return sessions

    def update_diag_session(self, user: str, session_id: str,
                            updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update fields of a diagnosis session."""
        with self._lock:
            for s in self._diag_sessions.get(user, []):
                if s["id"] == session_id:
                    for key, val in updates.items():
                        s[key] = val
                    s["updated_at"] = _now()
                    # Auto-generate title if vehicle or problem changed — but keep
                    # any custom name the user typed via rename, and keep it unique.
                    if ("vehicle" in updates or "problem" in updates) and not s.get("title_custom"):
                        base = self._generate_session_title(s.get("vehicle"), s.get("problem"))
                        s["title"] = self._unique_title(user, base, exclude_id=session_id)
                    self._save()
                    return s
        return None

    def rename_diag_session(self, user: str, session_id: str,
                            title: str) -> dict[str, Any] | None:
        """Rename a diagnosis session."""
        with self._lock:
            for s in self._diag_sessions.get(user, []):
                if s["id"] == session_id:
                    s["title"] = self._unique_title(user, title.strip() or s["title"],
                                                    exclude_id=session_id)
                    s["title_custom"] = True  # user-chosen name; don't auto-overwrite
                    s["updated_at"] = _now()
                    self._save()
                    return s
        return None

    def delete_diag_session(self, user: str, session_id: str) -> bool:
        """Delete a diagnosis session and its associated chat."""
        with self._lock:
            sessions = self._diag_sessions.get(user, [])
            target = None
            for s in sessions:
                if s["id"] == session_id:
                    target = s
                    break
            if not target:
                return False
            # Delete associated chat
            chat_id = target.get("chat_id")
            if chat_id:
                self._chats[user] = [c for c in self._chats.get(user, [])
                                     if c["id"] != chat_id]
                if self._active.get(user) == chat_id:
                    self._active.pop(user, None)
            self._diag_sessions[user] = [s for s in sessions
                                         if s["id"] != session_id]
            if self._diag_active.get(user) == session_id:
                self._diag_active.pop(user, None)
            self._save()
            return True

    def set_active_diag_session(self, user: str,
                                session_id: str) -> dict[str, Any] | None:
        with self._lock:
            for s in self._diag_sessions.get(user, []):
                if s["id"] == session_id:
                    self._diag_active[user] = session_id
                    return s
        return None

    def active_diag_session(self, user: str) -> dict[str, Any] | None:
        session_id = self._diag_active.get(user)
        if session_id:
            return self.diag_session(user, session_id)
        return None

    def search_diag_sessions(self, user: str, query: str,
                             limit: int = 20) -> list[dict[str, Any]]:
        """Search diagnosis sessions by title, vehicle, problem."""
        q = (query or "").strip().lower()
        if not q:
            return self.diag_sessions(user)
        hits: list[dict[str, Any]] = []
        with self._lock:
            for s in self._diag_sessions.get(user, []):
                title = (s.get("title") or "").lower()
                problem = (s.get("problem") or "").lower()
                brand = (s.get("vehicle") or {}).get("brand", "").lower()
                model = (s.get("vehicle") or {}).get("model", "").lower()
                if (q in title or q in problem or q in brand or q in model):
                    hits.append(s)
                if len(hits) >= limit:
                    break
        for s in hits:
            s["time_ago"] = _relative_time(s.get("updated_at", ""))
        return hits

    def link_diag_session_chat(self, user: str, session_id: str,
                               chat_id: str) -> None:
        """Link a chat thread to a diagnosis session."""
        with self._lock:
            for s in self._diag_sessions.get(user, []):
                if s["id"] == session_id:
                    s["chat_id"] = chat_id
                    s["updated_at"] = _now()
                    self._save()
                    return

    # ---------- maintenance ----------
    def add_maintenance(self, user: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            item = dict(data)
            item["id"] = item.get("id") or self._new_id("MAINT")
            item.setdefault("date_added", _now())
            item.setdefault("status", "active")
            self._maintenance.setdefault(user, []).insert(0, item)
            self._twin.pop(user, None)
            self._save()
            return item

    def maintenance(self, user: str) -> list[dict[str, Any]]:
        return list(self._maintenance.get(user, []))

    def maintenance_item(self, user: str, mid: str) -> dict[str, Any] | None:
        with self._lock:
            for m in self._maintenance.get(user, []):
                if m["id"] == mid:
                    return m
        return None

    def update_maintenance(self, user: str, mid: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for m in self._maintenance.get(user, []):
                if m["id"] == mid:
                    m.update(updates)
                    self._save()
                    return m
        return None

    def delete_maintenance(self, user: str, mid: str) -> bool:
        with self._lock:
            before = len(self._maintenance.get(user, []))
            self._maintenance[user] = [m for m in self._maintenance.get(user, []) if m["id"] != mid]
            changed = len(self._maintenance.get(user, [])) != before
            if changed:
                self._save()
            return changed


# Global singleton shared across requests.
store = Store()
