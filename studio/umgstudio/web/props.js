// Панель свойств с правкой: поле под каждое значение UE (числа, флажки, списки, цвет, текст), «{}» — строка как есть,
// «×» — убрать свойство, «+ свойство» — из шаблонов класса. Правка → onEdit(где, ключ, строка UE | null).
import { parse, stringify, isLoc, locArgs, withLocText, num, quote } from "./uevalue.js";
import { lin, hex } from "./slate.js";

const ENUMS = {
  HorizontalAlignment: ["HAlign_Fill", "HAlign_Left", "HAlign_Center", "HAlign_Right"],
  VerticalAlignment: ["VAlign_Fill", "VAlign_Top", "VAlign_Center", "VAlign_Bottom"],
  Justification: ["Left", "Center", "Right"],
  SizeRule: ["Auto", "Fill"],
  TextTransformPolicy: ["None", "ToLower", "ToUpper"],
  DrawAs: ["NoDrawType", "Box", "Border", "Image", "RoundedBox"],
  Visibility: ["Visible", "Collapsed", "Hidden", "HitTestInvisible", "SelfHitTestInvisible"],
  Stretch: ["None", "Fill", "ScaleToFit", "ScaleToFitX", "ScaleToFitY", "ScaleToFill", "ScaleBySafeZone", "UserSpecified"],
  StretchDirection: ["Both", "DownOnly", "UpOnly"],
  ImageType: ["NoImage", "FullColor", "Linear"],
  Tiling: ["NoTile", "Horizontal", "Vertical", "Both"],
  RoundingType: ["FixedRadius", "HalfHeightRadius"],
  Orientation: ["Orient_Horizontal", "Orient_Vertical"],
  OverflowPolicy: ["Clip", "Ellipsis"],
  Clipping: ["Inherit", "ClipToBounds", "ClipToBoundsWithoutIntersecting", "ClipToBoundsAlways", "OnDemand"],
};
const FACES = ["Medium", "SemiBold", "Bold", "SemiBoldItalic", "BoldItalic"];
const NAMES = {   // подписи как в Details редактора
  ColorAndOpacity: "Color and Opacity", ShadowColorAndOpacity: "Shadow Color", ShadowOffset: "Shadow Offset",
  TypefaceFontName: "Typeface", LetterSpacing: "Letter Spacing", ImageSize: "Image Size", TintColor: "Tint",
  ResourceObject: "Image", SpecifiedColor: "Color", LayoutData: "Layout", bAutoSize: "Size To Content",
  ZOrder: "ZOrder", RenderOpacity: "Render Opacity", TextTransformPolicy: "Transform Policy",
  HorizontalAlignment: "H Align", VerticalAlignment: "V Align", WidthOverride: "Width Override",
  HeightOverride: "Height Override", BrushColor: "Brush Color", OutlineSettings: "Outline", CornerRadii: "Corner Radii",
};
const C1 = "(R=1.000000,G=1.000000,B=1.000000,A=1.000000)";
const PAD = "(Left=0.000000,Top=0.000000,Right=0.000000,Bottom=0.000000)";
const ALIGN = { HorizontalAlignment: "HAlign_Fill", VerticalAlignment: "VAlign_Fill" };
const COMMON = [
  ["Render Opacity", { RenderOpacity: "1.000000" }],
  ["Render Transform", { RenderTransform: "(Translation=(X=0.000000,Y=0.000000),Scale=(X=1.000000,Y=1.000000),Shear=(X=0.000000,Y=0.000000),Angle=0.000000)" }],
  ["Transform Pivot", { RenderTransformPivot: "(X=0.500000,Y=0.500000)" }],
  ["Visibility", { Visibility: "HitTestInvisible" }],
  ["Clipping", { Clipping: "ClipToBounds" }],
];
function propTemplates(cls, font) {
  const t = {
    TextBlock: [
      ["Text", { Text: 'NSLOCTEXT("Widgets", "Text", "Текст")' }],
      ["Color and Opacity", { ColorAndOpacity: `(SpecifiedColor=${C1})` }],
      ["Font", { Font: `(FontObject="/Script/Engine.Font'${font}.${font.split("/").pop()}'",TypefaceFontName="SemiBold",Size=12.000000)` }],
      ["Justification", { Justification: "Center" }],
      ["Transform Policy (UPPER)", { TextTransformPolicy: "ToUpper" }],
      ["Shadow", { ShadowOffset: "(X=0.000000,Y=1.000000)", ShadowColorAndOpacity: "(R=0.000000,G=0.000000,B=0.000000,A=0.700000)" }],
      ["Auto Wrap Text", { AutoWrapText: "True" }],
      ["Min Desired Width", { MinDesiredWidth: "0.000000" }],
      ["Line Height %", { LineHeightPercentage: "1.000000" }],
    ],
    Image: [["Brush", { Brush: "(ImageSize=(X=32.000000,Y=32.000000))" }], ["Color and Opacity", { ColorAndOpacity: C1 }]],
    SizeBox: [
      ["Width Override", { WidthOverride: "100.000000", bOverride_WidthOverride: "True" }],
      ["Height Override", { HeightOverride: "100.000000", bOverride_HeightOverride: "True" }],
      ["Min Desired Width", { MinDesiredWidth: "0.000000", bOverride_MinDesiredWidth: "True" }],
      ["Min Desired Height", { MinDesiredHeight: "0.000000", bOverride_MinDesiredHeight: "True" }],
      ["Max Desired Width", { MaxDesiredWidth: "0.000000", bOverride_MaxDesiredWidth: "True" }],
      ["Max Desired Height", { MaxDesiredHeight: "0.000000", bOverride_MaxDesiredHeight: "True" }],
    ],
    Border: [
      ["Brush Color", { BrushColor: C1 }], ["Padding", { Padding: PAD }],
      ["Rounded Box", { Background: "(DrawAs=RoundedBox,OutlineSettings=(CornerRadii=(X=4.000000,Y=4.000000,Z=4.000000,W=4.000000),RoundingType=FixedRadius))" }],
      ["Content Color", { ContentColorAndOpacity: C1 }], ["H/V Align", { ...ALIGN }],
    ],
    Spacer: [["Size", { Size: "(X=8.000000,Y=8.000000)" }]],
    ScaleBox: [["Stretch", { Stretch: "ScaleToFit" }], ["Stretch Direction", { StretchDirection: "Both" }]],
  };
  return [...(t[cls] || []), ...COMMON];
}
function slotTemplates(slotCls) {
  const box = [["Padding", { Padding: PAD }], ["Size (Fill)", { Size: "(SizeRule=Fill,Value=1.000000)" }],
    ["H Align", { HorizontalAlignment: "HAlign_Fill" }], ["V Align", { VerticalAlignment: "VAlign_Fill" }]];
  const simple = [["Padding", { Padding: PAD }], ["H Align", { HorizontalAlignment: "HAlign_Fill" }], ["V Align", { VerticalAlignment: "VAlign_Fill" }]];
  return {
    CanvasPanelSlot: [
      ["Layout", { LayoutData: "(Offsets=(Left=0.000000,Top=0.000000,Right=100.000000,Bottom=30.000000),Anchors=(Minimum=(X=0.000000,Y=0.000000),Maximum=(X=0.000000,Y=0.000000)),Alignment=(X=0.000000,Y=0.000000))" }],
      ["Size To Content", { bAutoSize: "True" }], ["ZOrder", { ZOrder: "0" }],
    ],
    HorizontalBoxSlot: box, VerticalBoxSlot: box,
    UniformGridSlot: [["Row", { Row: "0" }], ["Column", { Column: "0" }], ["H Align", { HorizontalAlignment: "HAlign_Fill" }], ["V Align", { VerticalAlignment: "VAlign_Fill" }]],
    GridSlot: [["Row", { Row: "0" }], ["Column", { Column: "0" }], ["Row Span", { RowSpan: "1" }], ["Column Span", { ColumnSpan: "1" }], ...simple],
  }[slotCls] || simple;
}

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const isColor = (g) => g.t === "g" && g.items.length && g.items.every((it) => ["R", "G", "B", "A"].includes(it.k)) && ["R", "G", "B"].every((k) => g.items.some((it) => it.k === k));

