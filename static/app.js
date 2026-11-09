const $ = (id) => document.getElementById(id);
const screens = ["scenario", "form", "progress", "result", "error"];
let scenario = null;
let pollTimer = null;


function show(name) {
  screens.forEach((s) => ($("screen-" + s).hidden = s !== name));
}


async function api(path, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error(data.detail || "Ошибка " + res.status);
  return data;
}


function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}


// ---------- выбор сценария и форма ----------
document.querySelectorAll(".card").forEach((btn) =>
  btn.addEventListener("click", () => openForm(btn.dataset.scenario)));


function sourceType() {
  return document.querySelector("input[name=source_type]:checked").value;
}


function syncSource() {
  const isFile = sourceType() === "file";
  $("url-row").hidden = isFile;
  $("file-row").hidden = !isFile;
}


function openForm(name) {
  scenario = name;
  $("form-error").hidden = true;
  $("form-title").textContent = name === "video" ? "Видео" : "Расшифровка созвона";
  $("source-type-row").hidden = name === "meeting";
  if (name === "meeting") {
    document.querySelector("input[name=source_type][value=file]").checked = true;
  }
  syncSource();
  show("form");
}


document.querySelectorAll("input[name=source_type]").forEach((r) =>
  r.addEventListener("change", syncSource));
$("back-btn").addEventListener("click", () => show("scenario"));


$("pick-file").addEventListener("click", async () => {
  $("pick-file").disabled = true;
  try {
    const data = await api("/api/pick-file", "POST");
    if (data.path) $("file-input").value = data.path;
  } finally {
    $("pick-file").disabled = false;
  }
});


$("start-btn").addEventListener("click", async () => {
  const type = scenario === "meeting" ? "file" : sourceType();
  const source = (type === "file" ? $("file-input") : $("url-input")).value.trim();
  const payload = {
    scenario,
    source_type: type,
    source,
    profile: document.querySelector("input[name=profile]:checked").value,
    speakers: parseInt($("speakers").value, 10),
    glossary: $("glossary").value,
  };
  try {
    await api("/api/start", "POST", payload);
    show("progress");
    startPolling();
  } catch (e) {
    $("form-error").textContent = e.message;
    $("form-error").hidden = false;
  }
});


// ---------- прогресс ----------
function startPolling() {
  clearInterval(pollTimer);
  pollTimer = setInterval(poll, 700);
  poll();
}


async function poll() {
  let s;
  try { s = await api("/api/status"); } catch (e) { return; }
  if (s.status === "running") return renderProgress(s);
  clearInterval(pollTimer);
  if (s.status === "done") renderResult(s.result);
  else if (s.status === "error") { $("error-text").textContent = s.error; show("error"); }
  else if (s.status === "cancelled") { show("form"); }
  else show("scenario");
}


function renderProgress(s) {
  show("progress");
  $("progress-label").textContent = s.label;
  $("progress-detail").textContent = s.detail || "";
  $("bar-wrap").hidden = !!s.finalizing;
  const fill = $("bar-fill");
  if (s.fraction === null || s.fraction === undefined) {
    fill.classList.add("indeterminate");
    fill.style.width = "";
    $("bar-percent").textContent = "";
  } else {
    fill.classList.remove("indeterminate");
    fill.style.width = (s.fraction * 100).toFixed(1) + "%";
    $("bar-percent").textContent = Math.round(s.fraction * 100) + "%";
  }
}


$("cancel-btn").addEventListener("click", () => api("/api/cancel", "POST"));


// ---------- результат ----------
function block(title) {
  const b = el("div", null, "block-card");
  b.appendChild(el("h3", title));
  return b;
}


function textBlock(container, text) {
  if (!text) { container.appendChild(el("p", "В записи не найдено.", "muted")); return; }
  let ul = null;
  text.split("\n").forEach((raw) => {
    const line = raw.trim();
    if (!line) return;
    if (/^[-•*]\s/.test(line)) {
      if (!ul) { ul = el("ul"); container.appendChild(ul); }
      ul.appendChild(el("li", line.slice(2)));
    } else {
      ul = null;
      container.appendChild(el("p", line));
    }
  });
}


function renderResult(r) {
  $("result-title").textContent = r.title;
  $("result-path").textContent = r.docx_path;
  const root = $("result-blocks");
  root.innerHTML = "";
  let n = 1;


  const sum = block(n++ + ") Саммари");
  textBlock(sum, r.summary);
  root.appendChild(sum);


  const tr = block(n++ + ") Расшифровка");
  r.transcript.forEach((t) => {
    const p = el("p", null, "turn");
    p.appendChild(el("b", "[" + t.time + "] " + t.speaker + ": "));
    p.appendChild(document.createTextNode(t.text));
    tr.appendChild(p);
  });
  root.appendChild(tr);
  show("result");
}


$("reveal-btn").addEventListener("click", () => api("/api/reveal", "POST").catch((e) => alert(e.message)));
$("new-btn").addEventListener("click", async () => { await api("/api/reset", "POST"); show("scenario"); });
$("error-back").addEventListener("click", async () => { await api("/api/reset", "POST"); show("form"); });


// ---------- при загрузке страницы ----------
(async function init() {
  try {
    const s = await api("/api/status");
    if (s.status === "running") { show("progress"); startPolling(); }
    else if (s.status === "done") renderResult(s.result);
    else show("scenario");
  } catch (e) { show("scenario"); }
})();
