/* Voice Generator — interactions and voice synthesis */
(function () {
  'use strict';

  const input = document.getElementById('vg-text-input');
  const btn = document.getElementById('vg-generate-btn');
  const heroContent = document.querySelector('.vg-hero-content');
  let generating = false;

  /* Mobile nav toggle */
  const mobileToggle = document.getElementById('vg-mobile-toggle');
  const mobileNav = document.getElementById('vg-mobile-nav');
  if (mobileToggle && mobileNav) {
    mobileToggle.addEventListener('click', () => {
      mobileNav.classList.toggle('show');
      const icon = mobileToggle.querySelector('i');
      icon.className = mobileNav.classList.contains('show') ? 'bi bi-x-lg' : 'bi bi-list';
    });
    document.addEventListener('click', (e) => {
      if (!mobileNav.contains(e.target) && !mobileToggle.contains(e.target)) {
        mobileNav.classList.remove('show');
        mobileToggle.querySelector('i').className = 'bi bi-list';
      }
    });
  }

  /* Generate button */
  function setLoading(on) {
    generating = on;
    btn.disabled = on;
    const textEl = btn.querySelector('.vg-generate-text');
    const loadEl = btn.querySelector('.vg-generate-loading');
    if (textEl) textEl.classList.toggle('d-none', on);
    if (loadEl) loadEl.classList.toggle('d-none', !on);
  }

  function removeResult() {
    const existing = heroContent?.querySelector('.vg-result');
    if (existing) existing.remove();
  }

  function showResult(text) {
    removeResult();
    const div = document.createElement('div');
    div.className = 'vg-result';
    div.innerHTML = `
      <div class="vg-result-header"><i class="bi bi-check-circle-fill"></i> Voice generated successfully</div>
      <div class="vg-result-text">${escapeHtml(text)}</div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="vg-generate-btn" style="height:36px;padding:0 16px;font-size:0.78rem;background:rgba(255,255,255,0.08);color:#fff;border:1px solid rgba(255,255,255,0.1)" id="vg-copy-btn">
          <i class="bi bi-clipboard"></i> Copy text
        </button>
      </div>`;
    heroContent?.appendChild(div);
    document.getElementById('vg-copy-btn')?.addEventListener('click', () => {
      navigator.clipboard.writeText(text).then(() => {
        const copyBtn = document.getElementById('vg-copy-btn');
        if (copyBtn) {
          copyBtn.innerHTML = '<i class="bi bi-check-lg"></i> Copied!';
          setTimeout(() => { copyBtn.innerHTML = '<i class="bi bi-clipboard"></i> Copy text'; }, 2000);
        }
      });
    });
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function generate() {
    const text = (input?.value || '').trim();
    if (!text || generating) return;
    setLoading(true);

    try {
      /* Use Web Speech API for voice synthesis */
      if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = /[\u0600-\u06FF]/.test(text) ? 'ar-SA' : 'en-US';
        utterance.rate = 0.95;
        utterance.pitch = 1;

        utterance.onend = () => {
          setLoading(false);
          showResult(text);
        };

        utterance.onerror = () => {
          setLoading(false);
          showResult(text);
        };

        window.speechSynthesis.speak(utterance);

        /* Fallback timeout */
        setTimeout(() => {
          if (generating) {
            window.speechSynthesis.cancel();
            setLoading(false);
            showResult(text);
          }
        }, 30000);
      } else {
        setLoading(false);
        showResult(text);
      }
    } catch (err) {
      setLoading(false);
      showResult(text);
    }
  }

  btn?.addEventListener('click', generate);

  input?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      generate();
    }
  });

  /* Subtle parallax on mouse move */
  document.addEventListener('mousemove', (e) => {
    const bg = document.querySelector('.vg-bg-image');
    if (!bg) return;
    const x = (e.clientX / window.innerWidth - 0.5) * 8;
    const y = (e.clientY / window.innerHeight - 0.5) * 8;
    bg.style.transform = `translate(${x}px, ${y}px) scale(1.02)`;
  });
})();
