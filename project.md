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
> a cross-device responsiveness pass. The **2026-09-07 fix pass** below is the
> latest batch.

---

## 0. Fix & improvement pass — 2026-09-07

This batch addressed a list of theming, diagnosis-flow, input and content issues.
Each item notes **what** changed and **where**, so this section is the quick map
to the code.

### Theming & styling
1. **Accent colour now applies on every page (incl. diagnosis pages).** The
   diagnosis CSS (`ai_report/static/diagnose.css`) and the shared stylesheets
   hard-coded the orange literal `#ff7a1a` / `rgba(255,122,26,…)` ~800 times, so
   the runtime accent override never reached them. Introduced an **`--accent-rgb`
   channel** token (`app.css :root`) and converted **all** accent literals across
   `diagnose.css`, `app.css`, `app-chat.css`, `voice_generator.css` and
   `my_diagnoses.html` to `var(--accent)` / `rgba(var(--accent-rgb), a)`. The JS
   `applyAccent()` (`app.js`) and the pre-paint head scripts (`base.html`,
   `base_auth.html`) now also set `--accent-rgb`, so a chosen accent recolours
   the whole app — diagnosis pages included.
2. **Default theme is now Blue.** `:root --accent` is `#3b82f6` (was safety
   orange), `--accent-rgb: 59,130,246`, `--brand`/`--accent-2`/`--brand-hover`
   updated to the blue family; `ACCENT_DEFAULT` in `app.js` and the Settings
   accent swatches/`accent-custom` default reordered to Blue-first.
3. **Light/Dark toggle works.** Mechanism (`data-bs-theme` + `applyTheme`) was
   fine, but hard-coded dark page backgrounds (`#101317`, `#0a0b0e`) kept the
   diagnosis/chat surfaces dark under the light theme — converted to
   `var(--page-bg)`. The sidebar theme toggle (`[data-theme-toggle]`) now also
   **persists to the server** (`POST /api/settings`), not just `localStorage`.
4. **Mobile menu fixed (was shaded / unclickable).** In the mobile breakpoint the
   `.sidebar-backdrop` had `z-index:1059` while `.sidebar` inherited only `1040`,
   so the backdrop rendered **over** the drawer (darkening it and eating clicks).
   The mobile `.sidebar` now sets `z-index:1060`.
5. **Margins / scrolling / responsiveness (targeted pass).** Added a global safety
   block (`html { overflow-x:hidden }`, `img { max-width:100% }`, consistent phone
   `.page` padding) to kill horizontal scroll and tighten mobile margins;
   normalised the diagnosis wrapper background to the theme token.
6. **AI Diagnosis ↔ My Diagnoses design unified.** `my_diagnoses.html` now uses a
   header that mirrors the AI-Diagnosis wizard header (icon badge + title +
   subtitle + "AI System Online" status pill) and shares the token-based card
   styling.

### Diagnosis flow
7. **Blank screen when opening a diagnosis — hardened.** `loadSession()`
   (`diagnose.js`) now always lands on a visible step: the completed-result path
   renders the wizard behind the modal first and is wrapped in try/catch, and the
   outer catch falls back to a safe wizard step, so a restore error can never
   leave a blank page.
8. **Removed the redundant "Start Diagnosis" button / duplicate step.** The
   welcome splash step (and its `#dz-start` button) was removed; the wizard opens
   directly on **Vehicle** selection. The session is created lazily on the first
   real action (picking a brand / VIN lookup) so empty visits don't create junk
   sessions. The final **Ready → Start Diagnosis** button (which actually runs the
   AI) is retained.
