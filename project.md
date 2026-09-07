# Car Service AI — Project Guide

> A bilingual-capable AI SaaS web app that diagnoses car problems with Google
> Gemini (by **text**, **image**, or **audio**), then guides the owner through
> repairs, maintenance and follow-up questions with an "AI Mechanic" chat.
>
> Stack: **FastAPI** + **Jinja2** server-rendered templates + **vanilla JS** +
> **Bootstrap 5**. **No database** — all state lives in an in-memory singleton.
> Graduation project; informational guidance only.

This document is the single onboarding reference. It is organised into four
parts: **Architecture**, **Business logic**, **Project structure**, and
**UI/UX**. Read the Architecture and Project-structure sections first, then the
Business-logic section for the domain workflows.

> **Recent changes:** ongoing redesign/enhancement work is logged per-requirement
> in [CHANGES.md](CHANGES.md). Highlights so far: a live cascading
> brand→model→engine vehicle autocomplete, rich typed problem suggestions,
> same-context continue-chat, edit/delete-with-safeguards for past diagnoses, and
> a cross-device responsiveness pass.

---

## 1. Architecture

### 1.1 Overall system design

Car Service AI is a **server-rendered monolith**. FastAPI serves HTML pages
(Jinja2) and a set of JSON / SSE APIs consumed by vanilla JavaScript on those
pages. There is no SPA framework and no separate frontend build step — the
"frontend" is HTML templates plus static CSS/JS shipped from the same app.

```
Browser (Bootstrap 5 + vanilla JS)
    │  HTML page loads  ──────────►  Jinja2 templates (server-rendered)
    │  fetch() JSON / SSE  ───────►  FastAPI route handlers (per feature module)
    │                                     │
    │                                     ├─► store (in-memory singleton, per-user)
    │                                     └─► gemini / openai_provider (AI layer)
    │                                              │
    ▼                                              ▼
  UI update                               Google Gemini API / OpenAI API
```

Key architectural properties:

- **Feature-module architecture.** Each feature is a self-contained package
  under `src/` exposing an `APIRouter` (`routes.py`) plus its own `templates/`
  and `static/` folders. `src/app.py` mounts every router and every module's
  static directory. See §3.
- **Shared application shell.** Layout, auth helpers, the AI layer, the data
  store, i18n and error pages live in `src/shared/`. Every page extends
  `shared/templates/base.html` (authenticated shell) or `base_auth.html`
  (splash/login).
- **One AI entry point, two providers.** All structured diagnosis flows go
  through `shared/utils/gemini.py`. Chat can stream from **either** Gemini or
  OpenAI through a common `stream_sse(...)` interface
  (`shared/utils/openai_provider.py`).
- **No demo/fake AI answers.** If no API key is configured or a call fails, the
  code raises `UnavailableError` (surfaced as HTTP 503 `error_type:
  "ai_unavailable"`) or emits an SSE `error` event with the exact provider
  message. (Note: the README's "Demo Mode returns realistic mock responses" is
  aspirational — the current code shows an error/unavailable state instead of
  fabricated data. "Demo mode" today just means "no working AI key".)
- **In-memory persistence.** `shared/store.py` is a single thread-safe `Store`
  instance keyed by the logged-in user's email. **All data is lost on restart**
  — intentional for the project scope.

### 1.2 Backend / frontend separation

There is no physical backend/frontend split — but there is a clear logical one:

| Concern | Where it lives |
|---|---|
| Routing, auth gate, AI calls, data | `src/**/routes.py`, `src/shared/utils/*`, `src/shared/store.py` |
| Page structure | `src/**/templates/*.html` (Jinja2) |
| Styling | `src/shared/static/css/app.css` (8,381 lines), `app-chat.css`, module CSS |
| Interactivity | `src/shared/static/js/app.js` (2,339 lines) + per-module JS |

The **global `app.js`** owns cross-cutting behaviour: theme switching, mobile
sidebar, toasts, markdown rendering, the splash-page animations, and the entire
**chat controller** (SSE streaming, history sidebar, model switch, voice input,
message actions). Per-module JS files are usually thin (e.g. `chat.js` is only a
textarea auto-grow helper; `maintenance.js` only rounds number inputs). The
notable exception is `ai_report/static/diagnose.js` (~3,250 lines), which is a
full client-side wizard engine.

### 1.3 API structure

Routes fall into two kinds:

- **Page routes** (`GET`, return HTML) — always call `require(request)` (auth
  gate → redirect to `/login`) then `render(...)`.
