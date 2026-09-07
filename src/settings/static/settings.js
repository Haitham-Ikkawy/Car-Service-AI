/* Settings module: handle API key toggle, theme picks, switches, and form submissions. */
(function () {
  'use strict';

  /* --- API key show/hide toggles --- */
  function setupToggle(btnSelector, inputEl) {
    if (!inputEl) return;
    var btn = inputEl.closest('.settings-input-group')?.querySelector(btnSelector);
    if (btn) {
      btn.addEventListener('click', function () {
        var show = inputEl.type === 'password';
        inputEl.type = show ? 'text' : 'password';
        this.querySelector('i').className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
      });
    }
  }
  setupToggle('[data-toggle-pass2]', document.getElementById('gemini-key'));
  setupToggle('[data-toggle-pass3]', document.getElementById('chatgpt-key'));

  /* --- Theme picks --- */
  document.querySelectorAll('.settings-pick[data-setting="theme"]').forEach(function (item) {
    item.addEventListener('click', function () {
      document.querySelectorAll('.settings-pick[data-setting="theme"]').forEach(function (i) { i.classList.remove('selected'); });
      this.classList.add('selected');
      var val = this.dataset.val;
      /* Use the shared helper so "auto" resolves to the OS preference instead of
         setting data-bs-theme="auto" literally. */
      if (window.CS && CS.applyTheme) { CS.applyTheme(val); }
      else { document.documentElement.setAttribute('data-bs-theme', val); localStorage.setItem('cs-theme', val); }
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: val })
      });
    });
  });

  /* --- Accent colour selection --- */
  function persistAccent(hex) {
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accent: hex || '' })
    });
  }
  function markAccentSelected(hex) {
    document.querySelectorAll('.accent-swatch[data-accent]').forEach(function (s) {
      s.classList.toggle('selected', hex && s.dataset.accent.toLowerCase() === hex.toLowerCase());
    });
  }
  document.querySelectorAll('.accent-swatch[data-accent]').forEach(function (sw) {
    sw.addEventListener('click', function () {
      var hex = this.dataset.accent;
      if (window.CS && CS.applyAccent) CS.applyAccent(hex);
      markAccentSelected(hex);
      persistAccent(hex);
    });
  });
  var accentCustom = document.getElementById('accent-custom');
  if (accentCustom) {
    accentCustom.addEventListener('input', function () {
      var hex = this.value;
      if (window.CS && CS.applyAccent) CS.applyAccent(hex);
      markAccentSelected(hex);
    });
    accentCustom.addEventListener('change', function () { persistAccent(this.value); });
  }
  var accentReset = document.getElementById('accent-reset');
  if (accentReset) {
    accentReset.addEventListener('click', function () {
      if (window.CS && CS.resetAccent) CS.resetAccent();
      markAccentSelected(null);
      persistAccent('');
    });
  }
  /* Reflect the stored accent (localStorage, else the server value) on load. */
  (function () {
    var container = document.getElementById('accent-swatches');
    var stored = localStorage.getItem('cs-accent') || (container && container.dataset.current) || '';
    if (stored) { markAccentSelected(stored); if (accentCustom) accentCustom.value = stored; }
  })();

  /* --- Toggle switches --- */
  document.querySelectorAll('.settings-switch-input[data-setting]').forEach(function (input) {
    input.addEventListener('change', function () {
      var group = this.dataset.group || 'settings';
      var setting = this.dataset.setting;
      var val = this.checked;
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group: group, [setting]: val })
      });
    });
  });

  /* --- Forms --- */
  var apiForm = document.getElementById('api-key-form');
  if (apiForm) {
    apiForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var geminiVal = document.getElementById('gemini-key')?.value || '';
      var chatgptVal = document.getElementById('chatgpt-key')?.value || '';
      var modelVal = document.getElementById('gemini-model')?.value || '';
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gemini_key: geminiVal, chatgpt_key: chatgptVal, model: modelVal })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (window.CS && window.CS.toast) CS.toast(d.ok ? 'success' : 'error', d.ok ? 'Saved' : 'Error');
      });
    });
  }

  var a11yForm = document.getElementById('a11y-form');
  if (a11yForm) {
    function collectA11y() {
      var data = {};
      a11yForm.querySelectorAll('[name]').forEach(function (el) {
        data[el.name] = el.type === 'checkbox' ? el.checked : el.value;
      });
      return data;
    }
    /* Apply instantly as the user toggles/selects — no save needed to see it. */
    a11yForm.querySelectorAll('[name]').forEach(function (el) {
      el.addEventListener('change', function () {
        if (window.CS && CS.applyA11y) CS.applyA11y(collectA11y());
      });
    });
    a11yForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var data = collectA11y();
      if (window.CS && CS.applyA11y) CS.applyA11y(data);
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ a11y: data })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (window.CS && window.CS.toast) CS.toast(d.ok ? 'success' : 'error', d.ok ? 'Saved' : 'Error');
      });
    });
  }
})();