9. **Distinct, descriptive diagnosis names.** New `Store._unique_title()` appends
   ` (2)`, ` (3)`… to avoid duplicates, and `Store.set_session_title_from_diagnosis()`
   renames a completed session to the **AI-detected fault** (e.g. *"Audi A4 — Worn
   brake pads"*), called from `POST /api/diagnose/complete`. User renames are
   respected via a `title_custom` flag.
10. **Progress is persisted per user.** The in-memory `Store` now snapshots all
    per-user collections (users, vehicles, chats, diagnoses, maintenance, settings,
    **diagnosis sessions**) to `data/store.json` after each mutation and reloads on
    startup (`Store._save()` / `Store._load()`). "Continue diagnosis" now survives a
    restart. `data/` is gitignored.
11. **Dynamic, per-vehicle images (incl. the model grid).** Static `.webp`
    placeholders (which were generic — every model showed the same car) are
    replaced by images fetched from an external CDN (imagin.studio) keyed on
    make/model/year. **Every** vehicle image now uses the API: the model-selection
    cards, the selected-vehicle card, the info panel, the loading screen and the
    continue-to-chat card — each requests its **own** `modelFamily` so the picture
    matches that exact model. Client `getVehicleImageUrl()` points at the server
    proxy `GET /api/vehicles/image` (→ `vehicle_api.image_url()`), which builds the
    CDN URL from the **env-configurable** `IMAGIN_CUSTOMER` key and 307-redirects.
    A progressive `onerror` fallback (`dzImgFallback`) degrades → shipped local
    image → icon. **⚠ Superseded by item 21:** the primary image source is now real
    Wikipedia photos, not the imagin CGI CDN (which produced schematic-looking
    watermarked renders); imagin is now off by default.
12. **"Unable to Complete Diagnosis" / `401 UNAUTHENTICATED
    ACCESS_TOKEN_TYPE_UNSUPPORTED` fixed.** Root cause: the Gemini client was
    letting the credential be treated as an OAuth access token. Fixes in
    `gemini.py`: (a) `genai.Client(api_key=…, vertexai=False)` forces the Gemini
    **Developer API** so the key is sent as an API key, never a bearer token;
    (b) a per-user **Settings key now takes priority** over the `.env` key (matching
    the documented intent) so a bad `.env` key can be overridden at runtime;
    (c) keys are sanitised (`_clean_key` strips whitespace/quotes/BOM);
    (d) auth/quota/timeout errors are surfaced as plain-language guidance
    (`_friendly_error`). **Note:** the committed `.env` key (`AQ.Ab8RN6…`) is **not**
    a valid Gemini API key (those start with `AIza…`) — replace it in `.env` or via
    **Settings → AI & Models**.

### Search & input
13. **VIN search added.** `vehicle_api.decode_vin()` (NHTSA vPIC `DecodeVinValues`)
    + `GET /api/vehicles/vin`, with a VIN input in the wizard's Vehicle step and
    `initVinLookup()`/`applyDecodedVehicle()` in `diagnose.js`. A valid 17-char VIN
    auto-fills make/model/year/engine (tested end-to-end: `1HGCM82633A004352` →
    *2003 Honda Accord, 3.0L 6-cyl*). Invalid/unknown VINs show a friendly message
    and let the user pick manually. Voice search is unchanged and still available.

### Content
14. **Less jargon / plain-language explanations.** VIN input explains it is the
    car's 17-character "chassis number" and where to find it; the sidebar AI-status
    reads *"AI offline · add your AI key"* instead of "Demo mode"; AI auth/errors
    now speak plainly (see item 12).

### Follow-up pass — UI consistency, accessibility, logo, brands
15. **Consistent card layout across pages.** `.dz-card` still hard-coded a navy
    background + **cyan** border (`rgba(8,22,38)`, `rgba(0,200,255)`) — converted to
    theme tokens (`rgba(var(--c-deep),…)`, `rgba(var(--accent-rgb),…)`) so it flips
    with theme and uses the accent. Added a shared **`.app-card`** + `.app-page-header`
    component in `app.css`, and **My Diagnoses** now wraps its content in an
    `.app-card` with the same header treatment as **AI Diagnosis** — the two pages
    now read as one app. (Other pages — Settings, Maintenance, Repair Guide — already
    use token-based cards; `.app-card` is the target to migrate them to next.)
16. **Accessibility settings now actually apply.** Root cause: nothing ever applied
    the stored a11y prefs to the DOM and **no CSS existed** for them. Added: (a) CSS
    for `html.a11y-reduce-motion`, `html.a11y-high-contrast`, and
    `html[data-font-size="large"|"xlarge"]` in `app.css`; (b) server-side application
    on `<html>` in `base.html` (class + `data-font-size` from `settings.a11y`), so it
    persists across page loads with no flash; (c) `CS.applyA11y()` in `app.js` +
    change listeners in `settings.js` so toggles/selects take effect **instantly**.
    Reduce-motion neutralises animations/transitions; high-contrast brightens text &
    strengthens borders; text-size scales all rem/em sizing (18px / 20px root).
17. **Theme-aware logo icon.** `logo-icon.svg` was loaded via `<img>` (an isolated
    document that can't read page CSS vars), so it never followed the accent. Replaced
    the in-page usages (splash, about, login) with a `<span class="cs-logo-icon">` that
    paints the SVG as a **CSS mask** filled with `var(--accent)` — so the logo now
    tracks the selected accent across all themes. (The browser-chrome favicon still
    references the static file.)
18. **"View all brands" now works.** The button had **no handler** and `renderBrandGrid()`
    only ever rendered the first 12 brands. Added `initViewAllBrands()` + a
    `renderBrandGrid(showAll)` toggle in `diagnose.js` that swaps between the popular 12
    and the full brand list (and updates the button/heading label).
19. **Diagnosis header ↔ cards edge alignment.** On wide screens (`≥1440px`) the
    wizard header bar was capped at `max-width:1280px` while the card grid widened to
    `1400px`, so the header's edges stopped ~60px short of the cards below. Replaced
    the three separate max-widths (`.dz-wizard-header-inner`, `.dz-main-grid`,
    `.dz-benefits`) with a single `--dz-content-max` variable (1280 → 1400 at ≥1440px)
    so the header, cards and benefits bar always share the same left/right edges. Also
    converted the header's leftover hard-coded navy background to `rgba(var(--c-deep),…)`.

### Full make/model coverage + realistic vehicle photos
20. **All makes / models / years selectable.** `vehicle_api.makes()` now unions the
    vPIC `car`, `mpv` (SUV/crossover) and `truck` (pickup) vehicle types → **406 makes**
    (was 195; SUV/EV-only brands like **Rivian**, **Lucid** were previously missing).
    "View all brands" (`ensureAllBrands()` in `diagnose.js`) merges the curated logo
    list with the full live catalogue, and the vehicle **search box** now appends live
    makes (`augmentWithLiveMakes()`) so any make is findable by typing — not just the
    curated 49. Models come from vPIC per make **across all production years** (no year
    restriction); selecting a live-only make loads its models the same way.
21. **Realistic vehicle photos (no blueprint/schematic renders).** The image source
    switched from the imagin.studio CGI CDN (whose demo key returned watermarked,
    schematic-looking renders) to **real photographs from Wikipedia / Wikimedia
    Commons**: `vehicle_api.photo_url()` resolves the model page's lead image via the
    MediaWiki `pageimages` API, **rejects SVG** results (logos/line-art), and falls back
    to a shipped local image → icon. `GET /api/vehicles/image` now redirects to the
    resolved photo (24h cache). Applied everywhere a vehicle image appears — model
    cards, search results, selected-vehicle card, info panel, loading screen. imagin is
    demoted to an opt-in last resort (only when a licensed `IMAGIN_CUSTOMER` key is set;
    default is empty/off). Verified: Honda Civic, Toyota RAV4, BMW 3 Series, Tesla
    Model 3, Kia EV6, Ford Mustang, Porsche 911 all resolve to genuine JPG photos.

### Quality/cleanup pass (post-audit P0/P1)
22. **Test suite added.** `tests/` (pytest) covers store logic (unique/descriptive
    titles, rename-custom flag, delete, **persistence round-trip**, id uniqueness),
    gemini helpers (`_clean_key`, Settings-over-env key precedence, friendly errors),
    vehicle_api pure helpers (VIN validation, slug/title, imagin off-by-default), and
    routes (auth redirect, authed pages render, a11y tab present, session create/list,
    invalid-VIN, short-problem rejection). **24 tests, all green**, fully isolated from
    the real store (persistence redirected to a tmp file per test — no network calls).
    `requirements-dev.txt`, `pytest.ini`, and a GitHub Actions `ci.yml` were added.
23. **Accessibility tab re-enabled.** Its nav button was commented out in
    `settings.html` while the (now-working) panel existed below it — users couldn't
    reach the accessibility settings. Un-commented.
24. **Duplicate `#a11y-form` handler removed.** The form was bound in *both*
    `settings.js` and `app.js`, so every save fired two `POST /api/settings`. Kept the
    `settings.js` handler (which also applies changes instantly); removed the `app.js` one.
25. **Debug logging stripped.** Removed the ~10 `console.log("[PERF]…")` timing
    statements from `diagnose.js`'s `runDiagnosis()` (production noise).

### Bug-fix batch (delete, VIN gate, a11y gate, vehicle media, workspace)
26. **"Delete Diagnosis" now works.** Two causes: (a) the delete + service-request
    routes called an **undefined `_lang(request)`** → every delete 500'd with a
    `NameError` (fixed to `resolve_lang`); (b) a *failed* diagnosis left the session
    stuck in `"diagnosing"`, which the delete route then rejected with 409 — so the
    former "cannot delete while diagnosing" guard was removed (a diagnosis runs
    synchronously, so that status only ever means an abandoned run) and
    `runDiagnosis()` now resets the session to `"ready"` on failure. The service-request
    lock guard is retained. New tests cover both delete paths.
27. **VIN lookup temporarily disabled (item 2).** Gated behind a
    `VIN_LOOKUP_ENABLED = false` flag in `diagnose.js`: the section is hidden and its
    wiring skipped — no code removed; flip the flag to re-enable.
28. **Accessibility tab temporarily disabled (item 3).** The `#tab-a11y` button and
    panel in `settings.html` are commented out (Jinja `{# #}`); the underlying logic
    (`CS.applyA11y`, `settings.js` handler, `base.html` classes) is intact. Un-comment
    both blocks to re-enable.
29. **Vehicle media clears on brand switch (item 4).** `selectBrand()` and
    `resetVehicleSelection()` now reset `#dz-selected-image` (and the info-panel image)
    to the placeholder, so a previous vehicle's photo no longer lingers when switching.
30. **Workspace layout fixed after continuing to chat (item 5).** `.dz-ws-chat` (the
    `1fr` grid column) lacked `min-width:0`, so a long chat message kept the column from
    shrinking — it overflowed and pushed the 420px result column out, where
    `.dz-ws-grid { overflow:hidden }` clipped it (result "disappeared"). Added
    `min-width:0` to `.dz-ws-chat` and `overflow-wrap:anywhere` to `.dz-ws-msg-text`.

### Bug-fix batch (engine, chat streaming, latency, chat layout, persistence)
31. **Dynamic engine type per car (item 1).** CarQuery (the live trim source) has a
    **broken TLS cert** (hostname mismatch) so it always failed → every car showed the
    same static petrol list (even a Tesla). Fixed: CarQuery is now called with
    `verify=False` (keyless read-only API, no secrets), and the fallback is
    **powertrain-aware** (`_smart_fallback_engines`) so EVs (Tesla, EV6, Leaf, e-tron…)
    show Electric options and hybrids (Prius) show Hybrid first, instead of petrol.
32. **Chat streaming no longer stalls after a diagnosis (item 2).** `/api/diagnose/complete`
    called the **blocking** `gemini.diagnose()` directly in the async handler, freezing
    the single event loop for the whole 10-30s diagnosis — so any chat SSE stream
    started during/after it hung. Now wrapped in `asyncio.to_thread(...)`.
33. **Gemini latency reduced (item 3).** (a) The above off-loop fix restores concurrency.
    (b) `_run_generation` now sends a **no-thinking** generation config
    (`ThinkingConfig(thinking_budget=0)`) for the structured diagnosis — flash models
    otherwise spend seconds "thinking" that a strict-schema JSON doesn't need — with a
    per-candidate retry *without* the config so a model that rejects it still works.
34. **Chat layout no longer breaks when continuing from a diagnosis (item 5).** On
    screens ≥1440px, `.gpt-main` re-applied `margin-left:260px` on top of the
    `.layout-main` sidebar offset — a **double offset** that left a ~260px black gap.
    Removed it. Also, opening `/chat` with an existing conversation now hides the
    marketing visual panel + welcome so the chat is full-width and the diagnosis result
    (first message) stays cleanly visible.
35. **Per-user history verified across logout/login (item 6).** Diagnoses/sessions are
    keyed by the user's **email** in the persisted store (`data/store.json`); `logout()`
    only clears the session cookie and never touches the store, and login never re-seeds
    an existing user — so history survives logout→login→restart. Locked in with a test
    (`test_history_persists_per_user_across_logout_login`).
36. **Diagnosis screen usability (item 4, targeted).** Wired the previously **dead**
    "Need help?" button on the vehicle step to real guidance (toast). *(A broader visual
    redesign was left out pending design direction — flagged for follow-up.)*

### Feature batch (pagination, VIN gate, Google avatar, year-aware photos, chat gap)
37. **Diagnosis history paginated (item 1).** `GET /my-diagnoses` now takes `page` +
    `q`, returns **9 per page** (limit/offset) scoped to the user, and passes
    `page/total_pages/total` to the template. `my_diagnoses.html` got Prev / "Page X of
    Y · N total" / Next controls and a **server-side search** (debounced auto-submit,
    so results span *all* pages, not just the visible one). Delete reloads when
    paginated so counts stay correct.
38. **VIN lookup fully gated (item 2).** In addition to the `diagnose.js` flag, the
    backend route is commented out with `# TODO: re-enable VIN lookup`; the decoder
    (`vehicle_api.decode_vin`) and validation stay intact. Route now 404s (tested).
39. **Google avatar as profile image (item 3).** OAuth already captured `picture`;
    `render()` now exposes `user_picture`/`user_name` and the **sidebar + navbar**
    render the real Google avatar (`referrerpolicy=no-referrer`), falling back to
    initials on error.
40. **Year-aware vehicle media (item 4).** `photo_url(make, model, year)` tries a
    year-qualified title first, then make+model — so different years can resolve to
    different images, with graceful fallback. Year is threaded through every image
    request that has it.
41. **Real per-car photo in the history list (item 5).** `my_diagnoses.html` cards now
    show the **actual car photo** (`/api/vehicles/image?make=&model=&year=`) instead of
    a generic brand logo, with a photo → brand-logo → icon fallback (`mdImgFallback`).
42. **Chat black-gap layout fixed (item 6).** Real cause: the base `.gpt-main` reserves
    `margin-left:260px` for the chat's *own* sidebar (`.gpt-side`), but the `/chat`
    PAGE uses `.gpt-wrap--no-side` (no `.gpt-side`) — with `.layout-main` already
    offsetting for the app sidebar, that 260px became a black gap, and **no rule reset
    it**. Added `.gpt-wrap--no-side .gpt-main { margin-left: 0 !important }` (higher
    specificity than the `!important` base/media rules). Combined with the earlier
    hide-visual-panel-on-load fix, the continued chat now renders full-width with the
    result visible.

### Diagnosis result panel persists in the continued chat
43. **Result panel shown alongside the chat (continue-chat from a diagnosis).** When a
    user continues chatting from a completed diagnosis (`mdChat` → `/chat?chat_id=…`),
    the diagnosis result now stays visible on the **right side**, using the *same*
    layout as the diagnosis flow's final step (the workspace `.dz-ws-result-*` panel).
    Implementation:
    - `Store.diag_session_by_chat()` — reverse lookup chat→session→diagnosis.
    - New reusable partial `shared/templates/partials/diagnosis_result_panel.html`
      renders the result (badge, vehicle, severity gauge, diagnosis, causes, actions,
      parts, cost/time, tips) with the workspace classes.
    - `chat_page` passes the linked diagnosis; `chat.html` renders the partial in the
      right visual panel (replacing the marketing content), loads `diagnose.css`, widens
      the column (`gpt-chat-layout--diag`) and marks it `data-has-diagnosis`.
    - `app.js` `hideVisualPanel()` + the on-load hook now **keep** the panel when
      `data-has-diagnosis` is set, so it survives sending messages. Plain chats are
      unchanged (marketing panel still collapses). Covered by two tests.

### Vehicle image mapping fix (top priority) + UI cleanups
44. **Root cause of "all Honda models show the Civic image".** The shipped local
    `image/vehicles/<brand>/<model>.webp` files are **broken duplicates** — all 6 Honda
    files are byte-identical, Toyota Camry == Audi A4, only **78 unique images across
    215 files**. So when the dynamic (Wikipedia) source was unavailable, the fallback
    to these identical files showed one image for every model.
45. **Fix — per-model authoritative resolution, no cross-model fallback.**
    `vehicle_api.photo_url()` resolves **Brand + exact Model** via Wikipedia
    `pageimages` (redirects normalise CR-V/CRV/Cr-v) with a full-text **search
    fallback** for odd variants; the unreliable local duplicates are **no longer used
    as a fallback** (they were the bug) — it falls back only to a licensed CGI render
    if configured, else "" → the UI shows a neutral icon, **never another model's
    photo**. Client-side, `getModelImage()` now returns `null` (single-point
    neutralisation of the duplicate files), so the Selected Vehicle card, model cards
    and "Why select your vehicle?" preview all use the per-model API image and update
    immediately on model switch. Verified: Honda Civic/Accord/CR-V/HR-V/City/Fit →
    **6 distinct correct photos**; CRV resolves to CR-V; Toyota/BMW/Ford samples correct.
46. **Favicon = sign-in logo (item 12).** `base.html` favicon now points to
    `/static/images/logo-icon.svg` (same steel logo used at sign-in / `base_auth.html`).
47. **VIN text removed from the UI (item 13).** The "or find your car by VIN" divider
    and the VIN explanation are commented out in `diagnose.html` (kept as future work).
48. **Circular avatar (item 14).** Added a rule forcing the account profile picture to
    a perfect circle (`aspect-ratio:1/1; overflow:hidden; border-radius:50%`).
49. **Centered empty state (item 15).** `.md-empty` in `my_diagnoses.html` now
    flex-centers (vertical + horizontal) so "No diagnoses yet" is centered.

### Voice chat + structured-result + branded background (item 1 & 16)
50. **Voice chat (record → send audio → play back).** The chat mic now records real
    audio via **MediaRecorder** (not just Web Speech): on stop it attaches the clip as a
    base64 **`audio_url`** in the chat payload. `chat_ai/routes.py` decodes it and
    `gemini.chat_stream`/`stream_sse` send the audio to Gemini as a `Part` (transcribe +
    answer); OpenAI provider is guarded (audio is Gemini-only). The user's note renders
    as a playable `<audio>` bubble, and every AI reply gets a **"Listen" (TTS) button**
    (SpeechSynthesis) to play the response back. Graceful fallback when the browser
    can't record. Verified end-to-end (audio reaches Gemini; empty payloads still 400).
    *(The chat page itself was restyled to the AI-Diagnosis `dz-ws-*` workspace look in a
    parallel edit — item 1 visual match.)*
51. **Consistent branded background (item 16).** Added a subtle, theme-aware accent-glow
    background at `body` level (two low-opacity radial gradients over `--page-bg`,
    `background-attachment: fixed`) shared across all app pages; `.dz-wrap` and
    `.dz-workspace` are now `transparent` so the treatment shows on AI Diagnosis /
    Analyzing / Workspace too. About & Login already carry the logo icon; added a small
    **automation icon** (`bi-robot`) to the sidebar brand tagline.

### AI Diagnosis ↔ My Diagnoses layout unification
52. **Same header, container & card on both pages (items 1 & 3).** `my_diagnoses.html`
    now loads `diagnose.css` and reuses the **exact** AI-Diagnosis structure —
    `.dz-wizard-header` (icon + title + "Smart vehicle problem analysis" + status pill,
    no stepper), `.dz-main-grid` (single column) and `.dz-card` — instead of its own
    `.md-wrap`/`.md-header`/`.app-card`. So the two pages share identical width,
    padding, radius, shadows and header treatment. The wizard stepper on AI Diagnosis
    is untouched (item 2).
53. **Header ↔ content edge alignment (item 4).** The wizard header bar's content was
    ~32px wider than the cards below it (header inner had no horizontal padding while
    the grid had 32px). Moved the 32px inset onto `.dz-wizard-header-inner` (bar bg
    stays full-width) and drove both the header inner and `.dz-main-grid` from one
    shared `--dz-gutter` variable (32 / 20 / 16px by breakpoint) so their left/right
    edges align exactly everywhere — and this alignment now applies to My Diagnoses too
    (same structure).
54. **Google avatar always refreshed (item 5).** `Store.login` now updates the profile
    `picture` on every login (was: only when absent), so the top-right avatar shows the
    real Google photo and back-fills accounts created before avatars were captured.
    *(Requires one Google re-login to populate an existing session that had none.)*

### Chat UI fixes (duplicate label, input icons, audio playback)
55. **Three chat fixes.** (1) **Duplicate "AI Mechanic"** — `chat.html` rendered the
    label in both the workspace header (`dz-ws-title`) and the chat sub-header
    (`dz-ws-chat-title`); removed the redundant `.dz-ws-chat-header` (the workspace
    header already shows it + status). (2) **Misaligned mic/clear icons** in the
    diagnosis "What's wrong…" textarea — it inherited `.dz-textarea`'s `resize:vertical`
    (a drag handle overlapping the icons) and `margin-bottom:20px` (which pushed the
    absolutely-positioned `.dz-problem-actions` off the textarea's true bottom); set
    `resize:none; margin-bottom:0` so the icons anchor bottom-right. (3) **Audio
    playback post-diagnosis** — the server-rendered assistant messages (a chat opened
    from a diagnosis) had copy/download/regen but **no "Listen" (TTS) button** (that
    lived only in the JS `actionsRow`), so the diagnosis reply couldn't be played back;
    added it to the template, and the TTS now strips markdown symbols for clean speech.

### Polish: profile avatar + chat header
56. **Two CSS polish fixes.** (1) **Top-bar profile avatar** — was a 26px circle
    floating inside a 38px rounded-*square* button (unpolished). New `.topbar-account`
    makes the button a 40px **circular** frame the avatar fills (`object-fit:cover`,
    `aspect-ratio:1/1`, accent ring that brightens on hover); the initials/icon
    fallback gets a matching circular accent chip. (2) **Chat "AI Mechanic" top bar**
    — bumped the title 0.88→1.05rem (brighter, tighter tracking) and subtitle
    0.72→0.76rem, enlarged the header icon to a 42px gradient chip, added header gap +
    padding and a token-based background; and fixed the header being **clipped** on the
    chat page (the shared `.dz-workspace` `-22px` top margin, meant for the diagnose
    page, is reset to 0 inside `.gpt-wrap`).

### Chat audio ReferenceError + manufacture-year support
57. **AI Chat audio fixed (real root cause).** When the mic was switched to
    MediaRecorder, the `_voiceSecure` **definition** was removed but the new code still
    referenced it — a runtime `ReferenceError` (not caught by `node --check`) that
    aborted `initChat()` at that line, breaking the mic *and* everything wired after it.
    Restored `const _voiceSecure = …` before its use; recording/playback + the "Listen"
    TTS now work again.
58. **Manufacture year is respected (item 1).** Root cause: the wizard had **no year
    field**, so `state.vehicle.year` was always empty and every lookup defaulted to the
    latest model. Added a **Model year** selector to the vehicle step (populated from
    `config.VEHICLE_YEARS`, all supported years), wired to `state.vehicle.year`,
    persisted/restored with the session, and reset on vehicle change. The year now flows
    into: the **diagnosis** (`gemini.diagnose` builds the vehicle label as
    `"{year} {make} {model}"`, so a 2001 Civic gets 2001-specific analysis) and the
    **image** request (`/api/vehicles/image?make=&model=&year=` → `photo_url(…, year)`,
    which tries a year-qualified title and passes `modelYear` to the CGI fallback).
    *Note:* free real-photo sources (Wikipedia) key on the model page, so a truly
    year-accurate **photo** is best-effort (a licensed `IMAGIN_CUSTOMER` key renders the
    exact year); the **data/diagnosis** is now fully year-specific.

### Responsiveness pass (no horizontal overflow)
59. **Fixed the real mobile overflow + hardened responsiveness app-wide.** The visible
    "cards cut off on the right" was caused by CSS grids using `minmax(NNNpx, 1fr)`
    (e.g. `.md-grid`'s `minmax(300px,1fr)`): on a ~360px screen the inner container is
    smaller than the fixed min, so the track overflowed (and `html{overflow-x:hidden}`
    merely clipped it). Guarded **all 5** such tracks with `minmax(min(NNNpx,100%),1fr)`
    (my_diagnoses grid, brands grid, model-parts grid, engine grid, an app.css grid) so
    a track never exceeds its container. Also: `.md-card-actions` now `flex-wrap`s;
    added a global safety net (`img/svg/video{max-width:100%}`, `pre/table{overflow-x:
    auto}`, long-word wrapping on titles, tighter `.page` padding ≤480px). The wizard
    containers (`.dz-wrap`, `.dz-wizard-header(-inner)`, `.dz-main-grid`) were already
    fluid (max-width + shared `--dz-gutter` 32/20/16px + `1fr`, collapsing to one column
    ≤1024px); the chat `.dz-ws-grid` stacks ≤900px; `--navbar-height` scales 62→54px
    ≤992px. Verified all pages render at each breakpoint with no unguarded fixed-min
    tracks remaining.

### Login logo + workspace chat audio
60. **Login logo fixed.** `.auth-logo` is an accent-gradient chip; the masked
    `.cs-logo-icon` inside was filled with `var(--accent)` — the **same colour as the
    chip** — so the car icon was invisible and it looked like a blank orange square.
    Forced the icon white inside the chip (`.auth-logo/.splash-logo .cs-logo-icon
    { background-color:#fff }`).
61. **Workspace chat audio fixed (final diagnosis stage).** The diagnosis **workspace**
    chat (`wsBindEvents` in `diagnose.js`) never wired its mic (`#dz-ws-mic`) — only
    the standalone `/chat` page had recording — so audio "stopped working" at the final
    stage and only returned after exiting to the list and re-entering (which loads the
    `/chat` controller). Ported the MediaRecorder flow into the workspace: mic records →
    `wsSendVoiceNote()` → `wsAddBubble` shows a playable `<audio>` note → `wsStream`
    sends `audio_url` to Gemini (transcribe + answer). Now continuous, no re-entry.
62. **My-Diagnoses empty state centring fixed (post-delete).** Deleting the last
    diagnosis injects `.md-empty` **into** `#md-grid` (a CSS grid), so it landed in the
    first column track (left-aligned); a refresh renders it as a sibling **outside** the
    grid (full-width, centred). Added `grid-column: 1 / -1` to `.md-empty` so it spans
    every column and centres in both paths — no refresh needed.
63. **Splash `/splash` waves + hero→features seam fixed.** (a) The ambient waves had
    `#ff7a1a` baked into the inline SVG (a `<defs>` gradient + direct fills), rendering a
    muddy brown band. Changed all three wave paths to `fill="currentColor"` (removed the
    orange gradient def) and set `.splash-wave { color: var(--accent) }`, so the waves now
    follow the theme accent dynamically. (b) There was a hard black seam where the hero
    photo cut off. Faded `.hp-hero-overlay`'s bottom to `rgba(--c-deep, 0.96)` and gave
    `.hp-section--alt` a matching opaque dark gradient (`--c-deep 0.96 → --c-panel 0.97`,
    was transparent rgba white 0.02) so the hero dissolves seamlessly into the section.

> **Outstanding from the audit (not yet done):** split the 8.6k-line `app.css`
> monolith + de-dupe the doubled `.page`/`.sidebar`/`.layout-main` rules; finish or
> remove the half-applied i18n (`diagnose.html` uses `t()` 0×, `resolve_lang` still
> hard-returns `"en"`); migrate Settings/Maintenance/Repair-Guide cards to `.app-card`;
> route hygiene (`require()` in `/about`,`/contact`; drop `/500`); pin dependencies;
> purge committed `env/`,`_env/`,`env.zip`.

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
- **Premium automotive dark aesthetic** — a navy/graphite palette with an
  **electric-blue accent by default** (`--accent: #3b82f6`, plus the
  `--accent-rgb: 59,130,246` channel used by `rgba(var(--accent-rgb), a)`) and
  semantic colors (`--success`, `--warning`, `--danger`). The accent is fully
  user-configurable in Settings and propagates to **every** page via the token
  system (see §0, item 1). Older revisions shipped a cyan (`#00e5ff`) then a
  safety-orange (`#ff7a1a`) accent — both are superseded by the blue default.
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

1. **Data now persists across restarts.** As of 2026-09-07 the `Store` snapshots
   per-user data (incl. diagnosis sessions/progress) to `data/store.json` and
   reloads it on startup (§0, item 10), so "continue diagnosis" survives a
   restart. It is still a single-file JSON snapshot, not a real database — fine
   for the project scope; delete `data/store.json` to reset. Login still seeds a
   demo Audi A4 + reminders + 2 AI reports on a brand-new user.
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
