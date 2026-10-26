// Интерфейс UMG Studio: список экранов, превью, Hierarchy, свойства, живое обновление.
import { Engine, layoutRoot, resetLayout, fontOf, lin, hex, textOf, assetName, PX_PER_PT } from "./slate.js";
import { GLMaterials } from "./shaders.js";

const $ = (id) => document.getElementById(id);
const S = {
  sources: [], src: null, result: null, wbp: 0,
  vis: {}, texts: {}, stateName: null, selected: null,
  materials: {}, images: {}, nested: {}, gl: null,
  design: { ok: false, components: [] },
};

// ─── ошибки интерфейса → лог программы (%LOCALAPPDATA%/UMGStudio/log.txt) ───
function reportError(msg) {
  try { fetch("/api/log", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ msg: String(msg) }) }); } catch (e) { /* сервер недоступен */ }
}
window.addEventListener("error", (e) => reportError(`${e.message} @ ${e.filename}:${e.lineno}`));
window.addEventListener("unhandledrejection", (e) => reportError("promise: " + (e.reason && (e.reason.stack || e.reason.message) || e.reason)));

// ─── настройки окна (только удобство: без localStorage всё работает) ───
const PREFS_KEY = "umgstudio-prefs-v1";
let prefs = {};
try { prefs = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") || {}; } catch (e) { prefs = {}; }
function savePrefs() { try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch (e) { /* нет хранилища */ } }

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  return r.json();
}

