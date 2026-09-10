♂# Changelog — Car Service AI redesign & enhancements

This document records every change, feature, and fix made during the
UI/UX-redesign + flow-enhancement effort. It is grouped by the numbered
requirements from the project brief. Newest work is at the top of each phase.

The work is delivered in **reviewable phases**. Phase 1 (Diagnosis data & flow)
covers requirements 4, 5, 9, 10. Cross-cutting requirements (documentation and
full responsiveness) are applied continuously.

Architectural decisions taken (product-owner approved):
- **Vehicle dataset:** live external open-source API (NHTSA vPIC for makes/models,
  CarQuery for engines) proxied + cached server-side.
- **Voice mode (req 7, later phase):** browser-native Web Speech API.

---

## Pipeline fixes (round 2)

### ✅ Listening / audio input — full pipeline restored
**Root causes (multi-layer):** the record UI (`#audio-record-btn` + controls) that
`initDiagnoseAudio()` drives was **absent from the template** (only file-upload
existed); the page (`/diagnose/audio`) **hard-redirected to `/diagnose`** so it was
unreachable; there was **no nav entry**; and browser recordings are
**`webm/opus`, which Gemini's audio API rejects** (it accepts wav/mp3/ogg/aac/flac).
**Fixes (capture → endpoint → backend → UI):**
- Un-retired `GET /diagnose/audio` to **render** the page; added a **"Sound
  Diagnosis" sidebar link**.
- Added the **Record / Stop / Cancel / Upload UI** (+ live timer, rec-dot CSS) to
  `diagnose_audio.html` matching the IDs the controller expects.
- Capture now converts the recording to **16 kHz mono WAV client-side** via the
  Web Audio API (`blobToWavFile`/`encodeWav`) before upload, so Gemini accepts it
  in every browser; MediaRecorder picks a supported container with fallbacks.
- Verified the rest of the pipeline: `POST /api/diagnose/audio` → `validate_audio`
  (wav ✓) → `gemini.diagnose(mode="audio")` → transcript + report → `renderReport`.

### ✅ Correct car images for every entry
- **Root cause:** the curated map is clean (215 paths, 0 missing/dupes), but the
  **live vPIC models discarded the backend-resolved image** (`loadLiveModels`
  dropped the `image` field), so most live cars showed the generic icon.
- **Fix:** `loadLiveModels` now passes a server-resolved `model → image` map into
  `renderModelGrid`, which prefers the curated image, then the exact-slug live
  image, then the icon — **never another model's image**. (`_image_for` verified
  to resolve by exact make/model slug.)

### ✅ Narrower "Estimated Cost" range
- **Root cause:** the prompt asked only for a vague "dollar range" and the default
  was wide (`$100–$500`).
- **Fix:** the prompt now demands a **tight range for the single most likely
  repair** (`$LOW - $HIGH`, HIGH ≤ ~1.4× LOW), and a backend safety-net
  `_narrow_cost()` **caps any still-too-wide range to ≤1.5×** and reformats it
  (tested: `$100–$900 → $100–$150`, tight ranges preserved). Default tightened.

### ✅ Theme applies across the entire app
- **Root cause:** `[data-bs-theme="light"]` tokens were still **dark** (so "light"
  looked identical), and ~200 hardcoded surface/text literals ignored tokens; the
  standalone `voice_generator.html` **hardcoded `data-bs-theme="dark"`**.
- **Fixes:**
  - Introduced theme-aware **colour-channel variables** (`--c-panel`, `--c-deep`,
    `--c-deep2`, `--c-muted`) and tokenised the dominant hardcoded families
    (`rgba(24,27,33…)`, `rgba(16,18,22…)`, `rgba(148,163,184…)`, `#e2e8f0`) across
    all three stylesheets so they flip with the theme.
  - Rebuilt the light theme as a **lifted-graphite "dim" theme** (safe: a pure-white
    theme would hide the ~70 hardcoded white-text elements) — visibly different and
    consistent everywhere, all text readable.
  - `voice_generator.html` now reads the stored theme via the pre-paint script
    (and its leftover blue favicon → safety orange).

