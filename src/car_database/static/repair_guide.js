(function () {
  "use strict";

  function q(sel) { return document.querySelector(sel); }
  function qa(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  document.addEventListener("DOMContentLoaded", function () {
    var search = q("#guide-search");
    var filters = q("#guide-filters");
    var items = qa(".guide-item");
    var empty = q("#guide-empty");
    var activeCat = "";

    function apply() {
      var term = (search.value || "").trim().toLowerCase();
      var visible = 0;
      items.forEach(function (item) {
        var matchCat = !activeCat || item.dataset.cats === activeCat;
        var matchTerm = !term || (item.dataset.title || "").toLowerCase().indexOf(term) !== -1;
        var show = matchCat && matchTerm;
        item.style.display = show ? "" : "none";
        if (show) visible += 1;
      });
      empty.hidden = visible !== 0;
    }

    search.addEventListener("input", apply);

    filters.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-cat]");
      if (!btn) return;
      Array.prototype.forEach.call(filters.querySelectorAll("[data-cat]"), function (b) {
        b.classList.toggle("btn-primary", b === btn);
        b.classList.toggle("btn-ghost", b !== btn);
      });
      activeCat = btn.dataset.cat || "";
      apply();
    });
  });
})();
