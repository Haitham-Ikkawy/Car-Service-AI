/* =====================================================================
   Car Service AI — Front-end behaviour
   Theme, sidebar, toasts, chat streaming, diagnosis, wizard, CRUD…
   ===================================================================== */
(() => {
  "use strict";

  const CS = (window.CS = {});

  /* ---------------- Helpers ---------------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (s) => {
    if (!s) return "";
    const d = new Date(String(s).replace(" ", "T"));
    if (isNaN(d)) return s;
    return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  };

  function toast(type, title, message = "", ms = 3800) {
    const icon = { success: "bi-check-circle", error: "bi-x-circle", info: "bi-info-circle", warning: "bi-exclamation-triangle" }[type] || "bi-info-circle";
    const holder = $("#toast-holder");
    if (!holder) return;
    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 shadow";
    el.setAttribute("role", "alert");
    el.innerHTML = `
      <div class="d-flex">
        <div class="toast-body d-flex gap-2 align-items-center">
          <i class="bi ${icon} fs-5 text-${type === "error" ? "danger" : type}"></i>
          <div><strong>${esc(title)}</strong>${message ? `<div class="text-soft small">${esc(message)}</div>` : ""}</div>
        </div>
        <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>`;
    holder.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: ms });
    el.addEventListener("hidden.bs.toast", () => el.remove());
    t.show();
  }
  CS.toast = toast;

  /* ---------------- i18n ---------------- */
  // Translations are injected server-side into window.CS_I18N (see i18n.js_bundle).
  CS.t = (key) => (window.CS_I18N && window.CS_I18N[key]) || key;

  /* ---------------- Theme ---------------- */
  const THEME_KEY = "cs-theme";
  function applyTheme(theme) {
    const resolved = theme === "auto" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;
    document.documentElement.setAttribute("data-bs-theme", resolved);
    document.documentElement.style.colorScheme = resolved;
    localStorage.setItem(THEME_KEY, theme || "dark");
    $$("[data-theme-icon]").forEach((i) => {
      i.className = `bi ${resolved === "dark" ? "bi-moon-stars-fill" : "bi-sun-fill"} text-soft`;
    });
  }
  CS.applyTheme = applyTheme;

  function initTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    const serverTheme = document.documentElement.dataset.serverTheme;
    applyTheme(stored || serverTheme || "dark");
    const accent = localStorage.getItem(ACCENT_KEY);
    if (accent) applyAccent(accent);
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-theme-toggle]");
    if (!btn) return;
    const current = localStorage.getItem(THEME_KEY) || "dark";
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    /* Persist to the server too so the choice survives across devices/sessions
       (fire-and-forget — the local change already applied instantly). */
    try {
      fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: next }),
      });
    } catch (_) { /* non-critical */ }
  });

  /* ---------------- Accent colour (custom theming) ---------------- */
  const ACCENT_KEY = "cs-accent";
  const ACCENT_DEFAULT = "#3b82f6";
  const ACCENT_PRESETS = {
    blue: "#3b82f6", cyan: "#06b6d4", violet: "#8b5cf6", green: "#22c55e",
    orange: "#ff7a1a", red: "#ef4444", amber: "#f59e0b",
  };
  function _hexToRgb(hex) {
    hex = String(hex || "").replace("#", "");
    if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
    const n = parseInt(hex, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function _shade(hex, amt) {
    /* amt: -1..1 (negative darkens, positive lightens) */
    const [r, g, b] = _hexToRgb(hex);
    const f = (c) => Math.max(0, Math.min(255, Math.round(c + (amt < 0 ? c : 255 - c) * amt)));
    return "#" + [f(r), f(g), f(b)].map((c) => c.toString(16).padStart(2, "0")).join("");
  }
  /* Set the whole accent family from one base colour so every token-driven
     component recolours together. Persists to localStorage; the head script
     re-applies it before first paint on the next load. */
  function applyAccent(hex) {
    if (!hex) return;
    const [r, g, b] = _hexToRgb(hex);
    const rgb = `${r}, ${g}, ${b}`;
    const s = document.documentElement.style;
    s.setProperty("--accent", hex);
    s.setProperty("--accent-rgb", rgb);
    s.setProperty("--brand", hex);
    s.setProperty("--accent-2", _shade(hex, 0.28));
    s.setProperty("--brand-hover", _shade(hex, -0.14));
    s.setProperty("--accent-soft", `rgba(${rgb}, 0.12)`);
    s.setProperty("--brand-soft", `rgba(${rgb}, 0.18)`);
    s.setProperty("--glass-border", `rgba(${rgb}, 0.10)`);
    s.setProperty("--sidebar-active", `rgba(${rgb}, 0.14)`);
    localStorage.setItem(ACCENT_KEY, hex);
  }
  function resetAccent() {
    ["--accent", "--accent-rgb", "--brand", "--accent-2", "--brand-hover",
     "--accent-soft", "--brand-soft", "--glass-border", "--sidebar-active"].forEach((v) =>
      document.documentElement.style.removeProperty(v));
    localStorage.removeItem(ACCENT_KEY);
  }
  CS.applyAccent = applyAccent;
  CS.resetAccent = resetAccent;
  CS.ACCENT_PRESETS = ACCENT_PRESETS;
  CS.ACCENT_DEFAULT = ACCENT_DEFAULT;

  /* ---------------- Accessibility (reduce motion / high contrast / text size) ----
     Applied as classes/attr on <html>. base.html sets these server-side on load;
     applyA11y() lets the Settings page reflect changes instantly. */
  function applyA11y(a) {
    a = a || {};
    const el = document.documentElement;
    if ("reduce_motion" in a) el.classList.toggle("a11y-reduce-motion", !!a.reduce_motion);
    if ("high_contrast" in a) el.classList.toggle("a11y-high-contrast", !!a.high_contrast);
    if ("font_size" in a) el.setAttribute("data-font-size", a.font_size || "normal");
  }
  CS.applyA11y = applyA11y;

  /* ---------------- Sidebar (mobile) ---------------- */
  function initSidebar() {
    const sidebar = $(".sidebar");
    const backdrop = $(".sidebar-backdrop");
    if (!sidebar) return;
    const open = () => { sidebar.classList.add("open"); backdrop?.classList.add("show"); };
    const close = () => { sidebar.classList.remove("open"); backdrop?.classList.remove("show"); };
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-sidebar-toggle]")) open();
      if (e.target.closest(".sidebar-backdrop")) close();
      if (e.target.closest(".sidebar-link")) close();
    });
  }

  /* ---------------- Sidebar hover-to-expand (desktop) — DISABLED ---------------- */
  function initHoverSidebar() {
    /* Sidebar is now permanently expanded on desktop. No hover behavior needed. */
  }

  /* ---------------- Sidebar tooltips (collapsed rail, desktop) — DISABLED ---------------- */
  function initSidebarTooltips() {
    /* Sidebar is now permanently expanded. No tooltips needed. */
  }

  /* ---------------- Count up ---------------- */
  function initCountUp() {
    $$("[data-count]").forEach((el) => {
      const target = parseFloat(el.dataset.count || "0");
      const dur = 500;
      const t0 = performance.now();
      const step = (t) => {
        const p = Math.min((t - t0) / dur, 1);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased).toLocaleString();
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  /* ---------------- Splash ---------------- */
  /* ---------------- Home Page (Splash) ---------------- */
  function initSplash() {
    const video = $("#hp-video");
    if (!video) return;

    /* --- Interactive video: mouse horizontal + scroll scrubbing --- */
    const hero = $("#hp-hero");
    if (!hero || !video) return;

    let targetTime = 0;
    let currentMouseX = 0.5; // 0..1 normalized
    let videoReady = false;

    // Wait for video metadata so duration is available
    video.addEventListener("loadedmetadata", () => { videoReady = true; });
    video.addEventListener("canplay", () => { videoReady = true; });
    // Also try to play so currentTime is settable
    video.play().then(() => { video.pause(); video.currentTime = 0; videoReady = true; }).catch(() => {});

    /* Mouse horizontal movement: left = start, right = end */
    hero.addEventListener("mousemove", (e) => {
      if (!videoReady || !video.duration) return;
      currentMouseX = e.clientX / window.innerWidth;
      targetTime = currentMouseX * video.duration;
    });

    /* Scroll scrubbing disabled — use native page scroll.
       Re-enable only when the hero video is visible again. */

    /* --- AI Core 3D parallax (smooth lerp) --- */
    const aiCoreEl = document.getElementById("ai-core");
    if (aiCoreEl) {
      const aiRig = document.getElementById("ai-core-rig");
      if (aiRig) {
        let mouseX = 0, mouseY = 0, curX = 0, curY = 0;
        const lerp = 0.12;
        const maxTilt = 18;
        let coreVisible = true;

        const coreObs = new IntersectionObserver((entries) => {
          coreVisible = entries[0].isIntersecting;
        }, { threshold: 0.1 });
        coreObs.observe(aiCoreEl);

        document.addEventListener("mousemove", (ev) => {
          if (!coreVisible) return;
          const r = aiCoreEl.getBoundingClientRect();
          mouseX = ((ev.clientX - r.left) / r.width - 0.5) * maxTilt;
          mouseY = ((ev.clientY - r.top) / r.height - 0.5) * -maxTilt;
        }, { passive: true });

        function coreTick() {
          if (document.hidden || !coreVisible) {
            requestAnimationFrame(coreTick);
            return;
          }
          curX += (mouseX - curX) * lerp;
          curY += (mouseY - curY) * lerp;
          aiRig.style.transform =
            "translateY(" + (-14 * Math.sin(Date.now() / 1000 * Math.PI / 3)) + "px) " +
            "rotateX(" + (12 + curY) + "deg) " +
            "rotateY(" + curX + "deg)";
          requestAnimationFrame(coreTick);
        }
        requestAnimationFrame(coreTick);
      }
    }

    /* Smooth interpolation loop — paused when tab hidden */
    let heroRafId = null;
    function heroTick() {
      if (document.hidden) { heroRafId = null; return; }
      if (videoReady && video.duration) {
        const diff = targetTime - video.currentTime;
        if (Math.abs(diff) > 0.005) {
          video.currentTime += diff * 0.12;
        }
      }
      heroRafId = requestAnimationFrame(heroTick);
    }
    heroRafId = requestAnimationFrame(heroTick);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && heroRafId == null) heroRafId = requestAnimationFrame(heroTick);
    }, { passive: true });

    /* Nav background handled by .scrolled class in initSplash */

    /* Smooth anchor scrolling */
    document.querySelectorAll('a[href^="#"]').forEach((a) => {
      a.addEventListener("click", (e) => {
        const id = a.getAttribute("href");
        if (!id || id === "#") return;
        const target = document.querySelector(id);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    /* ---- 3D Ring Carousel ---- */
    const ringEl = $("#ring3d-ring");
    const ringViewport = $(".ring3d-viewport");
    const dotsContainer = $("#ring3d-dots");
    if (ringEl && ringViewport) {
      const cards = Array.from(ringEl.querySelectorAll(".ring3d-card"));
      const dots = dotsContainer ? Array.from(dotsContainer.querySelectorAll(".ring3d-dot")) : [];
      const TOTAL = cards.length;
      const ANGLE_STEP = 360 / TOTAL;
      const RADIUS = 200;
      const DISPLAY_MS = 5000;
      const RESUME_DELAY_MS = 2000;
      let currentIndex = 0;
      let autoTimer = null;
      let resumeTimer = null;
      let isDragging = false;
      let dragStartX = 0;
      let dragDelta = 0;
      let isHovered = false;

      function applyCardTransforms(ringAngle) {
        cards.forEach((card, i) => {
          const angle = (ANGLE_STEP * i) + ringAngle;
          const rad = (angle * Math.PI) / 180;
          const x = Math.sin(rad) * RADIUS;
          const z = Math.cos(rad) * RADIUS;
          const normZ = (z + RADIUS) / (2 * RADIUS);
          const scale = 0.55 + normZ * 0.5;
          const opacity = 0.15 + normZ * 0.85;
          const rotY = -angle * 0.3;
          card.style.transform =
            `translate3d(${x}px, 0, ${z}px) rotateY(${rotY}deg) scale(${scale})`;
          card.style.opacity = opacity;
          card.style.zIndex = Math.round(normZ * 100);
          const isPrimary = normZ > 0.92;
          const isSecondary = normZ > 0.4 && normZ <= 0.92;
          card.classList.toggle("is-primary", isPrimary);
          card.classList.toggle("is-secondary", isSecondary);
        });
      }

      function goTo(index) {
        currentIndex = ((index % TOTAL) + TOTAL) % TOTAL;
        const targetAngle = -(ANGLE_STEP * currentIndex);
        ringEl.style.transform = `translateZ(${-RADIUS}px) rotateY(${targetAngle}deg)`;
        applyCardTransforms(targetAngle);
        dots.forEach((d, i) => d.classList.toggle("active", i === currentIndex));
      }

      function next() { goTo(currentIndex + 1); }

      function startAuto() {
        stopAuto();
        autoTimer = setInterval(next, DISPLAY_MS);
      }

      function stopAuto() {
        if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
      }

      function pauseAndScheduleResume() {
        stopAuto();
        clearTimeout(resumeTimer);
        resumeTimer = setTimeout(() => {
          if (!isHovered && !isDragging) startAuto();
        }, RESUME_DELAY_MS);
      }

      /* Hover pause on any card */
      cards.forEach((card) => {
        card.addEventListener("mouseenter", () => {
          isHovered = true;
          stopAuto();
          clearTimeout(resumeTimer);
        });
        card.addEventListener("mouseleave", () => {
          isHovered = false;
          clearTimeout(resumeTimer);
          resumeTimer = setTimeout(() => {
            if (!isHovered && !isDragging) startAuto();
          }, RESUME_DELAY_MS);
        });
      });

      /* Dot navigation */
      dots.forEach((d) => d.addEventListener("click", () => {
        goTo(parseInt(d.dataset.dot, 10));
        pauseAndScheduleResume();
      }));

      /* Mouse drag */
      ringViewport.addEventListener("mousedown", (e) => {
        isDragging = true;
        dragStartX = e.clientX;
        dragDelta = 0;
        stopAuto();
        e.preventDefault();
      });
      window.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        dragDelta = e.clientX - dragStartX;
      });
      window.addEventListener("mouseup", () => {
        if (!isDragging) return;
        isDragging = false;
        if (Math.abs(dragDelta) > 40) {
          dragDelta > 0 ? goTo(currentIndex - 1) : goTo(currentIndex + 1);
          pauseAndScheduleResume();
        }
        dragDelta = 0;
      });

      /* Touch swipe */
      let touchStartX = 0;
      ringViewport.addEventListener("touchstart", (e) => {
        touchStartX = e.touches[0].clientX;
        stopAuto();
      }, { passive: true });
      ringViewport.addEventListener("touchend", (e) => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(dx) > 40) {
          dx > 0 ? goTo(currentIndex - 1) : goTo(currentIndex + 1);
          pauseAndScheduleResume();
        } else {
          pauseAndScheduleResume();
        }
      });

      /* Mouse wheel over carousel — allow page scroll to pass through */
      ringViewport.addEventListener("wheel", (e) => {
        if (Math.abs(e.deltaY) > 15) {
          e.deltaY > 0 ? goTo(currentIndex + 1) : goTo(currentIndex - 1);
          pauseAndScheduleResume();
        }
      }, { passive: true });

      /* Init */
      goTo(0);
      startAuto();
    }

    /* ---- Feature Cards — grid + inner 3D tilt ---- */
    const feat2Grid = document.getElementById("feat2-grid");
    if (feat2Grid) {
      const feat2Cards = Array.from(feat2Grid.querySelectorAll(".feat2-card"));
      const isMobile2 = () => window.innerWidth < 576;

      feat2Cards.forEach((card) => {
        const inner = card.querySelector(".feat2-inner");
        if (!inner) return;

        card.addEventListener("mousemove", (e) => {
          if (isMobile2()) return;
          const rect = card.getBoundingClientRect();
          const x = (e.clientX - rect.left) / rect.width - 0.5;
          const y = (e.clientY - rect.top) / rect.height - 0.5;
          const rotateY = x * 8;
          const rotateX = -y * 5;
          inner.style.transform =
            `perspective(800px) translateZ(30px) rotateY(${rotateY}deg) rotateX(${rotateX}deg) scale(1.04)`;
          inner.style.transition = "transform 0.15s ease-out, filter 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease";
          card.classList.add("is-hovered");
        });

        card.addEventListener("mouseleave", () => {
          if (isMobile2()) return;
          inner.style.transform = "perspective(800px) translateZ(0) rotateY(0deg) rotateX(0deg) scale(1)";
          inner.style.transition = "transform 0.6s cubic-bezier(0.22, 1, 0.36, 1), filter 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease";
          card.classList.remove("is-hovered");
        });
      });
    }

    /* ---- Deck of Cards — viewport trigger + spread ---- */
    const deckScene = document.getElementById("deck-scene");
    if (deckScene) {
      const deckCards = Array.from(deckScene.querySelectorAll(".deck-card"));
      const isMobile = () => window.innerWidth < 576;

      /* IntersectionObserver triggers the spread once */
      let hasSpread = false;
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasSpread && !isMobile()) {
            hasSpread = true;
            setTimeout(() => deckScene.classList.add("is-spread"), 150);
          }
        });
      }, { threshold: 0.1 });
      observer.observe(deckScene);

      /* On mobile, just show spread immediately (no 3D tilt needed) */
      if (isMobile()) {
        deckScene.classList.add("is-spread");
      }

      /* ---- Smooth lerp-based 3D tilt on each card ---- */
      const LERP = 0.14;
      const MAX_RX = 3;
      const MAX_RY = 4;
      const spreadTransforms = [
        { tz: 0, ry: -2 },
        { tz: 16, ry: 0 },
        { tz: 0, ry: 2 }
      ];

      /* Attach state objects to each card FIRST */
      deckCards.forEach(card => {
        card._deck = { rx: 0, ry: 0, tz: parseInt(card.dataset.card, 10) === 1 ? 16 : 10, hovered: false, mouseX: 0.5, mouseY: 0.5 };
      });

      /* Event listeners use card._deck */
      deckCards.forEach((card) => {
        const d = card._deck;

        card.addEventListener("mouseenter", () => {
          if (!deckScene.classList.contains("is-spread")) return;
          d.hovered = true;
          card.classList.add("is-hovered");
        });

        card.addEventListener("mousemove", (e) => {
          if (!d.hovered) return;
          const rect = card.getBoundingClientRect();
          d.mouseX = (e.clientX - rect.left) / rect.width;
          d.mouseY = (e.clientY - rect.top) / rect.height;
        });

        card.addEventListener("mouseleave", () => {
          d.hovered = false;
          card.classList.remove("is-hovered");
        });
      });

      /* rAF loop uses card._deck — same object */
      const isTouchDevice = () => window.matchMedia("(hover: none) and (pointer: coarse)").matches;
      function tickDeck() {
        if (isTouchDevice()) return;
        deckCards.forEach((card) => {
          const d = card._deck;
          const idx = parseInt(card.dataset.card, 10);
          const spread = spreadTransforms[idx];

          let targetRX, targetRY, targetTZ;
          if (d.hovered) {
            const dx = d.mouseX - 0.5;
            const dy = d.mouseY - 0.5;
            targetRX = -dy * MAX_RX * 2;
            targetRY = dx * MAX_RY * 2;
            targetTZ = 40;
          } else {
            targetRX = 0;
            targetRY = spread.ry;
            targetTZ = spread.tz;
          }

          d.rx += (targetRX - d.rx) * LERP;
          d.ry += (targetRY - d.ry) * LERP;
          d.tz += (targetTZ - d.tz) * LERP;

          const rx = Math.abs(d.rx) < 0.01 ? 0 : d.rx;
          const ry = Math.abs(d.ry) < 0.01 ? 0 : d.ry;
          const tz = Math.abs(d.tz - spread.tz) < 0.1 && !d.hovered ? spread.tz : d.tz;

          card.style.transform =
            `translateY(${d.hovered ? -6 : 0}px) translateZ(${tz}px) rotateY(${ry}deg) rotateX(${rx}deg)${d.hovered ? ' scale(1.015)' : ''}`;
        });
        requestAnimationFrame(tickDeck);
      }
      requestAnimationFrame(tickDeck);
    }
  }

  /* ---------------- Markdown ---------------- */
  function renderMarkdown(md) {
    if (!window.marked) return esc(md);
    let html;
    try {
      html = marked.parse(md || "", { breaks: true, gfm: true });
      html = DOMPurify ? DOMPurify.sanitize(html) : html;
    } catch (e) {
      html = esc(md);
    }
    return html;
  }

  /* ---------------- Chat ---------------- */
  function initChat() {
    const shell = $("#gpt-main");
    if (!shell) return;
    if (shell.dataset.chatInit) return;
    shell.dataset.chatInit = "1";

    const form = $("#chat-form");
    const input = $("#chat-input");
    const historyEl = $("#chat-history");
    const sendBtn = $("#chat-send");
    const stopBtn = $("#chat-stop");
    const newBtn = $("#chat-new");
    const clearBtn = $("#chat-clear");
    const prompts = $$(".gpt-suggestion");
    const historyList = $("#chat-history-list");
    const sideSearch = $("#chat-side-search");
    const side = $("#gpt-side");
    const sideToggle = $("#gpt-side-toggle");
    const topbarToggle = $("#gpt-topbar-toggle");
    const topbarNew = $("#chat-topbar-new");
    const topbarClear = $("#chat-topbar-clear");
    const imgInput = $("#gpt-img-input");
    const imgPreview = $("#gpt-img-preview");
    const imgThumb = $("#gpt-img-thumb");
    const imgRemove = $("#gpt-img-remove");
    const micBtn = $("#gpt-mic");
    let chatId = document.documentElement.dataset.chatId || "";
    let streaming = false;
    let controller = null;
    let lastAiId = null;
    let attachedImage = null;
    let recognition = null;
    let currentProvider = "gemini";

    /* Opened with an existing conversation (e.g. "Continue Chat" from a diagnosis):
       hide the welcome + marketing visual panel so the chat is full-width and the
       diagnosis result (the first message) stays cleanly visible (item 5). */
    (function () {
      const msgs = $("#chat-messages");
      if (msgs && msgs.children.length > 0) {
        const welcome = $("#gpt-welcome");
        if (welcome) welcome.style.display = "none";
        const visual = $("#gpt-chat-visual");
        /* If the panel holds a diagnosis result, keep it visible (don't collapse). */
        if (visual && visual.dataset.hasDiagnosis === "1") return;
        const layout = $(".gpt-chat-layout");
        if (visual) visual.classList.add("chat-active");
        if (layout) layout.classList.add("chat-active");
      }
    })();

    /* Model selector dropdown */
    const modelBtn = $("#gpt-model-btn");
    const modelDropdown = $("#gpt-model-dropdown");
    const modelOptions = $$(".gpt-model-option");
    if (modelBtn && modelDropdown) {
      modelBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        modelDropdown.classList.toggle("show");
      });
      document.addEventListener("click", () => modelDropdown.classList.remove("show"));
      modelOptions.forEach((opt) => {
        opt.addEventListener("click", () => {
          modelOptions.forEach((o) => o.classList.remove("active"));
          opt.classList.add("active");
          currentProvider = opt.dataset.provider;
          const label = modelBtn.querySelector(".gpt-model-label");
          if (label) label.textContent = opt.querySelector("span").textContent;
          modelDropdown.classList.remove("show");
        });
      });
    }

    /* Sidebar toggle */
    const backdrop = document.querySelector(".sidebar-backdrop");
    const gptOverlay = document.getElementById("gpt-side-overlay");
    /* Auto-collapse on mobile */
    if (side && window.innerWidth < 992) side.classList.add("collapsed");
    function toggleSide() {
      if (!side) return;
      side.classList.toggle("collapsed");
      if (window.innerWidth < 992) {
        const isOpen = !side.classList.contains("collapsed");
        if (backdrop) backdrop.classList.toggle("show", isOpen);
        if (gptOverlay) gptOverlay.classList.toggle("visible", isOpen);
        document.body.style.overflow = isOpen ? "hidden" : "";
      }
    }
    sideToggle?.addEventListener("click", toggleSide);
    topbarToggle?.addEventListener("click", toggleSide);
    if (backdrop) backdrop.addEventListener("click", () => {
      side.classList.add("collapsed");
      backdrop.classList.remove("show");
      if (gptOverlay) gptOverlay.classList.remove("visible");
      document.body.style.overflow = "";
    });
    if (gptOverlay) gptOverlay.addEventListener("click", () => {
      side.classList.add("collapsed");
      gptOverlay.classList.remove("visible");
      if (backdrop) backdrop.classList.remove("show");
      document.body.style.overflow = "";
    });

    const scrollBottom = () => { if (historyEl) historyEl.scrollTop = historyEl.scrollHeight; };
    const fmtTime = (s) => {
      if (!s) return "";
      const d = new Date(String(s).replace(" ", "T"));
      if (isNaN(d)) return s;
      return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    };
    const toggleStop = (show) => {
      if (stopBtn) stopBtn.classList.toggle("d-none", !show);
      if (sendBtn) sendBtn.classList.toggle("d-none", show);
    };

    const actionsRow = (id, includeRegen = true) => `
      <div class="gpt-msg-actions" style="display:flex;gap:6px;margin-top:8px;">
        <button class="gpt-action-btn" title="${esc(CS.t("Copy response"))}" data-act="copy" data-id="${id}"><i class="bi bi-clipboard"></i></button>
        <button class="gpt-action-btn" title="${esc(CS.t("Download response"))}" data-act="download" data-id="${id}"><i class="bi bi-download"></i></button>
        ${includeRegen ? `<button class="gpt-action-btn" title="${esc(CS.t("Regenerate response"))}" data-act="regen" data-id="${id}"><i class="bi bi-arrow-repeat"></i></button>` : ""}
      </div>`;

    function addBubble(role, content, { ts = "", regen = role === "assistant", image = null } = {}) {
      const wrap = document.createElement("div");
      wrap.className = `dz-ws-msg dz-ws-msg-${role}`;
      const avatar = role === "user"
        ? `<div class="dz-ws-msg-avatar user"><i class="bi bi-person-fill"></i></div>`
        : `<div class="dz-ws-msg-avatar ai"><i class="bi bi-stars"></i></div>`;
      const id = "m" + Date.now() + Math.floor(Math.random() * 1e4);
      const imgHtml = image ? `<div class="gpt-msg-image"><img src="${esc(image)}" alt="Attached image" style="max-height:180px;border-radius:10px;margin-bottom:6px"></div>` : "";
      const roleLabel = role === "assistant" ? CS.t("AI Mechanic") : CS.t("You");
      wrap.innerHTML = `${avatar}
        <div class="dz-ws-msg-body" data-id="${id}">
          <div class="dz-ws-msg-role">${esc(roleLabel)}</div>
          ${imgHtml}
          <div class="dz-ws-msg-text ${role === "assistant" ? "md-body" : ""}">${role === "user" ? esc(content) : renderMarkdown(content)}</div>
          ${ts ? `<div class="dz-ws-msg-time" style="font-size:0.62rem;color:rgba(255,255,255,0.18);margin-top:4px;">${esc(fmtTime(ts))}</div>` : ""}
          ${role === "assistant" ? actionsRow(id, regen) : ""}
        </div>`;
      historyEl.appendChild(wrap);
      if (role === "assistant") lastAiId = id;
      return wrap;
    }

    function addThinking() {
      const wrap = document.createElement("div");
      wrap.className = "dz-ws-thinking";
      wrap.id = "thinking-msg";
      wrap.innerHTML = `<div class="dz-ws-msg-avatar ai"><i class="bi bi-stars"></i></div>
        <div class="dz-ws-thinking-body">
          <div class="dz-ws-thinking-dot"></div>
          <div class="dz-ws-thinking-dot"></div>
          <div class="dz-ws-thinking-dot"></div>
        </div>`;
      historyEl.appendChild(wrap);
      scrollBottom();
      return wrap;
    }

    function setActions(id, show) {
      const body = historyEl.querySelector(`.dz-ws-msg-body[data-id="${id}"]`);
      if (!body) return;
      const row = body.querySelector(".gpt-msg-actions");
      if (row) row.style.opacity = show ? "1" : "";
    }

    function markLatestRegen() {
      const ais = $$(".dz-ws-msg-assistant .dz-ws-msg-body", historyEl);
      ais.forEach((b) => {
        const btn = b.querySelector('[data-act="regen"]');
        if (btn) btn.classList.toggle("d-none", b !== ais[ais.length - 1]);
      });
    }

    /* --- Image attach --- */
    function clearImage() {
      attachedImage = null;
      if (imgInput) imgInput.value = "";
      if (imgPreview) imgPreview.style.display = "none";
    }
    imgInput?.addEventListener("change", () => {
      const file = imgInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        attachedImage = e.target.result;
        if (imgThumb) imgThumb.src = attachedImage;
        if (imgPreview) imgPreview.style.display = "block";
      };
      reader.readAsDataURL(file);
    });
    imgRemove?.addEventListener("click", clearImage);

    /* --- Voice input (Web Speech API) --- */
    /* Requires a secure context (HTTPS) or localhost — otherwise start() fails. */
    const _voiceSecure = window.isSecureContext ||
      ["localhost", "127.0.0.1", "[::1]"].indexOf(location.hostname) >= 0;
    if (micBtn && _voiceSecure && ("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognition = new SR();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";
      let lastTranscript = "";
      const recBar = document.getElementById("gpt-recording-bar");
      const recTimer = document.getElementById("gpt-rec-timer");
      const recStop = document.getElementById("gpt-rec-stop");
      let recInterval = null;
      let recSeconds = 0;

      function showRecBar() {
        recSeconds = 0;
        if (recTimer) recTimer.textContent = "0:00";
        if (recBar) {
          recBar.classList.add("visible");
        }
        recInterval = setInterval(() => {
          recSeconds++;
          const m = Math.floor(recSeconds / 60);
          const s = (recSeconds % 60).toString().padStart(2, "0");
          if (recTimer) recTimer.textContent = m + ":" + s;
        }, 1000);
      }
      function hideRecBar() {
        clearInterval(recInterval);
        recInterval = null;
        if (recBar) {
          recBar.classList.remove("visible");
        }
      }

      recognition.onresult = (e) => {
        let transcript = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript;
        }
        lastTranscript = transcript;
        input.value = transcript;
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 160) + "px";
      };
      const resetMic = () => {
        micBtn.classList.remove("recording");
        micBtn.querySelector("i").className = "bi bi-mic";
        hideRecBar();
      };
      recognition.onend = () => {
        resetMic();
        if (lastTranscript.trim()) {
          input.value = lastTranscript.trim();
          lastTranscript = "";
          setTimeout(() => form.requestSubmit(), 150);
        }
      };
      recognition.onerror = (e) => {
        resetMic();
        lastTranscript = "";
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          toast("error", CS.t("Microphone blocked"), CS.t("Allow microphone access in your browser settings."));
        } else if (e.error !== "aborted") {
          toast("error", CS.t("Voice input failed"), CS.t("Please try again."));
        }
      };
      micBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        if (micBtn.classList.contains("recording")) {
          recognition.stop();
        } else {
          lastTranscript = "";
          try {
            recognition.start();
          } catch (err) {
            /* start() throws if already running or on an insecure origin. */
            toast("error", CS.t("Voice input failed"), CS.t("Please try again."));
            return;
          }
          micBtn.classList.add("recording");
          micBtn.querySelector("i").className = "bi bi-record-circle";
          showRecBar();
        }
      });
      recStop?.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        if (micBtn.classList.contains("recording")) recognition.stop();
      });
    } else if (micBtn) {
      const reason = _voiceSecure
        ? CS.t("Voice input not supported in this browser")
        : CS.t("Voice input needs a secure connection (HTTPS) or localhost.");
      micBtn.title = reason;
      micBtn.style.opacity = "0.35";
      micBtn.style.cursor = "not-allowed";
      micBtn.addEventListener("click", () => toast("warning", CS.t("Voice unavailable"), reason));
    }

    /* --- Stream --- */
    async function stream(payload) {
      if (streaming) return;
      streaming = true;
      controller = new AbortController();
      sendBtn.disabled = true;
      toggleStop(true);
      const thinking = addThinking();
      const streamOn = localStorage.getItem("cs-streaming") !== "0";
      let md = "";
      let aiId = null;
      let firstChunk = true;
      let aborted = false;
      let failed = false;
      const renderFull = () => {
        thinking.remove();
        if (firstChunk) firstChunk = false;
        const wrap = addBubble("assistant", md);
        aiId = wrap.querySelector(".dz-ws-msg-body").dataset.id;
        setActions(aiId, true);
        scrollBottom();
      };
      try {
        const res = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          thinking.remove();
          toast("error", CS.t("Chat failed"), data.error || CS.t("Please try again."));
          failed = true;
        } else {
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          while (true) {
            let r;
            try { r = await reader.read(); } catch (err) { aborted = true; break; }
            if (r.done) break;
            buf += decoder.decode(r.value, { stream: true });
            const parts = buf.split("\n\n");
            buf = parts.pop();
            for (const part of parts) {
              const line = part.trim();
              if (!line.startsWith("data:")) continue;
              const data = line.slice(5).trim();
              if (data === "[DONE]") {
                if (!streamOn && md && !aiId) renderFull();
                continue;
              }
              let obj = null;
              try { obj = JSON.parse(data); } catch (e) { continue; }
              if (obj.error) {
                thinking.remove();
                failed = true;
                addBubble("assistant", obj.error, { regen: false });
                scrollBottom();
                input.focus();
                markLatestRegen();
                return;
              }
              if (obj.text) {
                md += obj.text;
                if (streamOn) {
                  if (firstChunk) {
                    firstChunk = false;
                    thinking.remove();
                    const wrap = addBubble("assistant", md);
                    const body = wrap.querySelector(".dz-ws-msg-body");
                    aiId = body.dataset.id;
                    setActions(aiId, true);
                  } else if (aiId) {
                    const bubble = historyEl.querySelector(`.dz-ws-msg-body[data-id="${aiId}"] .dz-ws-msg-text`);
                    if (bubble) bubble.innerHTML = renderMarkdown(md);
                  }
                } else if (firstChunk) {
                  firstChunk = false;
                  scrollBottom();
                }
                scrollBottom();
              }
            }
          }
        }
      } catch (err) {
        if (err && err.name === "AbortError") aborted = true;
        else { thinking.remove(); toast("error", CS.t("Chat failed"), err?.message || CS.t("Please try again.")); }
      } finally {
        streaming = false;
        controller = null;
        sendBtn.disabled = false;
        toggleStop(false);
        if (aborted && !streamOn && md && !aiId) renderFull();
        if (firstChunk && !failed) thinking.remove();
        if (!aborted && !failed) markLatestRegen();
        input.focus();
        updateHistoryList();
      }
    }

    /* --- Submit --- */
    function hideVisualPanel() {
      /* No-op in new dz-ws layout — visual panel is not present */
    }
    function showVisualPanel() {
      /* No-op in new dz-ws layout — visual panel is not present */
    }
    function sendMessage() {
      const message = input.value.trim();
      if ((!message && !attachedImage) || streaming) return;
      const welcome = $("#gpt-welcome");
      if (welcome) welcome.style.display = "none";
      hideVisualPanel();
      addBubble("user", message, { image: attachedImage });
      const payload = { message, chat_id: chatId, provider: currentProvider };
      if (attachedImage) payload.image_url = attachedImage;
      clearImage();
      input.value = "";
      input.style.height = "auto";
      stream(payload);
    }

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    });

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      sendMessage();
    });

    stopBtn?.addEventListener("click", () => { if (controller) controller.abort(); });

    /* --- Message actions --- */
    historyEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      const id = btn.dataset.id;
      const body = historyEl.querySelector(`.dz-ws-msg-body[data-id="${id}"]`);
      const bubble = body?.querySelector(".dz-ws-msg-text");
      const text = bubble ? bubble.innerText : "";
      if (btn.dataset.act === "copy") {
        navigator.clipboard?.writeText(text).then(() => toast("success", CS.t("Copied"), CS.t("Response copied to clipboard."))).catch(() => toast("error", CS.t("Copy failed")));
      } else if (btn.dataset.act === "download") {
        const blob = new Blob([text], { type: "text/markdown" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `car-ai-response-${id}.md`;
        a.click();
        URL.revokeObjectURL(a.href);
        toast("success", CS.t("Downloaded"), CS.t("Response saved as Markdown."));
      } else if (btn.dataset.act === "regen") {
        const aiMsg = body?.closest(".dz-ws-msg-assistant");
        if (aiMsg) aiMsg.remove();
        stream({ message: "", chat_id: chatId, regenerate: true });
      }
    });

    /* --- New chat --- */
    async function doNewChat() {
      const res = await fetch("/api/chat/new", { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        chatId = data.id;
        document.documentElement.dataset.chatId = chatId;
        historyEl.innerHTML = "";
        lastAiId = null;
        updateHistoryList();
        const welcome = $("#gpt-welcome");
        if (welcome) welcome.style.display = "";
        showVisualPanel();
        input.focus();
      }
    }
    newBtn?.addEventListener("click", doNewChat);
    topbarNew?.addEventListener("click", doNewChat);

    /* --- Clear chat --- */
    async function doClear() {
      if (!chatId) return;
      if (!confirm(CS.t("Clear this conversation? The thread stays, all messages are removed."))) return;
      const res = await fetch("/api/chat/clear", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: chatId }),
      });
      if (res.ok) {
        historyEl.innerHTML = "";
        lastAiId = null;
        const welcome = $("#gpt-welcome");
        if (welcome) welcome.style.display = "";
        showVisualPanel();
        toast("success", CS.t("Conversation cleared"));
      }
    }
    clearBtn?.addEventListener("click", doClear);
    topbarClear?.addEventListener("click", doClear);

    /* --- Search --- */
    sideSearch?.addEventListener("input", () => {
      updateHistoryList(); // re-render with filter
    });

    /* --- Prompt chips --- */
    prompts.forEach((p) => p.addEventListener("click", () => {
      input.value = p.dataset.prompt || p.innerText.trim();
      input.dispatchEvent(new Event("input"));
      input.focus();
      setTimeout(() => form.requestSubmit(), 80);
    }));

    /* --- Textarea autosize --- */
    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 160) + "px";
    });

    /* --- History list --- */
    if (historyList) {
      historyList.addEventListener("click", async (e) => {
        /* Context menu (⋯ button) */
        const menuBtn = e.target.closest("[data-chat-menu]");
        if (menuBtn) {
          e.stopPropagation();
          const chatIdTarget = menuBtn.dataset.chatMenu;
          const existing = document.querySelector(`.gpt-side-menu[data-for="${chatIdTarget}"]`);
          document.querySelectorAll(".gpt-side-menu").forEach(m => m.remove());
          if (existing) return;
          const menu = document.createElement("div");
          menu.className = "gpt-side-menu";
          menu.dataset.for = chatIdTarget;
          menu.innerHTML = `
            <button class="gpt-side-menu-item" data-menu-open="${chatIdTarget}"><i class="bi bi-box-arrow-in-right"></i> Open</button>
            <button class="gpt-side-menu-item" data-menu-rename="${chatIdTarget}"><i class="bi bi-pencil"></i> Rename</button>
            <button class="gpt-side-menu-divider"></button>
            <button class="gpt-side-menu-item gpt-side-menu-danger" data-menu-delete="${chatIdTarget}"><i class="bi bi-trash"></i> Delete</button>`;
          menuBtn.parentElement.style.position = "relative";
          menuBtn.parentElement.appendChild(menu);
          const closeMenu = (ev) => { if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener("click", closeMenu); } };
          setTimeout(() => document.addEventListener("click", closeMenu), 10);
          return;
        }
        /* Menu actions */
        const openItem = e.target.closest("[data-menu-open]");
        if (openItem) {
          const targetId = openItem.dataset.menuOpen;
          document.querySelectorAll(".gpt-side-menu").forEach(m => m.remove());
          await selectChat(targetId);
          return;
        }
        const renameItem = e.target.closest("[data-menu-rename]");
        if (renameItem) {
          const targetId = renameItem.dataset.menuRename;
          document.querySelectorAll(".gpt-side-menu").forEach(m => m.remove());
          showRenameDialog(targetId);
          return;
        }
        const deleteItem = e.target.closest("[data-menu-delete]");
        if (deleteItem) {
          const targetId = deleteItem.dataset.menuDelete;
          document.querySelectorAll(".gpt-side-menu").forEach(m => m.remove());
          showDeleteDialog(targetId);
          return;
        }
        /* Legacy delete button */
        const del = e.target.closest("[data-del-chat]");
        if (del) {
          e.stopPropagation();
          showDeleteDialog(del.dataset.delChat);
          return;
        }
        /* Select chat */
        const item = e.target.closest("[data-chat]");
        if (!item) return;
        await selectChat(item.dataset.chat);
      });
    }

    async function selectChat(targetId) {
      const res = await fetch("/api/chat/select", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: targetId }),
      });
      const data = await res.json();
      if (!data.ok) return;
      chatId = data.id;
      document.documentElement.dataset.chatId = chatId;
      historyEl.innerHTML = "";
      lastAiId = null;
      const welcome = $("#gpt-welcome");
      if (welcome) welcome.style.display = "none";
      hideVisualPanel();
      data.messages.forEach((m) => addBubble(m.role, m.content, { ts: m.ts, regen: false }));
      markLatestRegen();
      scrollBottom();
      updateHistoryList();
      if (window.innerWidth < 992 && side) side.classList.add("collapsed");
    }

    function showDeleteDialog(targetId) {
      const overlay = document.createElement("div");
      overlay.className = "gpt-dialog-overlay";
      overlay.innerHTML = `
        <div class="gpt-dialog">
          <div class="gpt-dialog-header">
            <div class="gpt-dialog-icon gpt-dialog-icon--danger"><i class="bi bi-trash"></i></div>
            <h3 class="gpt-dialog-title">Delete conversation?</h3>
          </div>
          <p class="gpt-dialog-text">This conversation and its messages will be permanently removed.</p>
          <div class="gpt-dialog-actions">
            <button class="gpt-dialog-btn gpt-dialog-btn--ghost" id="gpt-dialog-cancel">Cancel</button>
            <button class="gpt-dialog-btn gpt-dialog-btn--danger" id="gpt-dialog-confirm">Delete</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      requestAnimationFrame(() => overlay.classList.add("open"));
      overlay.querySelector("#gpt-dialog-cancel").onclick = () => { overlay.classList.remove("open"); setTimeout(() => overlay.remove(), 200); };
      overlay.querySelector("#gpt-dialog-confirm").onclick = async () => {
        overlay.classList.remove("open");
        setTimeout(() => overlay.remove(), 200);
        await fetch("/api/chat/delete", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: targetId }),
        });
        if (targetId === chatId) { chatId = ""; historyEl.innerHTML = ""; lastAiId = null; }
        updateHistoryList();
      };
      overlay.addEventListener("click", (ev) => { if (ev.target === overlay) { overlay.classList.remove("open"); setTimeout(() => overlay.remove(), 200); } });
    }

    function showRenameDialog(targetId) {
      const item = document.querySelector(`.gpt-side-item[data-chat="${targetId}"]`);
      const currentTitle = item?.querySelector(".gpt-side-title")?.textContent || "";
      const overlay = document.createElement("div");
      overlay.className = "gpt-dialog-overlay";
      overlay.innerHTML = `
        <div class="gpt-dialog">
          <div class="gpt-dialog-header">
            <div class="gpt-dialog-icon"><i class="bi bi-pencil"></i></div>
            <h3 class="gpt-dialog-title">Rename conversation</h3>
          </div>
          <input class="gpt-dialog-input" id="gpt-rename-input" value="${esc(currentTitle)}" placeholder="Enter a new title...">
          <div class="gpt-dialog-actions">
            <button class="gpt-dialog-btn gpt-dialog-btn--ghost" id="gpt-dialog-cancel">Cancel</button>
            <button class="gpt-dialog-btn gpt-dialog-btn--primary" id="gpt-dialog-confirm">Rename</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      requestAnimationFrame(() => overlay.classList.add("open"));
      const inputEl = overlay.querySelector("#gpt-rename-input");
      inputEl.focus();
      inputEl.select();
      inputEl.addEventListener("keydown", (ev) => { if (ev.key === "Enter") overlay.querySelector("#gpt-dialog-confirm").click(); });
      overlay.querySelector("#gpt-dialog-cancel").onclick = () => { overlay.classList.remove("open"); setTimeout(() => overlay.remove(), 200); };
      overlay.querySelector("#gpt-dialog-confirm").onclick = async () => {
        const newTitle = inputEl.value.trim();
        if (!newTitle) return;
        overlay.classList.remove("open");
        setTimeout(() => overlay.remove(), 200);
        await fetch("/api/chat/rename", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: targetId, title: newTitle }),
        });
        updateHistoryList();
      };
      overlay.addEventListener("click", (ev) => { if (ev.target === overlay) { overlay.classList.remove("open"); setTimeout(() => overlay.remove(), 200); } });
    }

    async function updateHistoryList() {
      if (!historyList) return;
      try {
        const res = await fetch("/api/chats");
        const data = await res.json();
        const q = sideSearch ? sideSearch.value.trim().toLowerCase() : "";
        const chats = data.chats || [];
        /* Group chats by date */
        const now = new Date();
        const today = now.toDateString();
        const yesterday = new Date(now - 86400000).toDateString();
        const weekAgo = new Date(now - 604800000);
        const groups = { today: [], yesterday: [], week: [], older: [] };
        chats.forEach((c) => {
          if (q && !(c.title || "").toLowerCase().includes(q) && !(c.last_message || "").toLowerCase().includes(q)) return;
          const d = new Date(c.updated || c.created);
          const ds = d.toDateString();
          if (ds === today) groups.today.push(c);
          else if (ds === yesterday) groups.yesterday.push(c);
          else if (d > weekAgo) groups.week.push(c);
          else groups.older.push(c);
        });
        function renderItems(items) {
          return items.map((c) => {
            const v = c.vehicle || {};
            const brand = v.brand || "";
            const model = v.model || "";
            const vehicleStr = [brand, model].filter(Boolean).join(" ");
            const isActive = c.id === chatId;
            const msgCount = c.message_count || 0;
            const preview = c.last_message || "No messages yet";
            return `<div class="gpt-side-item ${isActive ? "active" : ""}" data-chat="${c.id}">
              <div class="gpt-side-item-content">
                <div class="gpt-side-title-row">
                  <span class="gpt-side-title">${esc(c.title)}</span>
                </div>
                <div class="gpt-side-meta">
                  ${vehicleStr ? `<span class="gpt-side-vehicle"><i class="bi bi-car-front-fill"></i> ${esc(vehicleStr)}</span>` : ""}
                  <span class="gpt-side-count">${msgCount} message${msgCount !== 1 ? "s" : ""}</span>
                </div>
                <div class="gpt-side-preview">${esc(preview)}</div>
              </div>
              <button class="gpt-side-menu-btn" data-chat-menu="${c.id}" title="Options"><i class="bi bi-three-dots"></i></button>
            </div>`;
          }).join("");
        }
        let html = "";
        if (groups.today.length) html += `<div class="gpt-side-group-label">Today</div>${renderItems(groups.today)}`;
        if (groups.yesterday.length) html += `<div class="gpt-side-group-label">Yesterday</div>${renderItems(groups.yesterday)}`;
        if (groups.week.length) html += `<div class="gpt-side-group-label">This week</div>${renderItems(groups.week)}`;
        if (groups.older.length) html += `<div class="gpt-side-group-label">Older</div>${renderItems(groups.older)}`;
        if (!html) html = `<div class="gpt-side-empty">No conversations found</div>`;
        historyList.innerHTML = html;
      } catch (err) { /* chat list unavailable */ }
    }

    markLatestRegen();
    window._updateChatHistoryList = updateHistoryList;
    /* Expose chatId setter for history panel new-chat flow */
    window._setChatId = function (id) { chatId = id; document.documentElement.dataset.chatId = id; };
    /* Initialize chat history panel if present */
    if (typeof initChatHistoryPanel === "function") {
      initChatHistoryPanel();
    }
    /* Auto-select pending chat (from history panel open) */
    if (window._pendingChatId) {
      var pendingId = window._pendingChatId;
      window._pendingChatId = null;
      selectChat(pendingId);
    }
  }

  /* ---------------- Save diagnosis to chat history ---------------- */
  async function saveDiagToChat(type, problem, result, vehicle) {
    try {
      await fetch("/api/chat/save-diagnosis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, problem, result, vehicle }),
      });
      if (window._updateChatHistoryList) { window._updateChatHistoryList(); return; }
      /* Fallback: inline render */
      const historyList = $("#chat-history-list");
      if (historyList) {
        const res = await fetch("/api/chats");
        const data = await res.json();
        const chatId = document.documentElement.dataset.chatId || "";
        const chats = data.chats || [];
        historyList.innerHTML = chats.map((c) => {
          const v = c.vehicle || {};
          const vehicleStr = [v.brand, v.model].filter(Boolean).join(" ");
          return `<div class="gpt-side-item ${c.id === chatId ? "active" : ""}" data-chat="${c.id}">
            <div class="gpt-side-item-content">
              <div class="gpt-side-title-row"><span class="gpt-side-title">${esc(c.title)}</span></div>
              <div class="gpt-side-meta">
                ${vehicleStr ? `<span class="gpt-side-vehicle"><i class="bi bi-car-front-fill"></i> ${esc(vehicleStr)}</span>` : ""}
                <span class="gpt-side-count">${c.message_count || 0} messages</span>
              </div>
            </div>
            <button class="gpt-side-menu-btn" data-chat-menu="${c.id}" title="Options"><i class="bi bi-three-dots"></i></button>
          </div>`;
        }).join("");
      }
    } catch (e) { /* ignore */ }
  }
  window.initChat = initChat;
  /* Pending chat to auto-select after modal reload (set by history panel) */
  window._pendingChatId = null;

  /* ---------------- Diagnosis: text ---------------- */
  function initDiagnoseText() {
    const form = $("#diagnose-text-form");
    if (!form) return;
    const output = $("#diagnose-text-output") || $("#diagnose-output");
    const desc = $("#diag-desc");

    /* Enter submits, Shift+Enter adds newline */
    desc?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const val = desc.value.trim();
      if (val.length < 8) { toast("warning", CS.t("Add a description"), CS.t("Describe the problem in a few words.")); return; }
      output.innerHTML = loadingPanel(CS.t("Asking the AI mechanic…"));
      const res = await fetch("/api/diagnose/text", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ description: val }),
      });
      const data = await res.json();
      if (!res.ok) { output.innerHTML = ""; toast("error", CS.t("Diagnosis failed"), data.error); return; }
      output.innerHTML = renderReport(data.result);
      wireReport();
      output.scrollIntoView({ behavior: "smooth" });
      saveDiagToChat("text", val, data.result);
    });
  }

  /* ---------------- Diagnosis: image ---------------- */
  function initDiagnoseImage() {
    const zone = $("#image-zone");
    if (!zone) return;
    const fileInput = $("#image-file");
    const preview = $("#image-preview");
    const analyzeBtn = $("#image-analyze");
    const output = $("#diagnose-image-output") || $("#diagnose-output");
    let currentFile = null;

    const show = (file) => {
      if (!file || !file.type.startsWith("image/")) { toast("warning", CS.t("Invalid file"), CS.t("Please choose an image.")); return; }
      currentFile = file;
      zone.classList.add("d-none");
      preview.innerHTML = `<div class="d-flex flex-column align-items-center gap-2">
        <img class="preview-thumb" src="${URL.createObjectURL(file)}" alt="Preview">
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-ghost" type="button" data-clear-image><i class="bi bi-x-lg"></i> ${esc(CS.t("Remove"))}</button>
          <button class="btn btn-sm btn-primary" type="button" id="image-go"><i class="bi bi-stars"></i> ${esc(CS.t("Analyze image"))}</button>
        </div></div>`;
      $("#image-go")?.addEventListener("click", analyze);
    };
    const clear = () => { currentFile = null; preview.innerHTML = ""; zone.classList.remove("d-none"); };
    const analyze = async () => {
      if (!currentFile) return;
      output.innerHTML = loadingPanel(CS.t("Reading the image…"));
      const fd = new FormData();
      fd.append("file", currentFile);
      fd.append("description", $("#image-desc")?.value || "");
      const res = await fetch("/api/diagnose/image", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) { output.innerHTML = ""; toast("error", CS.t("Analysis failed"), data.error); return; }
      output.innerHTML = renderReport(data.result);
      wireReport();
      output.scrollIntoView({ behavior: "smooth" });
      const desc = $("#image-desc")?.value || currentFile.name;
      saveDiagToChat("image", desc, data.result);
    };

    zone.addEventListener("click", () => fileInput.click());
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault(); zone.classList.remove("dragover");
      if (e.dataTransfer.files.length) show(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => { if (fileInput.files.length) show(fileInput.files[0]); });
    preview.addEventListener("click", (e) => { if (e.target.closest("[data-clear-image]")) clear(); });
    if (analyzeBtn) analyzeBtn.addEventListener("click", analyze);

    /* Enter in description triggers analyze */
    $("#image-desc")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (currentFile) analyze();
      }
    });
  }

  /* Convert a recorded audio Blob (e.g. webm/opus, which Gemini's audio API does
     NOT accept) into a 16 kHz mono WAV File that every backend/model supports.
     Uses the Web Audio API — no server transcoding or extra libraries. */
  async function blobToWavFile(blob, name) {
    const AC = window.AudioContext || window.webkitAudioContext;
    const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!AC || !OAC) throw new Error("Web Audio API unavailable");
    const arr = await blob.arrayBuffer();
    const ctx = new AC();
    const decoded = await ctx.decodeAudioData(arr);
    try { ctx.close(); } catch (_) {}
    const rate = 16000;
    const frames = Math.max(1, Math.ceil(decoded.duration * rate));
    const off = new OAC(1, frames, rate);
    const src = off.createBufferSource();
    src.buffer = decoded;
    src.connect(off.destination);
    src.start(0);
    const rendered = await off.startRendering();
    return new File([encodeWav(rendered.getChannelData(0), rate)], name, { type: "audio/wav" });
  }
  function encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeStr = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
    writeStr(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); writeStr(8, "WAVE");
    writeStr(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    writeStr(36, "data"); view.setUint32(40, samples.length * 2, true);
    let off = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      off += 2;
    }
    return new Blob([view], { type: "audio/wav" });
  }

  /* ---------------- Diagnosis: audio ---------------- */
  function initDiagnoseAudio() {
    const zone = $("#audio-zone");
    if (!zone) return;
    const fileInput = $("#audio-file");
    const preview = $("#audio-preview");
    const analyzeBtn = $("#audio-analyze");
    const output = $("#diagnose-audio-output") || $("#diagnose-output");
    const recordBtn = $("#audio-record-btn");
    const uploadBtn = $("#audio-upload-btn");
    const recordCtrl = $("#audio-record-ctrl");
    const recordTimer = $("#audio-record-timer");
    const recordStop = $("#audio-record-stop");
    const recordCancel = $("#audio-record-cancel");
    const recordStatus = $("#audio-record-status");
    let currentFile = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let recordInterval = null;
    let recordSeconds = 0;

    const show = (file) => {
      if (!file.type.startsWith("audio/")) { toast("warning", CS.t("Invalid file"), CS.t("Please choose an audio file.")); return; }
      currentFile = file;
      zone.classList.add("d-none");
      preview.innerHTML = `<div class="d-flex flex-column align-items-center gap-3">
        <div class="d-flex align-items-center gap-2 text-soft"><i class="bi bi-file-earmark-music fs-4"></i><span class="small">${esc(file.name)} · ${(file.size / 1024 / 1024).toFixed(2)} MB</span></div>
        <audio controls class="w-100" src="${URL.createObjectURL(file)}"></audio>
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-ghost" type="button" data-clear-audio><i class="bi bi-x-lg"></i> ${esc(CS.t("Remove"))}</button>
          <button class="btn btn-sm btn-primary" type="button" id="audio-go"><i class="bi bi-stars"></i> ${esc(CS.t("Transcribe & diagnose"))}</button>
        </div></div>`;
      $("#audio-go")?.addEventListener("click", analyze);
    };
    const clear = () => { currentFile = null; preview.innerHTML = ""; zone.classList.remove("d-none"); };
    const analyze = async () => {
      if (!currentFile) return;
      output.innerHTML = loadingPanel(CS.t("Listening and analyzing…"));
      const fd = new FormData();
      fd.append("file", currentFile);
      fd.append("description", $("#audio-desc")?.value || "");
      const res = await fetch("/api/diagnose/audio", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) { output.innerHTML = ""; toast("error", CS.t("Analysis failed"), data.error); return; }
      output.innerHTML = renderReport(data.result);
      wireReport();
      output.scrollIntoView({ behavior: "smooth" });
      const desc = $("#audio-desc")?.value || currentFile.name;
      saveDiagToChat("audio", desc, data.result);
    };

    function formatTime(s) {
      const m = Math.floor(s / 60).toString().padStart(2, "0");
      const sec = (s % 60).toString().padStart(2, "0");
      return `${m}:${sec}`;
    }

    async function startRecording() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recordedChunks = [];
        /* Pick a supported recording container (Chrome→webm, Safari→mp4…). */
        let mr;
        const prefs = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
        const chosen = (window.MediaRecorder && MediaRecorder.isTypeSupported)
          ? prefs.find((t) => MediaRecorder.isTypeSupported(t)) : null;
        try { mr = chosen ? new MediaRecorder(stream, { mimeType: chosen }) : new MediaRecorder(stream); }
        catch (_) { mr = new MediaRecorder(stream); }
        mediaRecorder = mr;
        mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) recordedChunks.push(e.data); };
        mediaRecorder.onstop = async () => {
          stream.getTracks().forEach(t => t.stop());
          if (recordCtrl) recordCtrl.classList.add("d-none");
          if (recordedChunks.length === 0) { zone.classList.remove("d-none"); return; }
          const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || "audio/webm" });
          let file;
          try {
            /* Convert to WAV so Gemini's audio API accepts it (webm is rejected). */
            file = await blobToWavFile(blob, "recording.wav");
          } catch (err) {
            file = new File([blob], "recording.webm", { type: blob.type || "audio/webm" });
          }
          show(file);
        };
        mediaRecorder.start();
        recordSeconds = 0;
        recordTimer.textContent = "00:00";
        zone.classList.add("d-none");
        recordCtrl.classList.remove("d-none");
        recordStatus.textContent = CS.t("Recording…");
        recordInterval = setInterval(() => {
          recordSeconds++;
          recordTimer.textContent = formatTime(recordSeconds);
        }, 1000);
      } catch (err) {
        toast("error", CS.t("Error"), CS.t("Microphone access denied."));
      }
    }

    function stopRecording() {
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
      }
      clearInterval(recordInterval);
    }

    function cancelRecording() {
      recordedChunks = [];
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.ondataavailable = null;
        mediaRecorder.onstop = () => {};
        mediaRecorder.stop();
      }
      clearInterval(recordInterval);
      mediaRecorder = null;
      recordCtrl.classList.add("d-none");
      zone.classList.remove("d-none");
    }

    uploadBtn?.addEventListener("click", () => fileInput.click());
    recordBtn?.addEventListener("click", startRecording);
    recordStop?.addEventListener("click", stopRecording);
    recordCancel?.addEventListener("click", cancelRecording);

    zone.addEventListener("click", (e) => {
      if (e.target.closest("#audio-upload-btn")) return;
      if (e.target.closest("#audio-record-btn")) return;
      fileInput.click();
    });
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault(); zone.classList.remove("dragover");
      if (e.dataTransfer.files.length) show(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => { if (fileInput.files.length) show(fileInput.files[0]); });
    preview.addEventListener("click", (e) => { if (e.target.closest("[data-clear-audio]")) clear(); });
    if (analyzeBtn) analyzeBtn.addEventListener("click", analyze);

    /* Enter in description triggers analyze */
    $("#audio-desc")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (currentFile) analyze();
      }
    });
  }

  /* ---------------- Diagnosis: video ---------------- */
  function initDiagnoseVideo() {
    const zone = $("#video-zone");
    if (!zone) return;
    const fileInput = $("#video-file");
    const preview = $("#video-preview");
    const analyzeBtn = $("#video-analyze");
    const output = $("#diagnose-video-output") || $("#diagnose-output");
    let currentFile = null;

    const show = (file) => {
      if (!file.type.startsWith("video/")) { toast("warning", CS.t("Invalid file"), CS.t("Please choose a video.")); return; }
      currentFile = file;
      zone.classList.add("d-none");
      preview.innerHTML = `<div class="d-flex flex-column align-items-center gap-3">
        <div class="d-flex align-items-center gap-2 text-soft"><i class="bi bi-camera-reels fs-4"></i><span class="small">${esc(file.name)} · ${(file.size / 1024 / 1024).toFixed(2)} MB</span></div>
        <video controls class="w-100 rounded-3" style="max-height:280px" src="${URL.createObjectURL(file)}"></video>
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-ghost" type="button" data-clear-video><i class="bi bi-x-lg"></i> ${esc(CS.t("Remove"))}</button>
          <button class="btn btn-sm btn-primary" type="button" id="video-go"><i class="bi bi-stars"></i> ${esc(CS.t("Analyze video"))}</button>
        </div></div>`;
      $("#video-go")?.addEventListener("click", analyze);
    };
    const clear = () => { currentFile = null; preview.innerHTML = ""; zone.classList.remove("d-none"); };
    const analyze = async () => {
      if (!currentFile) return;
      output.innerHTML = loadingPanel(CS.t("Watching and analyzing…"));
      const fd = new FormData();
      fd.append("file", currentFile);
      fd.append("description", $("#video-desc")?.value || "");
      const res = await fetch("/api/diagnose/video", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) { output.innerHTML = ""; toast("error", CS.t("Analysis failed"), data.error); return; }
      output.innerHTML = renderReport(data.result);
      wireReport();
      output.scrollIntoView({ behavior: "smooth" });
      const desc = $("#video-desc")?.value || currentFile.name;
      saveDiagToChat("video", desc, data.result);
    };

    zone.addEventListener("click", () => fileInput.click());
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault(); zone.classList.remove("dragover");
      if (e.dataTransfer.files.length) show(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => { if (fileInput.files.length) show(fileInput.files[0]); });
    preview.addEventListener("click", (e) => { if (e.target.closest("[data-clear-video]")) clear(); });
    if (analyzeBtn) analyzeBtn.addEventListener("click", analyze);

    /* Enter in description triggers analyze */
    $("#video-desc")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (currentFile) analyze();
      }
    });
  }

  /* ---------------- Report rendering ---------------- */
  function loadingPanel(text) {
    return `<div class="card fade-up"><div class="card-body d-flex flex-column align-items-center gap-3 py-5">
      <div class="icon-chip grad xl"><i class="bi bi-stars spin"></i></div>
      <div class="skeleton" style="width:220px;height:16px"></div>
      <div class="skeleton" style="width:300px;height:14px"></div>
      <div class="text-soft small">${esc(text)}</div></div></div>`;
  }

  const URGENCY = {
    low: { label: CS.t("Safe to drive"), cls: "success", icon: "bi-shield-check" },
    medium: { label: CS.t("Drive carefully"), cls: "warning", icon: "bi-exclamation-triangle" },
    high: { label: CS.t("Service soon"), cls: "danger", icon: "bi-exclamation-octagon" },
    critical: { label: CS.t("Stop immediately"), cls: "danger", icon: "bi-stop-circle" },
  };

  function renderReport(r) {
    const u = URGENCY[r.urgency] || URGENCY.low;
    const ring = r.confidence != null ? `
      <div class="conf-ring">
        <svg width="148" height="148" viewBox="0 0 148 148">
          <defs><linearGradient id="grad"><stop offset="0%" stop-color="#3b82f6"/><stop offset="100%" stop-color="#60a5fa"/></linearGradient></defs>
          <circle class="track" cx="74" cy="74" r="62" fill="none" stroke-width="12"/>
          <circle class="bar" cx="74" cy="74" r="62" fill="none" stroke-width="12" stroke-dasharray="${2 * Math.PI * 62}" stroke-dashoffset="${2 * Math.PI * 62 * (1 - r.confidence / 100)}" data-dashoffset="${2 * Math.PI * 62 * (1 - r.confidence / 100)}"/>
        </svg>
        <div class="label"><div class="num" data-count="${r.confidence}">0</div><div class="cap">${esc(CS.t("Confidence"))}</div></div>
      </div>` : "";

    const meta = (icon, title, value) => `
      <div class="d-flex gap-3 align-items-start">
        <div class="report-icon" style="background:var(--brand-soft);color:var(--brand)"><i class="bi ${icon}"></i></div>
        <div><div class="eyebrow mb-1">${esc(title)}</div><div class="fw-semibold">${value}</div></div>
      </div>`;

    return `
    <div class="card fade-up overflow-hidden" id="report-card">
      <div class="card-body p-0">
        <div class="report-section d-flex flex-wrap align-items-center justify-content-between gap-3">
          <div class="d-flex align-items-center gap-3">
            <div class="icon-chip grad"><i class="bi bi-stars"></i></div>
            <div>
              <div class="eyebrow">${esc(CS.t("AI Diagnosis · "))}${fmtDate(r.date)}</div>
              <h4 class="mb-0 mt-1">${esc(r.problem)}</h4>
            </div>
          </div>
          <div class="d-flex flex-column align-items-end gap-2">
            <span class="badge badge-soft-${u.cls}"><i class="bi ${u.icon} me-1"></i>${u.label}</span>
            <a href="/diagnosis/${esc(r.id)}/print" class="btn btn-sm btn-secondary" target="_blank"><i class="bi bi-filetype-pdf me-1"></i>${esc(CS.t("Download PDF"))}</a>
          </div>
        </div>

        <div class="report-section">
          <div class="row g-3 align-items-center">
            <div class="col-md-7">
              <div class="eyebrow mb-1">${esc(CS.t("Summary"))}</div>
              <p class="mb-0 text-soft">${esc(r.summary || CS.t("AI analysis complete. See details below."))}</p>
              <div class="small text-soft mt-3 d-flex flex-wrap gap-2">
                <span class="badge badge-soft-muted"><i class="bi bi-car-front me-1"></i>${esc(r.vehicle || CS.t("Vehicle not set"))}</span>
                <span class="badge badge-soft-muted"><i class="bi bi-translate me-1"></i>${esc(r.mode)}</span>
              </div>
            </div>
            <div class="col-md-5 d-flex justify-content-center">${ring}</div>
          </div>
        </div>

        ${r.transcript ? `<div class="report-section">
          <div class="eyebrow mb-2">${esc(CS.t("Transcribed sound"))}</div>
          <p class="mb-0"><i class="bi bi-quote me-1 text-soft"></i>${esc(r.transcript)}</p>
        </div>` : ""}

        <div class="report-section">
          <div class="eyebrow mb-2"><i class="bi bi-search me-1"></i>${esc(CS.t("Possible causes"))}</div>
          <ul class="list-clean d-flex flex-column gap-2 mb-0">
            ${(r.causes || []).map((c) => `<li class="d-flex gap-2"><i class="bi bi-dot text-soft"></i><span>${esc(c)}</span></li>`).join("")}
          </ul>
        </div>

        <div class="report-section">
          <div class="eyebrow mb-3"><i class="bi bi-speedometer2 me-1"></i>${esc(CS.t("Can I still drive?"))}</div>
          <div class="urgency-hero ${u.cls}">
            <div class="d-flex gap-2 align-items-start">
              <i class="bi ${u.icon} fs-4"></i>
              <div><div class="fw-semibold">${u.label}</div><div class="small text-soft">${esc(r.can_drive)}</div></div>
            </div>
          </div>
        </div>

        <div class="report-section">
          <div class="row g-3">
            <div class="col-sm-6 col-lg-4">${meta("bi-cash-stack", CS.t("Estimated cost"), esc(r.cost))}</div>
            <div class="col-sm-6 col-lg-4">${meta("bi-clock", CS.t("Estimated time"), esc(r.time))}</div>
            <div class="col-sm-12 col-lg-4">${meta("bi-geo-alt", CS.t("Recommended service"), esc(r.center))}</div>
          </div>
        </div>

        <div class="report-section">
          <div class="eyebrow mb-2"><i class="bi bi-box-seam me-1"></i>${esc(CS.t("Required parts"))}</div>
          <div class="d-flex flex-wrap gap-2">
            ${(r.parts || []).map((p) => `<span class="badge badge-soft-info" style="font-size:.8rem;padding:.5em .9em">${esc(p)}</span>`).join("")}
          </div>
        </div>

        <div class="report-section">
          <div class="eyebrow mb-2"><i class="bi bi-wrench-adjustable me-1"></i>${esc(CS.t("Repair steps"))}</div>
          <ol class="mb-0 ps-3 d-flex flex-column gap-2">
            ${(r.steps || []).map((s) => `<li class="text-soft">${esc(s)}</li>`).join("")}
          </ol>
        </div>

        <div class="report-section d-flex justify-content-between gap-2 flex-wrap">
          <a href="/reports" class="btn btn-ghost"><i class="bi bi-arrow-left me-1"></i>${esc(CS.t("All reports"))}</a>
          <a href="/diagnosis/${esc(r.id)}" class="btn btn-primary"><i class="bi bi-eye me-1"></i>${esc(CS.t("Open full report"))}</a>
        </div>
      </div>
    </div>`;
  }

  function wireReport() {
    requestAnimationFrame(() => initCountUp());
  }

  /* ---------------- Maintenance ---------------- */
  const MAINT_BADGE = {
    upcoming: ["badge-soft-success", "Upcoming"],
    due_soon: ["badge-soft-warning", "Due soon"],
    overdue: ["badge-soft-danger", "Overdue"],
  };
  function initMaintenance() {
    const listEl = $("#maint-list");
    const doneEl = $("#maint-done");
    if (!listEl && !doneEl) return;

    const card = (m) => {
      const [bcls, blab] = MAINT_BADGE[m.service_status] || MAINT_BADGE.upcoming;
      return `
      <div class="col-md-6">
      <div class="card card-hover h-100" data-id="${m.id}">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start gap-2">
            <div class="d-flex gap-3">
              <div class="icon-chip"><i class="bi ${iconFor(m.category)}"></i></div>
              <div>
                <h6 class="mb-1">${esc(m.title)}</h6>
                <div class="small text-soft">${esc(m.category)}</div>
              </div>
            </div>
            <div class="d-flex flex-column align-items-end gap-1">
              <span class="badge ${bcls}">${esc(CS.t(blab))}</span>
              <div class="d-flex gap-1">
                <button class="btn-icon" data-done="${m.id}" title="${esc(CS.t("Mark done"))}"><i class="bi bi-check-lg" style="color:var(--success)"></i></button>
                <button class="btn-icon" data-del="${m.id}" title="${esc(CS.t("Delete"))}"><i class="bi bi-trash" style="color:var(--danger)"></i></button>
              </div>
            </div>
          </div>
          <div class="d-flex flex-wrap gap-2 small text-soft mt-2">
            <span>${esc(CS.t("Next service"))} <b>${(m.next_service_km ?? 0).toLocaleString()}</b> ${esc(CS.t("km"))}</span>
            <span>${esc(CS.t("Current"))} <b>${(m.current_km ?? 0).toLocaleString()}</b> ${esc(CS.t("km"))}</span>
            <span>${esc(CS.t("Remaining"))} <b>${(m.remaining_km ?? 0).toLocaleString()}</b> ${esc(CS.t("km"))}</span>
          </div>
          <div class="progress mt-2" style="height:8px;background:var(--surface-3)">
            <div class="progress-bar gradient-bg" style="width:${m.progress}%"></div>
          </div>
          <div class="d-flex justify-content-between mt-2"><span class="small text-soft">${Math.round(m.progress)}% ${esc(CS.t("of interval used"))}</span><span class="small text-soft">${m.notes ? esc(m.notes.slice(0, 40)) + (m.notes.length > 40 ? "…" : "") : ""}</span></div>
        </div>
      </div>
      </div>`;
    };
    const doneRow = (m) => `
      <div class="timeline-item done" data-id="${m.id}">
        <div class="d-flex justify-content-between">
          <div><div class="fw-semibold">${esc(m.title)}</div>
          <div class="small text-soft">${esc(m.category)} · ${fmtDate(m.date_added)}</div></div>
          <div class="d-flex gap-1">
            <button class="btn-icon" data-del="${m.id}" title="${esc(CS.t("Delete"))}"><i class="bi bi-trash" style="color:var(--danger)"></i></button>
          </div>
        </div>
      </div>`;

    async function refresh() {
      const res = await fetch("/api/maintenance/data");
      const data = await res.json();
      if (listEl) listEl.innerHTML = data.active.map(card).join("") || emptyMaint();
      if (doneEl) doneEl.innerHTML = data.done.map(doneRow).join("") || `<div class="small text-soft">${esc(CS.t("No completed services yet."))}</div>`;
    }

    listEl?.addEventListener("click", async (e) => {
      const doneBtn = e.target.closest("[data-done]");
      const delBtn = e.target.closest("[data-del]");
      if (doneBtn) {
        const res = await fetch(`/api/maintenance/${doneBtn.dataset.done}/done`, { method: "POST" });
        const body = await res.json().catch(() => ({}));
        if (!res.ok || !body.ok) { toast("error", CS.t("Error"), CS.t("Could not update the reminder. Please try again.")); return; }
        toast("success", CS.t("Marked done"), CS.t("Great — service completed."));
        refresh();
      }
      if (delBtn) {
        if (!confirm(CS.t("Delete this reminder?"))) return;
        const res = await fetch(`/api/maintenance/${delBtn.dataset.del}/delete`, { method: "POST" });
        const body = await res.json().catch(() => ({}));
        if (!res.ok || !body.ok) { toast("error", CS.t("Error"), CS.t("Could not delete the reminder. Please try again.")); return; }
        refresh();
      }
    });
    doneEl?.addEventListener("click", async (e) => {
      const delBtn = e.target.closest("[data-del]");
      if (!delBtn) return;
      if (!confirm(CS.t("Delete this history entry?"))) return;
      const res = await fetch(`/api/maintenance/${delBtn.dataset.del}/delete`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) { toast("error", CS.t("Error"), CS.t("Could not delete this history entry. Please try again.")); return; }
      refresh();
    });

    const modalEl = $("#addMaintenanceModal");
    if (modalEl) {
      const modal = new bootstrap.Modal(modalEl);
      $("#maint-add-btn").addEventListener("click", () => modal.show());
      $("#maint-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('button[type="submit"]');
        const fd = new FormData(e.target);
        btn.disabled = true;
        toast("info", CS.t("Saving reminder…"));
        try {
          const res = await fetch("/api/maintenance", { method: "POST", body: fd });
          const data = await res.json();
          if (!res.ok) { toast("error", CS.t("Error"), data.error || CS.t("Unable to save maintenance reminder. Please try again.")); return; }
          modal.hide();
          e.target.reset();
          toast("success", CS.t("Reminder added"), CS.t("Tracked in your maintenance plan."));
          refresh();
        } catch (err) {
          toast("error", CS.t("Error"), CS.t("Unable to save maintenance reminder. Please try again."));
        } finally {
          btn.disabled = false;
        }
      });
    }
    refresh();
  }

  function iconFor(cat) {
    const map = { Engine: "bi-thermometer-half", Brakes: "bi-disc", Tires: "bi-circle", Oil: "bi-droplet", Battery: "bi-battery-charging", Other: "bi-tools", Electrical: "bi-lightning-charge", Climate: "bi-snow", Exterior: "bi-car-front", General: "bi-tools", default: "bi-tools" };
    return map[cat] || map.default;
  }
  function emptyMaint() {
    return `<div class="empty-state py-4"><div class="es-icon"><i class="bi bi-calendar-check"></i></div>
      <h6>${esc(CS.t("No maintenance reminders"))}</h6><p class="text-soft small">${esc(CS.t("Add oil changes, inspections and more."))}</p></div>`;
  }

  /* ---------------- Settings ---------------- */
  function initSettings() {
    const root = $("#settings-page");
    if (!root) return;

    async function save(patch) {
      const res = await fetch("/api/settings", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
      });
      const data = await res.json();
      if (!res.ok) { toast("error", CS.t("Error"), data.error || CS.t("Please try again.")); return data; }
      toast("success", CS.t("Settings saved"), CS.t("Gemini is connected."));
      return data;
    }

    // Theme pick items
    $$('[data-setting="theme"]', root).forEach((el) => el.addEventListener("click", () => {
      $$('[data-setting="theme"]', root).forEach((x) => x.classList.remove("selected"));
      el.classList.add("selected");
      applyTheme(el.dataset.val);
      save({ theme: el.dataset.val });
    }));

    // Notification toggles
    $$('[data-group="notifications"]', root).forEach((el) => el.addEventListener("change", () => {
      const patch = { notifications: {} };
      $$('[data-group="notifications"]', root).forEach((x) => { patch.notifications[x.dataset.setting] = x.checked; });
      save(patch);
    }));

    // AI preference toggles (e.g. streaming responses)
    $$('[data-group="ai"]', root).forEach((el) => el.addEventListener("change", () => {
      if (el.dataset.setting === "streaming") localStorage.setItem("cs-streaming", el.checked ? "1" : "0");
      save({ [el.dataset.setting]: el.checked });
    }));

    // Clear in-memory AI caches
    $("#gemini-cache-btn")?.addEventListener("click", async () => {
      const res = await fetch("/api/settings/clear-cache", { method: "POST" });
      if (res.ok) toast("success", CS.t("Cache cleared"), CS.t("In-memory AI caches were reset."));
    });

    // explicit save buttons
    const apiForm = $("#api-key-form");
    if (apiForm) apiForm.addEventListener("submit", (e) => {
      e.preventDefault();
      save({ gemini_key: $("#gemini-key").value.trim(), model: $("#gemini-model").value });
    });
    /* NOTE: the #a11y-form submit (+ instant apply via CS.applyA11y) is handled in
       settings.js — do not bind it here too, or every save fires twice. */

    // Gemini connection test (✅ Connected / ❌ Invalid / ⚠ Missing)
    const testBtn = $("#gemini-test-btn");
    const statusEl = $("#gemini-test-status");
    if (testBtn && statusEl) {
      const statusIcon = $("#gemini-test-icon");
      const statusText = $("#gemini-test-text");
      const statusDetail = $("#gemini-test-detail");
      const STATES = {
        ok: ["bi-check-circle-fill text-success", "Connected"],
        invalid: ["bi-x-circle-fill text-danger", "Invalid API Key"],
        missing: ["bi-exclamation-triangle-fill text-warning", "API Key Missing"],
        error: ["bi-x-circle-fill text-danger", "Connection failed"],
      };
      function showStatus(state, detail) {
        const [icon, msg] = STATES[state] || STATES.error;
        statusEl.classList.remove("d-none");
        statusEl.classList.add("d-inline-flex");
        statusIcon.className = icon;
        statusText.textContent = CS.t(msg);
        if (statusDetail) statusDetail.textContent = detail || "";
      }
      async function testConnection() {
        testBtn.disabled = true;
        statusEl.classList.remove("d-none");
        statusEl.classList.add("d-inline-flex");
        statusIcon.className = "bi bi-arrow-repeat";
        statusText.textContent = CS.t("Testing connection…");
        if (statusDetail) statusDetail.textContent = "";
        try {
          const res = await fetch("/api/settings/test-gemini", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gemini_key: $("#gemini-key").value.trim() }),
          });
          const data = await res.json();
          showStatus(data.state, data.detail);
        } catch (err) {
          showStatus("error");
        } finally {
          testBtn.disabled = false;
        }
      }
      testBtn.addEventListener("click", testConnection);
      if ($("#gemini-key").value.trim()) testConnection();
    }
  }

  /* ---------------- Contact ---------------- */
  function initContact() {
    const form = $("#contact-form");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(form).entries());
      const res = await fetch("/api/contact", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) { toast("error", CS.t("Could not send"), data.error); return; }
      form.reset();
      toast("success", CS.t("Message sent"), data.message);
    });
  }

  /* ---------------- Chat History Panel (inside popup) ---------------- */
  function initChatHistoryPanel() {
    var panel = document.getElementById("gpt-history-panel");
    if (!panel || panel.dataset.historyInit) return;
    panel.dataset.historyInit = "1";
    var backBtn = document.getElementById("gpt-history-back");
    var newBtn = document.getElementById("gpt-history-new-btn");
    var searchInput = document.getElementById("gpt-history-search");
    var list = document.getElementById("gpt-history-list");
    var historyBtn = document.getElementById("chat-modal-history-btn");
    if (!panel || !list) return;

    /* Toggle panel */
    function openHistory() {
      panel.classList.add("open");
      if (historyBtn) historyBtn.classList.add("active");
      loadHistory();
    }
    function closeHistory() {
      panel.classList.remove("open");
      if (historyBtn) historyBtn.classList.remove("active");
    }
    function toggleHistory() {
      if (panel.classList.contains("open")) closeHistory();
      else openHistory();
    }

    if (historyBtn) historyBtn.addEventListener("click", toggleHistory);
    if (backBtn) backBtn.addEventListener("click", closeHistory);

    /* Load chats */
    async function loadHistory() {
      try {
        list.innerHTML = '<div class="gpt-history-loading">Loading conversations...</div>';
        var res = await fetch("/api/chats");
        var data = await res.json();
        renderHistory(data.chats || []);
      } catch (e) {
        list.innerHTML = '<div class="gpt-history-empty"><i class="bi bi-exclamation-circle"></i>Failed to load conversations</div>';
      }
    }

    /* Render history list */
    function renderHistory(chats) {
      var q = searchInput ? searchInput.value.trim().toLowerCase() : "";
      var now = new Date();
      var today = now.toDateString();
      var yesterday = new Date(now - 86400000).toDateString();
      var weekAgo = new Date(now - 604800000);
      var groups = { today: [], yesterday: [], week: [], older: [] };

      chats.forEach(function (c) {
        if (q) {
          var title = (c.title || "").toLowerCase();
          var preview = (c.last_message || "").toLowerCase();
          var vid = c.vehicle || {};
          var vStr = ((vid.brand || "") + " " + (vid.model || "")).toLowerCase();
          var id = (c.id || "").toLowerCase();
          if (!title.includes(q) && !preview.includes(q) && !vStr.includes(q) && !id.includes(q)) return;
        }
        var d = new Date(c.updated || c.created);
        var ds = d.toDateString();
        if (ds === today) groups.today.push(c);
        else if (ds === yesterday) groups.yesterday.push(c);
        else if (d > weekAgo) groups.week.push(c);
        else groups.older.push(c);
      });

      var currentChatId = document.documentElement.dataset.chatId || "";

      function renderItems(items) {
        return items.map(function (c) {
          var vid = c.vehicle || {};
          var brand = vid.brand || "";
          var model = vid.model || "";
          var isActive = c.id === currentChatId;
          var msgCount = c.message_count || 0;
          var preview = c.last_message || "No messages yet";
          var logoPath = brand ? "image/car_logos/" + brand.toLowerCase().replace(/[^a-z0-9]/g, "-") + ".svg" : "";
          var d = new Date(c.updated || c.created);
          var dateStr = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });

          return '<div class="gpt-history-item' + (isActive ? " active" : "") + '" data-history-chat="' + c.id + '">' +
            '<div class="gpt-history-item-logo">' +
              (logoPath
                ? '<img src="' + logoPath + '" alt="' + esc(brand) + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="gpt-history-item-icon" style="display:none"><i class="bi bi-car-front-fill"></i></div>'
                : '<div class="gpt-history-item-icon"><i class="bi bi-car-front-fill"></i></div>') +
            '</div>' +
            '<div class="gpt-history-item-content">' +
              (brand ? '<div class="gpt-history-item-vehicle"><i class="bi bi-car-front-fill"></i> ' + esc(brand) + (model ? " " + esc(model) : "") + '</div>' : '') +
              '<div class="gpt-history-item-title">' + esc(c.title || "Untitled") + '</div>' +
              '<div class="gpt-history-item-preview">' + esc(preview) + '</div>' +
              '<div class="gpt-history-item-meta">' +
                '<span class="gpt-history-item-date">' + dateStr + '</span>' +
                '<span class="gpt-history-item-count">' + msgCount + ' message' + (msgCount !== 1 ? "s" : "") + '</span>' +
              '</div>' +
            '</div>' +
            (isActive ? '<span class="gpt-history-active-badge">Active</span>' : '') +
            '<button class="gpt-history-item-menu" data-history-menu="' + c.id + '" title="Options"><i class="bi bi-three-dots"></i></button>' +
          '</div>';
        }).join("");
      }

      var html = "";
      if (groups.today.length) html += '<div class="gpt-history-group">Today</div>' + renderItems(groups.today);
      if (groups.yesterday.length) html += '<div class="gpt-history-group">Yesterday</div>' + renderItems(groups.yesterday);
      if (groups.week.length) html += '<div class="gpt-history-group">This week</div>' + renderItems(groups.week);
      if (groups.older.length) html += '<div class="gpt-history-group">Older</div>' + renderItems(groups.older);
      if (!html) html = '<div class="gpt-history-empty"><i class="bi bi-chat-dots"></i>No conversations found</div>';
      list.innerHTML = html;
    }

    /* Search */
    var searchTimeout = null;
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(loadHistory, 200);
      });
    }

    /* List click handler */
    list.addEventListener("click", async function (e) {
      /* Context menu button */
      var menuBtn = e.target.closest("[data-history-menu]");
      if (menuBtn) {
        e.stopPropagation();
        var chatIdTarget = menuBtn.dataset.historyMenu;
        var existing = document.querySelector(".gpt-history-menu[data-for=\"" + chatIdTarget + "\"]");
        document.querySelectorAll(".gpt-history-menu").forEach(function (m) { m.remove(); });
        if (existing) return;
        var menu = document.createElement("div");
        menu.className = "gpt-history-menu";
        menu.dataset.for = chatIdTarget;
        menu.innerHTML =
          '<button class="gpt-history-menu-item" data-hmenu-open="' + chatIdTarget + '"><i class="bi bi-box-arrow-in-right"></i> Open</button>' +
          '<button class="gpt-history-menu-item" data-hmenu-rename="' + chatIdTarget + '"><i class="bi bi-pencil"></i> Rename</button>' +
          '<div class="gpt-history-menu-divider"></div>' +
          '<button class="gpt-history-menu-item gpt-history-menu-danger" data-hmenu-delete="' + chatIdTarget + '"><i class="bi bi-trash"></i> Delete</button>';
        menuBtn.parentElement.style.position = "relative";
        menuBtn.parentElement.appendChild(menu);
        var closeMenu = function (ev) { if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener("click", closeMenu); } };
        setTimeout(function () { document.addEventListener("click", closeMenu); }, 10);
        return;
      }

      /* Menu actions */
      var openItem = e.target.closest("[data-hmenu-open]");
      if (openItem) {
        document.querySelectorAll(".gpt-history-menu").forEach(function (m) { m.remove(); });
        await openHistoryChat(openItem.dataset.hmenuOpen);
        return;
      }
      var renameItem = e.target.closest("[data-hmenu-rename]");
      if (renameItem) {
        document.querySelectorAll(".gpt-history-menu").forEach(function (m) { m.remove(); });
        showHistoryRenameDialog(renameItem.dataset.hmenuRename);
        return;
      }
      var deleteItem = e.target.closest("[data-hmenu-delete]");
      if (deleteItem) {
        document.querySelectorAll(".gpt-history-menu").forEach(function (m) { m.remove(); });
        showHistoryDeleteDialog(deleteItem.dataset.hmenuDelete);
        return;
      }

      /* Click on item to open */
      var item = e.target.closest("[data-history-chat]");
      if (item) {
        await openHistoryChat(item.dataset.historyChat);
      }
    });

    /* Open a chat */
    async function openHistoryChat(targetId) {
      closeHistory();
      /* Set pending ID so initChat auto-selects it after reload */
      window._pendingChatId = targetId;
      /* Reload the chat modal */
      var chatModalBody = document.getElementById("chat-modal-body");
      if (chatModalBody) {
        chatModalBody.innerHTML = '<div class="chat-modal-loading"><div class="chat-modal-loading-ring"></div><div>Loading conversation...</div></div>';
        fetch("/chat", { credentials: "same-origin" })
          .then(function (r) { return r.text(); })
          .then(function (html) {
            var parser = new DOMParser();
            var doc = parser.parseFromString(html, "text/html");
            var gptWrap = doc.querySelector(".gpt-wrap");
            if (gptWrap) {
              var side = gptWrap.querySelector(".gpt-side");
              if (side) side.remove();
              var overlay2 = gptWrap.querySelector(".gpt-side-overlay");
              if (overlay2) overlay2.remove();
              var tabs = gptWrap.querySelector(".gpt-mode-tabs");
              if (tabs) tabs.remove();
              var toggle = gptWrap.querySelector(".gpt-topbar-toggle");
              if (toggle) toggle.remove();
              var main = gptWrap.querySelector(".gpt-main");
              if (main) main.style.marginLeft = "0";
              var visual = gptWrap.querySelector(".gpt-chat-visual");
              if (visual) visual.style.display = "none";
              var chatLayout = gptWrap.querySelector(".gpt-chat-layout");
              if (chatLayout) chatLayout.style.gridTemplateColumns = "1fr";
              chatModalBody.innerHTML = "";
              chatModalBody.appendChild(gptWrap);
              if (typeof window.initChat === "function") window.initChat();
              if (typeof initChatHistoryPanel === "function") initChatHistoryPanel();
            }
          });
      }
    }

    /* New chat from history panel — dynamic, no page reload */
    if (newBtn) {
      newBtn.addEventListener("click", async function () {
        /* Prevent double-click */
        if (newBtn.disabled) return;
        newBtn.disabled = true;
        var originalHTML = newBtn.innerHTML;
        newBtn.innerHTML = '<i class="bi bi-arrow-repeat" style="animation:spin 1s linear infinite"></i> Creating...';

        try {
          var res = await fetch("/api/chat/new", { method: "POST" });
          var data = await res.json();
          if (!data.ok || !data.id) {
            throw new Error(data.error || "Failed to create chat");
          }

          /* Update chat ID in DOM and internal state */
          if (typeof window._setChatId === "function") {
            window._setChatId(data.id);
          } else {
            document.documentElement.dataset.chatId = data.id;
          }

          /* Clear current messages */
          var msgsEl = document.getElementById("chat-history");
          if (msgsEl) msgsEl.innerHTML = "";

          /* Show welcome screen */
          var welcome = document.getElementById("gpt-welcome");
          if (welcome) welcome.style.display = "";

          /* Reset visual panel state (hidden in modal) */
          var visual = document.getElementById("gpt-chat-visual");
          var layout = document.querySelector(".gpt-chat-layout");
          if (visual) visual.classList.add("chat-active");
          if (layout) layout.classList.add("chat-active");

          /* Close history panel */
          closeHistory();

          /* Focus the input */
          var chatInput = document.getElementById("chat-input");
          if (chatInput) { chatInput.value = ""; chatInput.style.height = "auto"; chatInput.focus(); }

        } catch (err) {
          /* Show error with retry inside the history panel */
          var listEl = document.getElementById("gpt-history-list");
          if (listEl) {
            listEl.innerHTML =
              '<div class="gpt-history-empty">' +
                '<i class="bi bi-exclamation-triangle"></i>' +
                '<div>Unable to create a new conversation.</div>' +
                '<div style="font-size:0.78rem;color:rgba(255,255,255,0.15);margin-top:6px">' + esc(err.message || "Unknown error") + '</div>' +
                '<button class="gpt-history-new-btn" id="gpt-history-retry-btn" type="button" style="margin-top:14px">' +
                  '<i class="bi bi-arrow-repeat"></i> Retry' +
                '</button>' +
              '</div>';
            var retryBtn = document.getElementById("gpt-history-retry-btn");
            if (retryBtn) retryBtn.addEventListener("click", function () { newBtn.click(); });
          }
        } finally {
          newBtn.disabled = false;
          newBtn.innerHTML = originalHTML;
        }
      });
    }

    /* Delete dialog */
    function showHistoryDeleteDialog(targetId) {
      var overlay = document.createElement("div");
      overlay.className = "gpt-dialog-overlay";
      overlay.innerHTML =
        '<div class="gpt-dialog">' +
          '<div class="gpt-dialog-header">' +
            '<div class="gpt-dialog-icon gpt-dialog-icon--danger"><i class="bi bi-trash"></i></div>' +
            '<h3 class="gpt-dialog-title">Delete conversation?</h3>' +
          '</div>' +
          '<p class="gpt-dialog-text">This conversation and its messages will be permanently removed.</p>' +
          '<div class="gpt-dialog-actions">' +
            '<button class="gpt-dialog-btn gpt-dialog-btn--ghost" id="gpt-dialog-cancel">Cancel</button>' +
            '<button class="gpt-dialog-btn gpt-dialog-btn--danger" id="gpt-dialog-confirm">Delete</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);
      requestAnimationFrame(function () { overlay.classList.add("open"); });
      overlay.querySelector("#gpt-dialog-cancel").onclick = function () { overlay.classList.remove("open"); setTimeout(function () { overlay.remove(); }, 200); };
      overlay.querySelector("#gpt-dialog-confirm").onclick = async function () {
        overlay.classList.remove("open");
        setTimeout(function () { overlay.remove(); }, 200);
        await fetch("/api/chat/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: targetId }),
        });
        /* If deleted the active chat, auto-create a new one — dynamically */
        var currentId = document.documentElement.dataset.chatId || "";
        if (targetId === currentId) {
          var newRes = await fetch("/api/chat/new", { method: "POST" });
          var newData = await newRes.json();
          if (newData.ok && newData.id) {
            /* Update chat ID in DOM and internal state */
            if (typeof window._setChatId === "function") {
              window._setChatId(newData.id);
            } else {
              document.documentElement.dataset.chatId = newData.id;
            }
            /* Clear messages and show welcome */
            var msgsEl = document.getElementById("chat-history");
            if (msgsEl) msgsEl.innerHTML = "";
            var welcome = document.getElementById("gpt-welcome");
            if (welcome) welcome.style.display = "";
            /* Reset visual panel */
            var visual = document.getElementById("gpt-chat-visual");
            var layout = document.querySelector(".gpt-chat-layout");
            if (visual) visual.classList.add("chat-active");
            if (layout) layout.classList.add("chat-active");
          }
        }
        loadHistory();
      };
      overlay.addEventListener("click", function (ev) { if (ev.target === overlay) { overlay.classList.remove("open"); setTimeout(function () { overlay.remove(); }, 200); } });
    }

    /* Rename dialog */
    function showHistoryRenameDialog(targetId) {
      var item = list.querySelector('[data-history-chat="' + targetId + '"]');
      var currentTitle = item ? (item.querySelector(".gpt-history-item-title")?.textContent || "") : "";
      var overlay = document.createElement("div");
      overlay.className = "gpt-dialog-overlay";
      overlay.innerHTML =
        '<div class="gpt-dialog">' +
          '<div class="gpt-dialog-header">' +
            '<div class="gpt-dialog-icon"><i class="bi bi-pencil"></i></div>' +
            '<h3 class="gpt-dialog-title">Rename conversation</h3>' +
          '</div>' +
          '<input class="gpt-dialog-input" id="gpt-history-rename-input" value="' + esc(currentTitle) + '" placeholder="Enter a new title...">' +
          '<div class="gpt-dialog-actions">' +
            '<button class="gpt-dialog-btn gpt-dialog-btn--ghost" id="gpt-dialog-cancel">Cancel</button>' +
            '<button class="gpt-dialog-btn gpt-dialog-btn--primary" id="gpt-dialog-confirm">Rename</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);
      requestAnimationFrame(function () { overlay.classList.add("open"); });
      var inputEl = overlay.querySelector("#gpt-history-rename-input");
      inputEl.focus();
      inputEl.select();
      inputEl.addEventListener("keydown", function (ev) { if (ev.key === "Enter") overlay.querySelector("#gpt-dialog-confirm").click(); });
      overlay.querySelector("#gpt-dialog-cancel").onclick = function () { overlay.classList.remove("open"); setTimeout(function () { overlay.remove(); }, 200); };
      overlay.querySelector("#gpt-dialog-confirm").onclick = async function () {
        var newTitle = inputEl.value.trim();
        if (!newTitle) return;
        overlay.classList.remove("open");
        setTimeout(function () { overlay.remove(); }, 200);
        await fetch("/api/chat/rename", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: targetId, title: newTitle }),
        });
        loadHistory();
      };
      overlay.addEventListener("click", function (ev) { if (ev.target === overlay) { overlay.classList.remove("open"); setTimeout(function () { overlay.remove(); }, 200); } });
    }
  }

  /* ---------------- Chat Modal ---------------- */
  function initChatModal() {
    const overlay = document.getElementById("chat-modal-overlay");
    const backdrop = document.getElementById("chat-modal-backdrop");
    const closeBtn = document.getElementById("chat-modal-close");
    const body = document.getElementById("chat-modal-body");
    const sidebarLink = document.getElementById("sidebar-ai-chat");
    if (!overlay || !body) return;

    let lastFocused = null;

    function openChatModal() {
      lastFocused = document.activeElement;
      overlay.classList.add("open");
      overlay.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";

      /* Show loading then fetch chat page */
      body.innerHTML = '<div class="chat-modal-loading"><div class="chat-modal-loading-ring"></div><div>Loading AI Chat...</div></div>';

      fetch("/chat", { credentials: "same-origin" })
        .then(function (res) { return res.text(); })
        .then(function (html) {
          var parser = new DOMParser();
          var doc = parser.parseFromString(html, "text/html");
          var gptWrap = doc.querySelector(".gpt-wrap");
          if (gptWrap) {
            /* Remove any sidebar elements */
            var side = gptWrap.querySelector(".gpt-side");
            if (side) side.remove();
            var overlay2 = gptWrap.querySelector(".gpt-side-overlay");
            if (overlay2) overlay2.remove();
            /* Remove mode tabs */
            var tabs = gptWrap.querySelector(".gpt-mode-tabs");
            if (tabs) tabs.remove();
            /* Remove topbar toggle */
            var toggle = gptWrap.querySelector(".gpt-topbar-toggle");
            if (toggle) toggle.remove();
            /* Make main full width */
            var main = gptWrap.querySelector(".gpt-main");
            if (main) main.style.marginLeft = "0";
            /* Hide visual panel */
            var visual = gptWrap.querySelector(".gpt-chat-visual");
            if (visual) visual.style.display = "none";
            /* Make chat layout single column */
            var chatLayout = gptWrap.querySelector(".gpt-chat-layout");
            if (chatLayout) chatLayout.style.gridTemplateColumns = "1fr";

            body.innerHTML = "";
            body.appendChild(gptWrap);

            /* Re-attach inline script functionality */
            var scripts = doc.querySelectorAll("script");
            scripts.forEach(function (s) {
              if (s.src && s.src.indexOf("chat.js") !== -1) {
                var newScript = document.createElement("script");
                newScript.src = s.src;
                document.body.appendChild(newScript);
              }
            });

            /* Initialize chat if available */
            if (typeof window.initChat === "function") {
              window.initChat();
            }
            /* Initialize chat history panel */
            if (typeof initChatHistoryPanel === "function") {
              initChatHistoryPanel();
            }
          } else {
            body.innerHTML = '<div class="chat-modal-loading">Failed to load chat.</div>';
          }
        })
        .catch(function () {
          body.innerHTML = '<div class="chat-modal-loading">Failed to load chat.</div>';
        });
    }

    function closeChatModal() {
      overlay.classList.remove("open");
      overlay.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
      if (lastFocused && lastFocused.focus) lastFocused.focus();
    }

    /* Sidebar link */
    if (sidebarLink) {
      sidebarLink.addEventListener("click", function (e) {
        e.preventDefault();
        openChatModal();
      });
    }

    /* Close handlers */
    if (closeBtn) closeBtn.addEventListener("click", closeChatModal);
    if (backdrop) backdrop.addEventListener("click", closeChatModal);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && overlay.classList.contains("open")) {
        e.preventDefault();
        closeChatModal();
      }
    });
  }

  /* ---------------- Init ---------------- */
  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initSidebar();
    initHoverSidebar();
    initSidebarTooltips();
    initSplash();
    initCountUp();
    initChat();
    initChatModal();
    initDiagnoseText();
    initDiagnoseImage();
    initDiagnoseAudio();
    initDiagnoseVideo();
    initMaintenance();
    initSettings();
    initContact();
  });
})();
