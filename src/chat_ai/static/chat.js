/* Chat AI module: auto-grow the message textarea. */
(function () {
  'use strict';
  var ta = document.getElementById('chat-input');
  if (!ta) return;
  function grow() {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  }
  ta.addEventListener('input', grow);
  grow();
})();