- **Data routes** (`/api/...`, return JSON or `text/event-stream`) — consumed
  by `fetch()` from the page JS.

Representative endpoints (see §2 for behaviour):

| Area | Endpoint(s) |
|---|---|
| Diagnosis wizard | `GET /diagnose`, `POST /api/diagnose/complete` |
| Diagnosis sessions (autosave) | `POST /api/diag-sessions/new`, `GET /api/diag-sessions`, `GET/POST /api/diag-sessions/{id}[/update|/rename|/delete|/complete|/link-chat]` |
| Media diagnosis | `POST /api/diagnose/image`, `POST /api/diagnose/audio`, `POST /api/diagnose/text` |
| Reports | `GET /my-diagnoses`, `GET /reports`, `GET /diagnosis/{id}`, `GET /diagnosis/{id}/print` |
| Chat | `GET /chat`, `POST /api/chat/stream` (SSE), `/api/chat/new|select|delete|clear|rename|save-diagnosis`, `GET /api/chats`, `GET /api/chat/search` |
| Vehicle / digital twin | `POST /api/vehicle`, `POST /api/vehicle/detect`, `POST /api/vehicle/twin`, `GET /api/vehicle/parts/{key}` |
| Vehicle autocomplete (live) | `GET /api/vehicles/makes`, `/models?make=`, `/engines?make=&model=` — NHTSA vPIC + CarQuery, proxied & cached (`car_database/vehicle_api.py`) |
| Diagnosis sessions (extra) | `POST /api/diag-sessions/{id}/service-request` (locks against deletion); `/delete` now guarded (409 while `diagnosing` or service-locked) |
| Repair guides | `GET /repair-guide`, `GET /repair-guide/{slug}` |
| Maintenance | `GET /maintenance`, `POST /api/maintenance`, `POST /api/maintenance/{id}/done|/delete`, `GET /api/maintenance/data` |
| Settings | `GET /settings`, `POST /api/settings`, `POST /api/settings/test-gemini`, `POST /api/settings/clear-cache` |
| Auth | `GET /auth/google[/callback]`, `GET /auth/apple`, `POST /auth/apple/callback`, `POST /logout` |
| Shell | `/`, `/splash`, `/start`, `/login`, `/about`, `/contact`, `POST /api/contact` |
| Voice generator | `GET /voice` (browser TTS only; no API) |

**SSE convention** (chat + workspace chat): frames are `data: {"text": "..."}\n\n`,
errors are `data: {"error": "...", "error_type": "ai_unavailable"}\n\n`, and the
stream terminates with `data: [DONE]\n\n`. Response sets `Cache-Control:
no-cache` and `X-Accel-Buffering: no` to defeat proxy buffering.

### 1.4 Data models (in-memory `Store`)

There is no ORM. `shared/store.py` keeps per-user dictionaries under a
`threading.Lock`. Entities (all keyed by user email):

- **User profile** — `{email, name, provider, provider_id, picture, last_login}`.
- **Vehicle** — `{manufacturer, model, year, fuel, transmission, mileage,
  chassis?, updated}` (one per user).
- **Chat thread** — `{id (CHAT-…), title, messages[], created, updated, vehicle,
  diag_id}`; messages are `{role, content, ts}`. Newest-first.
- **Diagnosis report** — the normalized AI result dict (id `DIA-…`), stored via
  `add_diagnosis`. Includes `problem, summary, causes[], urgency, can_drive,
  cost, time, parts[], steps[], center, confidence, tips[]` and optional
  `image_data`/`audio_data`/`transcript`.