### ✅ Auto-select the Quick problem category
- New `autoDetectCategory()` maps the typed problem to the correct chip
  (engine/brakes/battery/ac/electrical/transmission/suspension) via keyword rules,
  and auto-selects it **as the user types** — unless they pick one manually
  (`_categoryAuto` guard; a saved category on resume is treated as manual).



## Fixes & theming (post-Phase-2)

### ✅ Theme + custom accent colour (with persistence)

- Light / Dark / Auto already worked; **added accent-colour customization** in
  **Settings › Appearance**: 7 presets (orange/blue/green/violet/red/cyan/amber)
  + a **custom colour picker** + Reset.
- New `CS.applyAccent(hex)` (in `app.js`) derives the whole accent family
  (`--accent`, `--brand`, `--accent-2`, `--brand-hover`, `--accent-soft`,
  `--brand-soft`, `--glass-border`, `--sidebar-active`) from one colour, so every
  token-driven component recolours together.
- **Persistence:** localStorage (instant, per-device) **and** the per-user store
  (`accent` field added to `_default_settings` + save whitelist). Applied
  **before first paint** in the `base.html` / `base_auth.html` head scripts
  (localStorage, falling back to the server-stored value → works cross-device,
  no flash).
- Bonus fix: the Settings theme pick now calls `CS.applyTheme()` so **"Auto"
  resolves to the OS preference** instead of literally setting
  `data-bs-theme="auto"`.

### ✅ Fix — "Continue diagnosis" returned a blank result

- **Root cause:** a diagnosis session is autosaved with the current wizard
  `step`. During/after a run that step becomes a **transient non-wizard value**
  (`loading` / `workspace` / `result`). `showStep()` deliberately *hides* the
  wizard for those steps (the result lives in a modal/overlay), so resuming such
  a session via **Continue Diagnosis** ran `showStep("loading")` and rendered a
  blank page.
- **Fix:** `loadSession()` now **clamps any non-wizard step** back to a safe
  wizard step on resume (`ready` if a problem exists, else `describe`/`welcome`).
  Completed sessions with a saved diagnosis still open straight to the result.

### ✅ Fix — Voice "listening" not working

- **Root cause:** the Web Speech API only works in a **secure context**
  (HTTPS or `localhost`/`127.0.0.1`). On an insecure origin (e.g. a LAN IP in the
  Docker/deployed build) the API object still exists, so the mic looked enabled,
  but `recognition.start()` failed — sometimes throwing synchronously — leaving
  the UI stuck in "Listening…" with no feedback.
