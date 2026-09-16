/* ============================================================
   AI Diagnosis Wizard — Car Service AI
   ============================================================ */
(function () {
  "use strict";

  const $ = (sel, root) => document.querySelector(sel, root);
  const $$ = (sel, root) => Array.from(document.querySelectorAll(sel, root));

  /* ---- Feature flags — temporarily disabled features (flip to re-enable) ---- */
  const VIN_LOOKUP_ENABLED = false;   /* TODO: re-enable VIN lookup (future work) */

  /* ---- State ---- */
  const state = {
    step: "vehicle",
    sessionId: null,  /* diagnosis session id for persistence */
    vehicle: { brand: "", model: "", engine: "", year: "" },
    problem: "",
    notice: "",
    category: "",
    when: "",
    where: "",
    answers: {},
    image: null,
    video: null,
    videoFile: null,
    questionIndex: 0,
    questions: [],
    /* Dialect state */
    dialect: "neutral",         /* active dialect profile key */
    dialectConfidence: 0.0,     /* detection confidence 0.0–1.0 */
    dialectDetected: "",        /* raw detected dialect name */
    userTerms: {},              /* canonical_id → user's local term */
    dialectResult: null,        /* full dialect detection result from server */
  };

  /* ---- Step mapping: wizard step name -> step number (1-6) ---- */
  const STEP_MAP = {
    vehicle: 1,
    describe: 2,
    questions: 3,
    image: 4,
    review: 5,
    ready: 6,
  };

  /* ---- Browser history tracking for wizard Back/Forward ---- */
  /* The wizard now opens straight on "vehicle" — the old "welcome" splash step
     (with its duplicate "Start Diagnosis" button) was removed. */
  const WIZARD_STEPS = ["vehicle", "describe", "questions", "image", "review", "ready"];
  let _wizIdx = -1;        /* current position in WIZARD_STEPS; -1 = not in wizard */
  let _navGuard = false;   /* true while we are programmatic pushState/popstate handling */

  /* ============================================================
     DIALECT-AWARE UI SYSTEM
     ============================================================
     Provides tr() for getting localized strings, applyDialectUI()
     for updating all static DOM text, and dialect-aware question/answer
     handling for dynamic content.
     ============================================================ */

  /** Get the current dialect profile. Falls back to neutral. */
  function dialectProfile() {
    return (window.DIALECT_PROFILES && window.DIALECT_PROFILES[state.dialect])
      || (window.DIALECT_PROFILES && window.DIALECT_PROFILES.neutral)
      || {};
  }

  /** Get a translated UI string by key. Falls back to key itself if missing. */
  function tr(key) {
    const p = dialectProfile();
    return p[key] || key;
  }

  /** Get a translated string with placeholder replacement. */
  function trFmt(key, vars) {
    let s = tr(key);
    if (vars) {
      Object.keys(vars).forEach((k) => {
        s = s.replace(new RegExp("\\{" + k + "\\}", "g"), vars[k]);
      });
    }
    return s;
  }

  /** Resolve a dialect name from the server result to a profile key. */
  function resolveDialectKey(dialectName) {
    if (!dialectName) return "neutral";
    if (window.DIALECT_MAP && window.DIALECT_MAP[dialectName]) return window.DIALECT_MAP[dialectName];
    const lower = dialectName.toLowerCase();
    if (window.DIALECT_MAP) {
      for (const [key, val] of Object.entries(window.DIALECT_MAP)) {
        if (key.toLowerCase() === lower) return val;
      }
    }
    return "neutral";
  }

  /** Apply the detected dialect and update the entire UI. */
  function applyDialect(dialectResult) {
    if (!dialectResult || dialectResult.language !== "ar") {
      state.dialect = "neutral";
      state.dialectConfidence = 0;
      state.dialectDetected = "";
      state.dialectResult = null;
      state.userTerms = {};
      return;
    }
    const conf = dialectResult.dialect_confidence || 0;
    state.dialectDetected = dialectResult.dialect || "";
    state.dialectConfidence = conf;
    state.dialectResult = dialectResult;

    /* Only apply a specific dialect if confidence > 0.25, otherwise stay neutral */
    if (conf > 0.25 && dialectResult.dialect) {
      state.dialect = resolveDialectKey(dialectResult.dialect);
    } else {
      state.dialect = "neutral";
    }

    /* Remember user's automotive vocabulary */
    if (dialectResult.canonical_concepts) {
      dialectResult.canonical_concepts.forEach((c) => {
        if (c.id && c.local) state.userTerms[c.id] = c.local;
      });
    }

    /* Apply UI text */
    applyDialectUI();
  }

  /** Apply dialect UI to all static elements in the DOM. */
  function applyDialectUI() {
    const p = dialectProfile();
    if (!p || !p.wizardTitle) return;

    /* Wizard header */
    _setText("#dz-wizard-title", p.wizardTitle);
    _setText("#dz-wizard-subtitle", p.wizardSubtitle);
    _setText("#dz-status-text", p.statusOnline);

    /* Stepper labels */
    _setText("[data-step-label='vehicle']", p.stepVehicle);
    _setText("[data-step-label='describe']", p.stepProblem);
    _setText("[data-step-label='questions']", p.stepQuestions);
    _setText("[data-step-label='image']", p.stepMedia);
    _setText("[data-step-label='review']", p.stepReview);
    _setText("[data-step-label='ready']", p.stepDiagnose);

    /* Step 1 — Vehicle */
    _setText("#dz-vehicle-title", p.vehicleTitle);
    _setText("#dz-vehicle-subtitle", p.vehicleSubtitle);
    _setAttr("#dz-vehicle-search", "placeholder", p.searchPlaceholder);
    _setText("#dz-popular-label", p.popularBrands);
    _setText("#dz-view-all-label", p.viewAllBrands);
    _setText("#dz-vehicle-badge-label", p.selectedVehicle);
    _setText("#dz-change-vehicle", p.changeVehicle);
    _setText("#dz-model-title", p.selectModel);
    _setText("#dz-engine-title", p.selectEngine);
    _setAttr("#dz-engine-input", "placeholder", p.enginePlaceholder);
    _setText("#dz-year-label", p.modelYear);
    _setAttr("#dz-year-select", "data-default", p.yearDefault);
    _setText("#dz-vehicle-validation", p.vehicleValidation);

    /* Step 2 — Problem */
    _setText("#dz-problem-title", p.problemTitle);
    _setText("#dz-problem-subtitle", p.problemSubtitle);
    _setAttr("#dz-problem", "placeholder", p.problemPlaceholder);
    _setText("#dz-problem-count-label", p.characters);
    _setText("#dz-problem-validation", p.problemValidation);
    _setText("#dz-notice-title", p.noticeTitle);
    _setText("#dz-notice-subtitle", p.noticeSubtitle);
    _setAttr("#dz-notice", "placeholder", p.noticePlaceholder);
    _setText("#dz-notice-label", p.optionalDetails);
    _setText("#dz-when-title", p.whenTitle);
    _setText("#dz-where-title", p.whereTitle);

    /* Category buttons */
    _setText("[data-cat='engine']", p.catEngine);
    _setText("[data-cat='brakes']", p.catBrakes);
    _setText("[data-cat='battery']", p.catBattery);
    _setText("[data-cat='ac']", p.catAc);
    _setText("[data-cat='electrical']", p.catElectrical);
    _setText("[data-cat='transmission']", p.catTransmission);
    _setText("[data-cat='suspension']", p.catSuspension);
    _setText("[data-cat='other']", p.catOther);

    /* When chips */
    _setText("[data-when='always']", p.whenAlways);
    _setText("[data-when='sometimes']", p.whenSometimes);
    _setText("[data-when='starting']", p.whenStarting);
    _setText("[data-when='driving']", p.whenDriving);
    _setText("[data-when='braking']", p.whenBraking);
    _setText("[data-when='turning']", p.whenTurning);

    /* Where chips */
    _setText("[data-where='front']", p.whereFront);
    _setText("[data-where='rear']", p.whereRear);
    _setText("[data-where='left']", p.whereLeft);
    _setText("[data-where='right']", p.whereRight);
    _setText("[data-where='engine']", p.whereEngine);
    _setText("[data-where='cabin']", p.whereCabin);

    /* Step 4 — Media */
    _setText("#dz-photo-label", p.photoLabel);
    _setText("#dz-photo-text", p.photoText);
    _setText("#dz-photo-formats", p.photoFormats);
    _setText("#dz-video-label", p.videoLabel);
    _setText("#dz-video-text", p.videoText);
    _setText("#dz-video-formats", p.videoFormats);

    /* Step 5 — Review */
    _setText("#dz-review-title", p.reviewTitle);
    _setText("#dz-review-subtitle", p.reviewSubtitle);

    /* Step 6 — Ready */
    _setText("#dz-ready-title", p.readyTitle);
    _setText("#dz-ready-subtitle", p.readySubtitle);
    _setText("#dz-diagnose", p.startDiagnosis);

    /* Loading */
    _setText("#dz-loading-title", p.loadingTitle);
    _setText("#dz-loading-subtitle", p.loadingSubtitle);

    /* Result modal */
    _setText("#dz-modal-title", p.modalTitle);
    _setText("#dz-modal-subtitle", p.modalSubtitle);
    _setText("#dz-new-diagnosis", p.newDiagnosis);

    /* Benefits */
    _setText("#dz-benefit-secure-title", p.benefitSecure);
    _setText("#dz-benefit-secure-desc", p.benefitSecureDesc);
    _setText("#dz-benefit-ai-title", p.benefitAi);
    _setText("#dz-benefit-ai-desc", p.benefitAiDesc);
    _setText("#dz-benefit-fast-title", p.benefitFast);
    _setText("#dz-benefit-fast-desc", p.benefitFastDesc);
    _setText("#dz-benefit-trusted-title", p.benefitTrusted);
    _setText("#dz-benefit-trusted-desc", p.benefitTrustedDesc);

    /* Info panel */
    _setText("#dz-info-title", p.infoTitle);
    _setText("#dz-info-text", p.infoText);
    _setText("#dz-info-specs", p.infoSpecs);
    _setText("#dz-info-issues", p.infoIssues);
    _setText("#dz-info-mfr", p.infoMfrData);
    _setText("#dz-info-bulletins", p.infoBulletins);
    _setText("#dz-info-tip", p.infoTip);

    /* Chat modal */
    _setText("#dz-chat-confirm-title", p.chatConfirmTitle);
    _setText("#dz-chat-confirm-desc", p.chatConfirmDesc);
    _setText("#dz-chat-cancel", p.chatConfirmCancel);
    _setText("#dz-chat-ok", p.chatConfirmOk);
  }

  /** Helper: set textContent if element exists. */
  function _setText(sel, text) {
    if (text == null) return;
    const el = $(sel);
    if (el) el.textContent = text;
  }

  /** Helper: set attribute if element exists. */
  function _setAttr(sel, attr, val) {
    if (val == null) return;
    const el = $(sel);
    if (el) el.setAttribute(attr, val);
  }

  /** Get the loading message for the current dialect (rotates). */
  let _loadingMsgIdx = 0;
  function nextLoadingMessage() {
    const msgs = tr("loadingMessages");
    if (Array.isArray(msgs) && msgs.length > 0) {
      _loadingMsgIdx = (_loadingMsgIdx + 1) % msgs.length;
      return msgs[_loadingMsgIdx];
    }
    return tr("loadingTitle");
  }
  function resetLoadingMessages() { _loadingMsgIdx = 0; }

  /* ============================================================
     RESULT MODAL — open / close / scroll lock
     ============================================================ */
  let _modalResult = null;   /* stores latest diagnosis result for button handlers */
  let _lastFocused = null;   /* element to restore focus on close */

  /* ---- Workspace chat state ---- */
  let _wsChatId = "";
  let _wsStreaming = false;
  let _wsController = null;
  let _wsLastAiId = null;

  function openModal() {
    const overlay = $("#dz-modal-overlay");
    if (!overlay) return;
    _lastFocused = document.activeElement;
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    /* focus the modal container for keyboard access */
    const container = $("#dz-modal-container");
    if (container) container.focus();
    /* Push history so Back closes modal before leaving the page */
    if (!_navGuard) {
      _navGuard = true;
      window.history.pushState({ modal: true }, "", "");
      _navGuard = false;
    }
  }

  function closeModal() {
    const overlay = $("#dz-modal-overlay");
    if (!overlay) return;
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    /* restore focus */
    if (_lastFocused && _lastFocused.focus) _lastFocused.focus();
    /* After modal close, restore the wizard step hash in the URL */
    if (state.step && state.step !== "welcome") {
      _navGuard = true;
      window.history.replaceState({ wiz: true, idx: WIZARD_STEPS.indexOf(state.step) }, "", "#step-" + state.step);
      _navGuard = false;
    } else {
      _navGuard = true;
      window.history.replaceState({}, "", "/diagnose");
      _navGuard = false;
    }
  }

  function initModal() {
    const overlay = $("#dz-modal-overlay");
    const closeBtn = $("#dz-modal-close");
    const backdrop = $("#dz-modal-backdrop");
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (backdrop) backdrop.addEventListener("click", closeModal);
    /* ESC key */
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay && overlay.classList.contains("open")) {
        e.preventDefault();
        closeModal();
      }
    });
  }

  function modalLoading() {
    const body = $("#dz-modal-body");
    const footer = $("#dz-modal-footer");
    if (!body) return;

    /* Vehicle data */
    const brand = state.vehicle.brand || "";
    const model = state.vehicle.model || "";
    const vehicleLabel = [brand, model].filter(Boolean).join(" ") || "your vehicle";
    const problem = state.problem || "";
    const hasImage = !!state.image;
    const hasQuestion = !!(state.answers && state.answers.length);

    /* Build info rows */
    let infoRows = "";
    if (brand || model) {
      infoRows += `<div class="dz-loading-info-row"><span class="dz-loading-info-label">Vehicle</span><span class="dz-loading-info-value">${esc(vehicleLabel)}</span></div>`;
    }
    if (problem) {
      infoRows += `<div class="dz-loading-info-row"><span class="dz-loading-info-label">Problem</span><span class="dz-loading-info-value">${esc(problem.slice(0, 60))}${problem.length > 60 ? "..." : ""}</span></div>`;
    }
    if (hasImage) {
      infoRows += `<div class="dz-loading-info-row"><span class="dz-loading-info-label">Media</span><span class="dz-loading-info-value">1 image</span></div>`;
    }

    /* Vehicle image */
    let vehicleImgHtml = "";
    if (brand && model) {
      const local = getModelImage(brand, model);
      const primary = getVehicleImageUrl(brand, model, state.vehicle.year) || local;
      if (primary) {
        vehicleImgHtml = `<img src="${esc(primary)}" data-local="${esc(local || "")}" alt="${esc(brand)} ${esc(model)}" class="dz-loading-vehicle-img" onerror="dzImgFallback(this)">`;
      }
    }

    body.innerHTML = `
      <div class="dz-loading-screen">
        <!-- HUD Corners -->
        <div class="dz-loading-hud-corners" aria-hidden="true">
          <span class="dz-loading-hud-corner dz-loading-hud-tl"></span>
          <span class="dz-loading-hud-corner dz-loading-hud-tr"></span>
          <span class="dz-loading-hud-corner dz-loading-hud-bl"></span>
          <span class="dz-loading-hud-corner dz-loading-hud-br"></span>
        </div>

        <!-- Vehicle Visual -->
        <div class="dz-loading-vehicle">
          <div class="dz-loading-vehicle-frame">
            ${vehicleImgHtml || `<div class="dz-loading-vehicle-icon"><i class="bi bi-car-front-fill"></i></div>`}
            <div class="dz-loading-scan-line"></div>
            <div class="dz-loading-scan-dots" aria-hidden="true">
              <span class="dz-loading-dot" style="top:20%;left:15%"></span>
              <span class="dz-loading-dot" style="top:40%;right:20%"></span>
              <span class="dz-loading-dot" style="bottom:30%;left:25%"></span>
              <span class="dz-loading-dot" style="bottom:20%;right:15%"></span>
            </div>
          </div>
          <div class="dz-loading-vehicle-label">
            <span class="dz-loading-vehicle-brand">${esc(brand || "AI")}</span>
            <span class="dz-loading-vehicle-model">${esc(model || "Mechanic")}</span>
          </div>
        </div>

        <!-- Main Text -->
        <div class="dz-loading-text">
          <div class="dz-loading-title">AI is analyzing your vehicle</div>
          <div class="dz-loading-sub">Our AI Mechanic is checking the information you provided.</div>
        </div>

        <!-- Live Status -->
        <div class="dz-loading-status">
          <span class="dz-loading-status-dot"></span>
          <span class="dz-loading-status-text" id="dz-loading-status-text">Reading vehicle information...</span>
        </div>

        <!-- Info Rows -->
        ${infoRows ? `<div class="dz-loading-info">${infoRows}</div>` : ""}

        <!-- Progress Bar -->
        <div class="dz-loading-progress">
          <div class="dz-loading-progress-track">
            <div class="dz-loading-progress-fill"></div>
          </div>
        </div>

        <!-- System Status -->
        <div class="dz-loading-system">
          <span class="dz-loading-system-dot"></span>
          <span class="dz-loading-system-text">GEMINI ANALYSIS ACTIVE</span>
        </div>
      </div>`;

    if (footer) footer.innerHTML = "";
    openModal();

    /* Start live status messages (visual only — no delay on result) */
    _startLoadingStatus();
  }

  /* ---- Live status messages (visual only, does NOT control request) ---- */
  let _loadingStatusTimer = null;

  function _startLoadingStatus() {
    _stopLoadingStatus();
    let idx = 0;
    const el = document.getElementById("dz-loading-status-text");
    if (!el) return;
    /* Use dialect-aware messages */
    const msgs = tr("loadingMessages");
    const loadingMessages = Array.isArray(msgs) && msgs.length > 0
      ? msgs
      : ["Reading vehicle information...", "Reviewing reported symptoms...", "Analyzing possible causes...", "Checking repair recommendations...", "Preparing your diagnosis..."];
    el.textContent = loadingMessages[0];
    _loadingStatusTimer = setInterval(() => {
      idx = (idx + 1) % loadingMessages.length;
      el.style.opacity = "0";
      setTimeout(() => {
        el.textContent = loadingMessages[idx];
        el.style.opacity = "1";
      }, 150);
    }, 2500);
  }

  function _stopLoadingStatus() {
    if (_loadingStatusTimer) {
      clearInterval(_loadingStatusTimer);
      _loadingStatusTimer = null;
    }
  }

  /* ============================================================
     CHAT CONFIRMATION MODAL
     ============================================================ */
  let _chatModalResult = null;   /* diagnosis result passed to chat */
  let _chatModalBusy = false;    /* prevent double-click */

  function openChatModal(result) {
    _chatModalResult = result;
    _chatModalBusy = false;
    const overlay = $("#dz-chat-modal-overlay");
    if (!overlay) return;
    _lastFocused = document.activeElement;

    /* Populate vehicle info */
    const brand = state.vehicle.brand || "";
    const model = state.vehicle.model || "";
    const brandEl = $("#dz-chat-modal-vehicle-brand");
    const modelEl = $("#dz-chat-modal-vehicle-model");
    const imgEl = $("#dz-chat-modal-vehicle-img");
    if (brandEl) brandEl.textContent = brand || "—";
    if (modelEl) modelEl.textContent = model || "—";

    /* Vehicle image */
    if (imgEl) {
      const local = getModelImage(brand, model);
      const primary = getVehicleImageUrl(brand, model, state.vehicle.year) || local;
      if (primary) {
        const img = document.createElement("img");
        img.src = primary;
        if (local) img.setAttribute("data-local", local);
        img.alt = brand + " " + model;
        img.onerror = function() {
          const lc = img.getAttribute("data-local");
          if (lc && img.getAttribute("src") !== lc) {
            img.removeAttribute("data-local");
            img.src = lc;
            return;
          }
          imgEl.innerHTML = '<i class="bi bi-car-front-fill"></i>';
        };
        imgEl.innerHTML = "";
        imgEl.appendChild(img);
      } else {
        imgEl.innerHTML = '<i class="bi bi-car-front-fill"></i>';
      }
    }

    /* Hide error */
    const errEl = $("#dz-chat-modal-error");
    if (errEl) errEl.classList.add("d-none");

    /* Reset confirm button */
    const confirmBtn = $("#dz-chat-modal-confirm");
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.innerHTML = '<i class="bi bi-chat-right-text"></i> Continue to Chat <i class="bi bi-arrow-right"></i>';
    }

    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";

    /* Focus the modal */
    const container = $("#dz-chat-modal-container");
    if (container) container.focus();
  }

  function closeChatModal() {
    const overlay = $("#dz-chat-modal-overlay");
    if (!overlay) return;
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    _chatModalBusy = false;

    /* Restore focus */
    if (_lastFocused && _lastFocused.focus) _lastFocused.focus();
  }

  function initChatModal() {
    const overlay = $("#dz-chat-modal-overlay");
    const closeBtn = $("#dz-chat-modal-close");
    const backdrop = $("#dz-chat-modal-backdrop");
    const cancelBtn = $("#dz-chat-modal-cancel");
    const confirmBtn = $("#dz-chat-modal-confirm");

    if (closeBtn) closeBtn.addEventListener("click", closeChatModal);
    if (backdrop) backdrop.addEventListener("click", closeChatModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeChatModal);

    /* Confirm button — delegate to startDiagnosisChat */
    if (confirmBtn) {
      confirmBtn.addEventListener("click", async () => {
        if (_chatModalBusy) return;
        if (!_chatModalResult) return;
        _chatModalBusy = true;
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Creating conversation...';

        const errEl = $("#dz-chat-modal-error");
        if (errEl) errEl.classList.add("d-none");

        try {
          const res = await fetch("/api/chat/save-diagnosis", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              type: _chatModalResult.mode || state.mode || "text",
              problem: buildFullProblem(),
              result: _chatModalResult,
              session_id: state.sessionId || null,
              vehicle: state.vehicle || null,
            }),
          });
          const data = await res.json();
          if (data.ok && data.id) {
            closeChatModal();
            window.location.href = "/chat?chat_id=" + encodeURIComponent(data.id);
          } else {
            throw new Error(data.error || "Failed to create chat");
          }
        } catch (err) {
          _chatModalBusy = false;
          confirmBtn.disabled = false;
          confirmBtn.innerHTML = '<i class="bi bi-chat-right-text"></i> Continue to Chat <i class="bi bi-arrow-right"></i>';
          if (errEl) errEl.classList.remove("d-none");
        }
      });
    }

    /* ESC key */
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay && overlay.classList.contains("open")) {
        e.preventDefault();
        closeChatModal();
      }
    });
  }

  /* ============================================================
     SESSION PERSISTENCE — Autosave / Restore
     ============================================================ */
  let _saveTimeout = null;

  function scheduleSave() {
    if (_saveTimeout) clearTimeout(_saveTimeout);
    _saveTimeout = setTimeout(saveSession, 500);
  }

  async function saveSession() {
    if (!state.sessionId) return;
    try {
      const payload = {
        vehicle: state.vehicle,
        problem: state.problem,
        notice: state.notice,
        category: state.category,
        when: state.when,
        where: state.where,
        answers: state.answers,
        questions: state.questions,
        question_index: state.questionIndex,
        step: state.step,
        dialect_result: state.dialectResult || state._dialectResult || null,
      };
      /* Only send image if it changed (avoid sending large base64 on every save) */
      if (state._imageDirty) {
        payload.image = state.image;
        state._imageDirty = false;
      }
      /* Only send video if it changed */
      if (state._videoDirty) {
        payload.video = state.video;
        state._videoDirty = false;
      }
      await fetch(`/api/diag-sessions/${state.sessionId}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (e) { /* ignore save errors */ }
  }

  async function createSession() {
    try {
      const res = await fetch("/api/diag-sessions/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vehicle: state.vehicle,
          problem: state.problem,
        }),
      });
      const data = await res.json();
      if (data.ok && data.session) {
        state.sessionId = data.session.id;
        /* Update page title with session name */
        document.title = data.session.title + " · Car Service AI";
      }
    } catch (e) { /* ignore */ }
  }

  async function loadSession(sessionId, editMode) {
    try {
      const res = await fetch(`/api/diag-sessions/${sessionId}`);
      const data = await res.json();
      if (!data.ok || !data.session) return false;
      const s = data.session;

      /* Restore all state */
      state.sessionId = s.id;
      state.vehicle = s.vehicle || { brand: "", model: "", engine: "" };
      const _savedEngine = state.vehicle.engine || "";
      state.problem = s.problem || "";
      state.notice = s.notice || "";
      state.category = s.category || "";
      state.when = s.when || "";
      state.where = s.where || "";
      state.answers = s.answers || {};
      state.questions = s.questions || [];
      state.questionIndex = s.question_index || 0;
      state.image = s.image || null;
      state.step = s.step || "welcome";

      /* Restore dialect state */
      if (s.dialect_result) {
        state.dialectResult = s.dialect_result;
        applyDialect(s.dialect_result);
      } else if (state.problem) {
        /* Re-detect dialect from saved problem */
        const dialectResult = await detectDialect(state.problem);
        applyDialect(dialectResult);
      }

      /* A session can be autosaved on a transient, non-wizard step
         ("loading" / "workspace" / "result") if the user navigated away
         mid-diagnosis. showStep() hides the wizard for those and shows nothing,
         which is why "Continue Diagnosis" appeared blank. Clamp any unknown
         step back to a safe wizard step so the user always lands somewhere. */
      if (WIZARD_STEPS.indexOf(state.step) < 0) {
        state.step = state.problem
          ? "ready"
          : ((s.vehicle && s.vehicle.brand) ? "describe" : "vehicle");
      }

      document.title = s.title + " · Car Service AI";

      /* If diagnosis is already completed, show result — unless the user asked
         to EDIT it, in which case fall through and restore the wizard so they
         can change inputs and re-run the diagnosis (item 10). */
      if (s.status === "completed" && s.diagnosis && !editMode) {
        /* Land the wizard on a real step FIRST so there is always visible
           content behind the result (prevents a blank page if the modal fails
           to open for any reason). */
        state.step = "ready";
        try { showReady(); } catch (e) { showStep("vehicle"); }
        try {
          showResult(s.diagnosis);
        } catch (e) {
          /* Modal failed to render — keep the wizard visible rather than blank. */
          showStep("ready");
        }
        return true;
      }
      if (editMode) {
        /* Land on the review step so every field is visible and editable. */
        state.step = "review";
      }

      /* Restore vehicle selection UI */
      if (state.vehicle.brand) {
        selectBrand(state.vehicle.brand);
        if (state.vehicle.model) {
          state.vehicle.model = state.vehicle.model;
          const modelCard = document.querySelector(
            `.dz-car-model-card[data-model="${state.vehicle.model}"]`
          );
          if (modelCard) {
            document.querySelectorAll(".dz-car-model-card").forEach(c =>
              c.classList.remove("selected")
            );
            modelCard.classList.add("selected");
            const modelEl = document.getElementById("dz-car-selected-model");
            if (modelEl) modelEl.textContent = state.vehicle.model;
            updateSelectedVehicleImage(state.vehicle.brand, state.vehicle.model);
            updateInfoPanelVehicleImage(state.vehicle.brand, state.vehicle.model);
          }
          /* Restore engine cascade + previously chosen engine */
          loadEngines(state.vehicle.brand, state.vehicle.model).then(() => {
            if (_savedEngine) selectEngine(_savedEngine);
          });
          /* Restore the model-year selector. */
          const yearWrap = $("#dz-car-year");
          if (yearWrap) yearWrap.classList.remove("d-none");
          const yearSel = $("#dz-year-select");
          if (yearSel && state.vehicle.year) yearSel.value = String(state.vehicle.year);
        }
        updateVehicleBadge();
      }

      /* Restore problem step UI */
      const problemEl = document.getElementById("dz-problem");
      if (problemEl && state.problem) {
        problemEl.value = state.problem;
        problemEl.dispatchEvent(new Event("input"));
      }
      const noticeEl = document.getElementById("dz-notice");
      if (noticeEl && state.notice) {
        noticeEl.value = state.notice;
      }

      /* Restore category selection (treat a saved category as the user's choice
         so typing doesn't auto-override it). */
      if (state.category) {
        const catBtn = document.querySelector(
          `.dz-category-btn[data-category="${state.category}"]`
        );
        if (catBtn) catBtn.classList.add("selected");
        _categoryAuto = false;
      }

      /* Restore when/where chips */
      if (state.when) {
        const whenBtn = document.querySelector(
          `#dz-when-chips .dz-chip-btn[data-when="${state.when}"]`
        );
        if (whenBtn) whenBtn.classList.add("selected");
      }
      if (state.where) {
        const whereBtn = document.querySelector(
          `#dz-where-chips .dz-chip-btn[data-where="${state.where}"]`
        );
        if (whereBtn) whereBtn.classList.add("selected");
      }

      /* Restore image preview */
      if (state.image) {
        const thumb = document.getElementById("dz-img-thumb");
        const preview = document.getElementById("dz-img-preview");
        const zone = document.getElementById("dz-upload-zone");
        if (thumb) thumb.src = state.image;
        if (preview) preview.style.display = "inline-block";
        if (zone) zone.style.display = "none";
      }

      /* Restore video preview */
      if (state.video) {
        const videoThumb = document.getElementById("dz-video-thumb");
        const videoPreview = document.getElementById("dz-video-preview");
        const videoZone = document.getElementById("dz-video-zone");
        if (videoThumb) { videoThumb.src = state.video; videoThumb.load(); }
        if (videoPreview) videoPreview.style.display = "inline-block";
        if (videoZone) videoZone.style.display = "none";
      }

      /* Update continue button visibility */
      updateContinueButton();

      /* Navigate to the saved step */
      if (state.step === "questions" && state.questions.length > 0) {
        showQuestion();
      }
      showStep(state.step);

      return true;
    } catch (e) {
      /* Never leave the user on a blank page — fall back to a safe wizard step. */
      try { showStep(WIZARD_STEPS.indexOf(state.step) >= 0 ? state.step : "vehicle"); }
      catch (_) { showStep("vehicle"); }
      return false;
    }
  }

  /* ---- Car brand data (from config.py) with local logos ---- */
  const CAR_BRANDS = [
    { name: "Acura", logo: "/image/car_logos/acura.svg", models: ["ILX", "TLX", "RDX", "MDX"] },
    { name: "Alfa Romeo", logo: "/image/car_logos/alfa-romeo.svg", models: ["Giulia", "Stelvio", "Tonale"] },
    { name: "Aston Martin", logo: "/image/car_logos/aston-martin.svg", models: ["Vantage", "DB12", "DBX"] },
    { name: "Audi", logo: "/image/car_logos/audi.svg", models: ["A3", "A4", "A6", "Q3", "Q5", "Q7", "e-tron"] },
    { name: "Bentley", logo: "/image/car_logos/bentley.svg", models: ["Continental GT", "Flying Spur", "Bentayga"] },
    { name: "BMW", logo: "/image/car_logos/bmw.svg", models: ["1 Series", "3 Series", "5 Series", "X1", "X3", "X5", "i4"] },
    { name: "Buick", logo: "/image/car_logos/buick.svg", models: ["Encore", "Envision", "LaCrosse"] },
    { name: "Cadillac", logo: "/image/car_logos/cadillac.svg", models: ["CT4", "CT5", "XT4", "XT5", "Escalade"] },
    { name: "Chevrolet", logo: "/image/car_logos/chevrolet.svg", models: ["Spark", "Cruze", "Malibu", "Trailblazer", "Equinox"] },
    { name: "Chrysler", logo: "/image/car_logos/chrysler.svg", models: ["300", "Pacifica"] },
    { name: "Citroen", logo: "/image/car_logos/citroen.svg", models: ["C1", "C3", "C4", "C5", "Berlingo"] },
    { name: "Dodge", logo: "/image/car_logos/dodge.svg", models: ["Challenger", "Charger", "Durango"] },
    { name: "Ferrari", logo: "/image/car_logos/ferrari.svg", models: ["Roma", "SF90", "296", "812", "F8"] },
    { name: "Fiat", logo: "/image/car_logos/fiat.svg", models: ["500", "Panda", "Punto", "Tipo"] },
    { name: "Ford", logo: "/image/car_logos/ford.svg", models: ["Fiesta", "Focus", "Mustang", "Ranger", "Escape", "Explorer"] },
    { name: "Genesis", logo: "/image/car_logos/genesis.svg", models: ["G70", "G80", "G90", "GV70", "GV80"] },
    { name: "GMC", logo: "/image/car_logos/gmc.svg", models: ["Terrain", "Acadia", "Yukon", "Sierra"] },
    { name: "Honda", logo: "/image/car_logos/honda.svg", models: ["Civic", "Accord", "CR-V", "HR-V", "City", "Fit"] },
    { name: "Hyundai", logo: "/image/car_logos/hyundai.svg", models: ["i20", "i30", "Tucson", "Santa Fe", "Elantra", "Kona"] },
    { name: "Infiniti", logo: "/image/car_logos/infiniti.svg", models: ["Q50", "Q60", "QX50", "QX60"] },
    { name: "Jaguar", logo: "/image/car_logos/jaguar.svg", models: ["XE", "XF", "F-PACE", "E-PACE", "I-PACE"] },
    { name: "Jeep", logo: "/image/car_logos/jeep.svg", models: ["Renegade", "Compass", "Cherokee", "Wrangler", "Grand Cherokee"] },
    { name: "Kia", logo: "/image/car_logos/kia.svg", models: ["Rio", "Ceed", "Sportage", "Sorento", "Picanto", "EV6"] },
    { name: "Lamborghini", logo: "/image/car_logos/lamborghini.svg", models: ["Huracan", "Urus", "Revuelto"] },
    { name: "Land Rover", logo: "/image/car_logos/land-rover.svg", models: ["Range Rover", "Discovery", "Defender", "Evoque"] },
    { name: "Lexus", logo: "/image/car_logos/lexus.svg", models: ["UX", "NX", "RX", "ES", "LS"] },
    { name: "Lincoln", logo: "/image/car_logos/lincoln.svg", models: ["Corsair", "Aviator", "Navigator"] },
    { name: "Maserati", logo: "/image/car_logos/maserati.svg", models: ["Ghibli", "Levante", "Grecale", "GranTurismo"] },
    { name: "Mazda", logo: "/image/car_logos/mazda.svg", models: ["2", "3", "6", "CX-3", "CX-5", "MX-5"] },
    { name: "McLaren", logo: "/image/car_logos/mclaren.svg", models: ["720S", "750S", "Artura", "GT"] },
    { name: "Mercedes-Benz", logo: "/image/car_logos/mercedes-benz.svg", models: ["A-Class", "C-Class", "E-Class", "GLC", "GLE", "EQC"] },
    { name: "Mitsubishi", logo: "/image/car_logos/mitsubishi.svg", models: ["Lancer", "Outlander", "ASX", "Pajero"] },
    { name: "Nissan", logo: "/image/car_logos/nissan.svg", models: ["Micra", "Qashqai", "X-Trail", "Leaf", "Altima"] },
    { name: "Opel", logo: "/image/car_logos/opel.svg", models: ["Corsa", "Astra", "Insignia", "Mokka", "Grandland"] },
    { name: "Peugeot", logo: "/image/car_logos/peugeot.svg", models: ["208", "308", "3008", "5008", "2008"] },
    { name: "Porsche", logo: "/image/car_logos/porsche.svg", models: ["911", "Cayenne", "Macan", "Taycan", "Panamera"] },
    { name: "Ram", logo: "/image/car_logos/ram.svg", models: ["1500", "2500", "3500"] },
    { name: "Renault", logo: "/image/car_logos/renault.svg", models: ["Clio", "Megane", "Captur", "Duster", "Arkana"] },
    { name: "Rolls-Royce", logo: "/image/car_logos/rolls-royce.svg", models: ["Ghost", "Phantom", "Cullinan", "Spectre"] },
    { name: "Seat", logo: "/image/car_logos/seat.svg", models: ["Ibiza", "Leon", "Arona", "Ateca", "Tarraco"] },
    { name: "Skoda", logo: "/image/car_logos/skoda.svg", models: ["Fabia", "Octavia", "Superb", "Karoq", "Kodiaq"] },
    { name: "Smart", logo: "/image/car_logos/smart.svg", models: ["ForTwo", "ForFour"] },
    { name: "Subaru", logo: "/image/car_logos/subaru.svg", models: ["Impreza", "Forester", "Outback", "XV", "WRX"] },
    { name: "Suzuki", logo: "/image/car_logos/suzuki.svg", models: ["Swift", "Baleno", "Vitara", "Jimny", "Ertiga"] },
    { name: "Tesla", logo: "/image/car_logos/tesla.svg", models: ["Model 3", "Model Y", "Model S", "Model X"] },
    { name: "Toyota", logo: "/image/car_logos/toyota.svg", models: ["Corolla", "Camry", "RAV4", "Land Cruiser", "Yaris", "Prius", "Hilux"] },
    { name: "Volkswagen", logo: "/image/car_logos/volkswagen.svg", models: ["Golf", "Passat", "Tiguan", "Polo", "Touareg", "Arteon"] },
    { name: "Volvo", logo: "/image/car_logos/volvo.svg", models: ["S60", "S90", "XC40", "XC60", "XC90"] },
  ];

  /* ---- Vehicle image mapping: brand/model -> local image path ---- */
  const VEHICLE_IMAGES = {
    "Acura": {"ILX":"/image/vehicles/acura/ilx.webp","TLX":"/image/vehicles/acura/tlx.webp","RDX":"/image/vehicles/acura/rdx.webp","MDX":"/image/vehicles/acura/mdx.webp"},
    "Alfa Romeo": {"Giulia":"/image/vehicles/alfa-romeo/giulia.webp","Stelvio":"/image/vehicles/alfa-romeo/stelvio.webp","Tonale":"/image/vehicles/alfa-romeo/tonale.webp"},
    "Aston Martin": {"Vantage":"/image/vehicles/aston-martin/vantage.webp","DB12":"/image/vehicles/aston-martin/db12.webp","DBX":"/image/vehicles/aston-martin/dbx.webp"},
    "Audi": {"A3":"/image/vehicles/audi/a3.webp","A4":"/image/vehicles/audi/a4.webp","A6":"/image/vehicles/audi/a6.webp","Q3":"/image/vehicles/audi/q3.webp","Q5":"/image/vehicles/audi/q5.webp","Q7":"/image/vehicles/audi/q7.webp","e-tron":"/image/vehicles/audi/e-tron.webp"},
    "Bentley": {"Continental GT":"/image/vehicles/bentley/continental-gt.webp","Flying Spur":"/image/vehicles/bentley/flying-spur.webp","Bentayga":"/image/vehicles/bentley/bentayga.webp"},
    "BMW": {"1 Series":"/image/vehicles/bmw/1-series.webp","3 Series":"/image/vehicles/bmw/3-series.webp","5 Series":"/image/vehicles/bmw/5-series.webp","X1":"/image/vehicles/bmw/x1.webp","X3":"/image/vehicles/bmw/x3.webp","X5":"/image/vehicles/bmw/x5.webp","i4":"/image/vehicles/bmw/i4.webp"},
    "Buick": {"Encore":"/image/vehicles/buick/encore.webp","Envision":"/image/vehicles/buick/envision.webp","LaCrosse":"/image/vehicles/buick/lacrosse.webp"},
    "Cadillac": {"CT4":"/image/vehicles/cadillac/ct4.webp","CT5":"/image/vehicles/cadillac/ct5.webp","XT4":"/image/vehicles/cadillac/xt4.webp","XT5":"/image/vehicles/cadillac/xt5.webp","Escalade":"/image/vehicles/cadillac/escalade.webp"},
    "Chevrolet": {"Spark":"/image/vehicles/chevrolet/spark.webp","Cruze":"/image/vehicles/chevrolet/cruze.webp","Malibu":"/image/vehicles/chevrolet/malibu.webp","Trailblazer":"/image/vehicles/chevrolet/trailblazer.webp","Equinox":"/image/vehicles/chevrolet/equinox.webp"},
    "Chrysler": {"300":"/image/vehicles/chrysler/300.webp","Pacifica":"/image/vehicles/chrysler/pacifica.webp"},
    "Citroen": {"C1":"/image/vehicles/citroen/c1.webp","C3":"/image/vehicles/citroen/c3.webp","C4":"/image/vehicles/citroen/c4.webp","C5":"/image/vehicles/citroen/c5.webp","Berlingo":"/image/vehicles/citroen/berlingo.webp"},
    "Dodge": {"Challenger":"/image/vehicles/dodge/challenger.webp","Charger":"/image/vehicles/dodge/charger.webp","Durango":"/image/vehicles/dodge/durango.webp"},
    "Ferrari": {"Roma":"/image/vehicles/ferrari/roma.webp","SF90":"/image/vehicles/ferrari/sf90-stradale.webp","296":"/image/vehicles/ferrari/296-gtb.webp","812":"/image/vehicles/ferrari/812-superfast.webp","F8":"/image/vehicles/ferrari/f8-tributo.webp"},
    "Fiat": {"500":"/image/vehicles/fiat/500.webp","Panda":"/image/vehicles/fiat/panda.webp","Punto":"/image/vehicles/fiat/punto.webp","Tipo":"/image/vehicles/fiat/tipo.webp"},
    "Ford": {"Fiesta":"/image/vehicles/ford/fiesta.webp","Focus":"/image/vehicles/ford/focus.webp","Mustang":"/image/vehicles/ford/mustang.webp","Ranger":"/image/vehicles/ford/ranger.webp","Escape":"/image/vehicles/ford/escape.webp","Explorer":"/image/vehicles/ford/explorer.webp"},
    "Genesis": {"G70":"/image/vehicles/genesis/g70.webp","G80":"/image/vehicles/genesis/g80.webp","G90":"/image/vehicles/genesis/g90.webp","GV70":"/image/vehicles/genesis/gv70.webp","GV80":"/image/vehicles/genesis/gv80.webp"},
    "GMC": {"Terrain":"/image/vehicles/gmc/terrain.webp","Acadia":"/image/vehicles/gmc/acadia.webp","Yukon":"/image/vehicles/gmc/yukon.webp","Sierra":"/image/vehicles/gmc/sierra.webp"},
    "Honda": {"Civic":"/image/vehicles/honda/civic.webp","Accord":"/image/vehicles/honda/accord.webp","CR-V":"/image/vehicles/honda/cr-v.webp","HR-V":"/image/vehicles/honda/hr-v.webp","City":"/image/vehicles/honda/city.webp","Fit":"/image/vehicles/honda/fit.webp"},
    "Hyundai": {"i20":"/image/vehicles/hyundai/i20.webp","i30":"/image/vehicles/hyundai/i30.webp","Tucson":"/image/vehicles/hyundai/tucson.webp","Santa Fe":"/image/vehicles/hyundai/santa-fe.webp","Elantra":"/image/vehicles/hyundai/elantra.webp","Kona":"/image/vehicles/hyundai/kona.webp"},
    "Infiniti": {"Q50":null,"Q60":null,"QX50":null,"QX60":null},
    "Jaguar": {"XE":"/image/vehicles/jaguar/xe.webp","XF":"/image/vehicles/jaguar/xf.webp","F-PACE":"/image/vehicles/jaguar/f-pace.webp","E-PACE":"/image/vehicles/jaguar/e-pace.webp","I-PACE":"/image/vehicles/jaguar/i-pace.webp"},
    "Jeep": {"Renegade":"/image/vehicles/jeep/renegade.webp","Compass":"/image/vehicles/jeep/compass.webp","Cherokee":"/image/vehicles/jeep/cherokee.webp","Wrangler":"/image/vehicles/jeep/wrangler.webp","Grand Cherokee":"/image/vehicles/jeep/grand-cherokee.webp"},
    "Kia": {"Rio":"/image/vehicles/kia/rio.webp","Ceed":"/image/vehicles/kia/ceed.webp","Sportage":"/image/vehicles/kia/sportage.webp","Sorento":"/image/vehicles/kia/sorento.webp","Picanto":"/image/vehicles/kia/picanto.webp","EV6":"/image/vehicles/kia/ev6.webp"},
    "Lamborghini": {"Huracan":"/image/vehicles/lamborghini/huracan.webp","Urus":"/image/vehicles/lamborghini/urus.webp","Revuelto":"/image/vehicles/lamborghini/revuelto.webp"},
    "Land Rover": {"Range Rover":"/image/vehicles/land-rover/range-rover.webp","Discovery":"/image/vehicles/land-rover/discovery.webp","Defender":"/image/vehicles/land-rover/defender.webp","Evoque":"/image/vehicles/land-rover/evoque.webp"},
    "Lexus": {"UX":"/image/vehicles/lexus/ux.webp","NX":"/image/vehicles/lexus/nx.webp","RX":"/image/vehicles/lexus/rx.webp","ES":"/image/vehicles/lexus/es.webp","LS":"/image/vehicles/lexus/ls.webp"},
    "Lincoln": {"Corsair":"/image/vehicles/lincoln/corsair.webp","Aviator":"/image/vehicles/lincoln/aviator.webp","Navigator":"/image/vehicles/lincoln/navigator.webp"},
    "Maserati": {"Ghibli":"/image/vehicles/maserati/ghibli.webp","Levante":"/image/vehicles/maserati/levante.webp","Grecale":"/image/vehicles/maserati/grecale.webp","GranTurismo":"/image/vehicles/maserati/granturismo.webp"},
    "Mazda": {"2":"/image/vehicles/mazda/2.webp","3":"/image/vehicles/mazda/3.webp","6":"/image/vehicles/mazda/6.webp","CX-3":"/image/vehicles/mazda/cx-3.webp","CX-5":"/image/vehicles/mazda/cx-5.webp","MX-5":"/image/vehicles/mazda/mx-5.webp"},
    "McLaren": {"720S":"/image/vehicles/mclaren/720s.webp","750S":"/image/vehicles/mclaren/750s.webp","Artura":"/image/vehicles/mclaren/artura.webp","GT":"/image/vehicles/mclaren/gt.webp"},
    "Mercedes-Benz": {"A-Class":"/image/vehicles/mercedes-benz/a-class.webp","C-Class":"/image/vehicles/mercedes-benz/c-class.webp","E-Class":"/image/vehicles/mercedes-benz/e-class.webp","GLC":"/image/vehicles/mercedes-benz/glc.webp","GLE":"/image/vehicles/mercedes-benz/gle.webp","EQC":"/image/vehicles/mercedes-benz/eqc.webp"},
    "Mitsubishi": {"Lancer":"/image/vehicles/mitsubishi/lancer.webp","Outlander":"/image/vehicles/mitsubishi/outlander.webp","ASX":"/image/vehicles/mitsubishi/asx.webp","Pajero":"/image/vehicles/mitsubishi/pajero.webp"},
    "Nissan": {"Micra":"/image/vehicles/nissan/micra.webp","Qashqai":"/image/vehicles/nissan/qashqai.webp","X-Trail":"/image/vehicles/nissan/x-trail.webp","Leaf":"/image/vehicles/nissan/leaf.webp","Altima":"/image/vehicles/nissan/altima.webp"},
    "Opel": {"Corsa":null,"Astra":null,"Insignia":"/image/vehicles/opel/insignia.webp","Mokka":"/image/vehicles/opel/mokka.webp","Grandland":"/image/vehicles/opel/grandland.webp"},
    "Peugeot": {"208":"/image/vehicles/peugeot/208.webp","308":"/image/vehicles/peugeot/308.webp","3008":"/image/vehicles/peugeot/3008.webp","5008":"/image/vehicles/peugeot/5008.webp","2008":"/image/vehicles/peugeot/2008.webp"},
    "Porsche": {"911":"/image/vehicles/porsche/911.webp","Cayenne":"/image/vehicles/porsche/cayenne.webp","Macan":"/image/vehicles/porsche/macan.webp","Taycan":"/image/vehicles/porsche/taycan.webp","Panamera":"/image/vehicles/porsche/panamera.webp"},
    "Ram": {"1500":"/image/vehicles/ram/1500.webp","2500":"/image/vehicles/ram/2500.webp","3500":"/image/vehicles/ram/3500.webp"},
    "Renault": {"Clio":"/image/vehicles/renault/clio.webp","Megane":"/image/vehicles/renault/megane.webp","Captur":"/image/vehicles/renault/captur.webp","Duster":"/image/vehicles/renault/duster.webp","Arkana":"/image/vehicles/renault/arkana.webp"},
    "Rolls-Royce": {"Ghost":"/image/vehicles/rolls-royce/ghost.webp","Phantom":"/image/vehicles/rolls-royce/phantom.webp","Cullinan":"/image/vehicles/rolls-royce/cullinan.webp","Spectre":"/image/vehicles/rolls-royce/spectre.webp"},
    "Seat": {"Ibiza":"/image/vehicles/seat/ibiza.webp","Leon":"/image/vehicles/seat/leon.webp","Arona":"/image/vehicles/seat/arona.webp","Ateca":"/image/vehicles/seat/ateca.webp","Tarraco":"/image/vehicles/seat/tarraco.webp"},
    "Skoda": {"Fabia":"/image/vehicles/skoda/fabia.webp","Octavia":"/image/vehicles/skoda/octavia.webp","Superb":"/image/vehicles/skoda/superb.webp","Karoq":"/image/vehicles/skoda/karoq.webp","Kodiaq":"/image/vehicles/skoda/kodiaq.webp"},
    "Smart": {"ForTwo":"/image/vehicles/smart/fortwo.webp","ForFour":"/image/vehicles/smart/forfour.webp"},
    "Subaru": {"Impreza":"/image/vehicles/subaru/impreza.webp","Forester":"/image/vehicles/subaru/forester.webp","Outback":"/image/vehicles/subaru/outback.webp","XV":"/image/vehicles/subaru/xv.webp","WRX":"/image/vehicles/subaru/wrx.webp"},
    "Suzuki": {"Swift":"/image/vehicles/suzuki/swift.webp","Baleno":"/image/vehicles/suzuki/baleno.webp","Vitara":"/image/vehicles/suzuki/vitara.webp","Jimny":"/image/vehicles/suzuki/jimny.webp","Ertiga":"/image/vehicles/suzuki/ertiga.webp"},
    "Tesla": {"Model 3":"/image/vehicles/tesla/model-3.webp","Model Y":"/image/vehicles/tesla/model-y.webp","Model S":"/image/vehicles/tesla/model-s.webp","Model X":"/image/vehicles/tesla/model-x.webp"},
    "Toyota": {"Corolla":"/image/vehicles/toyota/corolla.webp","Camry":"/image/vehicles/toyota/camry.webp","RAV4":"/image/vehicles/toyota/rav4.webp","Land Cruiser":"/image/vehicles/toyota/land-cruiser.webp","Yaris":"/image/vehicles/toyota/yaris.webp","Prius":"/image/vehicles/toyota/prius.webp","Hilux":"/image/vehicles/toyota/hilux.webp"},
    "Volkswagen": {"Golf":"/image/vehicles/volkswagen/golf.webp","Passat":"/image/vehicles/volkswagen/passat.webp","Tiguan":"/image/vehicles/volkswagen/tiguan.webp","Polo":"/image/vehicles/volkswagen/polo.webp","Touareg":"/image/vehicles/volkswagen/touareg.webp","Arteon":"/image/vehicles/volkswagen/arteon.webp"},
    "Volvo": {"S60":"/image/vehicles/volvo/s60.webp","S90":"/image/vehicles/volvo/s90.webp","XC40":"/image/vehicles/volvo/xc40.webp","XC60":"/image/vehicles/volvo/xc60.webp","XC90":"/image/vehicles/volvo/xc90.webp"},
  };

  function getModelImage(brand, model) {
    /* The shipped local /image/vehicles/<brand>/<model>.webp files are unreliable
       DUPLICATES (many distinct models share one identical file — e.g. every Honda
       file is byte-identical), which caused every model to show the same (Civic)
       image. They are therefore no longer used: the correct per-model photo comes
       from the image API (getVehicleImageUrl → Wikipedia). Returning null makes any
       image fallback skip straight to a neutral icon instead of another model's
       photo. (VEHICLE_IMAGES is kept for reference / possible future re-population.) */
    return null;
  }

  /* Dynamic, per-vehicle image fetched from an external CDN (imagin.studio) so
     the picture matches the ACTUAL make/model/year instead of a static
     placeholder. Used as the primary <img> src; on error the UI falls back to a
     shipped image (getModelImage) and finally an icon — see dzImgFallback(). */
  function getVehicleImageUrl(brand, model, year) {
    if (!brand) return "";
    /* Route through the server proxy so the image-CDN key lives in one place
       (env IMAGIN_CUSTOMER) and can be swapped for a watermark-free licensed key
       without touching the client. The server 307-redirects to the CDN. */
    let u = "/api/vehicles/image?make=" + encodeURIComponent(brand) +
            "&model=" + encodeURIComponent(model || "");
    if (year) u += "&year=" + encodeURIComponent(year);
    return u;
  }

  /* Progressive image fallback: dynamic CDN image -> shipped local image ->
     icon. Attached inline via onerror on vehicle <img> tags. */
  window.dzImgFallback = function (img) {
    const local = img.getAttribute("data-local");
    if (local && img.getAttribute("src") !== local) {
      img.removeAttribute("data-local");
      img.src = local;
      return;
    }
    img.style.display = "none";
    const wrap = img.parentElement;
    if (!wrap) return;
    wrap.classList.add("dz-selected-img-failed", "dz-model-img-failed");
    const fb = wrap.querySelector(
      ".dz-selected-img-fallback, .dz-model-img-fallback, .dz-info-vehicle-fallback"
    );
    if (fb) { fb.classList.remove("hidden"); fb.style.display = "flex"; }
  };

  /* ============================================================
     LIVE VEHICLE DATA — cascading brand -> model -> engine
     Backed by /api/vehicles/{makes,models,engines} (NHTSA vPIC +
     CarQuery, proxied + cached server-side). Cached per-query and
     debounced client-side so typing never floods the network.
     ============================================================ */
  const VehicleAPI = (function () {
    const cache = new Map();          /* url -> Promise<items> */
    async function fetchItems(url) {
      if (cache.has(url)) return cache.get(url);
      const p = fetch(url, { headers: { "X-Requested-With": "fetch" } })
        .then((r) => (r.ok ? r.json() : { items: [] }))
        .then((d) => (d && Array.isArray(d.items) ? d.items : []))
        .catch(() => []);
      cache.set(url, p);
      return p;
    }
    const qp = (o) =>
      Object.entries(o)
        .filter(([, v]) => v != null && v !== "")
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
        .join("&");
    return {
      makes: (q, limit) => fetchItems(`/api/vehicles/makes?${qp({ q, limit })}`),
      models: (make, q) => fetchItems(`/api/vehicles/models?${qp({ make, q })}`),
      engines: (make, model, q) =>
        fetchItems(`/api/vehicles/engines?${qp({ make, model, q })}`),
    };
  })();

  /* Small debounce helper for autocomplete inputs */
  function debounce(fn, ms) {
    let t = null;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  /* ============================================================
     SMART MODEL SEARCH — searchable index + normalization
     ============================================================ */
  function normalizeModel(str) {
    return (str || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  /* Build flat model index from CAR_BRANDS + VEHICLE_IMAGES */
  const MODEL_INDEX = [];
  const IMAGE_SOURCES = {
    "Toyota": { "Corolla": "Toyota USA Newsroom", "Camry": "Toyota USA Newsroom" },
  };
  (function buildModelIndex() {
    for (const brand of CAR_BRANDS) {
      for (const model of brand.models) {
        MODEL_INDEX.push({
          brand: brand.name,
          model: model,
          logo: brand.logo,
          image: getModelImage(brand.name, model),
          imageSource: (IMAGE_SOURCES[brand.name] && IMAGE_SOURCES[brand.name][model]) || "CarDekho",
          _norm: normalizeModel(model),
          _brandNorm: normalizeModel(brand.name),
        });
      }
    }
  })();

  /* Search models by query — returns array of matches sorted by relevance */
  function searchModels(query) {
    if (!query || query.length < 1) return [];
    const q = normalizeModel(query);
    if (!q) return [];

    const exact = [];
    const prefix = [];
    const contains = [];

    for (const entry of MODEL_INDEX) {
      if (entry._norm === q) {
        exact.push(entry);
      } else if (entry._norm.startsWith(q)) {
        prefix.push(entry);
      } else if (entry._norm.includes(q)) {
        contains.push(entry);
      }
    }

    /* Also check brand name matches */
    const brandExact = [];
    const brandPrefix = [];
    for (const brand of CAR_BRANDS) {
      const bNorm = normalizeModel(brand.name);
      if (bNorm === q) {
        /* Brand exact match — return all its models */
        for (const model of brand.models) {
          const entry = MODEL_INDEX.find(e => e.brand === brand.name && e.model === model);
          if (entry) brandExact.push(entry);
        }
      } else if (bNorm.startsWith(q) || brand.name.toLowerCase().includes(query.toLowerCase())) {
        /* Brand prefix/contains — return all its models */
        for (const model of brand.models) {
          const entry = MODEL_INDEX.find(e => e.brand === brand.name && e.model === model);
          if (entry) brandPrefix.push(entry);
        }
      }
    }

    /* Merge: exact model > prefix model > brand exact > brand prefix > contains */
    const seen = new Set();
    const results = [];
    for (const list of [exact, prefix, brandExact, brandPrefix, contains]) {
      for (const entry of list) {
        const key = entry.brand + "|" + entry.model;
        if (!seen.has(key)) {
          seen.add(key);
          results.push(entry);
        }
      }
    }
    return results.slice(0, 12);
  }

  /* ---- Brand color utility — generates unique gradient per brand ---- */
  const BRAND_COLORS = {
    "Acura":         { from: "#1a1a2e", to: "#c4a35a" },
    "Alfa Romeo":    { from: "#1a1a2e", to: "#8b2020" },
    "Aston Martin":  { from: "#0d1117", to: "#1a6b4a" },
    "Audi":          { from: "#1a1a2e", to: "#bb0a30" },
    "Bentley":       { from: "#0d1117", to: "#6b5b3e" },
    "BMW":           { from: "#1a1a2e", to: "#0066b1" },
    "Buick":         { from: "#1a1a2e", to: "#5a3a28" },
    "Cadillac":      { from: "#1a1a2e", to: "#c4a35a" },
    "Chevrolet":     { from: "#1a1a2e", to: "#c4a35a" },
    "Chrysler":      { from: "#1a1a2e", to: "#4a6fa5" },
    "Citroen":       { from: "#1a1a2e", to: "#6b4a8a" },
    "Dodge":         { from: "#1a1a2e", to: "#c43a3a" },
    "Ferrari":       { from: "#1a0a0a", to: "#cc1e1e" },
    "Fiat":          { from: "#1a1a2e", to: "#b83a2a" },
    "Ford":          { from: "#1a1a2e", to: "#003478" },
    "Genesis":       { from: "#1a1a2e", to: "#3a5a8a" },
    "GMC":           { from: "#1a1a2e", to: "#8b2020" },
    "Honda":         { from: "#1a1a2e", to: "#cc2222" },
    "Hyundai":       { from: "#1a1a2e", to: "#002c5f" },
    "Infiniti":      { from: "#1a1a2e", to: "#3a3a5a" },
    "Jaguar":        { from: "#0d1117", to: "#1a5a3a" },
    "Jeep":          { from: "#1a1a2e", to: "#3a5a2a" },
    "Kia":           { from: "#1a1a2e", to: "#05141f" },
    "Lamborghini":   { from: "#1a1a0a", to: "#8a7a2a" },
    "Land Rover":    { from: "#0d1117", to: "#2a5a3a" },
    "Lexus":         { from: "#1a1a2e", to: "#5a2a2a" },
    "Lincoln":       { from: "#1a1a2e", to: "#3a3a5a" },
    "Maserati":      { from: "#0d1117", to: "#1a3a6a" },
    "Mazda":         { from: "#1a1a2e", to: "#911a2a" },
    "McLaren":       { from: "#1a1a0a", to: "#ff6600" },
    "Mercedes-Benz": { from: "#1a1a2e", to: "#3a3a5a" },
    "Mitsubishi":    { from: "#1a1a2e", to: "#cc2222" },
    "Nissan":        { from: "#1a1a2e", to: "#c43a3a" },
    "Opel":          { from: "#1a1a2e", to: "#3a8a5a" },
    "Peugeot":       { from: "#1a1a2e", to: "#3a5a8a" },
    "Porsche":       { from: "#1a1a2e", to: "#8a7a5a" },
    "Ram":           { from: "#1a1a2e", to: "#8b2020" },
    "Renault":       { from: "#1a1a2e", to: "#ccaa22" },
    "Rolls-Royce":   { from: "#0d1117", to: "#5a5a5a" },
    "Seat":          { from: "#1a1a2e", to: "#cc4422" },
    "Skoda":         { from: "#1a1a2e", to: "#3a8a5a" },
    "Smart":         { from: "#1a1a2e", to: "#6ab4a8" },
    "Subaru":        { from: "#1a1a2e", to: "#3a5a8a" },
    "Suzuki":        { from: "#1a1a2e", to: "#cc3a2a" },
    "Tesla":         { from: "#0d1117", to: "#cc2222" },
    "Toyota":        { from: "#1a1a2e", to: "#cc2222" },
    "Volkswagen":    { from: "#1a1a2e", to: "#3a5a8a" },
    "Volvo":         { from: "#1a1a2e", to: "#3a5a7a" },
  };
  function brandGradient(name) {
    const c = BRAND_COLORS[name] || { from: "#0a1628", to: "#1a3a5a" };
    return `linear-gradient(135deg, ${c.from}, ${c.to})`;
  }

  /* ---- Smart question banks ---- */
  const QUESTIONS通用 = [
    {
      key: "when",
      title: "When does the problem happen?",
      subtitle: "Select the situation that best describes it.",
      options: [
        "When starting the car",
        "When driving",
        "When turning",
        "When braking",
        "When accelerating",
        "All the time",
        "Not sure",
      ],
    },
    {
      key: "started",
      title: "When did you first notice the problem?",
      subtitle: "",
      options: ["Today", "A few days ago", "A few weeks ago", "A long time ago", "Not sure"],
    },
    {
      key: "severity",
      title: "How severe is the problem?",
      subtitle: "",
      options: [
        "Mild — just noticed it",
        "Moderate — noticeable while driving",
        "Severe — affects driving",
        "Critical — car may not be safe",
      ],
    },
  ];

  const QUESTIONS_BY_CATEGORY = {
    overheating: [
      {
        key: "temperature",
        title: "What does the temperature gauge show?",
        subtitle: "",
        options: ["In the red zone", "Fluctuating", "Slowly rising", "Normal but steam visible", "Not sure"],
      },
      {
        key: "warning_light",
        title: "Is the check engine or temperature warning light on?",
        subtitle: "",
        options: ["Temperature warning light", "Check engine light", "Both", "No warning lights", "Not sure"],
      },
      {
        key: "driving_condition",
        title: "When does the overheating occur?",
        subtitle: "",
        options: ["In city traffic", "On the highway", "When idling", "When climbing hills", "All the time", "Not sure"],
      },
    ],
    brakes: [
      {
        key: "noise_type",
        title: "What kind of noise do the brakes make?",
        subtitle: "",
        options: ["Squealing or screeching", "Grinding", "Clicking", "Thumping", "No noise — just vibration", "Not sure"],
      },
      {
        key: "location",
        title: "Which wheels seem affected?",
        subtitle: "",
        options: ["Front wheels", "Rear wheels", "All wheels", "Left side", "Right side", "Not sure"],
      },
      {
        key: "dashboard",
        title: "Does the brake warning light come on?",
        subtitle: "",
        options: ["Yes", "No", "Not sure"],
      },
    ],
    no_start: [
      {
        key: "dashboard",
        title: "What happens when you turn the key?",
        subtitle: "",
        options: [
          "Engine cranks but doesn't start",
          "Clicking sound but no crank",
          "Complete silence",
          "Engine starts briefly then dies",
          "Not sure",
        ],
      },
      {
        key: "fuel_level",
        title: "What is your fuel level?",
        subtitle: "",
        options: ["Full", "Half", "Low", "Near empty", "Not sure"],
      },
      {
        key: "recent_work",
        title: "Any recent work done on the car?",
        subtitle: "",
        options: ["Oil change", "Battery replaced", "Repair service", "Nothing recent", "Not sure"],
      },
    ],
    ac: [
      {
        key: "temperature",
        title: "What happens with the AC?",
        subtitle: "",
        options: [
          "Blows warm air",
          "Blows weak air",
          "Works sometimes then stops",
          "Strange smell from vents",
          "Not sure",
        ],
      },
      {
        key: "driving_condition",
        title: "Does it change while driving?",
        subtitle: "",
        options: [
          "Worse when idling",
          "Better when driving",
          "Same always",
          "Not sure",
        ],
      },
    ],
    noise: [
      {
        key: "noise_type",
        title: "Describe the sound.",
        subtitle: "",
        options: [
          "Knocking or clunking",
          "Squealing or whining",
          "Rattling",
          "Hissing",
          "Thumping",
          "Not sure",
        ],
      },
      {
        key: "location",
        title: "Where does the sound seem to come from?",
        subtitle: "",
        options: ["Front", "Rear", "Left side", "Right side", "Under the hood", "Under the car", "Not sure"],
      },
      {
        key: "when",
        title: "When do you hear the sound?",
        subtitle: "",
        options: [
          "When starting",
          "When accelerating",
          "When turning",
          "When braking",
          "At low speed",
          "At high speed",
          "All the time",
          "Not sure",
        ],
      },
    ],
    shake: [
      {
        key: "when",
        title: "When does the shaking happen?",
        subtitle: "",
        options: [
          "At idle",
          "When accelerating",
          "At certain speeds",
          "When braking",
          "When turning",
          "All the time",
          "Not sure",
        ],
      },
      {
        key: "location",
        title: "Where do you feel the shaking?",
        subtitle: "",
        options: [
          "Steering wheel",
          "Seat",
          "Floor",
          "Whole car",
          "Not sure",
        ],
      },
    ],
  };

  /* ---- Problem classification ---- */
  function classifyProblem(text) {
    const t = text.toLowerCase();
    if (/overheat|temperature|steam|radiat|coolant|boil/.test(t)) return "overheating";
    if (/brake|brak|squeal|screech|grind.*brake|pedal/.test(t)) return "brakes";
    if (/won.?t start|no.?start|crank|dead|battery|turn.?key|start/.test(t)) return "no_start";
    if (/ac|air.?cond|cool|vent|compr/.test(t)) return "ac";
    if (/shake|vibrat|shudder|rough|idle/.test(t)) return "shake";
    if (/noise|sound|knock|rattle|squeal|whine|clunk|hiss/.test(t)) return "noise";
    return "general";
  }

  function getQuestions(problem) {
    const cat = classifyProblem(problem);
    const specific = QUESTIONS_BY_CATEGORY[cat] || [];
    const general = QUESTIONS通用;
    const used = new Set(specific.map((q) => q.key));
    const merged = [...specific, ...general.filter((q) => !used.has(q.key))];
    return merged.slice(0, 6);
  }

  /* ---- Dialect detection & server-side questions ---- */
  const _dialectCache = {};

  /**
   * Detect Arabic dialect from user input text.
   * @param {string} text - User input text
   * @returns {Promise<{language: string, dialect: string, dialect_confidence: number, detected_terms: string[], canonical_concepts: object[]}>}
   */
  async function detectDialect(text) {
    if (!text || text.length < 3) {
      return { language: "en", dialect: "", dialect_confidence: 0.0, detected_terms: [], canonical_concepts: [] };
    }
    const cacheKey = text.toLowerCase().trim();
    if (_dialectCache[cacheKey]) return _dialectCache[cacheKey];
    try {
      const resp = await fetch("/api/diagnose/detect-dialect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await resp.json();
      if (data.ok) {
        _dialectCache[cacheKey] = data;
        return data;
      }
    } catch (e) {
      console.warn("[DIALECT] Detection failed:", e);
    }
    return { language: "en", dialect: "", dialect_confidence: 0.0, detected_terms: [], canonical_concepts: [] };
  }

  /**
   * Fetch dialect-aware questions from server using Gemini.
   * @param {string} problem - Problem description
   * @param {object} vehicle - Vehicle info {brand, model, engine, year}
   * @param {string} dialect - Detected dialect
   * @param {number} dialect_confidence - Dialect confidence 0.0-1.0
   * @param {string[]} detected_terms - Detected automotive terms
   * @param {object[]} canonical_concepts - Canonical concept mappings
   * @param {string} category - Problem category
   * @param {string} when - When problem occurs
   * @param {string} where - Where problem occurs
   * @returns {Promise<object[]>} Array of question objects
   */
  async function fetchServerQuestions(problem, vehicle, dialect, dialect_confidence, detected_terms, canonical_concepts, category, when, where) {
    try {
      const resp = await fetch("/api/diagnose/questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          problem,
          vehicle,
          dialect,
          dialect_confidence,
          detected_terms,
          canonical_concepts,
          category: category || "",
          when: when || "",
          where: where || "",
        }),
      });
      const data = await resp.json();
      if (data.ok && Array.isArray(data.questions) && data.questions.length > 0) {
        return data.questions;
      }
    } catch (e) {
      console.warn("[QUESTIONS] Server-side generation failed:", e);
    }
    return null;
  }

  /* ---- Problem suggestions (smart completion) ---- */
  /* Rich problem catalogue — each entry drives a media icon, a category tag and
     a contextual safety notice in the real-time suggestion list (item 5). */
  const PROBLEM_CATALOG = [
    { text: "Engine overheating", cat: "Engine", icon: "bi-thermometer-high", tone: "danger", notice: "Stop safely if the temperature gauge is in the red — driving on can warp the head." },
    { text: "Engine shaking", cat: "Engine", icon: "bi-activity", tone: "warning", notice: "Often a misfire — worse under load or at idle." },
    { text: "Engine won't start", cat: "Engine", icon: "bi-x-octagon", tone: "danger", notice: "Note if it cranks, clicks, or is silent — it narrows the cause." },
    { text: "Engine knocking", cat: "Engine", icon: "bi-soundwave", tone: "warning", notice: "A metallic knock can signal detonation or low oil — reduce load." },
    { text: "Check engine light", cat: "Engine", icon: "bi-exclamation-triangle", tone: "warning", notice: "Flashing = misfire, get it checked soon; steady = less urgent." },
    { text: "Rough idle", cat: "Engine", icon: "bi-activity", tone: "warning", notice: "Uneven RPM at a stop points to air, fuel or ignition." },
    { text: "Loss of power when accelerating", cat: "Engine", icon: "bi-speedometer", tone: "warning", notice: "Could be fuel delivery, a clogged filter or a sensor." },
    { text: "Car stalling at idle", cat: "Engine", icon: "bi-slash-circle", tone: "warning", notice: "Note if it restarts easily — helps isolate the fault." },
    { text: "Brake noise", cat: "Brakes", icon: "bi-disc", tone: "warning", notice: "Squeal often = worn pads; grinding = metal-on-metal, act now." },
    { text: "Brake pedal feels soft", cat: "Brakes", icon: "bi-disc", tone: "danger", notice: "A spongy pedal can mean air or a fluid leak — drive with caution." },
    { text: "Brakes squeaking", cat: "Brakes", icon: "bi-disc", tone: "warning", notice: "Common with worn pads or glazing; louder when cold." },
    { text: "Brake warning light", cat: "Brakes", icon: "bi-exclamation-triangle", tone: "danger", notice: "Check fluid level and parking brake first; have it inspected." },
    { text: "Battery draining", cat: "Electrical", icon: "bi-battery-half", tone: "warning", notice: "A parasitic draw or failing alternator is common." },
    { text: "Battery won't hold charge", cat: "Electrical", icon: "bi-battery", tone: "warning", notice: "Battery age (3–5 yrs) and terminal corrosion matter here." },
    { text: "Clicking sound when starting", cat: "Electrical", icon: "bi-volume-up", tone: "warning", notice: "Rapid clicks usually mean a weak battery or bad connection." },
    { text: "Headlights flickering", cat: "Electrical", icon: "bi-lightbulb", tone: "info", notice: "Could be the alternator, ground, or a loose connector." },
    { text: "Power windows not working", cat: "Electrical", icon: "bi-window", tone: "info", notice: "Often a fuse, switch or motor." },
    { text: "Dashboard warning lights", cat: "Electrical", icon: "bi-exclamation-diamond", tone: "warning", notice: "Note the colour — red is urgent, amber is caution." },
    { text: "AC not cooling", cat: "Climate", icon: "bi-snow", tone: "info", notice: "Low refrigerant or a compressor issue is typical." },
    { text: "AC blowing warm air", cat: "Climate", icon: "bi-thermometer-sun", tone: "info", notice: "Check if it's warm on one side only — hints at a blend door." },
    { text: "Strange smell from vents", cat: "Climate", icon: "bi-wind", tone: "info", notice: "Musty = cabin filter/mould; sweet = coolant leak." },
    { text: "Transmission slipping", cat: "Transmission", icon: "bi-gear-wide-connected", tone: "danger", notice: "RPM rising without speed — check fluid; avoid heavy driving." },
    { text: "Difficulty shifting gears", cat: "Transmission", icon: "bi-gear", tone: "warning", notice: "Manual: clutch/linkage; auto: fluid or solenoid." },
    { text: "Grinding noise when shifting", cat: "Transmission", icon: "bi-gear-wide", tone: "warning", notice: "Can indicate clutch or synchro wear." },
    { text: "Steering wheel vibration", cat: "Steering", icon: "bi-life-preserver", tone: "warning", notice: "At speed = wheel balance; when braking = warped rotors." },
    { text: "Car pulling to one side", cat: "Steering", icon: "bi-arrow-left-right", tone: "warning", notice: "Alignment, tyre pressure or a brake dragging." },
    { text: "Suspension noise over bumps", cat: "Suspension", icon: "bi-water", tone: "info", notice: "Clunks can be links, bushings or struts." },
    { text: "Car bouncing excessively", cat: "Suspension", icon: "bi-water", tone: "warning", notice: "Worn shocks/struts reduce control — check soon." },
    { text: "Unusual tire wear", cat: "Tires", icon: "bi-record-circle", tone: "info", notice: "Uneven wear points to alignment or pressure issues." },
    { text: "Oil pressure warning light", cat: "Warning", icon: "bi-droplet-half", tone: "danger", notice: "Stop the engine — low oil pressure can destroy it quickly." },
    { text: "Coolant leaking", cat: "Cooling", icon: "bi-droplet", tone: "warning", notice: "Watch the temp gauge; top up only when cool." },
    { text: "Smoke from engine", cat: "Engine", icon: "bi-cloud-haze2", tone: "danger", notice: "Blue = oil, white = coolant, black = fuel — stop if heavy." },
    { text: "Exhaust smell inside car", cat: "Warning", icon: "bi-cloud", tone: "danger", notice: "Fumes in the cabin are a safety risk — ventilate and inspect." },
    { text: "Fuel smell", cat: "Fuel", icon: "bi-fuel-pump", tone: "danger", notice: "A fuel odour is a fire risk — check for leaks promptly." },
    { text: "Hesitation when pressing gas", cat: "Engine", icon: "bi-speedometer2", tone: "warning", notice: "Fuel, ignition or a dirty throttle body are common." },
    { text: "Water leaking inside car", cat: "Body", icon: "bi-droplet", tone: "info", notice: "Blocked drains or seals; can affect electronics." },
    { text: "Windshield wipers not working", cat: "Body", icon: "bi-cloud-drizzle", tone: "info", notice: "Fuse, motor or linkage are usual suspects." },
    { text: "Horn not working", cat: "Electrical", icon: "bi-megaphone", tone: "info", notice: "Often a fuse, relay or the horn itself." },
  ];

  /* Category -> tone colour, used for the icon badge tint. */
  const PROBLEM_TONE = { danger: "danger", warning: "warning", info: "info", success: "success" };
  const PROBLEM_SUGGESTIONS = PROBLEM_CATALOG.map((p) => p.text);

  /* ============================================================
     SEVERITY GAUGE (item 6) — modern color-coded meter used in the
     result modal and the workspace result panel. Communicates
     Low → Moderate → Severe → Critical at a glance.
     ============================================================ */
  const SEV_POS = { low: 12.5, medium: 37.5, high: 62.5, critical: 87.5 };

  function severityMeter(sev, conf) {
    const pos = SEV_POS[sev.level] != null ? SEV_POS[sev.level] : 37.5;
    const confVal = Math.max(0, Math.min(100, conf || 0));
    return `
    <div class="dz-sevmeter dz-sevmeter--${sev.level}" role="group" aria-label="Problem severity: ${esc(sev.label)}">
      <div class="dz-sevmeter-top">
        <span class="dz-sevmeter-badge"><i class="bi ${sev.icon}"></i> ${esc(sev.label)}</span>
        <span class="dz-sevmeter-conf"><span class="dz-sevmeter-conf-num">${confVal}%</span> confidence</span>
      </div>
      <div class="dz-sevmeter-gauge">
        <span class="dz-sevmeter-seg s-low"></span>
        <span class="dz-sevmeter-seg s-med"></span>
        <span class="dz-sevmeter-seg s-high"></span>
        <span class="dz-sevmeter-seg s-crit"></span>
        <span class="dz-sevmeter-thumb" style="left:${pos}%"></span>
      </div>
      <div class="dz-sevmeter-scale">
        <span data-lvl="low">Low</span><span data-lvl="medium">Moderate</span>
        <span data-lvl="high">Severe</span><span data-lvl="critical">Critical</span>
      </div>
      <div class="dz-sevmeter-msg">${esc(sev.msg)}</div>
    </div>`;
  }

  /* ---- DOM refs ---- */
  function step(name) {
    return $(`.dz-step[data-step="${name}"]`);
  }
  function showStep(name, _opts) {
    const _pushHistory = !(_opts && _opts._fromPop);

    /* "loading" and "result" are now handled by the modal overlay */
    if (name === "loading" || name === "result") {
      const wizHeader = $("#dz-wizard-header");
      const mainGrid = $("#dz-main-grid");
      const benefits = $("#dz-benefits");
      if (wizHeader) wizHeader.style.display = "none";
      if (mainGrid) mainGrid.style.display = "none";
      if (benefits) benefits.style.display = "none";
      state.step = name;
      return;
    }

    /* Push browser history when navigating between wizard steps */
    if (_pushHistory && !_navGuard) {
      const idx = WIZARD_STEPS.indexOf(name);
      if (idx >= 0) {
        /* Only push if we are actually moving to a different step */
        if (_wizIdx < 0) {
          /* First wizard entry — replace current /diagnose with first step */
          _wizIdx = idx;
          _navGuard = true;
          window.history.replaceState({ wiz: true, idx: idx }, "", "#step-" + name);
          _navGuard = false;
        } else if (idx !== _wizIdx) {
          /* Moving to a different step — push new entry */
          _wizIdx = idx;
          _navGuard = true;
          window.history.pushState({ wiz: true, idx: idx }, "", "#step-" + name);
          _navGuard = false;
        }
      }
    } else if (_opts && _opts._fromPop) {
      _wizIdx = WIZARD_STEPS.indexOf(name);
    }

    $$(".dz-step").forEach((s) => s.classList.remove("active"));
    const el = step(name);
    if (el) {
      el.classList.add("active");
      state.step = name;
      el.style.animation = "none";
      el.offsetHeight;
      el.style.animation = "";
    }

    /* Show/hide wizard header, main grid, benefits based on step */
    const wizHeader = $("#dz-wizard-header");
    const mainGrid = $("#dz-main-grid");
    const benefits = $("#dz-benefits");
    const isStructural = ["welcome"].includes(name);

    if (wizHeader) wizHeader.style.display = isStructural ? "none" : "";
    if (mainGrid) mainGrid.style.display = isStructural ? "none" : "";
    if (benefits) benefits.style.display = isStructural ? "none" : "";

    updateStepIndicator(name);
  }

  /* ---- Update step indicator active/completed states ---- */
  function updateStepIndicator(stepName) {
    const num = STEP_MAP[stepName];
    if (num == null) return;

    /* Single persistent stepper in #dz-stepper */
    const items = $$("#dz-stepper .dz-stepper-item");
    const lines = $$("#dz-stepper .dz-stepper-line");
    items.forEach((item, i) => {
      const itemNum = parseInt(item.dataset.stepNum, 10);
      item.classList.remove("active", "completed");
      const circle = item.querySelector(".dz-stepper-circle");

      if (itemNum < num) {
        item.classList.add("completed");
        circle.innerHTML = '<i class="bi bi-check-lg"></i>';
      } else if (itemNum === num) {
        item.classList.add("active");
        circle.textContent = itemNum;
      } else {
        circle.textContent = itemNum;
      }
    });
    lines.forEach((line, i) => {
      line.classList.remove("completed", "active");
      if (i < num - 1) line.classList.add("completed");
      else if (i === num - 1) line.classList.add("active");
    });
  }

  /* ============================================================
     VEHICLE SELECTION
     ============================================================ */
  let highlightedIndex = -1;
  let filteredBrands = [];
  let filteredModels = [];

  function highlightMatch(text, query) {
    if (!query) return esc(text);
    const q = query.toLowerCase();
    const idx = text.toLowerCase().indexOf(q);
    if (idx === -1) return esc(text);
    const before = text.slice(0, idx);
    const match = text.slice(idx, idx + q.length);
    const after = text.slice(idx + q.length);
    return esc(before) + '<span class="dz-car-item-match">' + esc(match) + '</span>' + esc(after);
  }

  function renderSuggestions(query) {
    const container = $("#dz-car-dropdown");
    highlightedIndex = -1;
    filteredModels = [];
    filteredBrands = [];

    if (!container) return;

    if (!query || query.length < 1) {
      /* Browse mode: show all brands grouped by first letter */
      const groups = {};
      for (const brand of CAR_BRANDS) {
        const letter = brand.name.charAt(0).toUpperCase();
        if (!groups[letter]) groups[letter] = [];
        groups[letter].push(brand);
      }
      const sortedLetters = Object.keys(groups).sort();
      let html = "";
      let idx = 0;
      for (const letter of sortedLetters) {
        html += `<div class="dz-car-letter-header">${letter}</div>`;
        for (const brand of groups[letter]) {
          const logoHtml = brand.logo
            ? `<img src="${brand.logo}" alt="${esc(brand.name)}" class="dz-car-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="dz-car-item-icon" style="display:none"><i class="bi bi-car-front-fill"></i></div>`
            : `<div class="dz-car-item-icon"><i class="bi bi-car-front-fill"></i></div>`;
          html += `
          <div class="dz-car-item" data-index="${idx}" data-brand="${esc(brand.name)}">
            ${logoHtml}
            <div class="dz-car-item-name">${esc(brand.name)}</div>
          </div>`;
          idx++;
        }
      }
      filteredBrands = CAR_BRANDS.slice();
      container.innerHTML = html;
      container.classList.remove("d-none");
      container.querySelectorAll(".dz-car-item").forEach((item) => {
        item.addEventListener("click", () => selectBrand(item.dataset.brand));
      });
      return;
    }

    /* Smart search: search models + brands */
    const modelResults = searchModels(query);
    const q = query.toLowerCase();

    /* Also find brand-only matches */
    const brandMatches = [];
    for (const brand of CAR_BRANDS) {
      if (brand.name.toLowerCase().includes(q)) {
        brandMatches.push(brand);
      }
    }

    if (modelResults.length === 0 && brandMatches.length === 0) {
      container.classList.add("d-none");
      container.innerHTML = "";
      return;
    }

    let html = "";
    let idx = 0;

    /* Render model matches */
    if (modelResults.length > 0) {
      html += `<div class="dz-car-section-header">Models</div>`;
      for (const entry of modelResults) {
        const imgSrc = getVehicleImageUrl(entry.brand, entry.model) || entry.image;
        const vehicleImgHtml = imgSrc
          ? `<img src="${esc(imgSrc)}" alt="${esc(entry.brand)} ${esc(entry.model)}" class="dz-car-item-vehicle-img" loading="lazy" onerror="this.style.display='none'">`
          : "";
        const logoHtml = entry.logo
          ? `<img src="${entry.logo}" alt="${esc(entry.brand)}" class="dz-car-logo-img" onerror="this.style.display='none'">`
          : "";
        html += `
        <div class="dz-car-item dz-car-item--model" data-index="${idx}" data-brand="${esc(entry.brand)}" data-model="${esc(entry.model)}">
          <div class="dz-car-item-left">
            <div class="dz-car-item-logo">${logoHtml}</div>
            <div class="dz-car-item-info">
              <div class="dz-car-item-brand">${highlightMatch(entry.brand, query)}</div>
              <div class="dz-car-item-model">${highlightMatch(entry.model, query)}</div>
            </div>
          </div>
          <div class="dz-car-item-vehicle">${vehicleImgHtml}</div>
        </div>`;
        idx++;
      }
      filteredModels = modelResults;
    }

    /* Render brand-only matches (if they weren't already shown via model results) */
    if (brandMatches.length > 0 && modelResults.length === 0) {
      html += `<div class="dz-car-section-header">Brands</div>`;
      for (const brand of brandMatches.slice(0, 6)) {
        const logoHtml = brand.logo
          ? `<img src="${brand.logo}" alt="${esc(brand.name)}" class="dz-car-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="dz-car-item-icon" style="display:none"><i class="bi bi-car-front-fill"></i></div>`
          : `<div class="dz-car-item-icon"><i class="bi bi-car-front-fill"></i></div>`;
        html += `
        <div class="dz-car-item" data-index="${idx}" data-brand="${esc(brand.name)}">
          ${logoHtml}
          <div class="dz-car-item-name">${highlightMatch(brand.name, query)}</div>
        </div>`;
        idx++;
      }
      filteredBrands = brandMatches.slice(0, 6);
    }

    container.innerHTML = html;
    container.classList.remove("d-none");

    /* Click handlers for model items */
    container.querySelectorAll(".dz-car-item--model").forEach((item) => {
      item.addEventListener("click", () => {
        const brand = item.dataset.brand;
        const model = item.dataset.model;
        /* Select brand first, then auto-select model */
        selectBrand(brand);
        /* Find and click the model card */
        setTimeout(() => {
          const modelCard = document.querySelector(`.dz-car-model-card[data-model="${model}"]`);
          if (modelCard) {
            document.querySelectorAll(".dz-car-model-card").forEach(c => c.classList.remove("selected"));
            modelCard.classList.add("selected");
          }
          chooseModel(brand, model);
        }, 50);
      });
    });

    /* Click handlers for brand-only items */
    container.querySelectorAll(".dz-car-item:not(.dz-car-item--model)").forEach((item) => {
      item.addEventListener("click", () => selectBrand(item.dataset.brand));
    });

    /* Auto-select if exactly one unique model match */
    if (modelResults.length === 1 && brandMatches.length === 0) {
      const only = modelResults[0];
      const input = $("#dz-car-input");
      if (input && normalizeModel(input.value) === only._norm) {
        /* Unique exact match — auto-select */
        selectBrand(only.brand);
        setTimeout(() => {
          const modelCard = document.querySelector(`.dz-car-model-card[data-model="${only.model}"]`);
          if (modelCard) {
            document.querySelectorAll(".dz-car-model-card").forEach(c => c.classList.remove("selected"));
            modelCard.classList.add("selected");
          }
          chooseModel(only.brand, only.model);
        }, 50);
      }
    }
  }

  function selectBrand(brandName) {
    state.vehicle.brand = brandName;
    state.vehicle.model = "";

    /* Create the persistence session on the user's first real action (picking a
       brand) so visiting /diagnose without doing anything never leaves an empty
       session behind. */
    if (!state.sessionId) createSession();

    const brand = CAR_BRANDS.find((b) => b.name === brandName);
    const models = brand ? brand.models : [];
    const logo = brand ? brand.logo : null;

    /* Update UI — hide search/brands, show selected card */
    const input = $("#dz-car-input");
    if (input) input.value = "";
    const suggestions = $("#dz-car-suggestions");
    if (suggestions) { suggestions.classList.add("d-none"); suggestions.innerHTML = ""; }
    const dropdown = $("#dz-car-dropdown");
    if (dropdown) dropdown.classList.add("d-none");

    /* Hide brands section and search bar */
    const brandsSection = $("#dz-brands-section");
    if (brandsSection) brandsSection.style.display = "none";
    const searchBar = $("#dz-car-search");
    if (searchBar) searchBar.style.display = "none";

    /* Hide any vehicle validation */
    const vMsg = $("#dz-vehicle-validation");
    if (vMsg) vMsg.classList.add("d-none");

    /* Mark selected brand in grid */
    $$("#dz-brands-grid .dz-brand-card").forEach(c => {
      c.classList.toggle("selected", c.dataset.brand === brandName);
    });

    /* Show selected card with logo */
    const selectedEl = $("#dz-car-selected");
    if (selectedEl) selectedEl.classList.remove("d-none");
    const selectedIconEl = $("#dz-car-selected-icon");
    if (selectedIconEl) {
      selectedIconEl.style.background = brandGradient(brandName);
      if (logo) {
        selectedIconEl.innerHTML = `<img src="${logo}" alt="${esc(brandName)}" class="dz-car-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="dz-car-icon-fallback" style="display:none"><i class="bi bi-car-front-fill"></i></div>`;
      } else {
        selectedIconEl.innerHTML = `<div class="dz-car-icon-fallback"><i class="bi bi-car-front-fill"></i></div>`;
      }
    }
    const brandEl = $("#dz-car-selected-brand");
    if (brandEl) brandEl.textContent = brandName;
    const modelEl = $("#dz-car-selected-model");
    if (modelEl) modelEl.textContent = "";
    const engEl = $("#dz-car-selected-engine");
    if (engEl) { engEl.textContent = ""; engEl.classList.add("d-none"); }

    /* Clear the previous vehicle's photo — a model isn't chosen yet, so media
       from the prior vehicle must not linger when switching brands (item 4). */
    const selImg = $("#dz-selected-image");
    if (selImg) selImg.innerHTML = '<i class="bi bi-car-front-fill"></i>';
    updateInfoPanelVehicleImage("", "");

    /* Enable Continue button */
    const continueBtn = $("#dz-continue-vehicle");
    if (continueBtn) continueBtn.classList.remove("dz-btn-locked");

    /* Render the curated models instantly, then enrich from the live API so the
       full model catalogue for the brand is available (filtered by brand). */
    const modelsEl = $("#dz-car-models");
    if (modelsEl) modelsEl.classList.remove("d-none");
    renderModelGrid(brandName, logo, models);
    loadLiveModels(brandName, logo, models);
  }

  /* Render the model cards for a brand and wire selection.
     imgMap (optional): live model-name -> image URL resolved server-side by the
     exact make/model slug, so live models also show their correct shipped image. */
  function renderModelGrid(brandName, logo, models, imgMap) {
    const modelsEl = $("#dz-car-models");
    const grid = $("#dz-car-models-grid");
    if (!grid) return;
    if (!models.length) { if (modelsEl) modelsEl.classList.add("d-none"); return; }
    if (modelsEl) modelsEl.classList.remove("d-none");
    grid.innerHTML = models.map((m) => {
      /* Fetch each model's image from the vehicle-image API so every card is
         accurate for THAT model, falling back to the shipped local image and
         finally an icon (dzImgFallback). Never show another model's image. */
      const local = getModelImage(brandName, m) || (imgMap && imgMap[m]) || "";
      const primary = getVehicleImageUrl(brandName, m) || local;
      const modelImageHtml = primary
        ? `<div class="dz-model-img-wrap"><img src="${esc(primary)}" data-local="${esc(local)}" alt="${esc(brandName)} ${esc(m)}" class="dz-model-img" loading="lazy" onerror="dzImgFallback(this)"><div class="dz-model-img-fallback"><i class="bi bi-car-front-fill"></i></div></div>`
        : `<div class="dz-model-img-wrap dz-model-img-no"><div class="dz-model-img-fallback dz-model-img-fallback--visible"><i class="bi bi-car-front-fill"></i></div></div>`;
      const logoHtml = logo
        ? `<img src="${logo}" alt="${esc(brandName)}" class="dz-model-logo" onerror="this.style.display='none'">`
        : "";
      return `
      <div class="dz-car-model-card${state.vehicle.model === m ? " selected" : ""}" data-model="${esc(m)}">
        ${modelImageHtml}
        <div class="dz-model-card-footer">
          ${logoHtml}
          <span class="dz-car-model-name">${esc(m)}</span>
        </div>
      </div>`;
    }).join("");
    grid.querySelectorAll(".dz-car-model-card").forEach((card) => {
      card.addEventListener("click", () => {
        grid.querySelectorAll(".dz-car-model-card").forEach((c) => c.classList.remove("selected"));
        card.classList.add("selected");
        chooseModel(brandName, card.dataset.model);
      });
    });
  }

  /* Fetch the full live model list for a brand and merge with curated ones. */
  async function loadLiveModels(brandName, logo, curated) {
    let live = [];
    try {
      live = await VehicleAPI.models(brandName, "");
    } catch (_) {
      return;  /* keep curated on failure */
    }
    if (state.vehicle.brand !== brandName) return;  /* user changed brand meanwhile */
    if (!live.length) return;
    const merged = [];
    const seen = new Set();
    const imgMap = {};  /* model name -> server-resolved image URL */
    for (const x of live) { if (x && x.value && x.image) imgMap[x.value] = x.image; }
    for (const m of curated.concat(live.map((x) => x.value))) {
      const key = normalizeModel(m);
      if (key && !seen.has(key)) { seen.add(key); merged.push(m); }
    }
    renderModelGrid(brandName, logo, merged, imgMap);
  }

  function updateSelectedVehicleImage(brand, model) {
    const imgWrap = $("#dz-selected-image");
    if (!imgWrap) return;
    const local = getModelImage(brand, model);
    const primary = getVehicleImageUrl(brand, model, state.vehicle.year) || local;
    if (primary) {
      imgWrap.innerHTML = `<img src="${esc(primary)}" data-local="${esc(local || "")}" alt="${esc(brand)} ${esc(model)}" class="dz-selected-vehicle-img" onerror="dzImgFallback(this)"><div class="dz-selected-img-fallback"><i class="bi bi-car-front-fill"></i></div>`;
    } else {
      imgWrap.innerHTML = `<div class="dz-selected-img-fallback dz-selected-img-fallback--visible"><i class="bi bi-car-front-fill"></i></div>`;
    }
  }

  /* Update the "Why select your vehicle?" info panel image */
  function updateInfoPanelVehicleImage(brand, model) {
    const img = $("#dz-info-vehicle-img");
    const fallback = $("#dz-info-vehicle-fallback");
    if (!img || !fallback) return;
    const local = getModelImage(brand, model);
    const imgSrc = getVehicleImageUrl(brand, model, state.vehicle.year) || local;
    if (imgSrc) {
      img.setAttribute("data-local", local || "");
      img.src = imgSrc;
      img.alt = (brand || "vehicle") + " " + (model || "");
      img.onload = function() {
        img.style.display = "";
        img.classList.add("loaded");
        fallback.classList.add("hidden");
      };
      img.onerror = function() {
        const lc = img.getAttribute("data-local");
        if (lc && img.getAttribute("src") !== lc) {
          img.removeAttribute("data-local");
          img.src = lc;
          return;
        }
        img.style.display = "none";
        img.classList.remove("loaded");
        fallback.classList.remove("hidden");
      };
      img.style.display = "";
    } else {
      img.style.display = "none";
      img.classList.remove("loaded");
      fallback.classList.remove("hidden");
    }
  }

  /* ============================================================
     VIN LOOKUP — decode a 17-char VIN into a vehicle (NHTSA vPIC)
     ============================================================ */
  function applyDecodedVehicle(d) {
    const brand = d.make || "";
    const model = d.model || "";
    state.vehicle.brand = brand;
    state.vehicle.model = model;
    state.vehicle.engine = d.engine || "";
    state.vehicle.year = d.year || "";
    if (!state.sessionId) createSession();

    const known = CAR_BRANDS.find((b) => b.name === brand);
    if (known) {
      selectBrand(brand);   /* renders the selected card + logo (also resets model) */
    } else {
      /* Unlisted brand — render the selected card manually. */
      const brandsSection = $("#dz-brands-section");
      if (brandsSection) brandsSection.style.display = "none";
      const searchBar = $("#dz-car-search");
      if (searchBar) searchBar.style.display = "none";
      const selectedEl = $("#dz-car-selected");
      if (selectedEl) selectedEl.classList.remove("d-none");
      const brandEl = $("#dz-car-selected-brand");
      if (brandEl) brandEl.textContent = brand;
      const iconEl = $("#dz-car-selected-icon");
      if (iconEl) {
        iconEl.innerHTML = d.logo
          ? `<img src="${esc(d.logo)}" alt="${esc(brand)}" class="dz-car-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="dz-car-icon-fallback" style="display:none"><i class="bi bi-car-front-fill"></i></div>`
          : `<div class="dz-car-icon-fallback"><i class="bi bi-car-front-fill"></i></div>`;
      }
    }

    /* Fill in the exact model + engine from the VIN and hide the model grid. */
    state.vehicle.model = model;
    const modelEl = $("#dz-car-selected-model");
    if (modelEl) modelEl.textContent = model;
    const engEl = $("#dz-car-selected-engine");
    if (engEl && state.vehicle.engine) {
      engEl.textContent = state.vehicle.engine;
      engEl.classList.remove("d-none");
    }
    const modelsEl = $("#dz-car-models");
    if (modelsEl) modelsEl.classList.add("d-none");

    updateSelectedVehicleImage(brand, model);
    updateInfoPanelVehicleImage(brand, model);
    const cont = $("#dz-continue-vehicle");
    if (cont) cont.classList.remove("dz-btn-locked");
    updateVehicleBadge();
    scheduleSave();
  }

  /* ============================================================
     IDENTIFY VEHICLE FROM A PHOTO — reuses the existing
     /api/vehicle/identify-image endpoint (car_database module) and the
     VIN-lookup's applyDecodedVehicle() to fill in the vehicle selector.
     ============================================================ */
  const DZ_PHOTO_CONFIDENCE_THRESHOLD = 0.6;

  function matchKnownBrand(name) {
    if (!name) return null;
    const n = String(name).trim().toLowerCase();
    return CAR_BRANDS.find((b) => b.name.toLowerCase() === n) || null;
  }

  function applyPhotoDetectedVehicle(result) {
    const known = matchKnownBrand(result.manufacturer);
    applyDecodedVehicle({
      make: known ? known.name : (result.manufacturer || ""),
      model: result.model || "",
      year: result.year || "",
      logo: known ? known.logo : null,
    });
    if (window.CS && CS.toast) {
      CS.toast("success", "Vehicle detected",
        [result.manufacturer, result.model].filter(Boolean).join(" ") || "Vehicle selected.");
    }
  }

  function initPhotoDetectVehicle() {
    const zone = $("#dz-photo-detect-zone");
    const input = $("#dz-photo-detect-input");
    const status = $("#dz-photo-detect-status");
    const title = $("#dz-photo-detect-title");
    const hint = $("#dz-photo-detect-hint");
    if (!zone || !input) return;

    const defaultTitle = title ? title.textContent : "Upload Car Image";
    const defaultHint = hint ? hint.textContent : "";

    function setStatus(html) {
      if (!status) return;
      if (!html) { status.classList.add("d-none"); status.innerHTML = ""; return; }
      status.classList.remove("d-none");
      status.innerHTML = html;
    }

    function setBusy(busy) {
      zone.classList.toggle("dz-photo-detect-busy", busy);
      if (title) title.textContent = busy ? "Analyzing photo…" : defaultTitle;
      if (hint) hint.textContent = busy ? "Detecting the brand and model…" : defaultHint;
    }

    async function analyze(file) {
      if (!file || !file.type || file.type.indexOf("image/") !== 0) {
        if (window.CS && CS.toast) CS.toast("warning", "Invalid file", "Please choose an image.");
        return;
      }
      setBusy(true);
      setStatus("");
      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/api/vehicle/identify-image", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) {
          if (window.CS && CS.toast) CS.toast("error", "Detection failed", data.error || "Please try again.");
          return;
        }
        if (data.unavailable || (!data.manufacturer && !data.model)) {
          if (window.CS && CS.toast) {
            CS.toast("warning", "Couldn't identify the vehicle", "Please select it manually below.");
          }
          return;
        }
        const confidence = typeof data.confidence === "number" ? data.confidence : 0;
        if (confidence >= DZ_PHOTO_CONFIDENCE_THRESHOLD) {
          applyPhotoDetectedVehicle(data);
        } else {
          const label = [data.manufacturer, data.model].filter(Boolean).join(" ") || "vehicle";
          setStatus(`
            <div class="d-flex align-items-center gap-2 flex-wrap">
              <span>Detected: <strong>${esc(label)}</strong> (${Math.round(confidence * 100)}% confidence)</span>
              <button class="dz-btn-outline-sm" type="button" id="dz-photo-detect-confirm"><i class="bi bi-check2"></i> Use this</button>
              <button class="dz-btn-outline-sm" type="button" id="dz-photo-detect-retry"><i class="bi bi-arrow-repeat"></i> Try another</button>
            </div>`);
          $("#dz-photo-detect-confirm")?.addEventListener("click", () => {
            applyPhotoDetectedVehicle(data);
            setStatus("");
          });
          $("#dz-photo-detect-retry")?.addEventListener("click", () => {
            setStatus("");
            input.click();
          });
        }
      } catch (_) {
        if (window.CS && CS.toast) CS.toast("error", "Detection failed", "Please try again.");
      } finally {
        setBusy(false);
        input.value = "";
      }
    }

    zone.addEventListener("click", () => input.click());
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) analyze(e.dataTransfer.files[0]);
    });
    input.addEventListener("change", () => {
      if (input.files && input.files[0]) analyze(input.files[0]);
    });
  }

  function initVinLookup() {
    const input = $("#dz-vin-input");
    const btn = $("#dz-vin-btn");
    const msg = $("#dz-vin-msg");
    if (!input || !btn) return;

    function showMsg(text, kind) {
      if (!msg) return;
      msg.textContent = text;
      msg.className = "dz-vin-msg " + kind;
    }

    async function lookup() {
      const vin = (input.value || "").trim().toUpperCase();
      if (vin.length !== 17) {
        showMsg("A VIN is exactly 17 characters (letters and numbers). Please check and try again.", "error");
        return;
      }
      btn.disabled = true;
      const orig = btn.innerHTML;
      btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Looking up…';
      showMsg("Looking up your vehicle…", "success");
      try {
        const res = await fetch("/api/vehicles/vin?vin=" + encodeURIComponent(vin));
        const data = await res.json();
        if (data && data.ok) {
          applyDecodedVehicle(data);
          const label = [data.year, data.make, data.model].filter(Boolean).join(" ");
          showMsg("Found your car: " + label + ". You can fine-tune the details below if needed.", "success");
        } else {
          showMsg((data && data.message) || "We couldn't find that VIN. Please pick your car manually.", "error");
        }
      } catch (e) {
        showMsg("Something went wrong looking up your VIN. Please try again, or pick your car manually.", "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    }

    btn.addEventListener("click", lookup);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); lookup(); }
    });
    /* Keep only valid VIN characters, uppercased, as the user types. */
    input.addEventListener("input", () => {
      const clean = input.value.toUpperCase().replace(/[^A-HJ-NPR-Z0-9]/g, "");
      if (clean !== input.value) input.value = clean;
    });
  }

  /* ============================================================
     ENGINE CASCADE — third autocomplete level (brand -> model -> engine)
     ============================================================ */
  let _engineItems = [];

  function chooseModel(brandName, model) {
    state.vehicle.model = model;
    state.vehicle.engine = "";
    const mEl = $("#dz-car-selected-model");
    if (mEl) mEl.textContent = model;
    const eLine = $("#dz-car-selected-engine");
    if (eLine) { eLine.textContent = ""; eLine.classList.add("d-none"); }
    updateSelectedVehicleImage(brandName, model);
    updateInfoPanelVehicleImage(brandName, model);
    loadEngines(brandName, model);
    /* Reveal the model-year selector once a model is chosen. */
    const yearWrap = $("#dz-car-year");
    if (yearWrap) yearWrap.classList.remove("d-none");
    if (typeof scheduleSave === "function") scheduleSave();
  }

  /* Model year → makes the diagnosis + image specific to that year. */
  function initYearSelect() {
    const sel = $("#dz-year-select");
    if (!sel) return;
    sel.addEventListener("change", () => {
      state.vehicle.year = sel.value || "";
      /* Re-fetch the image for the chosen year and update every image slot. */
      updateSelectedVehicleImage(state.vehicle.brand, state.vehicle.model);
      updateInfoPanelVehicleImage(state.vehicle.brand, state.vehicle.model);
      updateVehicleBadge();
      if (typeof scheduleSave === "function") scheduleSave();
    });
  }

  async function loadEngines(brand, model) {
    const wrap = $("#dz-car-engines");
    const input = $("#dz-engine-input");
    const list = $("#dz-engine-suggestions");
    if (!wrap || !list) return;
    wrap.classList.remove("d-none");
    if (input) input.value = "";
    list.innerHTML = '<div class="dz-engine-loading"><span class="dz-spinner"></span> Loading engine options…</div>';
    try {
      _engineItems = await VehicleAPI.engines(brand, model, "");
    } catch (_) {
      _engineItems = [];
    }
    renderEngineOptions("");
  }

  function renderEngineOptions(query) {
    const list = $("#dz-engine-suggestions");
    if (!list) return;
    const q = (query || "").trim().toLowerCase();
    const items = q
      ? _engineItems.filter((e) => (e.label || e.value || "").toLowerCase().includes(q))
      : _engineItems;
    if (!items.length) {
      list.innerHTML = '<div class="dz-engine-empty">No engine matches — you can type your own and press Enter.</div>';
      return;
    }
    list.innerHTML = items
      .map(
        (e) => `
        <button type="button" class="dz-engine-chip${state.vehicle.engine === (e.value || e.label) ? " selected" : ""}"
                data-engine="${esc(e.value || e.label)}">
          <i class="bi bi-fuel-pump"></i>
          <span>${esc(e.label || e.value)}</span>
        </button>`
      )
      .join("");
    list.querySelectorAll(".dz-engine-chip").forEach((chip) => {
      chip.addEventListener("click", () => selectEngine(chip.dataset.engine));
    });
  }

  function selectEngine(value) {
    value = (value || "").trim();
    state.vehicle.engine = value;
    const eLine = $("#dz-car-selected-engine");
    if (eLine) {
      eLine.textContent = value;
      eLine.classList.toggle("d-none", !value);
    }
    const list = $("#dz-engine-suggestions");
    if (list) {
      list.querySelectorAll(".dz-engine-chip").forEach((c) =>
        c.classList.toggle("selected", c.dataset.engine === value)
      );
    }
    if (typeof scheduleSave === "function") scheduleSave();
  }

  function initEngineInput() {
    const input = $("#dz-engine-input");
    if (!input) return;
    input.addEventListener("input", debounce(() => renderEngineOptions(input.value), 120));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const typed = input.value.trim();
        if (typed) selectEngine(typed);
      }
    });
  }

  function resetVehicleSelection() {
    state.vehicle = { brand: "", model: "", engine: "", year: "" };
    _engineItems = [];
    const enginesWrap = $("#dz-car-engines");
    if (enginesWrap) enginesWrap.classList.add("d-none");
    /* Reset + hide the year selector for the new vehicle. */
    const yearWrap = $("#dz-car-year");
    if (yearWrap) yearWrap.classList.add("d-none");
    const yearSel = $("#dz-year-select");
    if (yearSel) yearSel.value = "";

    /* Hide selected card and models */
    const selectedEl = $("#dz-car-selected");
    if (selectedEl) selectedEl.classList.add("d-none");
    const modelsEl = $("#dz-car-models");
    if (modelsEl) modelsEl.classList.add("d-none");

    /* Clear the selected-vehicle photo so it never carries over (item 4). */
    const selImg = $("#dz-selected-image");
    if (selImg) selImg.innerHTML = '<i class="bi bi-car-front-fill"></i>';

    /* Show brands section and search bar */
    const brandsSection = $("#dz-brands-section");
    if (brandsSection) brandsSection.style.display = "";
    const searchBar = $("#dz-car-search");
    if (searchBar) searchBar.style.display = "";

    /* Clear search input */
    const input = $("#dz-car-input");
    if (input) input.value = "";
    const suggestions = $("#dz-car-suggestions");
    if (suggestions) { suggestions.classList.add("d-none"); suggestions.innerHTML = ""; }
    const dropdown = $("#dz-car-dropdown");
    if (dropdown) dropdown.classList.add("d-none");

    /* Lock continue button */
    const continueBtn = $("#dz-continue-vehicle");
    if (continueBtn) continueBtn.classList.add("dz-btn-locked");

    /* Clear selected brand in grid */
    $$("#dz-brands-grid .dz-brand-card").forEach(c => c.classList.remove("selected"));

    /* Hide vehicle validation */
    const vMsg = $("#dz-vehicle-validation");
    if (vMsg) vMsg.classList.add("d-none");

    /* Reset info panel image */
    updateInfoPanelVehicleImage("", "");
  }

  /* Append live vPIC makes (beyond the curated list) to the search dropdown so
     every car make is findable by typing, not just via "View all brands". */
  const augmentWithLiveMakes = debounce(async (query) => {
    const q = (query || "").trim();
    if (q.length < 2) return;
    let makes = [];
    try { makes = await VehicleAPI.makes(q, 8); } catch (_) { return; }
    const input = $("#dz-car-input");
    if (!input || input.value.trim() !== q) return;   /* stale query */
    const container = $("#dz-car-suggestions");
    if (!container) return;
    const shown = new Set(
      Array.from(container.querySelectorAll(".dz-car-item"))
        .map((el) => (el.dataset.brand || "").toLowerCase())
    );
    const extra = makes.filter((m) => {
      const n = (m.value || m.label || "").toLowerCase();
      return n && !shown.has(n);
    });
    if (!extra.length) return;
    let html = `<div class="dz-car-section-header">More brands</div>`;
    for (const m of extra) {
      const name = m.value || m.label;
      const logoHtml = m.logo
        ? `<img src="${m.logo}" alt="${esc(name)}" class="dz-car-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="dz-car-item-icon" style="display:none"><i class="bi bi-car-front-fill"></i></div>`
        : `<div class="dz-car-item-icon"><i class="bi bi-car-front-fill"></i></div>`;
      html += `
      <div class="dz-car-item dz-car-item--live" data-brand="${esc(name)}">
        ${logoHtml}
        <div class="dz-car-item-name">${esc(name)}</div>
      </div>`;
    }
    container.insertAdjacentHTML("beforeend", html);
    container.classList.remove("d-none");
    container.querySelectorAll(".dz-car-item--live").forEach((item) => {
      if (item.dataset.wired) return;
      item.dataset.wired = "1";
      item.addEventListener("click", () => selectBrand(item.dataset.brand));
    });
  }, 300);

  function initVehicleSearch() {
    const input = $("#dz-car-input");
    const dropdown = $("#dz-car-dropdown");
    const clearBtn = $("#dz-car-clear");

    if (!input) return;

    /* Live search */
    input.addEventListener("input", () => {
      const val = input.value.trim();
      if (clearBtn) clearBtn.classList.toggle("d-none", !val);
      if (val.length >= 1) {
        renderSuggestions(val);
        augmentWithLiveMakes(val);   /* find makes beyond the curated list */
      } else {
        /* Empty: show all brands grouped by letter */
        renderSuggestions("");
      }
    });

    /* Clear button */
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        input.value = "";
        clearBtn.classList.add("d-none");
        if (dropdown) { dropdown.classList.add("d-none"); dropdown.innerHTML = ""; }
        input.focus();
      });
    }

    /* Keyboard navigation */
    input.addEventListener("keydown", (e) => {
      if (!dropdown) return;
      const items = dropdown.querySelectorAll(".dz-car-item");
      if (items.length === 0) {
        if (e.key === "Escape") { dropdown.classList.add("d-none"); }
        return;
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
        updateHighlight(items);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        highlightedIndex = Math.max(highlightedIndex - 1, 0);
        updateHighlight(items);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < items.length) {
          const item = items[highlightedIndex];
          if (item.dataset.model) {
            /* Model item — select brand then auto-select model */
            selectBrand(item.dataset.brand);
            setTimeout(() => {
              const modelCard = document.querySelector(`.dz-car-model-card[data-model="${item.dataset.model}"]`);
              if (modelCard) {
                document.querySelectorAll(".dz-car-model-card").forEach(c => c.classList.remove("selected"));
                modelCard.classList.add("selected");
                state.vehicle.model = item.dataset.model;
                const mEl = $("#dz-car-selected-model");
                if (mEl) mEl.textContent = item.dataset.model;
                updateSelectedVehicleImage(item.dataset.brand, item.dataset.model);
                updateInfoPanelVehicleImage(item.dataset.brand, item.dataset.model);
              }
            }, 50);
          } else {
            selectBrand(item.dataset.brand);
          }
        }
      } else if (e.key === "Escape") {
        dropdown.classList.add("d-none");
        highlightedIndex = -1;
      }
    });

    /* Close dropdown on outside click */
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#dz-search-bar")) {
        if (dropdown) dropdown.classList.add("d-none");
        highlightedIndex = -1;
      }
    });

    /* Change vehicle button */
    const changeBtn = $("#dz-car-change");
    if (changeBtn) changeBtn.addEventListener("click", resetVehicleSelection);
  }

  function updateHighlight(items) {
    items.forEach((item, i) => {
      item.classList.toggle("highlighted", i === highlightedIndex);
    });
    if (highlightedIndex >= 0 && items[highlightedIndex]) {
      items[highlightedIndex].scrollIntoView({ block: "nearest" });
    }
  }

  /* ---- Render brands grid (popular by default; ALL makes on demand) ---- */
  let _showAllBrands = false;
  let _allBrandsList = null;   /* curated ∪ live vPIC makes, cached */

  function brandCardHtml(brand) {
    const logoHtml = brand.logo
      ? `<img src="${brand.logo}" alt="${esc(brand.name)}" class="dz-car-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="dz-brand-card-fallback" style="display:none"><i class="bi bi-car-front-fill"></i></div>`
      : `<div class="dz-brand-card-fallback"><i class="bi bi-car-front-fill"></i></div>`;
    return `
      <div class="dz-brand-card" data-brand="${esc(brand.name)}">
        <div class="dz-brand-card-icon">${logoHtml}</div>
        <div class="dz-brand-card-name">${esc(brand.name)}</div>
      </div>`;
  }

  function renderBrandList(list) {
    const grid = $("#dz-brands-grid");
    if (!grid) return;
    grid.innerHTML = list.map(brandCardHtml).join("");
    grid.querySelectorAll(".dz-brand-card").forEach((card) => {
      card.addEventListener("click", () => selectBrand(card.dataset.brand));
    });
  }

  function renderBrandGrid() {
    _showAllBrands = false;
    renderBrandList(CAR_BRANDS.slice(0, 12));
  }

  /* Merge the curated brands (with logos + model lists) with the FULL live vPIC
     make catalogue so every car make is selectable. Cached after first load. */
  async function ensureAllBrands() {
    if (_allBrandsList) return _allBrandsList;
    let live = [];
    try { live = await VehicleAPI.makes("", 600); } catch (_) { live = []; }
    const seen = new Set(CAR_BRANDS.map((b) => b.name.toLowerCase()));
    const merged = CAR_BRANDS.slice();
    for (const it of live) {
      const name = (it.value || it.label || "").trim();
      if (name && !seen.has(name.toLowerCase())) {
        seen.add(name.toLowerCase());
        merged.push({ name: name, logo: it.logo || null, models: [] });
      }
    }
    merged.sort((a, b) => a.name.localeCompare(b.name));
    _allBrandsList = merged;
    return merged;
  }

  /* Wire the "View all brands" toggle — now loads EVERY make from the live API. */
  function initViewAllBrands() {
    const btn = $("#dz-brands-view-all");
    const title = document.querySelector(".dz-brands-title");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      _showAllBrands = !_showAllBrands;
      if (_showAllBrands) {
        btn.disabled = true;
        btn.innerHTML = 'Loading… <i class="bi bi-hourglass-split"></i>';
        const all = await ensureAllBrands();
        renderBrandList(all);
        btn.disabled = false;
        btn.innerHTML = 'Show popular only <i class="bi bi-arrow-up"></i>';
        if (title) title.textContent = 'All Brands (' + all.length + ')';
      } else {
        renderBrandGrid();
        btn.innerHTML = 'View all brands <i class="bi bi-arrow-right"></i>';
        if (title) title.textContent = 'Popular Brands';
      }
    });
  }

  /* ---- Init ---- */
  function init() {
    renderBrandGrid();
    initViewAllBrands();
    /* Wire the previously-dead "Need help?" button to actual guidance (item 4). */
    const helpBtn = $("#dz-vehicle-help");
    if (helpBtn) {
      helpBtn.addEventListener("click", () => {
        if (window.CS && CS.toast) {
          CS.toast("info", "Choosing your vehicle",
            "Type your brand or model in the search box, or tap a brand below. Then pick your model — we'll tailor the diagnosis to that exact car.");
        }
      });
    }
    initVehicleSearch();
    initPhotoDetectVehicle();
    initYearSelect();
    /* item 2: VIN lookup is gated off — hide the section and skip its wiring.
       Flip VIN_LOOKUP_ENABLED (top of file) to re-enable; no code was removed. */
    if (VIN_LOOKUP_ENABLED) {
      initVinLookup();
    } else {
      const vinSection = $("#dz-vin-section");
      if (vinSection) vinSection.style.display = "none";
    }
    initEngineInput();
    initVoiceInput();
    initProblemStep();
    initModal();
    initChatModal();

    /* ---- Bind ALL wizard navigation (always, regardless of session restore) ---- */

    /* Vehicle — first step. "Back" leaves the wizard for the diagnoses list
       (there is no longer a welcome splash to return to). */
    $("#dz-back-vehicle").addEventListener("click", () => { window.location.href = "/my-diagnoses"; });
    $("#dz-continue-vehicle").addEventListener("click", () => {
      if (state.vehicle.brand) {
        $("#dz-vehicle-validation").classList.add("d-none");
        updateVehicleBadge();
        showStep("describe");
        scheduleSave();
      } else {
        $("#dz-vehicle-validation").classList.remove("d-none");
      }
    });

    /* Describe */
    $("#dz-back-describe").addEventListener("click", () => showStep("vehicle"));
    $("#dz-continue-describe").addEventListener("click", async () => {
      const val = $("#dz-problem").value.trim();
      if (val.length < 5) {
        $("#dz-problem-validation").classList.remove("d-none");
        return;
      }
      state.problem = val;
      state.notice = ($("#dz-notice").value || "").trim();
      state.category = getSelectedCategory();
      state.when = getSelectedWhen();
      state.where = getSelectedWhere();
      const fullProblem = buildFullProblem();

      /* Detect dialect from user's problem description */
      const dialectResult = await detectDialect(fullProblem);
      /* Apply dialect to the ENTIRE UI — this updates all visible text */
      applyDialect(dialectResult);

      /* Generate questions — server-side for Arabic, client-side for English */
      if (dialectResult.language === "ar" && dialectResult.dialect_confidence > 0.3) {
        const serverQuestions = await fetchServerQuestions(
          fullProblem,
          state.vehicle,
          dialectResult.dialect,
          dialectResult.dialect_confidence,
          dialectResult.detected_terms || [],
          dialectResult.canonical_concepts || [],
          state.category,
          state.when,
          state.where
        );
        if (serverQuestions) {
          state.questions = serverQuestions;
        } else {
          state.questions = getQuestions(fullProblem);
        }
      } else {
        state.questions = getQuestions(fullProblem);
      }
      state.questionIndex = 0;
      state.answers = {};
      showQuestion();
      showStep("questions");
      scheduleSave();
    });

    /* Questions */
    $("#dz-back-q").addEventListener("click", () => {
      if (state.questionIndex > 0) {
        state.questionIndex--;
        showQuestion();
      } else {
        showStep("describe");
      }
    });
    $("#dz-continue-q").addEventListener("click", () => {
      const q = state.questions[state.questionIndex];
      if (q && state.answers[q.key]) {
        state.questionIndex++;
        if (state.questionIndex >= state.questions.length) {
          showStep("image");
        } else {
          showQuestion();
        }
        scheduleSave();
      }
    });

    /* Image & Video */
    $("#dz-back-img").addEventListener("click", () => showStep("questions"));
    $("#dz-skip-img").addEventListener("click", () => {
      showReview();
      scheduleSave();
    });
    $("#dz-continue-img").addEventListener("click", () => {
      showReview();
      scheduleSave();
    });
    $("#dz-upload-zone").addEventListener("click", () => $("#dz-file-input").click());
    $("#dz-file-input").addEventListener("change", handleImage);
    $("#dz-img-remove").addEventListener("click", () => {
      state.image = null;
      state._imageDirty = true;
      $("#dz-file-input").value = "";
      $("#dz-img-preview").style.display = "none";
      $("#dz-upload-zone").style.display = "";
      updateContinueButton();
      scheduleSave();
    });

    /* Video */
    $("#dz-video-zone").addEventListener("click", () => $("#dz-video-input").click());
    $("#dz-video-input").addEventListener("change", handleVideo);
    $("#dz-video-remove").addEventListener("click", () => {
      state.video = null;
      state.videoFile = null;
      state._videoDirty = true;
      $("#dz-video-input").value = "";
      $("#dz-video-preview").style.display = "none";
      $("#dz-video-zone").style.display = "";
      const videoEl = $("#dz-video-thumb");
      if (videoEl) { videoEl.src = ""; videoEl.load(); }
      updateContinueButton();
      scheduleSave();
    });

    /* Drag & drop for photo */
    const zone = $("#dz-upload-zone");
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.style.borderColor = "rgba(var(--accent-rgb), 0.4)"; });
    zone.addEventListener("dragleave", () => { zone.style.borderColor = ""; });
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.style.borderColor = "";
      if (e.dataTransfer.files.length) {
        processImage(e.dataTransfer.files[0]);
      }
    });

    /* Drag & drop for video */
    const videoZone = $("#dz-video-zone");
    videoZone.addEventListener("dragover", (e) => { e.preventDefault(); videoZone.style.borderColor = "rgba(var(--accent-rgb), 0.4)"; });
    videoZone.addEventListener("dragleave", () => { videoZone.style.borderColor = ""; });
    videoZone.addEventListener("drop", (e) => {
      e.preventDefault();
      videoZone.style.borderColor = "";
      if (e.dataTransfer.files.length) {
        processVideo(e.dataTransfer.files[0]);
      }
    });

    /* Review */
    $("#dz-back-review").addEventListener("click", () => showStep("image"));
    $("#dz-continue-review").addEventListener("click", () => {
      showReady();
      scheduleSave();
    });

    /* Ready */
    $("#dz-back-ready").addEventListener("click", () => showStep("review"));
    $("#dz-diagnose").addEventListener("click", runDiagnosis);

    /* New diagnosis */
    $("#dz-new-diag").addEventListener("click", () => {
      state.sessionId = null;
      state.vehicle = { brand: "", model: "", engine: "" };
      state.problem = "";
      state.notice = "";
      state.category = "";
      state.when = "";
      state.where = "";
      state.answers = {};
      state.image = null;
      state.video = null;
      state.videoFile = null;
      state.questionIndex = 0;
      state.questions = [];
      $("#dz-problem").value = "";
      $("#dz-problem-count").textContent = "0";
      $("#dz-problem-validation").classList.add("d-none");
      $("#dz-notice").value = "";
      $("#dz-problem-suggestions").classList.add("d-none");
      $("#dz-problem-suggestions").innerHTML = "";
      $("#dz-problem-voice-recording").classList.add("d-none");
      $("#dz-problem-voice-btn").classList.remove("recording");
      $$(".dz-category-btn").forEach((b) => b.classList.remove("selected"));
      $$(".dz-chip-btn").forEach((b) => b.classList.remove("selected"));
      const probClear = $("#dz-problem-clear");
      if (probClear) probClear.classList.add("d-none");
      $("#dz-file-input").value = "";
      $("#dz-img-preview").style.display = "none";
      $("#dz-upload-zone").style.display = "";
      $("#dz-video-input").value = "";
      $("#dz-video-preview").style.display = "none";
      $("#dz-video-zone").style.display = "";
      const videoEl = $("#dz-video-thumb");
      if (videoEl) { videoEl.src = ""; videoEl.load(); }
      $("#dz-continue-img").style.display = "none";
      $("#dz-skip-img").style.display = "";
      resetVehicleSelection();
      document.title = "AI Diagnosis · Car Service AI";
      _wizIdx = -1;
      _navGuard = true;
      window.history.replaceState({}, "", "/diagnose");
      _navGuard = false;
      showStep("vehicle");
    });

    /* ---- Check for session_id in URL — restore existing session ---- */
    const params = new URLSearchParams(window.location.search);
    const restoreId = params.get("session_id");
    const hashMatch = window.location.hash.match(/^#step-(\w+)$/);
    if (restoreId) {
      loadSession(restoreId, params.get("edit") === "1");
    } else if (!hashMatch) {
      /* Fresh visit with no session and no step hash — open directly on the
         vehicle step (the welcome splash + its duplicate Start button are gone). */
      showStep("vehicle");
    }

    /* ---- Browser Back/Forward handling ---- */
    /* If URL already has a wizard hash on load (e.g. refresh or direct link),
       restore that step immediately. */
    if (hashMatch) {
      const hashStep = hashMatch[1];
      if (WIZARD_STEPS.indexOf(hashStep) >= 0) {
        _wizIdx = WIZARD_STEPS.indexOf(hashStep);
        showStep(hashStep, { _fromPop: true });
      }
    } else if (state.step !== "welcome") {
      /* On first load without hash, push initial wizard state so Back
         can return to a pre-wizard page instead of /about.
         Use replaceState so the initial /diagnose entry becomes
         the first wizard entry (avoids duplicate history). */
      _wizIdx = WIZARD_STEPS.indexOf(state.step);
      if (_wizIdx >= 0) {
        _navGuard = true;
        window.history.replaceState({ wiz: true, idx: _wizIdx }, "", "#step-" + state.step);
        _navGuard = false;
      }
    }

    window.addEventListener("popstate", function (e) {
      if (_navGuard) return;

      /* Back from a modal-open pushState — close the modal */
      if (e.state && e.state.modal) {
        closeModal();
        return;
      }

      /* Back from workspace — hide workspace, restore wizard */
      const workspace = $("#dz-workspace");
      if (workspace && !workspace.classList.contains("d-none")) {
        workspace.classList.add("d-none");
        const wizHeader = $("#dz-wizard-header");
        const mainGrid = $("#dz-main-grid");
        const benefits = $("#dz-benefits");
        if (wizHeader) wizHeader.style.display = "";
        if (mainGrid) mainGrid.style.display = "";
        if (benefits) benefits.style.display = "";
        state.step = "ready";
        return;
      }

      /* If modal is currently open (no modal state, e.g. ESC or close btn),
         just close it */
      const overlay = $("#dz-modal-overlay");
      if (overlay && overlay.classList.contains("open")) {
        closeModal();
        return;
      }

      /* Wizard step navigation via Back/Forward */
      if (e.state && e.state.wiz && typeof e.state.idx === "number") {
        const target = WIZARD_STEPS[e.state.idx];
        if (target && target !== state.step) {
          _navGuard = true;
          showStep(target, { _fromPop: true });
          _navGuard = false;
        }
        return;
      }

      /* If the hash still looks like a wizard step, restore it */
      const hm = window.location.hash.match(/^#step-(\w+)$/);
      if (hm) {
        const s = hm[1];
        if (WIZARD_STEPS.indexOf(s) >= 0 && s !== state.step) {
          _navGuard = true;
          showStep(s, { _fromPop: true });
          _navGuard = false;
        }
        return;
      }

      /* No wizard state — let the browser navigate naturally (to /about, /splash, etc.) */
    }, { passive: false });
  }

  /* ============================================================
     PROBLEM STEP — Enhanced functionality
     ============================================================ */
  let problemSuggIndex = -1;
  /* true while the Quick problem category is auto-managed from the typed problem;
     flips to false once the user clicks a category chip themselves (item 5). */
  let _categoryAuto = true;

  /* Map free-text symptoms to one of the Quick-category chip values
     (engine/brakes/battery/ac/electrical/transmission/suspension/other). */
  const _CATEGORY_RULES = [
    ["transmission", /transmission|gear|gearbox|clutch|shift|slipping|slips|neutral/],
    ["brakes", /brake|brak|rotor|caliper|pedal|abs\b/],
    ["battery", /won.?t start|no.?start|not start|crank|dead battery|jump.?start|battery|alternator|charge|starter/],
    ["ac", /\bac\b|air.?cond|a\/c|climate|heater|blower|vent|compressor|cabin/],
    ["electrical", /light|bulb|headlight|indicator|window|door lock|central lock|horn|fuse|wiring|dashboard|warning light|electr|sensor/],
    ["suspension", /suspension|shock|strut|bounc|bump|steering|wheel|align|pull.*side|wobble|vibrat|shaky ride|tyre|tire/],
    ["engine", /engine|overheat|temperature|coolant|radiat|misfire|stall|idle|rough|knock|oil|smoke|check engine|power loss|hesitat|rev/],
  ];
  function autoDetectCategory(text) {
    const t = (text || "").toLowerCase();
    if (!t.trim()) return "";
    for (const [cat, re] of _CATEGORY_RULES) {
      if (re.test(t)) return cat;
    }
    return "";  /* leave unset rather than guessing "other" */
  }

  /* Select a category chip programmatically (does NOT count as a manual choice). */
  function selectCategoryChip(cat) {
    const buttons = $$(".dz-category-btn");
    buttons.forEach((b) => b.classList.toggle("selected", b.dataset.category === cat));
    if (typeof updateProblemValidation === "function") updateProblemValidation();
  }

  function initProblemStep() {
    const textarea = $("#dz-problem");
    const counter = $("#dz-problem-count");
    const clearBtn = $("#dz-problem-clear");
    const suggestionsEl = $("#dz-problem-suggestions");
    const validationEl = $("#dz-problem-validation");
    const voiceBtn = $("#dz-problem-voice-btn");
    const recordingEl = $("#dz-problem-voice-recording");
    const stopBtn = $("#dz-problem-voice-stop");
    const voiceTextEl = $("#dz-problem-voice-text");
    const continueBtn = $("#dz-continue-describe");

    /* ---- Auto-resize textarea ---- */
    textarea.addEventListener("input", () => {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 300) + "px";
      const len = textarea.value.length;
      counter.textContent = len;
      clearBtn.classList.toggle("d-none", len === 0);
      validationEl.classList.add("d-none");
      updateProblemValidation();
      renderProblemSuggestions(textarea.value.trim());
      /* Auto-select the Quick problem category from the description unless the
         user has already chosen one manually (item 5). */
      if (_categoryAuto) {
        const cat = autoDetectCategory(textarea.value);
        if (cat) selectCategoryChip(cat);
      }
    });

    /* ---- Clear button ---- */
    clearBtn.addEventListener("click", () => {
      textarea.value = "";
      counter.textContent = "0";
      clearBtn.classList.add("d-none");
      suggestionsEl.classList.add("d-none");
      suggestionsEl.innerHTML = "";
      textarea.style.height = "";
      textarea.focus();
      updateProblemValidation();
    });

    /* ---- Problem suggestions keyboard nav ---- */
    textarea.addEventListener("keydown", (e) => {
      const items = suggestionsEl.querySelectorAll(".dz-problem-suggestion");
      if (items.length === 0 || suggestionsEl.classList.contains("d-none")) {
        if (e.key === "Escape") {
          suggestionsEl.classList.add("d-none");
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        problemSuggIndex = Math.min(problemSuggIndex + 1, items.length - 1);
        updateProblemSuggHighlight(items);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        problemSuggIndex = Math.max(problemSuggIndex - 1, 0);
        updateProblemSuggHighlight(items);
      } else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (problemSuggIndex >= 0 && problemSuggIndex < items.length) {
          selectProblemSuggestion(items[problemSuggIndex].dataset.text);
        }
      } else if (e.key === "Escape") {
        suggestionsEl.classList.add("d-none");
        problemSuggIndex = -1;
      }
    });

    /* ---- Close suggestions on outside click ---- */
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".dz-problem-wrap")) {
        suggestionsEl.classList.add("d-none");
        problemSuggIndex = -1;
      }
    });

    /* ---- Category buttons ---- */
    $$(".dz-category-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const wasSelected = btn.classList.contains("selected");
        $$(".dz-category-btn").forEach((b) => b.classList.remove("selected"));
        if (!wasSelected) {
          btn.classList.add("selected");
          _categoryAuto = false;   /* user made an explicit choice — stop auto-detecting */
        } else {
          _categoryAuto = true;    /* deselected — resume auto-detection */
        }
        updateProblemValidation();
      });
    });

    /* ---- When chips ---- */
    $$("#dz-when-chips .dz-chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const wasSelected = btn.classList.contains("selected");
        $$("#dz-when-chips .dz-chip-btn").forEach((b) => b.classList.remove("selected"));
        if (!wasSelected) {
          btn.classList.add("selected");
        }
      });
    });

    /* ---- Where chips ---- */
    $$("#dz-where-chips .dz-chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const wasSelected = btn.classList.contains("selected");
        $$("#dz-where-chips .dz-chip-btn").forEach((b) => b.classList.remove("selected"));
        if (!wasSelected) {
          btn.classList.add("selected");
        }
      });
    });

    /* ---- Voice input for problem ---- */
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    /* Web Speech API only works in a secure context (HTTPS) or on localhost.
       On an insecure origin the API object exists but start() fails silently /
       with "not-allowed" — detect it up-front and explain, rather than looking
       broken. */
    const _voiceSecure = window.isSecureContext ||
      ["localhost", "127.0.0.1", "[::1]"].indexOf(location.hostname) >= 0;
    if (!SpeechRecognition || !_voiceSecure) {
      voiceBtn.title = !SpeechRecognition
        ? "Voice input is not supported in this browser (try Chrome or Edge)."
        : "Voice input needs a secure connection (HTTPS) or localhost.";
      voiceBtn.style.opacity = "0.35";
      voiceBtn.style.cursor = "not-allowed";
      voiceBtn.addEventListener("click", () => {
        if (window.CS && CS.toast) CS.toast("warning", "Voice unavailable", voiceBtn.title);
      });
      return;
    }

    let recognition = null;
    let isRecording = false;

    voiceBtn.addEventListener("click", () => {
      if (isRecording) {
        recognition.stop();
        return;
      }
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        isRecording = true;
        voiceBtn.classList.add("recording");
        recordingEl.classList.remove("d-none");
        recordingEl.querySelector(".dz-problem-voice-label").textContent = "Listening...";
        voiceTextEl.textContent = "";
      };

      recognition.onresult = (e) => {
        let transcript = "";
        for (let i = 0; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript;
        }
        voiceTextEl.textContent = transcript;
      };

      recognition.onend = () => {
        isRecording = false;
        voiceBtn.classList.remove("recording");
        const finalText = voiceTextEl.textContent.trim();
        if (finalText) {
          recordingEl.querySelector(".dz-problem-voice-label").textContent = "Adding to problem...";
          /* Insert speech into textarea */
          const current = textarea.value.trim();
          textarea.value = current ? current + " " + finalText : finalText;
          textarea.dispatchEvent(new Event("input"));
          setTimeout(() => {
            recordingEl.classList.add("d-none");
          }, 800);
        } else {
          recordingEl.classList.add("d-none");
        }
      };

      recognition.onerror = (e) => {
        isRecording = false;
        voiceBtn.classList.remove("recording");
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          recordingEl.querySelector(".dz-problem-voice-label").textContent = "Microphone access denied";
          setTimeout(() => recordingEl.classList.add("d-none"), 2000);
        } else if (e.error !== "aborted") {
          recordingEl.classList.add("d-none");
        }
      };

      /* start() can throw synchronously (e.g. already-started, or an insecure
         origin) — guard it so the UI never gets stuck in the recording state. */
      try {
        recognition.start();
      } catch (err) {
        isRecording = false;
        voiceBtn.classList.remove("recording");
        recordingEl.classList.add("d-none");
        if (window.CS && CS.toast) CS.toast("error", "Voice input failed", "Please try again.");
      }
    });

    stopBtn.addEventListener("click", () => {
      if (recognition && isRecording) {
        recognition.stop();
      }
    });
  }

  function updateProblemValidation() {
    const val = ($("#dz-problem").value || "").trim();
    const valid = val.length >= 5;
    $("#dz-continue-describe").disabled = !valid;
  }

  function renderProblemSuggestions(query) {
    const container = $("#dz-problem-suggestions");
    problemSuggIndex = -1;
    if (!query || query.length < 1) {
      container.classList.add("d-none");
      container.innerHTML = "";
      return;
    }
    const q = query.toLowerCase();
    const matches = [];
    /* Priority: title starts-with, then title contains, then notice/category contains */
    for (const p of PROBLEM_CATALOG) {
      if (p.text.toLowerCase().startsWith(q)) matches.push(p);
    }
    for (const p of PROBLEM_CATALOG) {
      if (!matches.includes(p) && p.text.toLowerCase().includes(q)) matches.push(p);
    }
    for (const p of PROBLEM_CATALOG) {
      if (!matches.includes(p) &&
          ((p.cat && p.cat.toLowerCase().includes(q)) ||
           (p.notice && p.notice.toLowerCase().includes(q)))) matches.push(p);
    }
    if (matches.length === 0) {
      container.classList.add("d-none");
      container.innerHTML = "";
      return;
    }
    container.innerHTML = matches.slice(0, 6).map((p) => {
      const s = p.text;
      const idx = s.toLowerCase().indexOf(q);
      let title;
      if (idx >= 0) {
        title = esc(s.slice(0, idx)) + '<span class="dz-sugg-match">' +
          esc(s.slice(idx, idx + query.length)) + "</span>" + esc(s.slice(idx + query.length));
      } else {
        title = esc(s);
      }
      const tone = PROBLEM_TONE[p.tone] || "info";
      return `
      <div class="dz-problem-suggestion" data-text="${esc(s)}" role="option">
        <div class="dz-sugg-media dz-sugg-media--${tone}"><i class="bi ${p.icon || "bi-wrench"}"></i></div>
        <div class="dz-sugg-body">
          <div class="dz-sugg-title">${title}</div>
          ${p.notice ? `<div class="dz-sugg-notice"><i class="bi bi-info-circle"></i> ${esc(p.notice)}</div>` : ""}
        </div>
        ${p.cat ? `<span class="dz-sugg-cat dz-sugg-cat--${tone}">${esc(p.cat)}</span>` : ""}
      </div>`;
    }).join("");
    container.classList.remove("d-none");
    container.querySelectorAll(".dz-problem-suggestion").forEach((el) => {
      el.addEventListener("click", () => selectProblemSuggestion(el.dataset.text));
    });
  }

  function selectProblemSuggestion(text) {
    const textarea = $("#dz-problem");
    textarea.value = text;
    textarea.dispatchEvent(new Event("input"));
    textarea.focus();
    $("#dz-problem-suggestions").classList.add("d-none");
    problemSuggIndex = -1;
  }

  function updateProblemSuggHighlight(items) {
    items.forEach((item, i) => {
      item.classList.toggle("highlighted", i === problemSuggIndex);
    });
    if (problemSuggIndex >= 0 && items[problemSuggIndex]) {
      items[problemSuggIndex].scrollIntoView({ block: "nearest" });
    }
  }

  function getSelectedCategory() {
    const sel = $(".dz-category-btn.selected");
    return sel ? sel.dataset.category : "";
  }

  function getSelectedWhen() {
    const sel = $("#dz-when-chips .dz-chip-btn.selected");
    return sel ? sel.dataset.when : "";
  }

  function getSelectedWhere() {
    const sel = $("#dz-where-chips .dz-chip-btn.selected");
    return sel ? sel.dataset.where : "";
  }

  function buildFullProblem() {
    let parts = [state.problem];
    if (state.category) parts.push("Category: " + state.category);
    if (state.when) parts.push("When: " + state.when);
    if (state.where) parts.push("Location: " + state.where);
    if (state.notice) parts.push("Additional info: " + state.notice);
    return parts.join(". ");
  }

  function updateVehicleBadge() {
    const badge = $("#dz-vehicle-badge");
    const text = $("#dz-vehicle-badge-text");
    if (state.vehicle.brand) {
      const label = [state.vehicle.brand, state.vehicle.model].filter(Boolean).join(" ")
        + (state.vehicle.engine ? " · " + state.vehicle.engine : "");
      text.textContent = label;
      badge.classList.remove("d-none");
    } else {
      badge.classList.add("d-none");
    }
  }

  /* ---- Show current question ---- */
  function showQuestion() {
    const q = state.questions[state.questionIndex];
    if (!q) return;
    const total = state.questions.length;
    const idx = state.questionIndex;
    const counter = trFmt("stepCounter", { current: idx + 1, total: total });

    $("#dz-q-title").textContent = q.title;
    $("#dz-q-subtitle").textContent = q.subtitle || "";
    $("#dz-step-counter").textContent = counter;
    $("#dz-continue-q").disabled = true;

    const container = $("#dz-q-options");
    container.innerHTML = "";
    q.options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dz-option" + (state.answers[q.key] === opt ? " selected" : "");
      btn.innerHTML = `<span class="dz-option-dot"></span><span>${esc(opt)}</span>`;
      btn.addEventListener("click", () => {
        state.answers[q.key] = opt;
        $$(".dz-option", container).forEach((o) => o.classList.remove("selected"));
        btn.classList.add("selected");
        $("#dz-continue-q").disabled = false;
      });
      container.appendChild(btn);
    });
  }

  /* ---- Image handling ---- */
  function handleImage() {
    const file = $("#dz-file-input").files[0];
    if (file) processImage(file);
  }
  function processImage(file) {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      state.image = e.target.result;
      state._imageDirty = true;
      $("#dz-img-thumb").src = state.image;
      $("#dz-img-preview").style.display = "inline-block";
      $("#dz-upload-zone").style.display = "none";
      updateContinueButton();
    };
    reader.readAsDataURL(file);
  }

  /* ---- Video handling ---- */
  const VIDEO_MAX_SIZE = 20 * 1024 * 1024; /* 20 MB */
  const VIDEO_ALLOWED_TYPES = ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska"];
  const VIDEO_ALLOWED_EXTS = ["mp4", "webm", "mov", "mkv", "3gp"];

  function handleVideo() {
    const file = $("#dz-video-input").files[0];
    if (file) processVideo(file);
  }

  function processVideo(file) {
    /* Validate file type */
    const ext = (file.name || "").split(".").pop().toLowerCase();
    const isValidType = VIDEO_ALLOWED_TYPES.includes(file.type) || VIDEO_ALLOWED_EXTS.includes(ext);
    if (!isValidType) {
      if (window.CS && CS.toast) CS.toast("warning", "Invalid file type", "Please upload an MP4, WebM, MOV or MKV video.");
      return;
    }

    /* Validate file size */
    if (file.size > VIDEO_MAX_SIZE) {
      if (window.CS && CS.toast) CS.toast("warning", "File too large", "Video must be under 20 MB.");
      return;
    }

    /* Store file reference */
    state.videoFile = file;

    /* Read as base64 */
    const reader = new FileReader();
    reader.onload = (e) => {
      state.video = e.target.result;
      state._videoDirty = true;

      /* Show video preview */
      const videoEl = $("#dz-video-thumb");
      if (videoEl) {
        videoEl.src = state.video;
        videoEl.load();
      }

      /* Show filename and size */
      const filenameEl = $("#dz-video-filename");
      const sizeEl = $("#dz-video-size");
      if (filenameEl) filenameEl.textContent = file.name || "video";
      if (sizeEl) sizeEl.textContent = formatFileSize(file.size);

      /* Toggle UI */
      $("#dz-video-preview").style.display = "inline-block";
      $("#dz-video-zone").style.display = "none";
      updateContinueButton();
    };
    reader.readAsDataURL(file);
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function updateContinueButton() {
    const hasMedia = state.image || state.video;
    const continueBtn = $("#dz-continue-img");
    const skipBtn = $("#dz-skip-img");
    if (continueBtn) continueBtn.style.display = hasMedia ? "" : "none";
    if (skipBtn) skipBtn.style.display = hasMedia ? "none" : "";
  }

  /* ---- Ready (Step 6: Diagnose) ---- */
  function showReady() {
    /* Vehicle */
    const logoEl = $("#dz-ready-logo");
    const brandEl = $("#dz-ready-brand");
    const modelEl = $("#dz-ready-model");
    const brandName = state.vehicle.brand || "";
    const modelName = state.vehicle.model || "";

    if (brandName) {
      const brandData = CAR_BRANDS.find((b) => b.name === brandName);
      logoEl.style.background = brandGradient(brandName);
      if (brandData && brandData.logo) {
        logoEl.innerHTML = `<img src="${esc(brandData.logo)}" alt="${esc(brandName)}" class="dz-ready-logo-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="dz-ready-logo-fallback" style="display:none"><i class="bi bi-car-front-fill"></i></div>`;
      } else {
        logoEl.innerHTML = `<div class="dz-ready-logo-fallback"><i class="bi bi-car-front-fill"></i></div>`;
      }
      logoEl.classList.remove("d-none");
    } else {
      logoEl.classList.add("d-none");
    }
    brandEl.textContent = brandName || tr("noVehicleSelected");
    modelEl.textContent = modelName || "";

    /* Problem */
    const problemEl = $("#dz-ready-problem");
    problemEl.textContent = state.problem || tr("noProblemDescribed");

    /* Notice */
    const noticeSection = $("#dz-ready-notice-section");
    const noticeEl = $("#dz-ready-notice");
    if (state.notice) {
      noticeEl.textContent = state.notice;
      noticeSection.classList.remove("d-none");
    } else {
      noticeSection.classList.add("d-none");
    }

    /* Media */
    const mediaSection = $("#dz-ready-media-section");
    const mediaEl = $("#dz-ready-media");
    if (state.image || state.video) {
      let mediaHtml = "";
      if (state.image) {
        mediaHtml += `<div class="dz-ready-media-item"><i class="bi bi-image"></i> <span>${tr("oneImageAttached")}</span></div>`;
      }
      if (state.video) {
        const videoName = state.videoFile ? state.videoFile.name : "video";
        mediaHtml += `<div class="dz-ready-media-item"><i class="bi bi-camera-reels"></i> <span>${esc(videoName)}</span></div>`;
      }
      mediaEl.innerHTML = mediaHtml;
      mediaSection.classList.remove("d-none");
    } else {
      mediaSection.classList.add("d-none");
    }

    showStep("ready");
  }

  /* ---- Review ---- */
  function showReview() {
    const container = $("#dz-review");
    container.innerHTML = "";

    const vehicleText = ([state.vehicle.brand, state.vehicle.model].filter(Boolean).join(" ") + (state.vehicle.engine ? " · " + state.vehicle.engine : "")) || tr("valueNotSpecified");
    const items = [
      { label: tr("labelVehicle"), value: vehicleText, edit: "vehicle" },
      { label: tr("labelProblem"), value: state.problem, edit: "describe" },
    ];
    if (state.category) {
      items.push({ label: tr("labelCategory"), value: state.category.charAt(0).toUpperCase() + state.category.slice(1), edit: "describe" });
    }
    if (state.when) {
      items.push({ label: tr("labelWhen"), value: state.when, edit: "describe" });
    }
    if (state.where) {
      items.push({ label: tr("labelWhere"), value: state.where, edit: "describe" });
    }
    if (state.notice) {
      items.push({ label: tr("labelNotice"), value: state.notice, edit: "describe" });
    }
    for (const q of state.questions) {
      if (state.answers[q.key]) {
        items.push({ label: q.title.replace("?", ""), value: state.answers[q.key], edit: "questions" });
      }
    }
    if (state.image) {
      items.push({ label: tr("labelPhoto"), value: tr("valueAdded"), edit: "image" });
    }
    if (state.video) {
      items.push({ label: tr("labelVideo"), value: state.videoFile ? state.videoFile.name : tr("valueAdded"), edit: "image" });
    }

    items.forEach((item) => {
      const div = document.createElement("div");
      div.className = "dz-review-item";
      div.innerHTML = `
        <div class="dz-review-info">
          <div class="dz-review-label">${esc(item.label)}</div>
          <div class="dz-review-value">${esc(item.value)}</div>
        </div>
        <span class="dz-review-edit" data-goto="${item.edit}">${tr("reviewEdit")}</span>
      `;
      div.querySelector(".dz-review-edit").addEventListener("click", () => {
        if (item.edit === "vehicle") showStep("vehicle");
        else if (item.edit === "describe") showStep("describe");
        else if (item.edit === "questions") {
          state.questionIndex = Math.max(0, state.questions.length - 1);
          showQuestion();
          showStep("questions");
        } else if (item.edit === "image") showStep("image");
      });
      container.appendChild(div);
    });

    showStep("review");
  }

  /* ---- Run diagnosis ---- */
  async function runDiagnosis() {
    /* Guard against duplicate submissions */
    if (state._diagnosing) return;
    state._diagnosing = true;
    const diagBtn = $("#dz-diagnose");
    if (diagBtn) { diagBtn.disabled = true; diagBtn.style.opacity = "0.5"; }

    modalLoading();
    /* Mark session as diagnosing */
    if (state.sessionId) {
      fetch(`/api/diag-sessions/${state.sessionId}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "diagnosing" }),
      }).catch(() => {});
    }
    let _completed = false;
    try {
      const fullProblem = buildFullProblem();
      const payload = {
        problem: fullProblem,
        answers: state.answers,
        image: state.image,
        video: state.video,
        vehicle: state.vehicle.brand ? state.vehicle : null,
      };
      if (state.sessionId) payload.session_id = state.sessionId;

      const res = await fetch("/api/diagnose/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || tr("errorMsgDefault"));
        return;
      }

      showWorkspace(data.result);
      _completed = true;
    } catch (err) {
      showError(tr("errorMsgDefault"));
    } finally {
      state._diagnosing = false;
      if (diagBtn) { diagBtn.disabled = false; diagBtn.style.opacity = ""; }
      /* If the run failed, don't leave the session stuck in "diagnosing" — that
         status blocks deletion (item 1). Reset it so it can be retried/deleted. */
      if (!_completed && state.sessionId) {
        fetch(`/api/diag-sessions/${state.sessionId}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "ready" }),
        }).catch(() => {});
      }
    }
  }

  function showError(msg) {
    _stopLoadingStatus();
    const body = $("#dz-modal-body");
    const footer = $("#dz-modal-footer");
    if (!body) return;
    body.innerHTML = `
      <div class="dz-modal-error">
        <div class="dz-modal-error-icon"><i class="bi bi-exclamation-triangle"></i></div>
        <div class="dz-modal-error-title">${tr("errorTitle")}</div>
        <div class="dz-modal-error-msg">${esc(msg || tr("errorMsgDefault"))}</div>
        <button class="dz-btn dz-btn-primary" id="dz-modal-retry"><i class="bi bi-arrow-repeat"></i> ${tr("tryAgain")}</button>
      </div>`;
    if (footer) footer.innerHTML = `<button class="dz-btn dz-btn-ghost" id="dz-modal-close-err"><i class="bi bi-x-lg"></i> ${tr("close")}</button>`;
    const retryBtn = $("#dz-modal-retry");
    if (retryBtn) retryBtn.addEventListener("click", () => { closeModal(); setTimeout(() => runDiagnosis(), 200); });
    const closeErrBtn = $("#dz-modal-close-err");
    if (closeErrBtn) closeErrBtn.addEventListener("click", closeModal);
    openModal();
  }

  /* ---- Start chat with AI Mechanic after diagnosis ---- */
  async function startDiagnosisChat(result) {
    const chatBtn = $("#dz-m-chat") || $("#dz-chat-continue");
    if (chatBtn) {
      chatBtn.disabled = true;
      chatBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Starting chat...';
    }
    try {
      const res = await fetch("/api/chat/save-diagnosis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: state.mode || "text",
          problem: buildFullProblem(),
          result: result,
          session_id: state.sessionId || null,
          vehicle: state.vehicle || null,
        }),
      });
      const data = await res.json();
      if (data.ok && data.id) {
        window.location.href = "/chat?chat_id=" + encodeURIComponent(data.id);
      } else {
        throw new Error(data.error || "Failed to create chat");
      }
    } catch (err) {
      if (chatBtn) {
        chatBtn.disabled = false;
        chatBtn.innerHTML = '<i class="bi bi-chat-right-text"></i> Continue Chat';
      }
      toast("error", "Chat failed", err.message || "Please try again.");
    }
  }

  /* ---- Show result ---- */
  function showResult(r) {
    _modalResult = r;
    const body = $("#dz-modal-body");
    const footer = $("#dz-modal-footer");
    if (!body) return;

    const vehicleLabel = [state.vehicle.brand, state.vehicle.model].filter(Boolean).join(" ") || r.vehicle || "Vehicle";
    const brandSlug = (state.vehicle.brand || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+$/, "");
    const conf = r.confidence || 0;

    const sevConfig = {
      low:      { level: "low",    label: "Low Severity",    icon: "bi-check-circle-fill",     color: "#22c55e", msg: "This issue does not appear urgent, but inspection may still be recommended." },
      medium:   { level: "medium", label: "Moderate Problem", icon: "bi-exclamation-circle-fill", color: "#f59e0b", msg: "This issue should be inspected soon to prevent further damage." },
      high:     { level: "high",   label: "Severe Problem",   icon: "bi-exclamation-triangle-fill", color: "#ef4444", msg: "This issue may require immediate attention. Avoid driving until checked." },
      critical: { level: "critical", label: "Critical Issue", icon: "bi-exclamation-octagon-fill", color: "#ef4444", msg: "Do not drive. This issue poses a safety risk and requires immediate service." },
    };
    const sev = sevConfig[r.urgency] || sevConfig.medium;
    const urgencyLabel = (r.urgency || "medium").charAt(0).toUpperCase() + (r.urgency || "medium").slice(1);

    let html = "";

    /* ---- Vehicle visual ---- */
    html += `<div class="dz-modal-vehicle">
      <div class="dz-modal-vehicle-logo">
        <img src="/image/car_logos/${esc(brandSlug)}.svg" alt="${esc(state.vehicle.brand)}" onerror="this.style.display='none';this.parentElement.innerHTML='<i class=\\'bi bi-car-front-fill\\' style=\\'font-size:1.5rem;color:rgba(var(--accent-rgb),0.3)\\'></i>'">
      </div>
      <div class="dz-modal-vehicle-info">
        <div class="dz-modal-vehicle-name">${esc(vehicleLabel)}</div>
        <div class="dz-modal-vehicle-problem">${esc((r.problem || "").slice(0, 60))}${(r.problem || "").length > 60 ? "..." : ""}</div>
      </div>
      <div class="dz-modal-vehicle-status">
        <span class="dz-modal-urgency-badge dz-modal-urgency-${sev.level}"><i class="bi ${sev.icon}"></i> ${sev.label}</span>
        <span class="dz-modal-conf-mini"><i class="bi bi-stars"></i> ${conf}% confidence</span>
      </div>
    </div>`;

    /* ---- Severity gauge (item 6) ---- */
    html += severityMeter(sev, conf);

    /* ---- Safety warning (high/critical) ---- */
    if ((sev.level === "high" || sev.level === "critical") && r.can_drive) {
      html += `<div class="dz-modal-safety">
        <div class="dz-modal-safety-icon"><i class="bi bi-shield-exclamation"></i></div>
        <div>
          <div class="dz-modal-safety-title">Safety Recommendation</div>
          <div class="dz-modal-safety-text">${esc(r.can_drive)}</div>
        </div>
      </div>`;
    }

    /* ---- Diagnosis ---- */
    html += `<div class="dz-modal-card">
      <div class="dz-modal-card-head">
        <div class="dz-modal-card-icon"><i class="bi bi-clipboard2-pulse"></i></div>
        <div class="dz-modal-card-title">Diagnosis</div>
      </div>
      <div class="dz-modal-card-label">Problem Detected</div>
      <div class="dz-modal-card-value" style="margin-bottom:12px">${esc(r.problem)}</div>
      <div class="dz-modal-card-label">Summary</div>
      <div class="dz-modal-card-text">${esc(r.summary)}</div>
      ${r.can_drive && !(sev.level === "high" || sev.level === "critical") ? `
      <div style="margin-top:12px"><div class="dz-modal-card-label">Can I Still Drive?</div>
      <div class="dz-modal-card-text">${esc(r.can_drive)}</div></div>` : ""}
    </div>`;

    /* ---- Possible Causes ---- */
    if (r.causes && r.causes.length) {
      html += `<div class="dz-modal-card">
        <div class="dz-modal-card-head">
          <div class="dz-modal-card-icon"><i class="bi bi-search"></i></div>
          <div class="dz-modal-card-title">Possible Causes</div>
        </div>
        <div class="dz-modal-causes">
          ${r.causes.map((c, i) => `<div class="dz-modal-cause">
            <span class="dz-modal-cause-num">${String(i + 1).padStart(2, "0")}</span>
            <span class="dz-modal-cause-text">${esc(c)}</span>
          </div>`).join("")}
        </div>
      </div>`;
    }

    /* ---- Recommended Actions (timeline) ---- */
    if (r.steps && r.steps.length) {
      html += `<div class="dz-modal-card">
        <div class="dz-modal-card-head">
          <div class="dz-modal-card-icon"><i class="bi bi-wrench-adjustable"></i></div>
          <div class="dz-modal-card-title">Recommended Actions</div>
        </div>
        <div class="dz-modal-timeline">
          ${r.steps.map((s, i) => `<div class="dz-modal-tl-item">
            <div class="dz-modal-tl-marker">
              <div class="dz-modal-tl-dot">${i + 1}</div>
              ${i < r.steps.length - 1 ? '<div class="dz-modal-tl-line"></div>' : ""}
            </div>
            <div class="dz-modal-tl-content">${esc(s)}</div>
          </div>`).join("")}
        </div>
      </div>`;
    }

    /* ---- Parts ---- */
    if (r.parts && r.parts.length) {
      html += `<div class="dz-modal-card">
        <div class="dz-modal-card-head">
          <div class="dz-modal-card-icon"><i class="bi bi-box-seam"></i></div>
          <div class="dz-modal-card-title">Parts Needed</div>
        </div>
        <div class="dz-modal-parts">
          ${r.parts.map((p) => `<div class="dz-modal-part"><i class="bi bi-gear"></i><span>${esc(p)}</span></div>`).join("")}
        </div>
      </div>`;
    }

    /* ---- Cost & Time ---- */
    html += `<div class="dz-modal-card">
      <div class="dz-modal-card-head">
        <div class="dz-modal-card-icon"><i class="bi bi-cash-stack"></i></div>
        <div class="dz-modal-card-title">Estimated Cost & Time</div>
      </div>
      <div class="dz-modal-cost">
        <div class="dz-modal-cost-item">
          <div class="dz-modal-cost-label">Estimated Cost</div>
          <div class="dz-modal-cost-value dz-modal-cost-green">${esc(r.cost || "Not available")}</div>
        </div>
        <div class="dz-modal-cost-item">
          <div class="dz-modal-cost-label">Estimated Time</div>
          <div class="dz-modal-cost-value dz-modal-cost-cyan">${esc(r.time || "Not available")}</div>
        </div>
        <div class="dz-modal-cost-item">
          <div class="dz-modal-cost-label">Recommended Service</div>
          <div class="dz-modal-cost-value dz-modal-cost-muted">${esc(r.center || "Not available")}</div>
        </div>
      </div>
    </div>`;

    /* ---- Prevention Tips ---- */
    if (r.tips && r.tips.length) {
      html += `<div class="dz-modal-card">
        <div class="dz-modal-card-head">
          <div class="dz-modal-card-icon"><i class="bi bi-lightbulb"></i></div>
          <div class="dz-modal-card-title">Prevention Tips</div>
        </div>
        <div class="dz-modal-tips">
          ${r.tips.map((t) => `<div class="dz-modal-tip"><i class="bi bi-check2-circle"></i><span>${esc(t)}</span></div>`).join("")}
        </div>
      </div>`;
    }

    body.innerHTML = html;

    /* ---- Footer buttons ---- */
    let footerHtml = `<button class="dz-btn dz-btn-primary" id="dz-m-save"><i class="bi bi-bookmark-check"></i> Save Diagnosis</button>`;
    footerHtml += `<button class="dz-btn dz-btn-ghost" id="dz-m-chat"><i class="bi bi-chat-right-text"></i> Continue Chat</button>`;
    if (r.id) footerHtml += `<a href="/diagnosis/${esc(r.id)}/print" class="dz-btn dz-btn-ghost" target="_blank"><i class="bi bi-file-earmark-pdf"></i> PDF</a>`;
    footerHtml += `<button class="dz-btn dz-btn-ghost" id="dz-m-new"><i class="bi bi-plus-lg"></i> New</button>`;
    footerHtml += `<button class="dz-btn dz-btn-ghost" id="dz-m-close"><i class="bi bi-x-lg"></i> Close</button>`;
    if (footer) footer.innerHTML = footerHtml;

    /* Attach handlers */
    const saveBtn = $("#dz-m-save");
    if (saveBtn) saveBtn.addEventListener("click", () => { window.location.href = "/my-diagnoses"; });
    const chatBtn = $("#dz-m-chat");
    if (chatBtn) chatBtn.addEventListener("click", () => openChatModal(r));
    const newBtn = $("#dz-m-new");
    if (newBtn) newBtn.addEventListener("click", () => { closeModal(); $("#dz-new-diag").click(); });
    const closeBtnFooter = $("#dz-m-close");
    if (closeBtnFooter) closeBtnFooter.addEventListener("click", closeModal);

    openModal();
  }

  /* ============================================================
     UNIFIED WORKSPACE — replaces modal result with two-column layout
     ============================================================ */
  function showWorkspace(r) {
    _modalResult = r;
    /* Stop loading status messages and close modal IMMEDIATELY */
    _stopLoadingStatus();
    closeModal();
    const wizHeader = $("#dz-wizard-header");
    const mainGrid = $("#dz-main-grid");
    const benefits = $("#dz-benefits");
    const workspace = $("#dz-workspace");
    const resultInner = $("#dz-ws-result-inner");
    if (!workspace || !resultInner) return;

    /* Hide wizard, show workspace */
    if (wizHeader) wizHeader.style.display = "none";
    if (mainGrid) mainGrid.style.display = "none";
    if (benefits) benefits.style.display = "none";
    workspace.classList.remove("d-none");
    state.step = "workspace";

    /* Push history so Back button exits workspace */
    if (!_navGuard) {
      _navGuard = true;
      window.history.pushState({ workspace: true }, "", "#workspace");
      _navGuard = false;
    }

    /* Update context label */
    const vehicleLabel = [state.vehicle.brand, state.vehicle.model].filter(Boolean).join(" ") || r.vehicle || "your vehicle";
    const ctx = $("#dz-ws-chat-context");
    if (ctx) ctx.textContent = "Discussing " + vehicleLabel + " diagnosis";

    /* ---- Render result panel (right side) ---- */
    const brandSlug = (state.vehicle.brand || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+$/, "");
    const conf = r.confidence || 0;
    const sevConfig = {
      low:      { level: "low",    label: "Low Severity",    icon: "bi-check-circle-fill",     color: "#22c55e", msg: "This issue does not appear urgent, but inspection may still be recommended." },
      medium:   { level: "medium", label: "Moderate Problem", icon: "bi-exclamation-circle-fill", color: "#f59e0b", msg: "This issue should be inspected soon to prevent further damage." },
      high:     { level: "high",   label: "Severe Problem",   icon: "bi-exclamation-triangle-fill", color: "#ef4444", msg: "This issue may require immediate attention. Avoid driving until checked." },
      critical: { level: "critical", label: "Critical Issue", icon: "bi-exclamation-octagon-fill", color: "#ef4444", msg: "Do not drive. This issue poses a safety risk and requires immediate service." },
    };
    const sev = sevConfig[r.urgency] || sevConfig.medium;

    let rhtml = "";

    /* Badge */
    rhtml += `<div class="dz-ws-result-badge"><i class="bi bi-patch-check-fill"></i> DIAGNOSIS RESULT</div>`;

    /* Vehicle card */
    rhtml += `<div class="dz-ws-result-vehicle">
      <div class="dz-ws-result-vehicle-logo">
        <img src="/image/car_logos/${esc(brandSlug)}.svg" alt="${esc(state.vehicle.brand)}" onerror="this.style.display='none';this.parentElement.innerHTML='<i class=\\'bi bi-car-front-fill\\' style=\\'font-size:1.2rem;color:rgba(var(--accent-rgb),0.3)\\'></i>'">
      </div>
      <div>
        <div class="dz-ws-result-vehicle-name">${esc(vehicleLabel)}</div>
        <div class="dz-ws-result-vehicle-problem">${esc((r.problem || "").slice(0, 80))}${(r.problem || "").length > 80 ? "..." : ""}</div>
      </div>
    </div>`;

    /* Severity gauge (item 6) */
    rhtml += severityMeter(sev, conf);

    /* Safety warning */
    if ((sev.level === "high" || sev.level === "critical") && r.can_drive) {
      rhtml += `<div class="dz-ws-safety">
        <div class="dz-ws-safety-icon"><i class="bi bi-shield-exclamation"></i></div>
        <div>
          <div class="dz-ws-safety-title">Safety Recommendation</div>
          <div class="dz-ws-safety-text">${esc(r.can_drive)}</div>
        </div>
      </div>`;
    }

    /* Diagnosis card */
    rhtml += `<div class="dz-ws-result-card">
      <div class="dz-ws-result-card-head">
        <div class="dz-ws-result-card-icon"><i class="bi bi-clipboard2-pulse"></i></div>
        <div class="dz-ws-result-card-title">Diagnosis</div>
      </div>
      <div class="dz-ws-result-card-label">Problem Detected</div>
      <div class="dz-ws-result-card-value" style="margin-bottom:10px">${esc(r.problem)}</div>
      <div class="dz-ws-result-card-label">Summary</div>
      <div class="dz-ws-result-card-text">${esc(r.summary)}</div>
      ${r.can_drive && !(sev.level === "high" || sev.level === "critical") ? `
      <div style="margin-top:10px"><div class="dz-ws-result-card-label">Can I Still Drive?</div>
      <div class="dz-ws-result-card-text">${esc(r.can_drive)}</div></div>` : ""}
    </div>`;

    /* Possible Causes */
    if (r.causes && r.causes.length) {
      rhtml += `<div class="dz-ws-result-card">
        <div class="dz-ws-result-card-head">
          <div class="dz-ws-result-card-icon"><i class="bi bi-search"></i></div>
          <div class="dz-ws-result-card-title">Possible Causes</div>
        </div>
        <div class="dz-ws-causes">
          ${r.causes.map((c, i) => `<div class="dz-ws-cause">
            <span class="dz-ws-cause-num">${String(i + 1).padStart(2, "0")}</span>
            <span>${esc(c)}</span>
          </div>`).join("")}
        </div>
      </div>`;
    }

    /* Recommended Actions */
    if (r.steps && r.steps.length) {
      rhtml += `<div class="dz-ws-result-card">
        <div class="dz-ws-result-card-head">
          <div class="dz-ws-result-card-icon"><i class="bi bi-wrench-adjustable"></i></div>
          <div class="dz-ws-result-card-title">Recommended Actions</div>
        </div>
        <div class="dz-ws-timeline">
          ${r.steps.map((s, i) => `<div class="dz-ws-tl-item">
            <div class="dz-ws-tl-marker">
              <div class="dz-ws-tl-dot">${i + 1}</div>
              ${i < r.steps.length - 1 ? '<div class="dz-ws-tl-line"></div>' : ""}
            </div>
            <div class="dz-ws-tl-content">${esc(s)}</div>
          </div>`).join("")}
        </div>
      </div>`;
    }

    /* Parts */
    if (r.parts && r.parts.length) {
      rhtml += `<div class="dz-ws-result-card">
        <div class="dz-ws-result-card-head">
          <div class="dz-ws-result-card-icon"><i class="bi bi-box-seam"></i></div>
          <div class="dz-ws-result-card-title">Parts Needed</div>
        </div>
        <div class="dz-ws-parts">
          ${r.parts.map((p) => `<div class="dz-ws-part"><i class="bi bi-gear"></i><span>${esc(p)}</span></div>`).join("")}
        </div>
      </div>`;
    }

    /* Cost & Time */
    rhtml += `<div class="dz-ws-result-card">
      <div class="dz-ws-result-card-head">
        <div class="dz-ws-result-card-icon"><i class="bi bi-cash-stack"></i></div>
        <div class="dz-ws-result-card-title">Estimated Cost & Time</div>
      </div>
      <div class="dz-ws-cost-grid">
        <div class="dz-ws-cost-item">
          <div class="dz-ws-cost-label">Estimated Cost</div>
          <div class="dz-ws-cost-value dz-ws-cost-green">${esc(r.cost || "Not available")}</div>
        </div>
        <div class="dz-ws-cost-item">
          <div class="dz-ws-cost-label">Estimated Time</div>
          <div class="dz-ws-cost-value dz-ws-cost-cyan">${esc(r.time || "Not available")}</div>
        </div>
        <div class="dz-ws-cost-item full">
          <div class="dz-ws-cost-label">Recommended Service</div>
          <div class="dz-ws-cost-value dz-ws-cost-muted">${esc(r.center || "Not available")}</div>
        </div>
      </div>
    </div>`;

    /* Prevention Tips */
    if (r.tips && r.tips.length) {
      rhtml += `<div class="dz-ws-result-card">
        <div class="dz-ws-result-card-head">
          <div class="dz-ws-result-card-icon"><i class="bi bi-lightbulb"></i></div>
          <div class="dz-ws-result-card-title">Prevention Tips</div>
        </div>
        <div class="dz-ws-tips">
          ${r.tips.map((t) => `<div class="dz-ws-tip"><i class="bi bi-check2-circle"></i><span>${esc(t)}</span></div>`).join("")}
        </div>
      </div>`;
    }

    /* Feedback */
    rhtml += `<div class="dz-ws-feedback" id="dz-ws-feedback">
      <div class="dz-ws-feedback-text">Was this diagnosis helpful?</div>
      <div class="dz-ws-feedback-actions">
        <button class="dz-ws-feedback-btn" id="dz-ws-fb-yes" type="button"><i class="bi bi-hand-thumbs-up"></i> Yes</button>
        <button class="dz-ws-feedback-btn" id="dz-ws-fb-no" type="button"><i class="bi bi-hand-thumbs-down"></i> No</button>
      </div>
    </div>
    <div class="dz-ws-feedback-msg d-none" id="dz-ws-fb-msg"></div>`;

    resultInner.innerHTML = rhtml;

    /* Feedback handlers */
    const fbYes = $("#dz-ws-fb-yes");
    const fbNo = $("#dz-ws-fb-no");
    const fbMsg = $("#dz-ws-fb-msg");
    if (fbYes) fbYes.addEventListener("click", () => {
      fbYes.classList.add("active-yes");
      fbNo.classList.remove("active-no");
      if (fbMsg) { fbMsg.textContent = "Glad this helped."; fbMsg.classList.remove("d-none"); }
    });
    if (fbNo) fbNo.addEventListener("click", () => {
      fbNo.classList.add("active-no");
      fbYes.classList.remove("active-yes");
      if (fbMsg) { fbMsg.textContent = "No problem. Tell the AI Mechanic what you'd like to clarify."; fbMsg.classList.remove("d-none"); }
      const input = $("#dz-ws-chat-input");
      if (input) input.focus();
    });

    /* ---- Initialize chat session ---- */
    wsInitChat(r);
  }

  /* ============================================================
     WORKSPACE CHAT — streaming conversation within the workspace
     ============================================================ */
  async function wsInitChat(result) {
    const history = $("#dz-ws-chat-history");
    if (!history) return;
    history.innerHTML = "";

    /* Create chat session via save-diagnosis endpoint */
    try {
      const res = await fetch("/api/chat/save-diagnosis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: result.mode || state.mode || "text",
          problem: buildFullProblem(),
          result: result,
          session_id: state.sessionId || null,
          vehicle: state.vehicle || null,
        }),
      });
      const data = await res.json();
      if (data.ok && data.id) {
        _wsChatId = data.id;
      }
    } catch (e) {
      /* Non-critical — chat will work without persistence */
    }

    /* Render initial AI greeting with diagnosis summary */
    const vehicleLabel = [state.vehicle.brand, state.vehicle.model].filter(Boolean).join(" ") || result.vehicle || "your vehicle";
    const summaryParts = [];
    if (result.problem) summaryParts.push("**Problem:** " + result.problem);
    if (result.urgency) summaryParts.push("**Severity:** " + result.urgency.charAt(0).toUpperCase() + result.urgency.slice(1));
    if (result.summary) summaryParts.push(result.summary);
    if (result.can_drive) summaryParts.push("**Safety:** " + result.can_drive);
    summaryParts.push("");
    summaryParts.push("You can ask me anything about this diagnosis — causes, repairs, costs, safety, or anything else.");

    wsAddBubble("assistant", summaryParts.join("\n"));

    /* Bind chat events (only once) */
    wsBindEvents();
  }

  function wsAddBubble(role, content, audioUrl) {
    const history = $("#dz-ws-chat-history");
    if (!history) return null;
    const wrap = document.createElement("div");
    wrap.className = "dz-ws-msg dz-ws-msg-" + role;
    const avatarClass = role === "assistant" ? "ai" : "user";
    const avatarIcon = role === "assistant" ? '<i class="bi bi-stars"></i>' : '<i class="bi bi-person-fill"></i>';
    const roleLabel = role === "assistant" ? "AI Mechanic" : "You";
    const id = "wsm" + Date.now() + Math.floor(Math.random() * 1e4);
    const textClass = role === "assistant" ? "dz-ws-msg-text md-body" : "dz-ws-msg-text";
    const audioHtml = audioUrl
      ? `<div class="gpt-msg-audio" style="margin-bottom:6px"><audio controls preload="metadata" src="${esc(audioUrl)}" style="max-width:100%;height:38px"></audio></div>`
      : "";
    const textContent = role === "user"
      ? (esc(content) || (audioUrl ? '<span style="opacity:.55"><i class="bi bi-mic-fill"></i> Voice message</span>' : ""))
      : wsRenderMarkdown(content);
    wrap.innerHTML = `<div class="dz-ws-msg-avatar ${avatarClass}">${avatarIcon}</div>
      <div class="dz-ws-msg-body" data-id="${id}">
        <div class="dz-ws-msg-role">${roleLabel}</div>
        ${audioHtml}
        <div class="${textClass}">${textContent}</div>
      </div>`;
    history.appendChild(wrap);
    if (role === "assistant") _wsLastAiId = id;
    wsScrollBottom();
    return wrap;
  }

  function wsAddThinking() {
    const history = $("#dz-ws-chat-history");
    if (!history) return null;
    const wrap = document.createElement("div");
    wrap.className = "dz-ws-thinking";
    wrap.id = "ws-thinking";
    wrap.innerHTML = `<div class="dz-ws-msg-avatar ai"><i class="bi bi-stars"></i></div>
      <div class="dz-ws-thinking-body">
        <div class="dz-ws-thinking-dot"></div>
        <div class="dz-ws-thinking-dot"></div>
        <div class="dz-ws-thinking-dot"></div>
      </div>`;
    history.appendChild(wrap);
    wsScrollBottom();
    return wrap;
  }

  function wsScrollBottom() {
    const history = $("#dz-ws-chat-history");
    if (history) history.scrollTop = history.scrollHeight;
  }

  function wsRenderMarkdown(text) {
    if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
      try { return DOMPurify.sanitize(marked.parse(text || "")); } catch (e) { /* fallback */ }
    }
    /* Fallback: simple paragraph wrapping + bold */
    return (text || "").split("\n\n").map(p => {
      const escaped = esc(p).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
      return "<p>" + escaped.replace(/\n/g, "<br>") + "</p>";
    }).join("");
  }

  async function wsSendMessage() {
    const input = $("#dz-ws-chat-input");
    if (!input) return;
    const message = input.value.trim();
    if (!message || _wsStreaming) return;

    wsAddBubble("user", message);
    input.value = "";
    input.style.height = "auto";

    await wsStream(message);
  }

  /* Voice note in the diagnosis workspace chat: record → attach playable audio →
     send to Gemini (transcribe + answer). Mirrors the /chat page behaviour so the
     mic keeps working at the final diagnosis stage (no re-entry needed). */
  function wsSendVoiceNote(dataUrl) {
    if (!dataUrl || _wsStreaming) return;
    wsAddBubble("user", "", dataUrl);
    wsStream("", dataUrl);
  }

  async function wsStream(message, audioUrl) {
    if (_wsStreaming) return;
    _wsStreaming = true;
    _wsController = new AbortController();

    const sendBtn = $("#dz-ws-send");
    const stopBtn = $("#dz-ws-stop");
    const input = $("#dz-ws-chat-input");
    if (sendBtn) sendBtn.classList.add("d-none");
    if (stopBtn) stopBtn.classList.remove("d-none");
    if (input) input.disabled = true;

    const thinking = wsAddThinking();
    let md = "";
    let aiId = null;
    let firstChunk = true;

    try {
      const payload = { message: message || "", chat_id: _wsChatId, provider: "gemini" };
      if (audioUrl) payload.audio_url = audioUrl;
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: _wsController.signal,
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        let r;
        try { r = await reader.read(); } catch (err) { break; }
        if (r.done) break;
        buf += decoder.decode(r.value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop();
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (data === "[DONE]") continue;
          let obj = null;
          try { obj = JSON.parse(data); } catch (e) { continue; }
          if (obj.error) {
            if (thinking) thinking.remove();
            wsAddBubble("assistant", "Sorry, I encountered an error. Please try again.");
            break;
          }
          if (obj.text) {
            md += obj.text;
            if (firstChunk) {
              firstChunk = false;
              if (thinking) thinking.remove();
              const wrap = wsAddBubble("assistant", md);
              if (wrap) {
                const body = wrap.querySelector(".dz-ws-msg-body");
                if (body) aiId = body.dataset.id;
              }
            } else if (aiId) {
              const bubble = $("#dz-ws-chat-history .dz-ws-msg-body[data-id=\"" + aiId + "\"] .dz-ws-msg-text");
              if (bubble) bubble.innerHTML = wsRenderMarkdown(md);
            }
            wsScrollBottom();
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        if (thinking) thinking.remove();
        wsAddBubble("assistant", "Sorry, something went wrong. Please try again.");
      }
    } finally {
      _wsStreaming = false;
      _wsController = null;
      if (thinking) thinking.remove();
      if (sendBtn) sendBtn.classList.remove("d-none");
      if (stopBtn) stopBtn.classList.add("d-none");
      if (input) { input.disabled = false; input.focus(); }
    }
  }

  function wsStopStream() {
    if (_wsController) _wsController.abort();
  }

  let _wsEventsBound = false;
  function wsBindEvents() {
    if (_wsEventsBound) return;
    _wsEventsBound = true;

    const form = $("#dz-ws-chat-form");
    const sendBtn = $("#dz-ws-send");
    const stopBtn = $("#dz-ws-stop");
    const input = $("#dz-ws-chat-input");
    const newBtn = $("#dz-ws-new");

    if (form) form.addEventListener("submit", (e) => { e.preventDefault(); wsSendMessage(); });
    if (sendBtn) sendBtn.addEventListener("click", wsSendMessage);
    if (stopBtn) stopBtn.addEventListener("click", wsStopStream);
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); wsSendMessage(); }
      });
      /* Auto-grow textarea */
      input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 120) + "px";
      });
    }
    if (newBtn) newBtn.addEventListener("click", () => {
      /* Reset to wizard */
      const workspace = $("#dz-workspace");
      const wizHeader = $("#dz-wizard-header");
      const mainGrid = $("#dz-main-grid");
      const benefits = $("#dz-benefits");
      if (workspace) workspace.classList.add("d-none");
      if (wizHeader) wizHeader.style.display = "";
      if (mainGrid) mainGrid.style.display = "";
      if (benefits) benefits.style.display = "";
      _wsChatId = "";
      $("#dz-new-diag").click();
    });

    /* Mic — voice notes in the workspace chat (was previously unwired, so audio
       "stopped working" at the final diagnosis stage). */
    const micBtn = $("#dz-ws-mic");
    if (micBtn) {
      const secure = window.isSecureContext ||
        ["localhost", "127.0.0.1", "[::1]"].indexOf(location.hostname) >= 0;
      const canRec = secure && navigator.mediaDevices &&
        typeof navigator.mediaDevices.getUserMedia === "function" && window.MediaRecorder;
      if (canRec) {
        let mr = null, chunks = [], micStream = null;
        micBtn.addEventListener("click", async (e) => {
          e.preventDefault();
          if (micBtn.classList.contains("recording")) {
            try { if (mr && mr.state !== "inactive") mr.stop(); } catch (_) {}
            return;
          }
          if (_wsStreaming) return;
          try { micStream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
          catch (_) { if (window.CS && CS.toast) CS.toast("error", "Microphone blocked", "Allow microphone access in your browser."); return; }
          chunks = [];
          const prefs = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
          let mime = "";
          if (window.MediaRecorder && MediaRecorder.isTypeSupported) mime = prefs.find((t) => MediaRecorder.isTypeSupported(t)) || "";
          try { mr = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream); }
          catch (_) { mr = new MediaRecorder(micStream); }
          mr.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunks.push(ev.data); };
          mr.onstop = () => {
            if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
            micBtn.classList.remove("recording");
            const i = micBtn.querySelector("i"); if (i) i.className = "bi bi-mic";
            if (!chunks.length) return;
            const blob = new Blob(chunks, { type: (mr && mr.mimeType) || "audio/webm" });
            const reader = new FileReader();
            reader.onload = () => wsSendVoiceNote(String(reader.result));
            reader.readAsDataURL(blob);
          };
          mr.start();
          micBtn.classList.add("recording");
          const i = micBtn.querySelector("i"); if (i) i.className = "bi bi-record-circle";
        });
      } else {
        micBtn.title = "Voice recording needs a secure connection (HTTPS) or localhost";
        micBtn.style.opacity = "0.4";
        micBtn.addEventListener("click", () => { if (window.CS && CS.toast) CS.toast("warning", "Voice unavailable", micBtn.title); });
      }
    }
  }

  /* ---- Helpers ---- */
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  /* ============================================================
     VOICE VEHICLE DETECTION
     ============================================================ */
  function normalizeText(text) {
    return text.toLowerCase().replace(/[^a-z0-9\s]/g, "").trim();
  }

  function detectVehicleFromSpeech(transcript) {
    const text = normalizeText(transcript);
    let detectedBrand = null;
    let detectedModel = null;

    /* Try to match brand (longest match first) */
    const sortedBrands = [...CAR_BRANDS].sort((a, b) => b.name.length - a.name.length);
    for (const brand of sortedBrands) {
      const brandName = normalizeText(brand.name);
      if (text.includes(brandName)) {
        detectedBrand = brand;
        /* Extract remaining text after brand name */
        const brandIdx = text.indexOf(brandName);
        const afterBrand = text.substring(brandIdx + brandName.length).trim();
        if (afterBrand && brand.models.length) {
          /* Try to match model (longest first, then exact) */
          const sortedModels = [...brand.models].sort((a, b) => b.length - a.length);
          for (const model of sortedModels) {
            const modelNorm = normalizeModel(model);
            if (normalizeText(model) === afterBrand || afterBrand.includes(normalizeText(model))) {
              detectedModel = model;
              break;
            }
            /* Partial match: e.g. "crv" matches "CR-V" */
            const afterNorm = normalizeModel(afterBrand);
            if (modelNorm && afterNorm && (afterNorm.includes(modelNorm) || modelNorm.includes(afterNorm))) {
              detectedModel = model;
              break;
            }
          }
        }
        break;
      }
    }

    /* If no brand found, try matching model across all brands using MODEL_INDEX */
    if (!detectedBrand) {
      for (const entry of MODEL_INDEX) {
        const modelNorm = normalizeModel(entry.model);
        const textNorm = normalizeModel(text);
        if (modelNorm && textNorm && (textNorm.includes(modelNorm) || modelNorm.includes(textNorm))) {
          detectedBrand = CAR_BRANDS.find(b => b.name === entry.brand);
          detectedModel = entry.model;
          break;
        }
      }
    }

    return { brand: detectedBrand, model: detectedModel };
  }

  function applyVoiceDetection(transcript) {
    const recordingEl = $("#dz-car-voice-recording");
    const labelEl = recordingEl ? recordingEl.querySelector(".dz-voice-label") : null;
    const textEl = $("#dz-car-voice-text");

    if (labelEl) labelEl.textContent = "Searching vehicle...";
    if (textEl) textEl.textContent = transcript;

    const result = detectVehicleFromSpeech(transcript);

    if (result.brand) {
      /* Auto-select the detected brand */
      selectBrand(result.brand.name);

      /* If model detected, auto-select it */
      if (result.model) {
        state.vehicle.model = result.model;
        const modelCard = document.querySelector(`.dz-car-model-card[data-model="${result.model}"]`);
        if (modelCard) {
          document.querySelectorAll(".dz-car-model-card").forEach(c => c.classList.remove("selected"));
          modelCard.classList.add("selected");
          const mEl = $("#dz-car-selected-model");
          if (mEl) mEl.textContent = result.model;
          updateSelectedVehicleImage(result.brand.name, result.model);
          updateInfoPanelVehicleImage(result.brand.name, result.model);
        }
      }

      /* Hide voice UI after brief delay */
      setTimeout(() => {
        if (recordingEl) recordingEl.classList.add("d-none");
        const voiceBtn = $("#dz-car-voice-btn");
        if (voiceBtn) voiceBtn.classList.remove("recording");
      }, 1200);
    } else {
      /* No match found */
      if (labelEl) labelEl.textContent = "Vehicle not recognized. Try again.";
      if (textEl) textEl.textContent = "";
      setTimeout(() => {
        if (recordingEl) recordingEl.classList.add("d-none");
        const voiceBtn = $("#dz-car-voice-btn");
        if (voiceBtn) voiceBtn.classList.remove("recording");
      }, 2000);
    }
  }

  function initVoiceInput() {
    const voiceBtn = $("#dz-car-voice-btn");
    const recordingEl = $("#dz-car-voice-recording");
    const stopBtn = $("#dz-car-voice-stop");
    const textEl = $("#dz-car-voice-text");

    if (!voiceBtn) return;

    /* Check for Speech Recognition support + secure context (HTTPS/localhost). */
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const _voiceSecure = window.isSecureContext ||
      ["localhost", "127.0.0.1", "[::1]"].indexOf(location.hostname) >= 0;
    if (!SpeechRecognition || !_voiceSecure) {
      voiceBtn.title = !SpeechRecognition
        ? "Voice input is not supported in this browser (try Chrome or Edge)."
        : "Voice input needs a secure connection (HTTPS) or localhost.";
      voiceBtn.style.opacity = "0.35";
      voiceBtn.style.cursor = "not-allowed";
      voiceBtn.addEventListener("click", () => {
        if (window.CS && CS.toast) CS.toast("warning", "Voice unavailable", voiceBtn.title);
      });
      return;
    }

    let recognition = null;
    let isRecording = false;

    voiceBtn.addEventListener("click", () => {
      if (isRecording) {
        recognition.stop();
        return;
      }

      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        isRecording = true;
        voiceBtn.classList.add("recording");
        if (recordingEl) recordingEl.classList.remove("d-none");
        const labelEl = recordingEl ? recordingEl.querySelector(".dz-voice-label") : null;
        if (labelEl) labelEl.textContent = "Listening...";
        if (textEl) textEl.textContent = "";
      };

      recognition.onresult = (e) => {
        let transcript = "";
        for (let i = 0; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript;
        }
        if (textEl) textEl.textContent = transcript;
      };

      recognition.onend = () => {
        isRecording = false;
        voiceBtn.classList.remove("recording");
        const finalText = textEl ? textEl.textContent.trim() : "";
        if (finalText) {
          applyVoiceDetection(finalText);
        } else {
          if (recordingEl) recordingEl.classList.add("d-none");
        }
      };

      recognition.onerror = (e) => {
        isRecording = false;
        voiceBtn.classList.remove("recording");
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          const labelEl = recordingEl ? recordingEl.querySelector(".dz-voice-label") : null;
          if (labelEl) labelEl.textContent = "Microphone access denied";
          setTimeout(() => { if (recordingEl) recordingEl.classList.add("d-none"); }, 2000);
        } else if (e.error !== "aborted") {
          if (recordingEl) recordingEl.classList.add("d-none");
        }
      };

      try {
        recognition.start();
      } catch (err) {
        isRecording = false;
        voiceBtn.classList.remove("recording");
        if (recordingEl) recordingEl.classList.add("d-none");
        if (window.CS && CS.toast) CS.toast("error", "Voice input failed", "Please try again.");
      }
    });

    if (stopBtn) {
      stopBtn.addEventListener("click", () => {
        if (recognition && isRecording) {
          recognition.stop();
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
