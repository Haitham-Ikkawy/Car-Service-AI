# Car Service AI

A bilingual (English / Arabic, RTL) AI SaaS web application that diagnoses car
problems with Google Gemini by **text**, **image**, or **audio** — and guides
you through maintenance and repairs.

Built with **FastAPI**, **Jinja2**, **Bootstrap 5**, and vanilla JavaScript.
No database — temporary data is stored in memory.

## Features

- **AI Assistant** — streaming chat with markdown, copy, download and regenerate
- **Diagnose by Text** — describe the problem, get a full structured repair report
- **Diagnose by Image** — upload a photo of the car / part, AI detects the issue + confidence score
- **Diagnose by Audio** — upload a recording of the sound, AI transcribes and diagnoses
- **Vehicle profile** — 6-step wizard with a **cascading brand → model → engine autocomplete** backed by a **live vehicle data API** (NHTSA vPIC + CarQuery, proxied & cached server-side, enriched with local logos/images), or AI auto-detect
- **Smart problem input** — real-time problem suggestions as you type, each with a category icon and a **contextual safety notice**
- **Continue after diagnosis** — keep chatting with the AI Mechanic on the *same* conversation context; **edit** a past diagnosis to change inputs and re-run
- **Service requests** — mark a diagnosis as tied to an active service request, which **safeguards it from deletion**
- **Maintenance** — reminders with progress bars and a service history timeline
- **Repair Guide** — step-by-step guides with difficulty, tools and torque specs
- **Reports** — every diagnosis saved as a report, printable / PDF download
- **Settings** — theme (light / dark / auto), language, Gemini API key, notifications, accessibility
- **Full dark & light mode**, glassmorphism design system, responsive for mobile & desktop
- **Full Arabic + English localization** with automatic language detection and RTL layout

> **No API key?** The app automatically runs in **Demo Mode** — every page, button and AI
> feature still works with realistic mock responses.

## Project structure

```
Car_Service_AI/
├── env/                          # virtualenv (python -m venv env)
├── src/
│   ├── app.py                    # FastAPI entry point, mounts all modules
│   ├── config.py                 # env/settings loader + reference data
│   ├── requirements.txt
│   ├── shared/
│   │   ├── store.py              # in-memory data store
│   │   ├── static/               # css/, js/, images/, audio/ (global assets)
│   │   ├── templates/            # base.html, navbar.html, sidebar.html, footer.html, auth pages
│   │   └── utils/                # gemini, translator, language, audio, image_ai, templating
│   ├── dashboard/                # /dashboard
│   ├── chat_ai/                  # /chat + streaming chat API
│   ├── image_diagnosis/          # /diagnose/image
│   ├── sound_diagnosis/          # /diagnose/audio
│   ├── ai_report/                # /diagnose/text, /diagnosis/{id}, /reports
│   ├── maintenance/              # /maintenance
│   ├── settings/                 # /settings
│   └── uploads/                  # images/, audio/ (upload staging)
├── .env                          # environment configuration
├── Dockerfile
├── cloudbuild.yaml               # Google Cloud Build
├── README.md
└── .gitignore
```

Each feature module owns its `routes.py`, `templates/` and `static/` folders; the
application shell (layout, auth, error pages) lives in `shared/`.

## Installation

```bash
python -m venv env
env\Scripts\activate            # Windows
# source env/bin/activate       # macOS / Linux
pip install -r src\requirements.txt
```

## Run

```bash
uvicorn src.app:app --reload
```

Open http://127.0.0.1:8000 — login is demo-only: **any valid email** and a
**password of 6+ characters** works (e.g. `tester@x.com` / `secret123`).

## Configuration

Copy `.env.example` to `.env` and optionally set your Gemini API key:

```
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.6-flash
SESSION_SECRET=change-me-car-service-ai-secret
```

`GEMINI_MODEL` defaults to the newest supported Flash model (`gemini-3.6-flash`);
if left empty or set to a deprecated model, the app automatically uses
`DEFAULT_GEMINI_MODEL` and falls back to other supported models when needed.

An empty `GEMINI_API_KEY` enables demo mode. You can also add a key later from the
in-app **Settings** page (stored in memory only).

### Vehicle data & connectivity

The vehicle **brand → model → engine** autocomplete pulls live data from
open-source APIs (NHTSA vPIC for makes/models, CarQuery for engines), proxied and
cached server-side. **No API key is required.** When offline, the wizard falls
back to a curated brand/model set and synthesized engine options, so it keeps
working. `httpx` (already a dependency) performs the upstream calls.

## Changelog

See **[CHANGES.md](CHANGES.md)** for a detailed, per-requirement log of the
redesign and enhancement work (features, fixes, responsiveness, and the files
touched). A full architecture/onboarding reference lives in
**[project.md](project.md)**.

## Docker

```bash
docker build -t car-service-ai .
docker run -p 8000:8000 car-service-ai
```

## License / notes

Graduation project — informational guidance only; always consult a certified mechanic.