- **Diagnosis session** — the wizard's resumable state (id `DXS-…`): `status
  (in_progress|ready|diagnosing|completed), step, vehicle, problem, notice,
  category, when, where, answers{}, questions[], question_index, image,
  diagnosis, chat_id`.
- **Maintenance reminder** — `{id (MAINT-…), title, category, interval_km,
  last_done_km, current_km, notes, status, date_added}`.
- **Settings** — per-user `{theme, language, gemini_key, model, streaming,
  notifications{}, a11y{}}`.
- **Digital twin** — cached AI health analysis of the vehicle (invalidated on
  vehicle/diagnosis/maintenance change).

ID scheme: `_new_id(prefix)` → `PREFIX-YYYYMMDD-NNNN` using a global counter.

### 1.5 Key design patterns

- **Router-per-feature** with lazy cross-module imports to avoid cycles (e.g.
  `auth` lazy-imports `app._seed`; the diagnosis workspace calls the chat
  module's `save-diagnosis`).
- **Prompt-engineered structured JSON** for all non-chat AI: a strict-schema
  prompt → `_extract_json()` → Python validation/clamping. Chat instead streams
  free-form markdown.
- **Provider strategy**: `gemini` and `openai_provider` expose the same
  `chat_stream` / `stream_sse` surface; the chat route picks one by a `provider`
  field.
- **Cache-and-invalidate** for the model client (`_MODEL_CACHE`) and the digital
  twin.
- **Graceful degradation**: missing key → friendly error surfaced, never a crash
  or fabricated answer.
- **Debounced autosave** of wizard state to a server-side session record so a
  diagnosis can be resumed from any device state.

### 1.6 Third-party integrations

- **Google Gemini** via `google-genai` SDK — primary AI (chat, diagnosis, twin,
  vehicle detect). Default model `gemini-3.6-flash` with a fallback chain
  (`gemini-3.5-flash`, `-flash-lite`, `gemini-3.1-flash-lite`).
- **OpenAI** (optional) — alternate chat provider (`gpt-4o-mini` default).
  ⚠️ **Known mismatch:** Settings saves the ChatGPT key as `CHATGPT_API_KEY`,
  but `openai_provider._api_key` reads `OPENAI_API_KEY` / a per-user `openai_key`
  — verify this end-to-end before relying on the ChatGPT path.
- **Google OAuth 2.0** (authorization-code) and **Sign in with Apple**
  (`form_post` id_token, ES256 + JWKS + nonce) — see `shared/utils/oauth.py`.
- **Starlette `SessionMiddleware`** — signed cookie sessions (`SESSION_SECRET`).
- **CDN assets** — Bootstrap 5.3, Bootstrap Icons, Google Fonts (Inter,
  JetBrains Mono, Tajawal); `marked` + `DOMPurify` for markdown in chat.
- **Deployment** — `Dockerfile` (python:3.12-slim, uvicorn) + `cloudbuild.yaml`
  (Google Cloud Build → GCR image `car-service-ai`).

---

## 2. Business logic

### 2.1 Core domain: the AI diagnosis pipeline

All three input modes (text / image / audio) converge on one function:
`gemini.diagnose(user, mode, description=, image_bytes=, audio_bytes=, lang=,
vehicle_override=, ...)`.

1. **Vehicle grounding.** Unless a `vehicle_override` is passed, the prompt is
   enriched with the user's saved vehicle, up to 8 maintenance records and up to
   5 recent diagnoses (`_vehicle_context`) so the model answers about *that
   specific car* and is told never to invent data.
2. **Strict-schema prompt** (`_DIAG_PROMPT`) requests a single JSON object:
   `problem, summary, possible_causes[], urgency(low|medium|high|critical),
   can_drive, estimated_cost, estimated_time, required_parts[], repair_steps[],
   recommended_center, confidence(0-100), preventive_tips[], transcript(audio
   only)`. Images/audio are attached as inline `types.Part.from_bytes`.
3. **Model fallback.** `_run_generation` tries the selected model, then the
   fallbacks, until one returns text.
4. **Parse + normalize.** `_extract_json` pulls the JSON out (fenced or raw).
   Python then applies business defaults: `urgency` defaults `"medium"`, `cost`
   `"$100 – $500"`, `time` `"2 – 4 hours"`, `center` an authorised dealer/garage,
   and **confidence is clamped to 55–99** (default 88). Empty lists fall back to
   "Have the vehicle inspected by a certified mechanic."
5. **Persist.** The result is saved via `store.add_diagnosis` (id `DIA-…`), which
   **invalidates the digital-twin cache**.

Business rule: **no fabricated results.** A missing key or failed/empty response
raises `UnavailableError` → HTTP 503 with the exact reason.

### 2.2 The Guided Diagnosis Wizard (primary user journey)

Entry point `GET /diagnose` → `ai_report/templates/diagnose.html`, driven by
`ai_report/static/diagnose.js`. It is a **client-side state machine** with 7
steps (`welcome → vehicle → describe → questions → image → review → ready`),
mapped to a 1–6 stepper.

- **Session created up-front.** Starting the wizard POSTs
  `/api/diag-sessions/new`, so an empty `DXS-…` session exists immediately for
  autosave.
- **Vehicle step.** A rich picker with 49 hardcoded brands (local logo SVGs +
  model lists) and per-model `.webp` images, letter-grouped browse, fuzzy search
  (exact > prefix > brand-exact > … > contains), and **voice vehicle detection**
  via the Web Speech API (e.g. spoken "crv" → "CR-V").
- **Describe step.** Problem textarea (min 5 chars) with live counter, ~40 canned
  problem suggestions, optional notice, a category selector, and `when`/`where`
  chips. `buildFullProblem()` concatenates all of this into one description
  string.
- **Guided questions — rule-based, NOT AI.** `classifyProblem(text)` regex-buckets
  the problem (overheating / brakes / no_start / ac / shake / noise / general);
  `getQuestions()` merges a category-specific question bank with general
  questions, **capped at 6**. Every bank includes a "Not sure" escape option
  (answers equal to "Not sure" are dropped from the AI description). *(Code
  curiosity: the general bank constant is named with a non-ASCII identifier
  `QUESTIONS通用`.)*
- **Image step.** Optional photo → base64 data-URI in state; an `_imageDirty`
  flag avoids re-sending the large blob on every autosave.
- **Review / Ready.** Editable summary, then a final confirmation card.
- **Run.** `POST /api/diagnose/complete` with `{problem, answers, image, vehicle,
  session_id}`. Server rejects `problem < 5` chars, builds the composite
  description, decodes the image off the event loop (`asyncio.to_thread`), picks
  `mode = "image" if image else "text"`, auto-detects Arabic, calls
  `gemini.diagnose`, saves, and marks the session `completed`.
- **Result → Workspace.** Success opens a two-column **workspace**: the diagnosis
  result panel (severity badge, SVG confidence ring, causes, actions, parts,
  cost/time, prevention tips, thumbs feedback) on one side and a **live AI chat**
  on the other. The workspace seeds a linked chat thread via
  `/api/chat/save-diagnosis` and streams follow-ups over SSE.

**Autosave & resume:** `scheduleSave()` debounces 500 ms and POSTs the whole
state to `/update`. Opening `/diagnose?session_id=…` restores full state and
jumps to the saved step (or straight to the result if completed). Deep
Back/Forward is supported via `history.pushState` + `#step-*` hashes.

