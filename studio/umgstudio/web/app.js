// Интерфейс UMG Studio: список экранов, превью, Hierarchy, свойства, живое обновление.
import { Engine, layoutRoot, resetLayout, fontOf, lin, hex, textOf, assetName, PX_PER_PT } from "./slate.js";
import { GLMaterials } from "./shaders.js";
import { valueOf } from "./uevalue.js";
import { buildEditor } from "./props.js";

const $ = (id) => document.getElementById(id);
const S = {
  sources: [], src: null, result: null, wbp: 0,
  vis: {}, texts: {}, stateName: null, selected: null,
  materials: {}, images: {}, nested: {}, gl: null,
  design: { ok: false, components: [] },
  edits: {},          // несохранённые правки из панели свойств: "WBP::имя" → {wbp, name, props, slot, var, collapsed}
  font: "/Game/UI/HUD/Fonts/F_HUD",
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
  if (!keep && id !== S.src && editCount() && !confirm("Несохранённые правки свойств пропадут. Перейти?")) return;
  if (!keep) { S.vis = {}; S.texts = {}; S.stateName = null; S.selected = null; S.wbp = 0; S.edits = {}; }
  S.src = id;
  prefs.src = id; savePrefs();
  document.querySelectorAll("#sources button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.id === id)));
  const src = S.sources.find((s) => s.id === id);
  $("srcTitle").textContent = src ? src.file : id;
  $("bBuild").disabled = !src || src.kind !== "spec";
  $("bMakeSpec").hidden = !src || src.kind === "spec";
  $("bRegen").hidden = !src || !src.generated;
  $("bAiTweaks").hidden = !src || !src.tweaks;
  $("diffPane").hidden = true;
  S.result = await api("/api/render?src=" + encodeURIComponent(id));
  if (keep && prefs.wbpName) {
    const i = (S.result.widgets || []).findIndex((w) => w.wbp === prefs.wbpName);
    if (i >= 0) S.wbp = i;
  }
  reapplyEdits();
  renderTabs();
  await render();
  updateEditBar();
  aiContext();
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
  const need = new Set(), tex = new Map();   // текстура: имя → пакет (/Game/…/T_X) — чтобы взять из открытого UE
  const scan = (r) => walk(r, (n) => {
    if (n.path && n.path.startsWith("/") && !n.path.startsWith("/Script/")) need.add(n.path);
    for (const k of ["Brush", "Background"]) {
      const a = n.props[k] && assetName(n.props[k].ResourceObject);
      if (a && a.kind === "Texture2D") tex.set(a.name, a.path.split(".")[0]);
    }
  });
  scan(root);
  for (let depth = 0; depth < 4 && need.size; depth++) {
    // путь класса /Game/…/WBP_X.WBP_X_C: имя — для поиска на диске, пакет — чтобы взять из открытого UE
    const todo = [...need].filter((p) => !(p.split(".").pop().replace(/_C$/, "") in S.nested));
    need.clear();
    await Promise.all(todo.map(async (path) => {
      const nm = path.split(".").pop().replace(/_C$/, ""), asset = path.split(".")[0];
      const r = await fetch(`/api/wbp?name=${encodeURIComponent(nm)}&asset=${encodeURIComponent(asset)}`);
      S.nested[nm] = r.ok ? (await r.json()).roots[0] : null;
      if (S.nested[nm]) scan(S.nested[nm]);
    }));
  }
  await Promise.all([...tex].filter(([t]) => !(t in S.images)).map(([t, asset]) => new Promise((res) => {
    const img = new Image();
    img.onload = () => { S.images[t] = img; res(); };
    img.onerror = () => { S.images[t] = null; res(); };
    img.src = `/api/texture?name=${encodeURIComponent(t)}&asset=${encodeURIComponent(asset)}`;
  })));
}

// ─── превью ───
let engine = null, root = null;
async function render(opts = {}) {
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
  walk(root, (n) => { if (n.missing) engine.warnings.push(`${n.name}: объекта нет в тексте — дерево неполное (старый плагин выгружал только корень: обнови плагин и «Пересоздать .py из UE»)`); });
  if (w.roots.length > 1) engine.warnings.push(`В тексте ${w.roots.length} корня — показан первый (${w.roots[0].name})`);
  $("dims").textContent = `${w.wbp} · ${Math.round(size[0])}×${Math.round(size[1])}`;
  fit(size);
  renderTree();
  renderStates(w.wbp);
  renderWarnings();
  if (S.selected) select(S.selected, false, opts.keepProps);
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

function select(name, scroll = true, keepProps = false) {
  S.selected = name;
  aiContext();
  document.querySelectorAll(".w.sel").forEach((e) => e.classList.remove("sel"));
  const el = stageEl(name); if (el) el.classList.add("sel");
  document.querySelectorAll(".row").forEach((r) => r.classList.toggle("sel", r.dataset.name === name));
  const row = document.querySelector(`.row[data-name="${CSS.escape(name)}"]`);
  if (row && scroll) row.scrollIntoView({ block: "nearest" });
  const n = findNode(name);
  if (n && keepProps && $("pGeom")) $("pGeom").innerHTML = geomHtml(n);
  else if (n) renderProps(n);
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
function geomHtml(n) {
  const r = n._r, d = n._d;
  let h = "";
  if (r) h += `<dt>Геометрия</dt><dd>x ${r.x.toFixed(1)}, y ${r.y.toFixed(1)}, ${r.w.toFixed(1)}×${r.h.toFixed(1)}</dd>`;
  if (d) h += `<dt>Desired</dt><dd>${d[0].toFixed(1)}×${d[1].toFixed(1)}</dd>`;
  return h + `<dt>Видимость</dt><dd>${escapeHtml(engine.visibility(n))}</dd>`;
}
function renderProps(n) {
  const box = $("props");
  let h = `<h4>${escapeHtml(n.name)} <span class="hint">${escapeHtml(n.cls)}</span></h4><dl>`;
  if (n.path && !n.path.startsWith("/Script/UMG.")) h += `<dt>Класс</dt><dd>${escapeHtml(n.path)}</dd>`;
  h += `</dl><dl id="pGeom">${geomHtml(n)}</dl>`;
  if (canEdit() && !n.missing) {
    box.innerHTML = h;
    box.append(buildEditor(n, { font: S.font, onEdit, onFlag }));
    return;
  }
  if (!canEdit()) h += `<p class="hint">Править можно спецификацию .py: ${S.result && S.result.ok ? "для этого текста нажми «Сделать .py»" : "она сейчас не собралась"}.</p>`;
  h += `<h4>Свойства</h4><dl>`;
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

// ─── правка свойств: сразу в превью, «Сохранить в .py» — в файл спецификации ───
function canEdit() {
  const src = S.sources.find((x) => x.id === S.src);
  return !!(src && src.kind === "spec" && S.result && S.result.ok && currentWidget());
}
function sourceNode(name) {
  const w = currentWidget();
  let f = null;
  if (w) walk(w.roots[0], (n) => { if (!f && n.name === name) f = n; });
  return f;
}
function setRaw(where, n, key, raw) {
  const raws = where === "props" ? n.raw : (n.slot.$raw = n.slot.$raw || {});
  const vals = where === "props" ? n.props : n.slot;
  if (raw === null) { delete raws[key]; delete vals[key]; } else { raws[key] = raw; vals[key] = valueOf(raw); }
}
function setFlag(n, flag, on) {
  const key = flag === "var" ? "bIsVariable" : "Visibility";
  setRaw("props", n, key, on ? (flag === "var" ? "True" : "Collapsed") : null);
  if (flag === "collapsed") delete S.vis[n.name];
}
function editEntry(name) {
  const w = currentWidget();
  const id = w.wbp + "::" + name;
  return (S.edits[id] = S.edits[id] || { wbp: w.wbp, name, props: {}, slot: {} });
}
function editCount() { return Object.values(S.edits).reduce((a, e) => a + Object.keys(e.props).length + Object.keys(e.slot).length + ("var" in e) + ("collapsed" in e), 0); }
let rerender = 0;
function scheduleRender(rebuild) {
  cancelAnimationFrame(rerender);
  rerender = requestAnimationFrame(() => render({ keepProps: !rebuild }));
}
function onEdit(where, key, raw, rebuild = false) {
  const n = sourceNode(S.selected);
  if (!n) return;
  setRaw(where, n, key, raw);
  editEntry(n.name)[where][key] = raw;
  updateEditBar();
  scheduleRender(rebuild);
}
function onFlag(flag, on) {
  const n = sourceNode(S.selected);
  if (!n) return;
  setFlag(n, flag, on);
  editEntry(n.name)[flag] = on;
  updateEditBar();
  scheduleRender(false);
}
function reapplyEdits() {
  // файл перечитан (сохранение, ИИ, правка в редакторе) — несохранённые правки ложатся сверху
  if (!S.result || !S.result.ok) return;
  for (const e of Object.values(S.edits)) {
    const w = S.result.widgets.find((x) => x.wbp === e.wbp);
    if (!w) continue;
    let n = null;
    walk(w.roots[0], (x) => { if (!n && x.name === e.name) n = x; });
    if (!n) continue;
    for (const where of ["props", "slot"]) for (const [k, v] of Object.entries(e[where])) setRaw(where, n, k, v);
    for (const f of ["var", "collapsed"]) if (f in e) setFlag(n, f, e[f]);
  }
}
function updateEditBar() {
  const n = editCount();
  $("editBar").hidden = !n;
  $("editCount").textContent = n ? `не сохранено: ${n}` : "";
}
async function saveEdits() {
  if (!editCount()) return;
  const byWbp = {};
  for (const e of Object.values(S.edits)) (byWbp[e.wbp] = byWbp[e.wbp] || []).push(e);
  const done = { inplace: [], tweak: [] };
  let tweaks = false;
  for (const [wbp, edits] of Object.entries(byWbp)) {
    const r = await api("/api/edit", { src: S.src, wbp, edits });
    if (!r.ok) return toast(r.error || "Не записалось", 7000);
    done.inplace.push(...r.report.inplace); done.tweak.push(...r.report.tweak); tweaks = r.tweaks;
  }
  S.edits = {};
  updateEditBar();
  setUndo(true);
  let msg = "Записано в .py";
  if (done.inplace.length) msg += ` · прямо в вызовы: ${[...new Set(done.inplace)].join(", ")}`;
  if (done.tweak.length) msg += ` · строками tweak(): ${[...new Set(done.tweak)].join(", ")} — «Встроить правки» в чате ИИ перенесёт их в код`;
  toast(msg, done.tweak.length ? 8000 : 4000);
  $("bAiTweaks").hidden = !tweaks;
  if (tweaks && !AI.open) aiToggle(true);
}
async function dropEdits() {
  S.edits = {};
  updateEditBar();
  await selectSource(S.src, true);
}
$("bSaveEdits").onclick = saveEdits;
$("bDropEdits").onclick = dropEdits;
window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveEdits(); }
});
function setUndo(on, label) {
  $("bUndo").hidden = !on;
  if (label) $("bUndo").title = "Отменить: " + label;
}
$("bUndo").onclick = async () => {
  const r = await api("/api/undo", {});
  if (!r.ok) { setUndo(false); return toast(r.error, 3000); }
  toast(`Отменено: ${r.label} (${r.files.join(", ")})`, 4000);
  setUndo(!!r.next, r.next);
};

// ─── ИИ: Claude Code на этом компьютере ───
const AI = { open: false, status: null, running: false };
function aiToggle(open = !AI.open) {
  AI.open = open;
  prefs.ai = open; savePrefs();
  $("aiPanel").hidden = !open;
  document.querySelector(".main").classList.toggle("ai-open", open);
  $("bAi").setAttribute("aria-pressed", String(open));
  if (open) { aiStatus(); aiContext(); setTimeout(() => $("aiInput").focus(), 0); }
  if (root) fit(stageSize());
}
async function aiStatus() {
  const r = await api("/api/agent/status");
  AI.status = r;
  const st = $("aiStatus");
  st.className = "ai-status" + (r.ok ? "" : " bad");
  st.textContent = r.ok ? `Claude Code ${r.version || ""}`.trim() : r.error;
  st.title = r.path || "";
  $("bAiSend").disabled = !r.ok;
  if (!$("aiLog").childElementCount && r.log && r.log.length) r.log.forEach(aiItem);
  aiRunning(r.running);
  setUndo(!!r.undo, r.undo);
}
function aiContext() {
  const box = $("aiCtx");
  if (!box) return;
  const src = S.sources.find((x) => x.id === S.src);
  const w = currentWidget();
  const parts = [];
  if (src) parts.push(`Экран: <b>${escapeHtml(src.file)}</b>${w ? " · " + escapeHtml(w.wbp) : ""}`);
  if (S.selected && $("cAiSel").checked) parts.push(`элемент: <b>${escapeHtml(S.selected)}</b>`);
  box.querySelector("span").innerHTML = parts.join(" · ") || "ничего не открыто";
}
function aiRunning(on) {
  AI.running = on;
  $("bAiStop").hidden = !on;
  $("bAiSend").disabled = on || !(AI.status && AI.status.ok);
  $("aiPanel").classList.toggle("busy", on);
}
const TOOL = { Read: "читает", Edit: "правит", Write: "пишет", MultiEdit: "правит", Glob: "ищет файлы", Grep: "ищет", Skill: "скилл" };
function mdLite(t) {
  return escapeHtml(t).replace(/`([^`\n]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
}
function aiItem(it) {
  const log = $("aiLog");
  const div = document.createElement("div");
  if (it.kind === "user") { div.className = "ai-msg me"; div.textContent = it.text; aiRunning(true); }
  else if (it.kind === "text") { div.className = "ai-msg"; div.innerHTML = mdLite(it.text); }
  else if (it.kind === "tool") { div.className = "ai-tool"; div.textContent = `${TOOL[it.name] || it.name} ${it.target || ""}`; }
  else if (it.kind === "done") {
    div.className = "ai-done" + (it.error ? " bad" : "");
    div.textContent = it.error ? it.error : `Готово за ${it.seconds} с` + (it.files && it.files.length ? ` · изменены: ${it.files.join(", ")}` : " · файлы не менялись");
    if (it.undo && !it.error) {
      const b = document.createElement("button");
      b.className = "mini"; b.textContent = "Отменить";
      b.onclick = () => $("bUndo").click();
      div.append(" ", b);
      setUndo(true, "ИИ");
    }
    aiRunning(false);
  }
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}
async function aiSend(text) {
  text = (text || "").trim();
  if (!text || AI.running) return;
  if (editCount() && confirm("Сначала сохранить несохранённые правки свойств в .py? (иначе ИИ их не увидит)")) await saveEdits();
  let selected = null;
  if (S.selected && $("cAiSel").checked) {
    const n = sourceNode(S.selected);
    if (n) selected = { name: n.name, cls: n.cls, props: n.raw, slot: n.slot && n.slot.$raw };
  }
  const w = currentWidget();
  const r = await api("/api/agent/send", { text, src: S.src, wbp: w ? w.wbp : null, selected });
  if (!r.ok) return aiItem({ kind: "done", error: r.error });
  $("aiInput").value = "";
}
$("bAi").onclick = () => aiToggle();
$("bAiClose").onclick = () => aiToggle(false);
$("aiForm").addEventListener("submit", (e) => { e.preventDefault(); aiSend($("aiInput").value); });
$("aiInput").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); aiSend($("aiInput").value); } });
$("bAiStop").onclick = () => api("/api/agent/stop", {});
$("bAiNew").onclick = async () => { await api("/api/agent/reset", {}); $("aiLog").innerHTML = ""; aiRunning(false); toast("Новый диалог", 1500); };
$("bAiTweaks").onclick = () => aiSend("Встрой правки tweak(...) из панели свойств в вызовы W()/фабрик этих элементов и удали строки tweak.");
$("cAiSel").addEventListener("change", aiContext);

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
let ueOnline = false, lastProjectDir = "";
async function ueStatus() {
  const r = await api("/api/ue/status");
  const el = $("ueStatus");
  el.className = "ue-status " + (r.ok ? (r.otherProject ? "on warn" : "on") : "off");
  el.textContent = r.ok ? `UE ${r.engine.split("-")[0]} · ${r.project}` : "UE: нет связи";
  el.title = r.ok ? (r.otherProject ? `Открыт другой проект (${r.projectDir}), чем в «⚙ Проект»` : "Мост UMG Studio Bridge на связи") : r.error;
  lastProjectDir = r.projectDir || "";
  if (r.adopted) toast(`Проект ${r.project} подключён: спецификации — ${r.projectDir}UMGStudio`, 6000);
  const was = ueOnline;
  ueOnline = !!r.ok;
  $("ueBlock").hidden = !ueOnline;
  if (ueOnline && (!was || r.adopted)) loadUeList();
  return r.ok;
}

