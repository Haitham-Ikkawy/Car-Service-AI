/* Maintenance module: thousands-separator formatting for km inputs. */
(function () {
  'use strict';
  var form = document.getElementById('maint-form');
  if (!form) return;
  var inputs = form.querySelectorAll('input[type="number"]');
  inputs.forEach(function (input) {
    input.addEventListener('blur', function () {
      var v = parseFloat(input.value);
      if (!isNaN(v) && input.getAttribute('min') !== '0') {
        input.value = String(Math.round(v));
      }
    });
  });
})();