### 2.3 Media diagnosis (image / audio)

- `POST /api/diagnose/image` — multipart upload, validated by
  `image_ai.validate_image` (**≤10 MB**, JPG/PNG/WebP) → `gemini.diagnose(...,
  "image", ...)`. Result carries `image_data` for later display.
- `POST /api/diagnose/audio` — validated by `audio.validate_audio` (**≤15 MB**,
  mp3/wav/m4a/ogg/webm/aac) → `gemini.diagnose(..., "audio", ...)`. The prompt
  adds "Transcribe the sound…"; the result includes a `transcript` and
  `audio_data`.
- The standalone `GET /diagnose/image` and `/diagnose/audio` pages now **redirect
  to `/diagnose`** — the unified wizard replaced them. Their old templates/JS are
  legacy.

### 2.4 AI Mechanic chat (streaming)

`POST /api/chat/stream` is the core. It:
1. Parses `{message, chat_id, regenerate, provider, image_url}` (image is a
   base64 data-URL, decoded to bytes; malformed data ignored).
2. Validates (needs a message, an image, or a regenerate), resolves the thread.
3. Appends the user message; on regenerate, pops the last assistant message.
4. Builds history = **last 24 messages** (`history_payload`).
5. Sets a **per-message language override** (Arabic vs English) so replies match
   the latest message even mid-conversation.
6. Picks the provider (`gemini` default, or `openai`) and relays its SSE stream.
7. **Persistence rule (in `finally`):** the assistant reply is saved **only if
   non-empty and not failed** — this runs even if the client aborts ("Stop"), so
   partial answers are kept but error text is never stored.

The Gemini chat persona (`_SYSTEM_CHAT`) is a warm expert mechanic that mirrors
the user's language, **asks 1–3 follow-up questions before a full diagnosis**
when details are missing, answers in structured markdown, and never claims to
replace a certified mechanic. **Smart auto-titling:** the first user message sets
the thread title to `"{brand model} — {topic}"`.

### 2.5 Vehicle profile & Digital Twin

- `POST /api/vehicle` saves the vehicle (manufacturer + model required; numeric
  fields coerced ≥0; chassis capped at 24 chars).
- `POST /api/vehicle/detect` (`twin.detect_vehicle`) — AI parses a free-text car
  description into structured fields; **matches the user's words only, never
  invents values** (unmentioned → `null`).
