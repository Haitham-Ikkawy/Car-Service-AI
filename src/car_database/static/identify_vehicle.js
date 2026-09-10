/* Identify Vehicle module: upload a car photo, detect make/model via AI. */
(function () {
  "use strict";
  var zone = document.getElementById("identify-zone");
  if (!zone) return;

  var fileInput = document.getElementById("identify-file");
  var preview = document.getElementById("identify-preview");
  var analyzeBtn = document.getElementById("identify-analyze");
  var output = document.getElementById("identify-output");
  var currentFile = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function t(key) {
    return (window.CS && CS.t) ? CS.t(key) : key;
  }

  function toast(type, title, message) {
    if (window.CS && CS.toast) CS.toast(type, title, message);
  }

  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(2) + " MB";
  }

  function show(file) {
    if (!file || !file.type || file.type.indexOf("image/") !== 0) {
      toast("warning", t("Invalid file"), t("Please choose an image."));
      return;
    }
    currentFile = file;
    zone.classList.add("d-none");
    var url = URL.createObjectURL(file);
    preview.innerHTML =
      '<div class="d-flex flex-column align-items-center gap-2">' +
      '<img class="preview-thumb" src="' + url + '" alt="Preview" style="max-height:240px;border-radius:12px">' +
      '<div class="d-flex align-items-center gap-2 text-soft small"><i class="bi bi-file-earmark-image"></i><span>' +
      esc(file.name) + " · " + fmtSize(file.size || 0) + "</span></div>" +
      '<button class="btn btn-sm btn-ghost" type="button" data-clear-identify><i class="bi bi-x-lg"></i> ' +
      esc(t("Remove")) + "</button></div>";
  }

  function clear() {
    currentFile = null;
    preview.innerHTML = "";
    zone.classList.remove("d-none");
  }

  function loadingPanel(text) {
    return '<div class="card fade-up"><div class="card-body d-flex flex-column align-items-center gap-3 py-5">' +
      '<div class="icon-chip grad xl"><i class="bi bi-stars spin"></i></div>' +
      '<div class="skeleton" style="width:220px;height:16px"></div>' +
      '<div class="skeleton" style="width:300px;height:14px"></div>' +
      '<div class="text-soft small">' + esc(text) + "</div></div></div>";
  }

  function resultRow(icon, label, value) {
    if (!value) return "";
    return '<div class="d-flex gap-3 align-items-start mb-3">' +
      '<div class="report-icon" style="background:var(--brand-soft);color:var(--brand)"><i class="bi ' + icon + '"></i></div>' +
      '<div><div class="eyebrow mb-1">' + esc(label) + '</div><div class="fw-semibold">' + esc(value) + "</div></div></div>";
  }

  function renderResult(r) {
    if (r.unavailable) {
      output.innerHTML = '<div class="card fade-up"><div class="card-body text-center py-5">' +
        '<i class="bi bi-cloud-slash fs-2 text-soft mb-3 d-block"></i>' +
        '<h5>' + esc(t("AI unavailable — enter details manually.")) + "</h5></div></div>";
      return;
    }
    var confPct = Math.round((r.confidence || 0) * 100);
    var noMatch = !r.manufacturer && !r.model;
    if (noMatch) {
      output.innerHTML = '<div class="card fade-up"><div class="card-body text-center py-5">' +
        '<i class="bi bi-search fs-2 text-soft mb-3 d-block"></i>' +
        '<h5>' + esc(t("No details found — enter manually.")) + "</h5></div></div>";
      return;
    }
    var title = [r.manufacturer, r.model].filter(Boolean).join(" ") || t("Vehicle detected");
    output.innerHTML =
      '<div class="card fade-up overflow-hidden" id="identify-card"><div class="card-body p-0">' +
      '<div class="report-section d-flex flex-wrap align-items-center justify-content-between gap-3">' +
      '<div class="d-flex align-items-center gap-3">' +
      '<div class="icon-chip grad"><i class="bi bi-car-front-fill"></i></div>' +
      '<div><div class="eyebrow">' + esc(t("Vehicle detected")) + '</div><h4 class="mb-0 mt-1">' + esc(title) + "</h4></div></div>" +
      '<span class="badge badge-soft-accent"><i class="bi bi-shield-check me-1"></i>' + confPct + "% " + esc(t("Confidence")) + "</span>" +
      "</div>" +
      '<div class="report-section">' +
      resultRow("bi-calendar3", t("Year"), r.year) +
      resultRow("bi-car-front", t("Body style"), r.body_style) +
      resultRow("bi-palette", t("Color"), r.color) +
      resultRow("bi-info-circle", t("Notes"), r.notes) +
      "</div>" +
      '<div class="report-section d-flex gap-2 flex-wrap">' +
      '<button class="btn btn-primary btn-sm" type="button" id="identify-save"><i class="bi bi-check2-circle me-1"></i>' +
      esc(t("Save vehicle")) + "</button>" +
      "</div></div></div>";

    var saveBtn = document.getElementById("identify-save");
    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>' + esc(t("Save vehicle"));
        var payload = { manufacturer: r.manufacturer || "", model: r.model || "" };
        var yr = parseInt(r.year, 10);
        if (!isNaN(yr)) payload.year = yr;
        fetch("/api/vehicle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
          .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
          .then(function (r2) {
            if (!r2.ok) {
              toast("error", t("Error"), r2.data && r2.data.error);
              saveBtn.disabled = false;
              saveBtn.innerHTML = '<i class="bi bi-check2-circle me-1"></i>' + esc(t("Save vehicle"));
              return;
            }
            toast("success", t("Saved"), title);
            saveBtn.innerHTML = '<i class="bi bi-check2-circle me-1"></i>' + esc(t("Saved"));
          })
          .catch(function () {
            toast("error", t("Error"), "");
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="bi bi-check2-circle me-1"></i>' + esc(t("Save vehicle"));
          });
      });
    }
  }

  function analyze() {
    if (!currentFile) {
      toast("warning", t("Invalid file"), t("Please choose an image."));
      return;
    }
    output.innerHTML = loadingPanel(t("Reading the image…"));
    var fd = new FormData();
    fd.append("file", currentFile);
    fetch("/api/vehicle/identify-image", { method: "POST", body: fd })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (r) {
        if (!r.ok) {
          output.innerHTML = "";
          toast("error", t("Analysis failed"), r.data && r.data.error);
          return;
        }
        renderResult(r.data);
        output.scrollIntoView({ behavior: "smooth" });
      })
      .catch(function () {
        output.innerHTML = "";
        toast("error", t("Analysis failed"), "");
      });
  }

  zone.addEventListener("click", function () { fileInput.click(); });
  zone.addEventListener("dragover", function (e) { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", function () { zone.classList.remove("dragover"); });
  zone.addEventListener("drop", function (e) {
    e.preventDefault();
    zone.classList.remove("dragover");
    if (e.dataTransfer.files.length) show(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", function () {
    if (fileInput.files.length) show(fileInput.files[0]);
  });
  preview.addEventListener("click", function (e) {
    if (e.target.closest("[data-clear-identify]")) clear();
  });
  if (analyzeBtn) analyzeBtn.addEventListener("click", analyze);
})();