function numberInput(n, commit, extra = {}) {
  const inp = el("input", "pe-num");
  inp.type = "number";
  const x = parseFloat(n.v);
  inp.value = String(+x.toFixed(6));
  inp.step = extra.step ?? (n.v.includes(".") && Math.abs(x) <= 1 ? "0.01" : "1");
  inp.addEventListener("input", () => {
    const v = parseFloat(inp.value);
    if (!Number.isFinite(v)) return;
    n.v = num(v, n.v);
    commit();
  });
  return inp;
}

function colorEditor(g, commit) {
  const get = (k) => { const it = g.items.find((i) => i.k === k); return it ? parseFloat(it.v.v) : 1; };
  const set = (k, v) => { let it = g.items.find((i) => i.k === k); if (!it) { it = { k, v: { t: "a", v: "" } }; g.items.push(it); } it.v = { t: "a", v: num(v) }; };
  const wrap = el("span", "pe-color");
  const pick = el("input"); pick.type = "color";
  const hx = el("input", "pe-hex"); hx.size = 7;
  const a = el("input", "pe-num"); a.type = "number"; a.step = "0.01"; a.min = "0"; a.max = "1"; a.title = "Альфа (A)";
  const sync = () => { const h = hex([get("R"), get("G"), get("B"), 1]); pick.value = "#" + h; hx.value = h; a.value = String(+get("A").toFixed(3)); wrap.title = `линейный: R=${get("R").toFixed(6)} G=${get("G").toFixed(6)} B=${get("B").toFixed(6)}`; };
  const fromHex = (h) => {
    h = h.replace(/^#/, "");
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return false;
    const toLin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    [0, 2, 4].forEach((o, i) => set("RGB"[i], toLin(parseInt(h.slice(o, o + 2), 16) / 255)));
    return true;
  };
  pick.addEventListener("input", () => { fromHex(pick.value); hx.value = pick.value.slice(1).toUpperCase(); commit(); });
  hx.addEventListener("change", () => { if (fromHex(hx.value)) { sync(); commit(); } else sync(); });
  a.addEventListener("input", () => { const v = parseFloat(a.value); if (Number.isFinite(v)) { set("A", Math.max(0, Math.min(1, v))); commit(); } });
  sync();
  wrap.append(pick, "#", hx, " A ", a);
  return wrap;
}

// поле для узла; path — ключи от свойства вглубь (для подписей и px у шрифта)
function editor(n, commit, path, ctx) {
  const key = path[path.length - 1];
  if (n.t === "g") {
    if (isColor(n)) return colorEditor(n, commit);
    // короткая группа чисел (X/Y, Z/W) — в одну строку
    const inline = n.items.length <= 4 && n.items.every((it) => it.k && it.k.length <= 2 && it.v.t === "a");
    const box = el("div", inline ? "pe-group pe-inline" : "pe-group");
    n.items.forEach((it, i) => {
      const row = el("div", "pe-sub");
      const lab = el("span", "pe-lab", it.k ? (ctx.label ? ctx.label(path.concat(it.k)) : null) || NAMES[it.k] || it.k : `[${i}]`);
      row.append(lab, editor(it.v, commit, path.concat(it.k ?? i), ctx));
      box.appendChild(row);
    });
    return box;
  }
  if (n.t === "s") {
    const inp = el("input", "pe-text");
    inp.value = n.v;
    if (key === "TypefaceFontName") {
      const sel = el("select", "pe-sel");
      const opts = FACES.includes(n.v) ? FACES : [n.v, ...FACES];
      sel.innerHTML = opts.map((o) => `<option${o === n.v ? " selected" : ""}>${o}</option>`).join("");
      sel.addEventListener("change", () => { n.v = sel.value; commit(); });
      return sel;
    }
    inp.addEventListener("change", () => { n.v = inp.value; commit(); });
    return inp;
  }
  const v = n.v;
  if (v === "True" || v === "False") {
    const c = el("input"); c.type = "checkbox"; c.checked = v === "True";
    c.addEventListener("change", () => { n.v = c.checked ? "True" : "False"; commit(); });
    return c;
  }
  if (/^-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(v)) {
    const inp = numberInput(n, commit);
    if (key === "Size" && path.includes("Font")) {
      // шрифт: Size UE ↔ px дизайна (× 4/3)
      const wrap = el("span", "pe-pair");
      const px = el("input", "pe-num"); px.type = "number"; px.step = "1"; px.title = "px дизайна (Size × 4/3)";
      const syncPx = () => { px.value = String(+(parseFloat(n.v) * 4 / 3).toFixed(2)); };
      syncPx();
      inp.addEventListener("input", syncPx);
      px.addEventListener("input", () => { const p = parseFloat(px.value); if (Number.isFinite(p)) { n.v = num(p * 0.75); inp.value = String(+(p * 0.75).toFixed(6)); commit(); } });
      wrap.append(inp, " = ", px, " px");
      return wrap;
    }
    return inp;
  }
  if (isLoc(v)) {
    const inp = el("input", "pe-text");
    const args = locArgs(v);
    inp.value = args.length ? args[args.length - 1] : "";
    inp.title = v;
    inp.addEventListener("input", () => { n.v = withLocText(n.v, inp.value); commit(); });
    return inp;
  }
  if (ENUMS[key]) {
    const sel = el("select", "pe-sel");
    const opts = ENUMS[key].includes(v) ? ENUMS[key] : [v, ...ENUMS[key]];
    sel.innerHTML = opts.map((o) => `<option${o === v ? " selected" : ""}>${o}</option>`).join("");
    sel.addEventListener("change", () => { n.v = sel.value; commit(); });
    return sel;
  }
  const inp = el("input", "pe-text");
  inp.value = v;
  inp.addEventListener("change", () => { n.v = inp.value; commit(); });
  return inp;
}

// подпись смещений Canvas: при точечном якоре по оси Left/Top — позиция, Right/Bottom — размер
function canvasLabel(rootNode) {
  return (path) => {
    if (path[0] !== "LayoutData" || path[1] !== "Offsets" || path.length !== 3) return null;
    const g = rootNode.items.find((it) => it.k === "Anchors");
    const val = (grp, k1, k2) => { const a = grp && grp.v.items.find((i) => i.k === k1); const b = a && a.v.items && a.v.items.find((i) => i.k === k2); return b ? parseFloat(b.v.v) : 0; };
    const pointX = !g || val(g, "Minimum", "X") === val(g, "Maximum", "X");
    const pointY = !g || val(g, "Minimum", "Y") === val(g, "Maximum", "Y");
    return { Left: pointX ? "X" : "Left", Top: pointY ? "Y" : "Top", Right: pointX ? "Ширина" : "Right", Bottom: pointY ? "Высота" : "Bottom" }[path[2]];
  };
}

function propRow(key, raw, where, opts) {
  const row = el("div", "pe-row");
  const head = el("div", "pe-head");
  head.append(el("span", "pe-key", NAMES[key] || key));
  head.title = key;
  const tools = el("span", "pe-tools");
  const bRaw = el("button", "pe-btn", "{}"); bRaw.type = "button"; bRaw.title = "Строка как в UE (правка вручную)";
  const bDel = el("button", "pe-btn", "×"); bDel.type = "button"; bDel.title = "Убрать свойство (станет значение по умолчанию)";
  tools.append(bRaw, bDel);
  head.append(tools);
  row.append(head);
  let node = parse(raw);
  const body = el("div", "pe-body");
  const commit = () => opts.onEdit(where, key, stringify(node));
  const ctx = { label: key === "LayoutData" ? canvasLabel(node.t === "g" ? node : { items: [] }) : null };
  const fill = () => {
    body.replaceChildren();
    if (row.classList.contains("raw")) {
      const ta = el("textarea", "pe-raw");
      ta.value = stringify(node); ta.rows = Math.min(6, 1 + Math.ceil(ta.value.length / 40)); ta.spellcheck = false;
      ta.addEventListener("change", () => { node = parse(ta.value); opts.onEdit(where, key, ta.value.trim()); });
      body.append(ta);
      return;
    }
    const ed = editor(node, commit, [key], ctx);
    if (node.t !== "g" || isColor(node)) { head.insertBefore(ed, tools); body.hidden = true; } else { body.hidden = false; body.append(ed); }
  };
  bRaw.onclick = () => { head.querySelectorAll(".pe-head > :not(.pe-key):not(.pe-tools)").forEach((e) => e.remove()); row.classList.toggle("raw"); fill(); };
  bDel.onclick = () => opts.onEdit(where, key, null, true);
  fill();
  row.append(body);
  return row;
}

function addRow(templates, have, where, opts) {
  const row = el("div", "pe-add");
  const sel = el("select", "pe-sel");
  const free = templates.filter(([, kv]) => Object.keys(kv).some((k) => !(k in have)));
  sel.innerHTML = '<option value="">+ свойство…</option>' + free.map(([label], i) => `<option value="${i}">${label}</option>`).join("") + '<option value="own">своё (имя = значение UE)…</option>';
  sel.addEventListener("change", () => {
    if (sel.value === "own") {
      const k = prompt("Имя свойства как в тексте UE (например RenderOpacity):");
      if (k && /^[A-Za-z_][A-Za-z0-9_]*$/.test(k)) {
        const v = prompt(`Значение ${k} в формате UE:`, "");
        if (v !== null) opts.onEdit(where, k, v.trim(), true);
      }
    } else if (sel.value !== "") {
      for (const [k, v] of Object.entries(free[+sel.value][1])) if (!(k in have)) opts.onEdit(where, k, v, true);
    }
    sel.value = "";
  });
  row.append(sel);
  return row;
}

const HIDDEN = new Set(["bExpandedInDesigner", "bIsVariable", "DisplayLabel"]);

// n — узел IR (raw — строки из текста); opts: {onEdit(где, ключ, строка|null, перерисовать), onFlag(флаг, bool), font}
export function buildEditor(n, opts) {
  const frag = document.createDocumentFragment();
  const flags = el("div", "pe-flags");
  const mk = (label, title, checked, flag) => {
    const l = el("label", "chk"); l.title = title;
    const c = el("input"); c.type = "checkbox"; c.checked = checked;
    c.addEventListener("change", () => opts.onFlag(flag, c.checked));
    l.append(c, " " + label);
    return l;
  };
  flags.append(mk("Is Variable ✎", "Переменная в графе / BindWidget", n.raw.bIsVariable === "True", "var"),
    mk("Collapsed", "Скрыт в вёрстке (Visibility = Collapsed)", n.raw.Visibility === "Collapsed", "collapsed"));
  frag.append(flags);

  frag.append(el("h4", null, "Свойства"));
  for (const [k, v] of Object.entries(n.raw)) {
    if (HIDDEN.has(k) || /^Slots\(\d+\)$/.test(k) || (k === "Visibility" && v === "Collapsed")) continue;
    frag.append(propRow(k, v, "props", opts));
  }
  frag.append(addRow(propTemplates(n.cls, opts.font), n.raw, "props", opts));

  if (n.slot && n.slot.$raw) {
    const h = el("h4", null, "Слот ");
    h.append(el("span", "hint", n.slot.cls));
    frag.append(h);
    for (const [k, v] of Object.entries(n.slot.$raw)) frag.append(propRow(k, v, "slot", opts));
    frag.append(addRow(slotTemplates(n.slot.cls), n.slot.$raw, "slot", opts));
  }
  return frag;
}

export { quote };