- `POST /api/vehicle/twin` (`twin.analyze_twin`) — cached AI "health model": JSON
  `{health 0–100, summary, components[]{key,status: ok|warn|critical},
  recommendations[], estimated_cost}`. Health is clamped 0–100; component keys
  validated against the 8 known parts. Cached in the store and **invalidated**
  when the vehicle, diagnoses, or maintenance change.
- `GET /api/vehicle/parts/{key}` (`twin.part_report`) — merges static part specs
  (`parts.py`) with a short AI condition insight.

⚠️ **Onboarding gap:** the twin / detect / parts endpoints have **no frontend
consumer yet**. The `x`/`y` marker coordinates and `MARKER_ORDER` /
`DEFAULT_MARKER_STATE` in `parts.py` imply a planned interactive blueprint /
"My Garage" view that is not built.

### 2.6 Repair guides & parts catalog (static)

`car_database/guides.py` holds **9 static repair guides** (slug, title, category,
difficulty, time, steps[], tools, parts, tips) across 5 categories, with helpers
`guide(slug)`, `guides_by_category`, and `related(slug)` (same-category first).
`parts.py` holds 8 components with specs/issues/tips/lifespan. These render
instantly with **no AI dependency**; AI is layered on only via the twin/part
endpoints.

### 2.7 Maintenance reminders

`_with_progress(items, vehicle_km)` computes each item's due status:
- `next_service_km = last_done_km + interval_km`
- `remaining_km = last_done_km + interval_km - current_km` (may be negative)
- `progress = clamp(0..100, (current - last) / max(1, interval) * 100)`
- `service_status`: **`overdue`** when `remaining ≤ 0`; **`due_soon`** when
  `remaining ≤ 1000 km`; else **`upcoming`**.

Rules: `current_km` falls back to the vehicle odometer; `interval_km` is forced
≥1 to keep the divisor safe; adding a reminder invalidates the twin cache. The
page splits `active` vs `done`; marking done moves an item to the history
timeline. *(Note: the "New reminder" trigger button is commented out in the
template, and the done/delete/add AJAX is expected from a global handler, not
`maintenance.js`.)*

### 2.8 Settings — split persistence

`POST /api/settings` persists to **two backends**:
1. **API keys → project `.env` on disk (process-global).** `config.save_api_key`
   / `save_chatgpt_key` rewrite the matching line, push to `os.environ`, and
   `load_dotenv(override=True)` — effective immediately, no restart.
2. **Everything else → per-user in-memory** (`theme, language, model, streaming,
   notifications{}, a11y{}`).

Saving always clears `gemini._MODEL_CACHE`. `POST /api/settings/test-gemini`
runs a real minimal Gemini request (ok/invalid/missing/error);
`/clear-cache` empties the model cache. *(Test/clear buttons are wired by a
global script, not `settings.js`.)*

### 2.9 Authentication & demo seeding

- **Only OAuth works.** `POST /login` (email/password) is a **no-op redirect** —
  functional sign-in is Google (auth-code) and Apple (`form_post` id_token,
  ES256 + JWKS + nonce). CSRF via a session `state` token; Apple adds a `nonce`.
- `_finish()` creates/fetches the user, opens the session, and calls
  `_seed(email)`, then redirects to `/diagnose`.
- **`_seed` (first login only)** builds a demo garage: an **Audi A4 2021 Diesel
  Automatic @62,000 km**, four maintenance reminders, a greeting chat, and — in a
  daemon thread — **two real AI-generated starter reports** (failures swallowed
  so login never blocks).

### 2.10 i18n / RTL — present in data, inert in behavior

The codebase carries a full Arabic layer (a ~500-string `AR` map, `AR_JS` bundle,
Arabic `urgency_label`, RTL `dir`) — **but it is currently never activated.**
`shared/utils/language.py :: resolve_lang()` hard-returns `"en"`, so `dir` is
always `ltr` and `tr()` returns English. Language is not user-configurable in the
Settings UI. **Treat the app as monolingual (EN, LTR) in behavior** even though
it is bilingual in data. Reactivating i18n means making `resolve_lang` honor the
stored per-user language.

---

## 3. Project structure

### 3.1 Directory layout