function toast(msg, ms = 3200) {
  const t = $("toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._h); toast._h = setTimeout(() => t.classList.remove("show"), ms);
}

// ─── источники ───
const GROUPS = [["spec", "Спецификации (.py)"], ["copy", "Копии из UE (copy.txt)"], ["paste", "Тексты вставки (paste.txt)"]];
async function loadSources() {
  const r = await api("/api/sources");
  S.sources = r.sources;
  const box = $("sources");
  box.innerHTML = "";
  for (const [kind, title] of GROUPS) {
    const list = S.sources.filter((s) => s.kind === kind);
    if (!list.length) continue;
    const g = document.createElement("div"); g.className = "grp"; g.textContent = title; box.appendChild(g);
    for (const s of list) {
      const b = document.createElement("button");
      b.textContent = s.file; b.title = s.dir + "/" + s.file; b.dataset.id = s.id;
      b.setAttribute("aria-current", String(s.id === S.src));
      b.onclick = () => selectSource(s.id);
      box.appendChild(b);
    }
  }
}

async function selectSource(id, keep = false) {
  if (!keep) { S.vis = {}; S.texts = {}; S.stateName = null; S.selected = null; S.wbp = 0; }
  S.src = id;
  prefs.src = id; savePrefs();
  document.querySelectorAll("#sources button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.id === id)));
  const src = S.sources.find((s) => s.id === id);
  $("srcTitle").textContent = src ? src.file : id;
  $("bBuild").disabled = !src || src.kind !== "spec";
  $("diffPane").hidden = true;
  S.result = await api("/api/render?src=" + encodeURIComponent(id));
  if (keep && prefs.wbpName) {
    const i = (S.result.widgets || []).findIndex((w) => w.wbp === prefs.wbpName);
    if (i >= 0) S.wbp = i;
  }
  renderTabs();
  await render();
}

function renderTabs() {
  const nav = $("wbpTabs");
  nav.innerHTML = "";
  const ws = (S.result && S.result.widgets) || [];
  if (ws.length < 2) return;
  ws.forEach((w, i) => {
    const b = document.createElement("button");
    b.textContent = w.wbp; b.setAttribute("aria-pressed", String(i === S.wbp));
    b.onclick = () => { S.wbp = i; prefs.wbpName = w.wbp; savePrefs(); S.vis = {}; S.texts = {}; S.selected = null; renderTabs(); render(); };
    nav.appendChild(b);
  });
}

// ─── подготовка: вложенные виджеты и текстуры ───
function walk(n, fn) { fn(n); n.children.forEach((c) => walk(c, fn)); }
async function prepare(root) {
  const need = new Set(), tex = new Set();
  const scan = (r) => walk(r, (n) => {
    if (n.path && n.path.startsWith("/") && !n.path.startsWith("/Script/")) need.add(n.path.split(".").pop().replace(/_C$/, ""));
    for (const k of ["Brush", "Background"]) {
      const a = n.props[k] && assetName(n.props[k].ResourceObject);
      if (a && a.kind === "Texture2D") tex.add(a.name);
    }
  });
  scan(root);
  for (let depth = 0; depth < 4 && need.size; depth++) {
    const todo = [...need].filter((nm) => !(nm in S.nested));
    need.clear();
    await Promise.all(todo.map(async (nm) => {
      const r = await fetch("/api/wbp?name=" + encodeURIComponent(nm));
      S.nested[nm] = r.ok ? (await r.json()).roots[0] : null;
      if (S.nested[nm]) scan(S.nested[nm]);
    }));
  }
  await Promise.all([...tex].filter((t) => !(t in S.images)).map((t) => new Promise((res) => {
    const img = new Image();
    img.onload = () => { S.images[t] = img; res(); };
    img.onerror = () => { S.images[t] = null; res(); };
    img.src = "/api/texture?name=" + encodeURIComponent(t);
  })));
}

// ─── превью ───
let engine = null, root = null;
async function render() {
  const res = S.result;
  const err = $("error");
  const stage = $("stage");
  if (!res || !res.ok) {
    err.hidden = false;
    err.textContent = "Спецификация не выполнилась — превью показывает последнее удачное состояние.\n\n" + ((res && res.error) || "нет ответа");
    return;
  }
  err.hidden = true;
  const w = res.widgets[S.wbp] || res.widgets[0];
  if (!w) { stage.innerHTML = ""; $("tree").innerHTML = '<p class="hint" style="padding:8px 12px">Спецификация ничего не сохранила (нет save()).</p>'; return; }
  root = structuredClone(w.roots[0]);
  await prepare(root);
  engine = new Engine({ vis: S.vis, texts: S.texts, nested: S.nested, images: S.images, materials: S.materials, gl: S.gl });
  const mode = $("selSize").value;
  const screen = { mode, w: mode === "custom" ? +$("inW").value : 1920, h: mode === "custom" ? +$("inH").value : 1080 };
  const size = layoutRoot(engine, root, screen);
  stage.innerHTML = "";
  stage.style.width = size[0] + "px"; stage.style.height = size[1] + "px";
  engine.paint(root, stage);
  const safe = document.createElement("div"); safe.className = "safe"; safe.hidden = !$("cSafe").checked; stage.appendChild(safe);
  if (w.roots.length > 1) engine.warnings.push(`В тексте ${w.roots.length} корня — показан первый (${w.roots[0].name})`);
  $("dims").textContent = `${w.wbp} · ${Math.round(size[0])}×${Math.round(size[1])}`;
  fit(size);
  renderTree();
  renderStates(w.wbp);
  renderWarnings();
  if (S.selected) select(S.selected, false);
  applyDesign(w.wbp, size);
}

// ─── макет из Claude Design ───
function guessComponent(wbp) {
  const base = wbp.replace(/^WBP_/, "").toLowerCase();
  const names = S.design.components.map((c) => c.name);
  return names.find((n) => n.toLowerCase() === base)
    || names.find((n) => n.toLowerCase().startsWith(base) || base.startsWith(n.toLowerCase()))
    || names.find((n) => n.toLowerCase().includes(base) || base.includes(n.toLowerCase())) || "";
}
function fillDesignSelect() {
  const sel = $("selDesign");
  sel.innerHTML = '<option value="">—</option>' + S.design.components.map((c) =>
    `<option value="${c.name}">${c.name}${c.card.page ? " · экран" : ""}</option>`).join("");
  sel.disabled = !S.design.ok;
}
let designLoaded = { over: "", side: "" };
function applyDesign(wbp, size) {
  prefs.design = prefs.design || {};
  const sel = $("selDesign");
  const comp = wbp in prefs.design ? prefs.design[wbp] : guessComponent(wbp);
  if (sel.value !== comp) sel.value = comp;
  const c = S.design.components.find((x) => x.name === comp);
  const modeSel = $("selDMode");
  const mode = (prefs.dmode && prefs.dmode[wbp]) || "side";
  modeSel.value = mode;
  const over = $("designOver"), pane = $("designPane"), vp = $("viewport");
  const showOver = !!c && mode !== "side";
  over.hidden = !showOver;
  pane.hidden = !(c && mode === "side");
  vp.classList.toggle("only-design", showOver && mode === "only");
  $("rngDOp").disabled = !showOver || mode !== "over";
  if (showOver) {
    const url = "/design/view/" + c.name;
    if (designLoaded.over !== url) { over.src = url; designLoaded.over = url; }
    over.style.width = size[0] + "px"; over.style.height = size[1] + "px";
    over.style.transform = $("stage").style.transform;
    over.classList.toggle("diff", mode === "diff");
    over.style.opacity = mode === "over" ? $("rngDOp").value / 100 : 1;
  }
  if (c && mode === "side") {
    const url = "/design/view/" + c.name;
    if (designLoaded.side !== url) { $("designSide").src = url; designLoaded.side = url; }
    $("designReadme").textContent = c.readme || "Нет README у компонента.";
  }
  if (root) fit(size);
}
function currentWbp() { const w = S.result && S.result.widgets && (S.result.widgets[S.wbp] || S.result.widgets[0]); return w && w.wbp; }
function stageSize() { return [parseFloat($("stage").style.width), parseFloat($("stage").style.height)]; }
$("selDesign").addEventListener("change", () => { const w = currentWbp(); if (!w) return; prefs.design = prefs.design || {}; prefs.design[w] = $("selDesign").value; savePrefs(); applyDesign(w, stageSize()); });
$("selDMode").addEventListener("change", () => { const w = currentWbp(); if (!w) return; prefs.dmode = prefs.dmode || {}; prefs.dmode[w] = $("selDMode").value; savePrefs(); applyDesign(w, stageSize()); });
$("rngDOp").addEventListener("input", () => { $("designOver").style.opacity = $("rngDOp").value / 100; });

function fit(size) {
  const vp = $("viewport"), wrap = $("stageWrap"), stage = $("stage");
  const z = $("selZoom").value;
  const s = z === "fit" ? Math.min((vp.clientWidth - 32) / size[0], (vp.clientHeight - 32) / size[1], 4) : +z;
  stage.style.transform = `scale(${s})`; stage.style.transformOrigin = "0 0";
  $("designOver").style.transform = stage.style.transform;
  wrap.style.width = size[0] * s + "px"; wrap.style.height = size[1] * s + "px";
  wrap.style.left = Math.max(16, (vp.clientWidth - size[0] * s) / 2) + "px";
  wrap.style.top = Math.max(16, (vp.clientHeight - size[1] * s) / 2) + "px";
  wrap.style.position = "absolute";
}

function renderWarnings() {
  const box = $("warnings");
  const list = [...new Set(engine.warnings)];
  box.hidden = !list.length;
  box.innerHTML = list.map((t) => `<div>⚠ ${escapeHtml(t)}</div>`).join("");
}

function renderStates(wbp) {
  const box = $("states");
  const states = ((S.result && S.result.states) || []).filter((s) => s.wbp === wbp);
  box.hidden = !states.length;
  box.innerHTML = "";
  if (!states.length) return;
  box.append("Состояния:");
  const mk = (label, st) => {
    const b = document.createElement("button");
    b.className = "chip"; b.textContent = label;
    b.setAttribute("aria-pressed", String(S.stateName === (st ? st.name : null)));
    b.onclick = () => {
      S.vis = {}; S.texts = {}; S.stateName = st ? st.name : null;
      if (st) {
        st.show.forEach((n) => (S.vis[n] = "Visible"));
        st.hide.forEach((n) => (S.vis[n] = "Collapsed"));
        Object.assign(S.texts, st.texts);
      }
      render();
    };
    box.appendChild(b);
  };
  mk("Как в вёрстке", null);
  states.forEach((st) => mk(st.name, st));
}

// ─── Hierarchy ───
function renderTree() {
  const box = $("tree");
  box.innerHTML = "";
  const add = (n, depth) => {
    const row = document.createElement("div");
    row.className = "row"; row.dataset.name = n.name; row.style.paddingLeft = 8 + depth * 14 + "px";
    const collapsed = engine.collapsed(n);
    if (collapsed) row.classList.add("collapsed");
    const isVar = n.props.bIsVariable === true;
    row.innerHTML = `<span class="nm">${escapeHtml(n.name)}</span>${isVar ? '<span class="var" title="Is Variable">✎</span>' : ""}<span class="cls">${escapeHtml(n.cls)}</span>`;
    const eye = document.createElement("button");
    eye.className = "eye" + (collapsed ? "" : " on"); eye.textContent = collapsed ? "◌" : "●";
    eye.title = collapsed ? "Collapsed — показать в превью" : "Скрыть (Collapsed) в превью";
    eye.onclick = (e) => { e.stopPropagation(); S.vis[n.name] = collapsed ? "Visible" : "Collapsed"; S.stateName = null; render(); };
    row.appendChild(eye);
    row.onclick = () => select(n.name);
    row.onmouseenter = () => highlight(n.name, true);
    row.onmouseleave = () => highlight(n.name, false);
    box.appendChild(row);
    n.children.forEach((c) => add(c, depth + 1));
  };
  add(root, 0);
}

function stageEl(name) { return $("stage").querySelector(`.w[data-name="${CSS.escape(name)}"]`); }
function highlight(name, on) { const el = stageEl(name); if (el) el.classList.toggle("hl", on); }

function findNode(name) { let f = null; walk(root, (n) => { if (!f && n.name === name) f = n; }); return f; }

function select(name, scroll = true) {
  S.selected = name;
  document.querySelectorAll(".w.sel").forEach((e) => e.classList.remove("sel"));
  const el = stageEl(name); if (el) el.classList.add("sel");
  document.querySelectorAll(".row").forEach((r) => r.classList.toggle("sel", r.dataset.name === name));
  const row = document.querySelector(`.row[data-name="${CSS.escape(name)}"]`);
  if (row && scroll) row.scrollIntoView({ block: "nearest" });
  const n = findNode(name);
  if (n) renderProps(n);
}

// ─── свойства (как пишет пользователь: значение в строке, HEX + линейный) ───
function colorCell(c) {
  return `<span class="sw" style="background:#${hex(c)};opacity:${Math.max(0.15, c[3])}"></span>#${hex(c)} a${(+c[3]).toFixed(2)} <span class="hint">(R=${c[0].toFixed(6)},G=${c[1].toFixed(6)},B=${c[2].toFixed(6)},A=${c[3].toFixed(6)})</span>`;
}
function pretty(k, v, n) {
  if (k === "Font") {
    const f = fontOf(n);
    const ls = v && v.LetterSpacing ? `, LS ${v.LetterSpacing}` : "";
    return `${f.face} ${+f.size.toFixed(3)} (${+(f.size * PX_PER_PT).toFixed(2)}px)${ls}`;
  }
  if (k === "Text") return escapeHtml(JSON.stringify(textOf(v)));
  if (v && typeof v === "object" && ("SpecifiedColor" in v || ("R" in v && "G" in v))) return colorCell(lin(v));
  if (k === "Brush" || k === "Background") {
    const parts = [];
    if (v.ImageSize) parts.push(`${v.ImageSize.X}×${v.ImageSize.Y}`);
    const a = assetName(v.ResourceObject); if (a) parts.push(a.name);
    if (v.DrawAs) parts.push(v.DrawAs);
    let s = escapeHtml(parts.join(" · ") || "белый квадрат");
    if (v.TintColor) s += "<br>tint " + colorCell(lin(v.TintColor));
    return s;
  }
  return escapeHtml(typeof v === "object" ? JSON.stringify(v) : String(v));
}
function renderProps(n) {
  const box = $("props");
  const r = n._r, d = n._d;
  let h = `<h4>${escapeHtml(n.name)} <span class="hint">${escapeHtml(n.cls)}</span></h4><dl>`;
  if (n.path && !n.path.startsWith("/Script/UMG.")) h += `<dt>Класс</dt><dd>${escapeHtml(n.path)}</dd>`;
  if (r) h += `<dt>Геометрия</dt><dd>x ${r.x.toFixed(1)}, y ${r.y.toFixed(1)}, ${r.w.toFixed(1)}×${r.h.toFixed(1)}</dd>`;
  if (d) h += `<dt>Desired</dt><dd>${d[0].toFixed(1)}×${d[1].toFixed(1)}</dd>`;
  h += `<dt>Видимость</dt><dd>${escapeHtml(engine.visibility(n))}</dd></dl><h4>Свойства</h4><dl>`;
  for (const [k, v] of Object.entries(n.props)) {
    if (k === "bExpandedInDesigner") continue;
    h += `<dt>${escapeHtml(k)}</dt><dd>${pretty(k, v, n)}</dd>`;
  }
  h += "</dl>";
  if (n.slot) {
    h += `<h4>Слот <span class="hint">${escapeHtml(n.slot.cls)}</span></h4><dl>`;
    for (const [k, v] of Object.entries(n.slot)) if (k !== "cls" && !k.startsWith("$")) h += `<dt>${escapeHtml(k)}</dt><dd>${pretty(k, v, n)}</dd>`;
    h += "</dl>";
  }
  box.innerHTML = h;
}

function escapeHtml(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// ─── действия ───
$("bCopy").onclick = async () => {
  const w = S.result && S.result.ok && (S.result.widgets[S.wbp] || S.result.widgets[0]);
  if (!w) return toast("Нечего копировать: спецификация не выполнилась");
  let ok = false;
  try { await navigator.clipboard.writeText(w.text); ok = true; } catch (e) { ok = false; }
  if (!ok) ok = (await api("/api/clipboard", { text: w.text })).ok;
  let count = 0; walk(w.roots[0], () => count++);
  toast(ok ? `Скопировано: ${w.wbp} (${count} элементов). В Designer: выдели пустую Hierarchy или панель → Ctrl+V`
    : "Не удалось положить в буфер обмена");
};
// ─── редактор UE ───
function currentWidget() { return S.result && S.result.ok && (S.result.widgets[S.wbp] || S.result.widgets[0]); }
async function ueStatus() {
  const r = await api("/api/ue/status");
  const el = $("ueStatus");
  el.className = "ue-status " + (r.ok ? "on" : "off");
  el.textContent = r.ok ? `UE ${r.engine.split("-")[0]} · ${r.project}` : "UE: нет связи";
  el.title = r.ok ? "Мост UMG Studio Bridge на связи" : r.error;
  return r.ok;
}
function showMessages(title, lines) {
  engine.warnings.push(title, ...lines);
  renderWarnings();
}
$("bPush").onclick = async () => {
  const w = currentWidget();
  if (!w) return toast("Нечего отправлять: источник не собрался");
  $("bPush").disabled = true; toast(`Отправляю ${w.wbp} в UE…`, 10000);
  const r = await api("/api/ue/push", { src: S.src, wbp: w.wbp });
  $("bPush").disabled = false;
  if (r.offline) { ueStatus(); return toast(r.error, 6000); }
  const head = r.ok ? `${w.wbp} ${r.created ? "создан" : "обновлён"} в UE: ${r.widgets} элементов, корень ${r.root}`
    : `${w.wbp}: ${r.error}`;
  toast(head + (r.backup ? " · копия в Saved/UMGStudio/Backups" : ""), 6000);
  showMessages("UE: " + head, (r.messages || []).filter((m) => !m.startsWith("Инфо")));
};
$("bPull").onclick = async () => {
  const w = currentWidget();
  if (!w) return;
  const r = await api("/api/ue/pull", { src: S.src, wbp: w.wbp });
  if (!r.ok) return toast(r.error, 6000);
  toast(`Забрал ${w.wbp} из UE → ${r.path.split(/[\\/]/).pop()}`, 4000);
  showDiff();
};
async function showDiff() {
  const w = currentWidget();
  if (!w) return;
  const r = await api(`/api/diff?src=${encodeURIComponent(S.src)}&wbp=${encodeURIComponent(w.wbp)}`);
  const pane = $("diffPane"), body = $("diffBody");
  pane.hidden = false;
  if (!r.ok) { $("diffTitle").textContent = "Сравнение с UE"; body.innerHTML = `<p class="hint">${escapeHtml(r.error)}</p>`; return; }
  $("diffTitle").textContent = r.items.length ? `${r.copy}: отличий ${r.items.length} — в UE правда, перенеси их в спецификацию` : `${r.copy}: совпадает со спецификацией`;
  const KIND = { added: "есть только в UE", removed: "нет в UE", class: "класс", parent: "родитель", order: "порядок", prop: "свойство", slot: "слот" };
  body.innerHTML = r.items.length ? "<table><tr><th>Элемент</th><th>Что</th><th>Спецификация</th><th>UE</th></tr>" + r.items.map((d) =>
    `<tr data-name="${escapeHtml(d.name)}"><td>${escapeHtml(d.name)}</td><td class="k-${d.kind}">${KIND[d.kind]}${d.key ? " " + escapeHtml(d.key) : ""}${d.cls ? " · " + escapeHtml(d.cls) : ""}</td>` +
    `<td class="v">${escapeHtml(d.spec ?? "—")}</td><td class="v">${escapeHtml(d.ue ?? (d.kind === "added" ? "в " + (d.parent || "?") : "—"))}</td></tr>`).join("") + "</table>" : "";
  body.querySelectorAll("tr[data-name]").forEach((tr) => (tr.onclick = () => select(tr.dataset.name)));
  if (root) fit(stageSize());
}
$("bDiff").onclick = showDiff;
$("bDiffClose").onclick = () => { $("diffPane").hidden = true; if (root) fit(stageSize()); };

$("bBuild").onclick = async () => {
  const r = await api("/api/build", { src: S.src });
  toast(r.ok ? "Записано:\n" + r.written.map((p) => p.split(/[\\/]/).pop()).join(", ") : "Ошибка: " + r.error, 5000);
};
$("bShowAll").onclick = () => { walk(root, (n) => { if (engine.collapsed(n)) S.vis[n.name] = "Visible"; }); S.stateName = null; render(); };
$("bReset").onclick = () => { S.vis = {}; S.texts = {}; S.stateName = null; render(); };
$("stage").addEventListener("click", (e) => { const el = e.target.closest(".w"); if (el) select(el.dataset.name); });

function bindPref(id, key, apply, prop = "value") {
  const el = $(id);
  if (prefs[key] !== undefined) el[prop] = prefs[key];
  el.addEventListener("change", () => { prefs[key] = el[prop]; savePrefs(); apply(); });
  apply();
}
const applyBg = () => { $("viewport").className = "viewport bg-" + $("selBg").value + ($("cOutline").checked ? " outline" : "") + ($("cVars").checked ? " vars" : ""); };
bindPref("selBg", "bg", applyBg);
bindPref("cOutline", "outline", applyBg, "checked");
bindPref("cVars", "vars", applyBg, "checked");
bindPref("cSafe", "safe", () => { const s = $("stage").querySelector(".safe"); if (s) s.hidden = !$("cSafe").checked; }, "checked");
bindPref("selSize", "size", () => { $("customSize").hidden = $("selSize").value !== "custom"; if (root) render(); });
bindPref("selZoom", "zoom", () => { if (root) fit([parseFloat($("stage").style.width), parseFloat($("stage").style.height)]); });
["inW", "inH"].forEach((id) => $(id).addEventListener("change", () => render()));
window.addEventListener("resize", () => { if (root) fit([parseFloat($("stage").style.width), parseFloat($("stage").style.height)]); });

// ─── живое обновление ───
function listen() {
  const es = new EventSource("/api/events");
  es.onmessage = async (e) => {
    const msg = JSON.parse(e.data);
    if (msg.reload) return location.reload();
    S.nested = {};
    if (msg.files.some((f) => /\.(hlsl|json)$/.test(f) || f === "ue_setup_hud.py")) {
      S.materials = await api("/api/materials");
      S.gl = new GLMaterials(await api("/api/shaders"));
    }
    if (msg.files.some((f) => /\.(html|css|md|json)$/.test(f))) {
      S.design = await api("/api/design"); if (!S.design.ok) S.design.components = [];
      designLoaded = { over: "", side: "" };
    }
    await loadSources();
    if (S.src && S.sources.some((s) => s.id === S.src)) await selectSource(S.src, true);
    toast("Обновлено: " + msg.files.join(", "), 1600);
  };
}

async function main() {
  try { await start(); } catch (e) { reportError("main: " + (e.stack || e)); }
  // окно программы ждёт этот сигнал: без него считает, что интерфейс не загрузился, и пробует другой способ
  fetch("/api/ready?info=" + encodeURIComponent(navigator.userAgent.slice(0, 120)));
}
async function start() {
  const faces = ["500", "600", "700", "italic 600", "italic 700"];
  await Promise.all(faces.map((f) => document.fonts.load(`${f} 20px F_HUD`, "AaЖж0")));
  S.materials = await api("/api/materials");
  S.gl = new GLMaterials(await api("/api/shaders"));
  S.design = await api("/api/design");
  if (!S.design.ok) S.design.components = [];
  fillDesignSelect();
  await loadSources();
  const first = S.sources.find((s) => s.id === prefs.src) || S.sources.find((s) => s.kind === "spec") || S.sources[0];
  if (first) await selectSource(first.id, true);
  listen();
  ueStatus();
  setInterval(ueStatus, 5000);
}
main();
