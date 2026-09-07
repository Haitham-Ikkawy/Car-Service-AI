"""Car Service AI — FastAPI application entry point.

Run with:  uvicorn src.app:app --reload
"""
from __future__ import annotations

import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, config
from .shared.store import store
from .shared.utils import gemini, translator as i18n
from .shared.utils.language import resolve_lang
from .shared.utils.templating import RedirectException, render

# Feature modules (each exposes an APIRouter).
from .ai_report.routes import router as ai_report_router
from .auth.routes import router as auth_router
from .car_database.routes import router as car_database_router
from .chat_ai.routes import router as chat_router
from .dashboard.routes import router as dashboard_router
from .image_diagnosis.routes import router as image_diagnosis_router
from .maintenance.routes import router as maintenance_router
from .settings.routes import router as settings_router
from .sound_diagnosis.routes import router as sound_diagnosis_router

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

app = FastAPI(title="Car Service AI", version=__version__)

app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET, same_site="lax")

# Module-specific static folders are served under /static/<module>/ before the
# shared assets (which live in shared/static) are mounted at /static.
for _name in ("chat_ai", "image_diagnosis", "sound_diagnosis",
              "ai_report", "maintenance", "settings", "car_database"):
    _dir = BASE_DIR / _name / "static"
    app.mount(f"/static/{_name}", StaticFiles(directory=str(_dir)), name=f"static-{_name}")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "shared" / "static")), name="static")
# Project-level media library (automotive images & video) served from the repo image/ folder.
app.mount("/image", StaticFiles(directory=str(PROJECT_ROOT / "image")), name="image")
app.mount("/img", StaticFiles(directory=str(PROJECT_ROOT / "image")), name="img")

for _router in (dashboard_router, chat_router, image_diagnosis_router,
                sound_diagnosis_router, ai_report_router, maintenance_router,
                settings_router, car_database_router, auth_router):
    app.include_router(_router)


# ---------------------------------------------------------------------------
# Demo data seeding
# ---------------------------------------------------------------------------

def _seed(user: str, lang: str = "en") -> None:
    if store.vehicle(user):
        return
    store.set_vehicle(user, {
        "manufacturer": "Audi", "model": "A4", "year": 2021,
        "fuel": "Diesel", "transmission": "Automatic", "mileage": 62000,
    })
    store.add_maintenance(user, {
        "title": "Oil & filter change", "category": "Engine",
        "interval_km": 15000, "last_done_km": 45000, "current_km": 62000, "notes": "Use 5W-30 fully synthetic.",
    })
    store.add_maintenance(user, {
        "title": "Brake pads inspection", "category": "Brakes",
        "interval_km": 40000, "last_done_km": 25000, "current_km": 62000,
        "notes": "Front and rear pads, check rotor thickness.",
    })
    store.add_maintenance(user, {
        "title": "Tire rotation & pressure", "category": "Tires",
        "interval_km": 10000, "last_done_km": 55000, "current_km": 62000,
        "notes": "Rotate front-to-back, check pressures to spec.",
    })
    store.add_maintenance(user, {
        "title": "Battery health check", "category": "Electrical",
        "interval_km": 20000, "last_done_km": 40000, "current_km": 62000,
        "notes": "Load test + terminal cleaning.",
    })

    # Starter reports come from the real AI (never fake data). Generate them in
    # the background so login is not blocked; failures are ignored silently.
    def _seed_reports() -> None:
        for text in (
            "The engine is shaking at idle and the check engine light flashed once on the highway.",
            "There is a loud squealing noise from the front when I brake at low speed.",
        ):
            try:
                report = gemini.diagnose(user, "text", description=text)
                report.setdefault("date", _now_str())
                store.add_diagnosis(user, report)
            except Exception:  # noqa: BLE001 — background task must never crash login
                pass

    threading.Thread(target=_seed_reports, daemon=True).start()
    chat = store.new_chat(user)
    store.append_message(user, chat["id"], "assistant", i18n.chat_greeting(lang))


def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.get("/")
async def root(request: Request):
    return RedirectResponse("/splash")


@app.get("/splash")
async def splash(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/diagnose", status_code=303)
    return render(request, "splash.html", active="splash")


@app.get("/start")
async def start(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/diagnose")
    return RedirectResponse("/login")


@app.get("/login")
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/diagnose", status_code=303)
    return render(request, "login.html", active="login",
                  error=request.query_params.get("error") or "")


@app.post("/login")
async def login(request: Request):
    return RedirectResponse("/login", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/splash", status_code=303)


# ---------------------------------------------------------------------------
# About / Contact
# ---------------------------------------------------------------------------

@app.get("/about")
async def about(request: Request):
    require_session = request.session.get("user")
    if not require_session:
        raise RedirectException("/login")
    return render(request, "about.html", active="about", page_title="About")


@app.get("/contact")
async def contact_page(request: Request):
    require_session = request.session.get("user")
    if not require_session:
        raise RedirectException("/login")
    return render(request, "contact.html", active="contact", page_title="Contact")


@app.post("/api/contact")
async def contact_send(request: Request):
    lang = resolve_lang(request)
    body = await request.json()
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip()
    subject = (body.get("subject") or "").strip()
    message = (body.get("message") or "").strip()
    if not name or "@" not in email or not subject or len(message) < 5:
        return JSONResponse({"error": i18n.tr(lang, "Please fill in all fields correctly.")}, status_code=400)
    # No backend mail — acknowledged in memory for demo purposes.
    return JSONResponse({"ok": True,
                         "message": i18n.tr(lang, "Thanks {name}! Your message has been received.", name=name)})


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------

@app.exception_handler(RedirectException)
async def _redirect_handler(request: Request, exc: RedirectException):
    return RedirectResponse(exc.url, status_code=303)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return render(request, "404.html", active="", page_title="Page not found", status_code=404)


@app.exception_handler(500)
async def internal_error(request: Request, exc):
    return render(request, "500.html", active="", page_title="Server error", status_code=500)


@app.get("/500")
async def force_500():
    raise RuntimeError("Forced 500 for testing the error page.")


if __name__ == "__main__":
    import webbrowser, threading
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8000/splash")).start()
    uvicorn.run("src.app:app", host="127.0.0.1", port=8000, reload=True)