// ─── виджеты открытого проекта UE ───
let ueWidgets = [];
async function loadUeList() {
  const box = $("ueList");
  box.innerHTML = '<div class="msg">Загружаю…</div>';
  const r = await api("/api/ue/list");
  if (!r.ok) { ueWidgets = []; box.innerHTML = `<div class="msg">${escapeHtml(r.error)}</div>`; return; }
  ueWidgets = r.widgets;
  renderUeList();
}
function renderUeList() {
  const f = $("ueFilter").value.trim().toLowerCase();
  const list = ueWidgets.filter((w) => !f || w.asset.toLowerCase().includes(f));
  const box = $("ueList");
  if (!ueWidgets.length) { box.innerHTML = '<div class="msg">В проекте нет Widget Blueprint</div>'; return; }
  box.innerHTML = "";
  for (const w of list) {
    const b = document.createElement("button");
    b.title = w.asset + (w.spec ? "\nЕсть спецификация — откроется она" : "\nЗабрать: copy.txt + спецификация .py");
    b.innerHTML = `<span class="dot">${w.spec ? "●" : ""}</span><span>${escapeHtml(w.name)}<div class="path">${escapeHtml(w.asset.replace(/\/[^/]+$/, ""))}</div></span>`;
    b.onclick = () => (w.spec ? openSource(w.spec) : fetchFromUe(w.asset));
    box.appendChild(b);
  }
}
async function openSource(id) { await loadSources(); await selectSource(id); }
async function fetchFromUe(asset) {
  toast("Забираю " + asset + "…", 8000);
  const r = await api("/api/ue/fetch", { asset });
  if (!r.ok) return toast(r.error, 7000);
  toast(r.created ? `Готово: ${r.path.split(/[\\/]/).pop()} — правь .py и жми «В UE ▶»` : "Спецификация уже есть — открываю её (copy.txt обновлён)", 6000);
  await openSource(r.src);
  loadUeList();
}
$("ueFilter").addEventListener("input", renderUeList);
$("bUeRefresh").onclick = loadUeList;
$("bUeFetch").onclick = () => { const p = $("uePath").value.trim(); if (p) fetchFromUe(p); };
$("uePath").addEventListener("keydown", (e) => { if (e.key === "Enter") $("bUeFetch").click(); });
$("bRegen").onclick = async () => {
  const w = currentWidget();
  const asset = w && w.asset;
  if (!asset) return toast("Не знаю путь виджета в UE", 4000);
  if (!confirm(`Пересоздать ${S.sources.find((x) => x.id === S.src).file} из ${asset}? Старый файл сохранится как .py.bak`)) return;
  const r = await api("/api/ue/fetch", { asset, regenerate: true });
  if (!r.ok) return toast(r.error, 7000);
  toast("Пересоздано из UE: " + r.path.split(/[\\/]/).pop(), 5000);
  await openSource(r.src);
};
$("bMakeSpec").onclick = async () => {
  const r = await api("/api/spec-from-copy", { src: S.src });
  if (!r.ok) return toast(r.error, 6000);
  toast("Спецификация: " + r.path.split(/[\\/]/).pop(), 5000);
  await openSource(r.src);
};

