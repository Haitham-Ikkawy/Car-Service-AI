/* AI report module (text diagnosis): live character counter for the description. */
(function () {
  'use strict';
  var ta = document.getElementById('diag-desc');
  if (!ta) return;
  var wrap = ta.closest('.mb-3') || ta.parentElement;
  var counter = document.createElement('div');
  counter.className = 'form-text text-end small';
  function update() {
    var min = parseInt(ta.getAttribute('minlength') || '0', 10) || 0;
    var n = (ta.value || '').length;
    counter.textContent = min ? n + ' / ' + min + '+' : String(n);
  }
  ta.addEventListener('input', update);
  update();
  wrap.appendChild(counter);
})();
