/* Sound diagnosis module: show the chosen recording file name and size. */
(function () {
  'use strict';
  var input = document.getElementById('audio-file');
  var preview = document.getElementById('audio-preview');
  if (!input || !preview) return;
  function fmt(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(2) + ' MB';
  }
  input.addEventListener('change', function () {
    var file = input.files && input.files[0];
    preview.innerHTML = '';
    if (!file) return;
    var tag = document.createElement('span');
    tag.className = 'badge badge-soft-accent';
    tag.textContent = (file.name || 'audio') + ' · ' + fmt(file.size || 0);
    preview.appendChild(tag);
  });
})();