- **Fix (all three voice entry points — chat mic in `app.js`, and the problem-
  description + vehicle-detection mics in `diagnose.js`):**
  - **Secure-context detection** up front: if not HTTPS/localhost, the mic is
    disabled with a clear tooltip + toast ("Voice input needs a secure
    connection (HTTPS) or localhost") instead of silently failing.
  - **`recognition.start()` wrapped in try/catch** so a synchronous throw no
    longer leaves the button stuck; the UI resets and shows a friendly error.
  - Unsupported-browser messaging clarified (Chrome/Edge).

---

## Phase 2 — Visual redesign & layout/UX fixes

Brand direction (product-owner approved): **Service Garage — Graphite + Safety Orange**.

### ✅ Req 1 (foundation) — Cohesive automotive "Service Garage" brand

App-wide re-theme from the previous navy + electric-cyan identity to a graphite +
safety-orange automotive-service identity, implemented at the design-token level
plus a controlled global swap of the hardcoded colour literals.

**Palette**
- Primary accent: **safety orange `#ff7a1a`** (`--accent` / `--brand`), lighter
  `#ffa24d` (`--accent-2`) for gradients/highlights.
- Surfaces: **graphite** — base `#101317`, surfaces `#181b21` / `#1e222a` /
  `#262c36` (replacing the navy `#060d18`/`#0a1628`/…).
- Secondary/informational: muted **steel-blue `#5b7d9e`** (`--steel` / `--info`).
- Semantic states warmed slightly (success `#22c55e`, danger `#ff4438`).

**Scope of the swap (mechanical, `git diff`-reviewable)**
- `--brand` remapped from blue to orange; `--accent-blue` repurposed as steel.
- Global literal replacement across `app.css`, `app-chat.css`, `diagnose.css`,
  `voice_generator.css` **and every template's inline styles/SVGs**:
  - cyan `#00e5ff` + `rgba(0,229,255,*)` → safety orange (≈730 occurrences)
  - bright blue `#3b82f6` / `#60a5fa` / `rgba(59,130,246,*)` / `rgba(0,180,255,*)`
    → orange / light-orange (≈80 occurrences)
  - navy surfaces `rgba(10,22,40,*)`, `rgba(6,13,24,*)`, `#0a1628`, `#0e1e35`, … →
    graphite equivalents (≈120 occurrences)
- Favicon tint updated to safety orange.
- Light-theme token block also moved off navy onto graphite.

**Validation:** CSS brace balance verified on all four stylesheets; every
top-level template compiles; `/splash` & `/login` render 200 and the served
`app.css` carries the orange accent.

### ✅ Req 6 — Modern severity indicator (color-coded gauge)

- New reusable **`severityMeter(sev, conf)`** component (`diagnose.js`) rendering a
  4-segment **Low → Moderate → Severe → Critical** gauge that fills up to the
  detected level, with a pointer thumb, a level badge, the AI confidence, a
  scale, and a plain-language message. Critical pulses subtly.
- Replaces the two older ad-hoc severity blocks in **both** the result modal and
  the workspace result panel, so severity now reads at a glance and is consistent.
- Colour-coded to the palette (green/amber/orange/red); respects
  `prefers-reduced-motion`. New CSS: `.dz-sevmeter*` in `diagnose.css`.

### ✅ Req 11 — Modern sidebar & navigation

- Active nav item now has an **orange left-accent bar** + subtle gradient wash;
  hover nudges the item; brand logo gets a playful hover tilt.
- **Keyboard focus rings** (`:focus-visible`) added to sidebar links, icon
  buttons, the brand, and dropdown items (a11y). Respects reduced-motion.
- Fixed a leftover cyan glow in the sidebar background gradient (now orange).

### ✅ Req 12 — Scroll behaviour

- `scroll-behavior: smooth` for anchor jumps (disabled under reduced-motion).
- **`overscroll-behavior: contain`** on all inner scroll regions (sidebar nav,
  page, chat history, suggestion lists, result panels, grids) to stop
  nested-scroll hijacking / rubber-band chaining (the "unexpected jump" class of
  bugs).
- Consistent **themed thin scrollbars** app-wide (WebKit + Firefox).

### ✅ Req 2 — Faster, smoother splash

- Compressed the hero entrance sequence: the last element now lands at ~0.67s
  instead of ~1.1s (badge/title/sub/actions delays 0.08→0.32s, durations 0.35s;
  content fade 0.4s@0.12s) — removes the perceived load lag.
- Made the 3D parallax follow snappier (AI-core lerp 0.06→0.12, deck tilt
  0.08→0.14) so motion feels responsive rather than laggy.

### ✅ Req 3 — Diagnosis-steps alignment/spacing

- Stepper now distributes evenly full-width; on phones only the **active step's
  label** shows (prevents label crowding/overlap), circles shrink ≤380px.
- (Earlier responsiveness pass also collapsed the answer-options and
  problem-category grids and aligned the wizard breakpoints.)

### ✅ Req 8 — "Last diagnosis" screen layout

- Fixed leftover **blue/cyan hardcoded colours** on the server-rendered report
  (`diagnosis.html` / `diagnosis_print.html`) — notably the **confidence-ring
  gradient** (`#2563EB`→`#06B6D4`) which the first swap missed (uppercase/other
  hexes) — so the report screen matches the Service Garage palette.
- Swept the remaining stray cyan/blue variants (`#22d3ee`, `#38bdf8`, `#0ea5e9`,
  `#06b6d4`, `#2563eb`) across all CSS/HTML/JS to zero.

## Phase 3 — Multi-modal & voice

### ✅ Req 7 (part 1) — Video upload diagnosis + image-based vehicle ID
- **New `src/video_diagnosis/` module** — mirrors the sound-diagnosis module
  shape: `GET /diagnose/video` page, `POST /api/diagnose/video` API, sidebar
  link. Accepts MP4/WebM/MOV/MKV up to 20 MB (`shared/utils/video.py:
  validate_video`), with drag-and-drop, live `<video>` preview, a loading
  state while Gemini analyses the clip, and the same structured report/PDF
  pipeline as image and audio diagnoses (`gemini.diagnose(mode="video")` now
  sends the clip inline via `Part.from_bytes` and prompts Gemini to reason
  about both visible symptoms — leaks, smoke, warning lights — and audible
  ones — knocking, squealing).
- **New "Identify Vehicle" tool** (`/vehicle/identify`, `car_database` module)
  — upload a photo of a car and get back a best-guess manufacturer/model/year/
  body style/color with a confidence score (`twin.identify_vehicle_image` +
  new `gemini.ask_gemini_image` helper), with a one-click "Save vehicle"
  action into the existing vehicle profile. Degrades gracefully (matches the
  existing digital-twin/detect-vehicle pattern) when no AI key is configured.
- Both flows validate file type/size before upload and surface clear,
  localized error toasts (unsupported format, oversized file, empty file, AI
  unavailable) rather than failing silently.
- Still pending: a browser-native (Web Speech API) ChatGPT-style voice
  conversation mode (req 7, part 2).

### ✅ Splash — responsiveness + background fixes
- `.hp-hero-content` had **no base rule**, only breakpoint overrides — on
  desktop/tablet it had no padding/max-width, and (lacking a `z-index`) was
  painted *below* `.hp-hero-overlay` in the stacking order, dimming the hero
  title/subtitle under the gradient scrim. Added a proper base rule.
  `.hp-hero` used bare `100vh`, which on mobile Safari/Chrome includes the
  area hidden behind the address bar; added an `svh` fallback so the hero
  never renders taller than the visible viewport.
- The hero photo (`ai-services.png`) has its subject (car headlight/wheel) in
  the right ~40% of the frame; `background-position: center center` cropped
  it out entirely on narrow/tall phone screens. Repositioned to `right
  center` so the car stays in frame as the viewport narrows.
- Layered a warm accent-tinted radial glow over the existing graphite panel
  gradient on `body.splash-bg::after`, built from the theme's own
  `--accent-rgb`/`--c-panel` tokens so it follows the light/dark/auto theme
  and any custom accent color automatically.

---

## Phase 1 — Diagnosis data & flow

### ✅ Req 4 — Cascading brand → model → engine autocomplete (live data)

**New backend module — `src/car_database/vehicle_api.py`**
- Live vehicle reference data via **NHTSA vPIC** (makes & models; free, no API key)
  and **CarQuery** (engines/trims) with a synthesized engine fallback.
- All requests are **proxied server-side** (no browser CORS) and **cached in
  memory for 12 h** with async locks so per-keystroke autocomplete never floods
  the upstream APIs.
- Models are fetched across the `car` + `mpv` + `truck` vehicle types and merged,
  so **SUVs/crossovers (e.g. CR-V) and pickups are included** while
  motorcycles/ATVs/trailers are excluded.
- Results are **enriched with the local brand logos and vehicle images** already
  shipped in `image/`, and make names are normalized to canonical form
  (`BMW`, `GMC`, `Mercedes-Benz`, `Rolls-Royce`, …) via a canonical map.
- Fully **graceful**: any upstream failure returns curated/fallback data instead
  of erroring; works offline (curated models + synthesized engines).

**New API routes — `src/car_database/routes.py`**
- `GET /api/vehicles/makes?q=` → `{items:[{value,label,logo}]}`
- `GET /api/vehicles/models?make=&q=` → `{items:[{value,label,image}]}`
- `GET /api/vehicles/engines?make=&model=&q=` → `{items:[{value,label,fuel}]}`
- All auth-protected (require a logged-in session).

**Frontend — the wizard cascade (`ai_report/static/diagnose.js`, `diagnose.html`, `diagnose.css`)**
- Added a cached, debounced `VehicleAPI` client (fetch + in-memory promise cache).
- Selecting a brand now renders the **full live model catalogue** for that brand
  (curated models render first for instant paint, live models are merged in).
- New **engine cascade step**: a search-as-you-type input + suggestion chips
  filtered by the selected model, or type-your-own (press Enter). Optional.
- `state.vehicle` gained an `engine` field; it persists through session
  autosave/restore, shows in the "Diagnosing:" badge and the review summary, and
  is included in the AI prompt (`gemini.py` appends the engine to the vehicle
  label passed to Gemini).
- New CSS: `.dz-car-engines`, `.dz-engine-input`, `.dz-engine-chip`,
  `.dz-selected-engine`, spinner, matching the existing `dz-` glass design.

### ✅ Req 5 — Real-time problem suggestions with media & contextual notices

**`ai_report/static/diagnose.js` + `diagnose.css`**
- Replaced the flat `PROBLEM_SUGGESTIONS` string list with a rich
  **`PROBLEM_CATALOG`** (38 entries). Each entry has: `text`, `cat` (category),
  `icon` (Bootstrap Icon = the "media"), `tone` (danger/warning/info/success),
  and a **contextual safety `notice`** (e.g. "Stop safely if the temperature
  gauge is in the red…").
- Rewrote `renderProblemSuggestions()` to render, as the user types, each
  suggestion with a **colour-coded media icon badge**, the highlighted matching
  text, a **category tag**, and the **contextual notice** — mirroring the
  autocomplete pattern from Req 4. Matching now also considers category and
  notice text, not just the title.
- New CSS: `.dz-sugg-media(--danger/warning/info/success)`, `.dz-sugg-body`,
  `.dz-sugg-title`, `.dz-sugg-notice`, `.dz-sugg-cat*` (category tags collapse on
  ≤576px to save space).

### ✅ Req 9 — Continue chatting after the wizard with the same context

**`src/chat_ai/routes.py`**
- Fixed a real bug: `POST /api/chat/save-diagnosis` created a **new chat thread
  on every call**, so the result-workspace chat and a later "Continue Chat"
  produced **duplicate threads** and lost the shared context.
- It is now **idempotent per diagnosis session**: if the session already has a
  linked `chat_id`, the existing thread is reused (and set active) instead of
  creating a duplicate — so the user keeps the **same conversation context**
  whether they continue from the result workspace or later from My Diagnoses.

_(The underlying continue-chat flow already existed: the result workspace seeds a
linked thread and streams follow-ups; My Diagnoses offers "Continue Chat". This
change makes that context single and stable.)_

### ✅ Req 10 — Edit / resume / delete past diagnoses with safeguards

**Store (`src/shared/store.py`)**
- Diagnosis sessions gained two fields: `locked` (bool) and `service_request`
  (`{active, requested_at}` or `None`).

**Backend (`src/ai_report/routes.py`)**
- `POST /api/diag-sessions/{id}/delete` is now **guarded**:
  - returns **409 `in_progress`** if the session status is `diagnosing`
    (a diagnosis is actively running);
  - returns **409 `locked`** if the session is tied to an **active service
    request** (`locked` or `service_request.active`), with a clear message.
- New route `POST /api/diag-sessions/{id}/service-request` `{active: bool}` —
  toggles an active service request, which **locks the diagnosis against
  deletion** (the concrete "active service request" safeguard).
- `service_request` and `locked` added to the autosave whitelist.

**Frontend — My Diagnoses (`ai_report/templates/my_diagnoses.html`)**
- **Edit** action on completed cards → opens the wizard at the review step
  (`/diagnose?session_id=…&edit=1`) so inputs can be changed and the diagnosis
  re-run (new `editMode` path in `loadSession()` avoids jumping straight to the
  result).
- **Continue Chat** now works whether or not a thread exists yet (falls back to
  the result workspace which seeds/continues the chat).
- **Request service / Cancel request** toggle button → calls the service-request
  route; a **"Service booked" lock badge** appears and the card is styled as
  locked. Attempting to delete a locked diagnosis surfaces the guard message.
- Delete confirmation modal retained; delete errors (incl. the 409 guards) are
  surfaced to the user.
- New CSS: `.md-card-btn--icon`, `.md-card-btn.active`, `.md-lock-badge`,
  `.md-card.locked`, disabled-button styling.

---

## Cross-cutting — Full responsiveness pass

Driven by a full responsive audit (mobile ≤576 / tablet 577–991 / desktop ≥992).

**Shell (`src/shared/static/css/app.css`)**
- Defined the previously-**undefined `--navbar-height`** token (62px desktop /
  54px ≤991) that several full-height panels referenced (it always fell back to
  56px and mismatched the real topbar, pushing bottom content off-screen).
- Switched full-height wrappers (`.settings-wrap`, `.gpt-wrap--no-side`) to
  **dynamic viewport height (`dvh`)** and removed a phantom `-44px` footer
  subtraction (there is no footer bar in the authed shell) — fixes the save
  bar / composer being clipped under mobile browser chrome.
- **44px minimum touch targets** on coarse pointers for `.btn-icon` (incl. the
  sidebar hamburger), chat-modal controls.
- Full-screen mobile chat modal uses `100dvh`.

**Diagnosis wizard (`src/ai_report/static/diagnose.css`)**
- `.dz-wrap` / `.dz-workspace` now use `dvh`.
- **Workspace mobile layout fixed** (≤991.98px): the **result panel moves to the
  top** (`order:-1`, capped height, scrollable) and the **chat gets a bounded
  scroll row** so the message list scrolls and the composer stays visible
  (previously the composer could be pushed off-screen).
- Answer options collapse to **1 column ≤480px** (`.dz-options`).
- Problem categories: **3-up on tablet, 2-up on phones**, labels may wrap
  (`.dz-problem-categories` / `.dz-category-btn`).
- Inline result rows stack ≤560px (`.dz-res-row`); mobile modals use `100dvh`.
- 44px touch targets for the wizard's icon buttons (search clear/voice, problem
  voice/clear, modal close) and comfortable sizing for the new engine chips.

---

## Files touched (Phase 1 + responsiveness)

| File | Change |
|---|---|
| `src/car_database/vehicle_api.py` | **New** — live makes/models/engines with cache + fallback |
| `src/car_database/routes.py` | +3 vehicle autocomplete routes |
| `src/ai_report/static/diagnose.js` | Engine cascade, live models, rich problem suggestions, edit-mode |
| `src/ai_report/templates/diagnose.html` | Engine cascade + selected-engine markup |
| `src/ai_report/static/diagnose.css` | Engine styles, rich suggestion styles, responsive refinements |
| `src/ai_report/routes.py` | Delete safeguards, service-request route, autosave whitelist |
| `src/ai_report/templates/my_diagnoses.html` | Edit / service-request / lock UI + handlers |
| `src/chat_ai/routes.py` | Idempotent `save-diagnosis` (same-context chat) |
| `src/shared/store.py` | `locked` / `service_request` session fields |
| `src/shared/utils/gemini.py` | Engine included in the AI vehicle label |
| `src/shared/static/css/app.css` | `--navbar-height`, dvh panels, touch targets |

## Validation performed
- `node --check` on `diagnose.js`; Python `ast` parse + `import src.app` for all
  edited modules; CSS brace-balance checks.
- Live-tested the vehicle API against upstream (makes/models/engines, image &
  logo enrichment, brand-name casing, SUV inclusion, mojibake filtering).
- Verified new routes resolve and are auth-protected via `TestClient`; verified
  the store's `locked`/`service_request` fields and the delete-guard path.
- **Recommended manual check:** run `uvicorn src.app:app --reload`, open
  `/diagnose`, and exercise the brand→model→engine cascade, typed problem
  suggestions, edit-a-past-diagnosis, and the service-request delete guard across
  mobile/tablet/desktop widths.

## Not yet done (later phases from the brief)
- Req 1 (full brand redesign), 2 (splash animation), 3 (diagnosis-step alignment),
  6 (severity indicator redesign), 7 (voice conversation mode — video/image
  upload is now done, see Phase 3), 8 (last-diagnosis screen), 11 (sidebar/nav
  redesign), 12 (scroll behaviour) — to be delivered in subsequent phases.
  Brand-search box could also be wired to the live `makes` endpoint (currently
  the popular-brands grid is curated; models + engines are fully live).