```
Car-Service-AI/
├── src/
│   ├── app.py                     # FastAPI entry: mounts routers + static, shell/auth/error routes, _seed
│   ├── config.py                  # .env loader, key persistence, reference data (models, manufacturers…)
│   ├── __init__.py                # __version__ = "1.0.0"
│   ├── requirements.txt
│   │
│   ├── shared/                    # application shell (not a feature)
│   │   ├── store.py               # in-memory Store singleton (all entities)
│   │   ├── static/                # css/ (app.css, app-chat.css), js/app.js, images/, audio/
│   │   ├── templates/             # base.html, base_auth.html, navbar, sidebar, footer,
│   │   │                          #   splash, login, about, contact, 404, 500, partials/
│   │   └── utils/                 # gemini, openai_provider, templating, oauth, language,
│   │                              #   translator, audio, image_ai
│   │
│   ├── ai_report/                 # THE diagnosis wizard + reports (largest module)
│   ├── chat_ai/                   # streaming AI Mechanic chat
│   ├── image_diagnosis/           # POST /api/diagnose/image (page redirects to /diagnose)
│   ├── sound_diagnosis/           # POST /api/diagnose/audio (page redirects to /diagnose)
│   ├── car_database/              # repair guides, parts, digital twin (guides.py, parts.py, twin.py)
│   ├── maintenance/               # reminders + service history
│   ├── settings/                  # theme / AI keys / accessibility
│   ├── dashboard/                 # redirect shim → /diagnose
│   ├── voice_generator/           # browser TTS demo page (no backend AI)
│   ├── auth/                      # Google + Apple OAuth
│   └── uploads/                   # images/, audio/ staging (gitignored)
│
├── image/                         # media library: car_logos/*.svg, vehicles/<brand>/<model>.webp
├── Dockerfile                     # python:3.12-slim + uvicorn
├── cloudbuild.yaml                # Google Cloud Build → GCR
├── .env / .env.example            # config (keys, model, session secret, OAuth)
├── README.md
└── env/ , _env/                   # bundled virtualenvs — NOT source; ignore when reading the repo
```

> ⚠️ The repo contains two committed virtualenvs (`env/`, `_env/`) and an
> `env.zip`. These are **not** application code. When searching/reading, exclude
> `env/`, `_env/`, `__pycache__/`, `.idea/`.

### 3.2 Module convention

Every feature module is a Python package with the same shape:

```
<feature>/
├── __init__.py
├── routes.py          # exposes `router = APIRouter()`
├── templates/*.html   # extend shared/base.html
└── static/*.{js,css}  # mounted at /static/<feature>/
```

Adding a feature = create the package, define `router`, then register it in the
two loops in `src/app.py` (the static-mount loop and the `include_router` loop).

### 3.3 How backend & frontend connect

- **Templating.** `shared/utils/templating.py` builds a `ChoiceLoader` over the
  shared templates dir + every module's `templates/` dir, so any template can
  `{% include %}`/`{% extends %}` any other. `render(request, name, **ctx)`
  injects a **standard base context** into every page: `current_user, settings,
  vehicle, is_demo, lang, dir, js_i18n, languages, years, fuel_types,
  transmissions, manufacturers, app_version, page_title, active`. A Jinja global
  `t('key')` translates strings.
- **Static mounts** (in `app.py`): `/static/<module>/` for each module's assets,
  `/static` for shared assets, and `/image` + `/img` for the repo media library.
- **Auth gate.** Page routes call `require(request)` → returns the user email or
  raises `RedirectException("/login")` (converted to a 303 by an exception
  handler in `app.py`).
- **Client → server** is plain `fetch()` to `/api/...` (JSON) or an SSE reader
  for chat.

### 3.4 Configuration (`config.py` + `.env`)

- `GEMINI_API_KEY` (empty ⇒ "demo"/unavailable), `GEMINI_MODEL`
  (default `gemini-3.6-flash`, invalid values fall back safely),
  `CHATGPT_API_KEY` / `OPENAI_API_KEY`, `SESSION_SECRET`,
  `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`, `APPLE_CLIENT_ID/REDIRECT_URI`.
- Reference data lives here too: `SUPPORTED_GEMINI_MODELS`, `MODEL_FALLBACKS`,
  `VEHICLE_YEARS`, `FUEL_TYPES`, `TRANSMISSIONS`, `MANUFACTURERS`,
  `SUPPORTED_LANGUAGES`.
- `config.py` strips a UTF-8 BOM from `.env` before loading (so the first key
  parses).

### 3.5 Running & deploying

```bash
python -m venv env && env\Scripts\activate      # Windows
pip install -r src\requirements.txt
uvicorn src.app:app --reload                     # http://127.0.0.1:8000
# or:  python -m src.app   (opens the browser automatically)
```

Docker: `docker build -t car-service-ai . && docker run -p 8000:8000
car-service-ai`. No API key ⇒ AI features report "unavailable"; add a key in
`.env` or the Settings page.