// ─── настройки проекта ───
async function openSettings() {
  const info = await api("/api/settings");
  const form = $("settingsForm"), s = info.settings, res = info.resolved;
  $("setFile").textContent = "Файл настроек: " + info.file;
  const ph = {
    project: "не задана — возьмётся из открытого редактора", specs: res.specs.join("\n"), materials: res.materials,
    setup_hud: res.setup_hud, assets: res.assets || "", textures: res.textures.join("\n"), design: res.design,
    widgets: info.defaults.widgets, font: info.defaults.font, materials_content: info.defaults.materials_content,
    textures_content: info.defaults.textures_content, ue: res.ue,
  };
  for (const el of form.elements) {
    if (!el.name) continue;
    const v = s[el.name];
    el.value = Array.isArray(v) ? v.join("\n") : v ?? "";
    if (el.placeholder !== undefined && ph[el.name] !== undefined) el.placeholder = ph[el.name];
    const ex = info.exists[el.name === "specs" ? "work_dir" : el.name];
    el.classList.toggle("bad", ex === false && !!(v && v.length));
    el.classList.toggle("good", ex === true && !!(v && v.length));
  }
  $("settingsDlg").showModal();
}
$("bSettings").onclick = openSettings;
$("bTakeProject").onclick = () => {
  if (!lastProjectDir) return toast("Редактор UE не на связи — открой проект с плагином", 4000);
  $("settingsForm").elements.project.value = lastProjectDir;
};
$("settingsDlg").addEventListener("close", async () => {
  if ($("settingsDlg").returnValue !== "save") return;
  const form = $("settingsForm"), out = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    out[el.name] = el.dataset.list ? el.value.split(/\n+/).map((x) => x.trim()).filter(Boolean) : el.value.trim();
  }
  const info = await api("/api/settings", { settings: out });
  toast("Настройки сохранены: " + info.file, 4000);
  await reloadProjectData();
});
async function reloadProjectData() {
  S.nested = {}; S.images = {};
  S.materials = await api("/api/materials");
  S.gl = new GLMaterials(await api("/api/shaders"));
  S.design = await api("/api/design"); if (!S.design.ok) S.design.components = [];
  fillDesignSelect();
  await loadSources();
  const first = S.sources.find((x) => x.id === S.src) || S.sources.find((x) => x.kind === "spec") || S.sources[0];
  if (first) await selectSource(first.id, first.id === S.src);
  if (ueOnline) loadUeList();
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
    if (msg.agent) return aiItem(msg.agent);
    if (msg.reload) return location.reload();
    if (msg.settings) return reloadProjectData();
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
  api("/api/settings").then((i) => { if (i.content && i.content.font) S.font = i.content.font; });
  if (prefs.ai) aiToggle(true); else api("/api/agent/status").then((r) => setUndo(!!r.undo, r.undo));
  ueStatus();
  setInterval(ueStatus, 5000);
}
main();
