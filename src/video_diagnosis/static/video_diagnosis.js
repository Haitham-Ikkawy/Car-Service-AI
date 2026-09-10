/* Video diagnosis module: live preview of the chosen video. */
(function () {
  'use strict';
  var input = document.getElementById('video-file');
  var preview = document.getElementById('video-preview');
  if (!input || !preview) return;
  input.addEventListener('change', function () {
    var file = input.files && input.files[0];
    if (!file) return;
    if (preview.querySelector('video')) preview.innerHTML = '';
    var video = document.createElement('video');
    video.className = 'w-100 rounded-3';
    video.style.maxHeight = '240px';
    video.controls = true;
    video.src = URL.createObjectURL(file);
    preview.appendChild(video);
  });
})();