### 3.6 Naming conventions

- Modules: lowercase package names; each exposes `router`.
- Store IDs: `CHAT-…`, `DIA-…`, `DXS-…`, `MAINT-…` (`PREFIX-YYYYMMDD-NNNN`).
- Templates extend `base.html` (app shell) or `base_auth.html` (splash/login).
- CSS uses design tokens as CSS custom properties (`--accent`, `--brand`,
  `--glass-bg`, …) defined in `:root` / `[data-bs-theme=…]`.

---

## 4. UI / UX

### 4.1 Design system & styling approach

- **Bootstrap 5.3** as the base grid/components, heavily themed on top by a
  single large stylesheet (`shared/static/css/app.css`, 8,381 lines) plus
  `app-chat.css`.
- **Premium automotive dark aesthetic** — a navy/graphite palette
  (`--bg-primary: #060d18`) with a cyan/electric-blue accent
  (`--accent: #00e5ff`, `--accent-blue: #3b82f6`) and semantic colors
  (`--success #00e676`, `--warning #ffab00`, `--danger #ff1744`).
- **Glassmorphism** — translucent surfaces (`--glass-bg`, `--glass-strong`,
  `--glass-border`), soft shadows, rounded radii (`--radius`, `--radius-lg`).
- **Theming** via `data-bs-theme` (`dark` / `light` / `auto`). An inline
  `<head>` script applies the saved theme **before paint** (from
  `localStorage['cs-theme']`, `auto` follows `prefers-color-scheme`) to avoid a
  flash. Both dark and light are variants of the same navy system.
- **Typography** — Inter (UI), JetBrains Mono (code/mono), Tajawal (Arabic).
- **Icons** — Bootstrap Icons throughout.

### 4.2 Application shell & navigation

Authenticated pages (`base.html`) use a three-part shell:

