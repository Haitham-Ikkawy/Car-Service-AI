/* Image diagnosis module: live preview of the chosen photo. */
(function () {
  'use strict';
  var input = document.getElementById('image-file');
  var preview = document.getElementById('image-preview');
  if (!input || !preview) return;
  input.addEventListener('change', function () {
    var file = input.files && input.files[0];
    if (!file) return;
    if (preview.querySelector('img')) preview.innerHTML = '';
    var img = document.createElement('img');
    img.className = 'img-fluid rounded-3';
    img.style.maxHeight = '240px';
    img.alt = '';
    var url = URL.createObjectURL(file);
    img.src = url;
    preview.appendChild(img);
  });
})();
