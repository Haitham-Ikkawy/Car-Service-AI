/* AI report module (reports): animated stat counters. */
(function () {
  'use strict';
  var els = document.querySelectorAll('.stat-value');
  if (!els.length || !('IntersectionObserver' in window)) return;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      var el = en.target;
      io.unobserve(el);
      var text = (el.textContent || '').trim();
      var m = text.replace(/[\s,]/g, '').match(/^(\D*)(\d+)(\D*)$/);
      if (!m) return;
      var target = parseInt(m[2], 10) || 0;
      var prefix = m[1], suffix = m[3];
      var dur = 600, t0 = null;
      function frame(ts) {
        if (!t0) t0 = ts;
        var p = Math.min(1, (ts - t0) / dur);
        el.textContent = prefix + Math.round(target * (1 - Math.pow(1 - p, 3))).toLocaleString() + suffix;
        if (p < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    });
  }, { threshold: 0.3 });
  els.forEach(function (el) { io.observe(el); });
})();