- **Sidebar** (`sidebar.html`) — brand, primary nav (**AI Diagnosis**
  `/diagnose`, **My Diagnoses** `/my-diagnoses`), system nav (**Settings**,
  **About**, **Contact**), an AI status dot (online / "Demo mode · add API
  key"), and a user chip with a theme toggle. The active item is highlighted via
  the `active` context key.
- **Topbar** (`navbar.html`) — mobile sidebar toggle, page title, an "AI System
  Online" pulse pill, and an account dropdown (Settings / About / Log out).
- **Main content** — the page body; every authenticated page also embeds a
  **global AI Chat modal** (`#chat-modal-overlay`) with a Gemini/ChatGPT model
  selector and a history button.

Navigation flow:

```
/  →  /splash  (marketing home)
      ├─ not signed in →  /start → /login → (Google / Apple OAuth) → /diagnose
      └─ signed in     →  /diagnose
/diagnose  ⇄  My Diagnoses (/my-diagnoses)  ⇄  Reports (/reports)  ⇄  Chat (/chat)
Sidebar → Settings / About / Contact ;  Repair guide, Maintenance, Voice = supporting pages
Dashboard (/dashboard) → 303 redirect → /diagnose
```

`/diagnose` is the effective home after login (dashboard is just a redirect
shim).

### 4.3 Key views & interaction patterns

- **Splash / home** (`splash.html`, `base_auth.html`) — an animated marketing
  landing page: video-style hero with gradient text, a 3×2 grid of 3D
  tilt/"deck of cards" feature cards, a "How it works" 4-step process, an AI
  Mechanic mock-conversation card, and CTAs. Animations (parallax, ring
  carousel, deck spread via IntersectionObserver, mouse-tilt) are in `app.js
  initSplash()`. Reduced-motion is respected on touch devices.
- **Login** (`login.html`) — a split panel: left branding + feature checklist
  over an animated "automotive AI" background (car silhouette SVG, scanning
  line, diagnostic dots, circuit lines, glow orbs, HUD corners); right card with
  a **Continue with Google** button and an AI-status chip.
- **Diagnosis wizard** (`diagnose.html`) — the flagship view: a 6-step stepper,
  brand/model picker with logos and images, voice input, a rule-based guided
  questionnaire, media upload, review, a themed "GEMINI ANALYSIS ACTIVE" loading
  overlay, and a two-column **result + live chat workspace**. Result cards show a
  severity badge, an SVG confidence ring, numbered causes/actions, parts, cost &
  time, prevention tips, and a thumbs feedback widget.
- **My Diagnoses** (`my_diagnoses.html`) — resumable session cards with a status
  pill (completed / in_progress / diagnosing / ready), inline rename, delete
  confirm, and client-side search. "Continue Diagnosis" reopens the wizard at the
  saved step; "View Result" jumps to the report; "Continue Chat" opens the linked
  thread.
- **Reports** (`reports.html`) — stat tiles with animated count-up
  (IntersectionObserver in `reports.js`): total, urgent, low-risk, and an
  aggregate estimated cost; plus a history table with View / PDF links.
  `diagnosis.html` and `diagnosis_print.html` render a single report (the latter
  print/PDF-friendly).
- **Chat** (`chat.html`) — a full ChatGPT-style workspace: slide-in history
  panel (new-chat, search, thread list), a topbar model switch
  (**Gemini** / **ChatGPT**), a welcome state with 8 preset suggestion chips,
  role-based bubbles with Copy / Download-as-`.md` / Regenerate actions, a
  composer with auto-grow textarea, image attach, and **voice input** (Web
  Speech API), and a decorative HUD panel that hides once a conversation starts.
  Live token-by-token markdown streaming is toggle-able (`cs-streaming` flag).
- **Maintenance** (`maintenance.html`) — two columns: "Upcoming services" cards
  (status badge, next/current/remaining km, gradient progress bar, "% of
  interval used") and a "Service history" timeline. An add-reminder modal exists
  (its trigger is currently commented out).
- **Repair guide** (`repair_guide.html` / `_detail.html`) — a searchable,
  category-filterable card catalog (pure client-side filtering) and a numbered
  step-by-step detail page with tools/parts chips and related guides.
- **Settings** (`settings.html`) — a tabbed panel with **Appearance** (theme
  picker), **AI & Models** (Gemini/ChatGPT keys with show/hide, model select,
  streaming toggle, Test-connection, Clear-cache), and **Accessibility**
  (reduce-motion, high-contrast, text-size). *(No Language or Notifications tab
  is currently rendered, though the store/translator carry those settings.)*
- **Voice generator** (`voice_generator.html`) — a standalone cinematic page that
  does **browser text-to-speech** only (Web Speech API); its "MP3 export / 50+
  voices" claims are marketing chips, not implemented backend features.

### 4.4 Usability & accessibility considerations

- **Skip-to-content** link and ARIA roles on the sidebar/nav and chat modal.
- **Accessibility settings**: reduce-motion, high-contrast, and font-size
  scaling (stored per user; applied via `a11y` settings).
- **Optimistic UI**: theme changes and toggles apply instantly and persist
  fire-and-forget; toasts (`CS.toast`) confirm saves/errors.
- **Progressive enhancement / graceful degradation**: voice features fall back
  cleanly when the Web Speech API is unavailable; AI errors render as a
  non-regenerable message rather than breaking the page.
- **Responsive**: mobile sidebar becomes a toggled drawer; grids collapse via
  Bootstrap breakpoints; the deck/tilt animations simplify on touch devices.
- **Resumability**: wizard autosave + browser Back/Forward integration means a
  user can leave mid-diagnosis and return exactly where they were.

---

## 5. Known gaps & gotchas (for the next developer)

1. **Data is ephemeral** — in-memory store; everything resets on restart. Login
   re-seeds a demo Audi A4 + reminders + 2 AI reports.
2. **i18n / RTL is inert** — `resolve_lang` hard-returns `"en"`; the Arabic layer
   and `dir=rtl` never activate; no language switch in the UI.
3. **Email/password login is a no-op** — only Google/Apple OAuth actually sign
   users in.
4. **ChatGPT key mismatch** — saved as `CHATGPT_API_KEY`, read as
   `OPENAI_API_KEY`; verify before shipping the ChatGPT provider.
5. **Unwired backends** — digital-twin, vehicle-detect, and parts-map endpoints
   have no frontend; a "My Garage" blueprint view is implied but unbuilt.
6. **Split JS wiring** — some interactions (maintenance done/delete/add, settings
   test/clear-cache buttons) are expected from a global handler, not the
   per-module JS; the maintenance "New reminder" button is commented out.
7. **Legacy pages** — `/diagnose/text|image|audio` GET pages redirect into the
   unified `/diagnose` wizard; their old templates/JS remain but are dormant.
8. **Two committed virtualenvs** (`env/`, `_env/`) and `env.zip` are noise — not
   source.
9. **README "Demo Mode returns mock data"** overstates current behavior — the
   code surfaces an unavailable/error state instead of fabricated answers.
```
