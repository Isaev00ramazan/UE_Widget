// Раскладка и отрисовка дерева IR (umgstudio/t3d.py) по правилам Slate/UMG.
// Два прохода, как в Slate: desired size снизу вверх, затем arrange сверху вниз; DOM повторяет вложенность,
// поэтому Render Transform родителя действует на детей. Значения по умолчанию — как у классов UMG
// (в тексте буфера UE их не пишет).

import { drawMaterial, materialInfo } from "./materials.js";

export const PX_PER_PT = 96 / 72;          // FontDPIPreset=Standard: Size UE × 4/3 = px
const ASC = 1.0, DESC = 0.2;              // Barlow Condensed hhea (upm 1000): 1000 / −200

// ─── значения ───
const num = (v, d = 0) => (typeof v === "number" ? v : d);
const vec = (v, d) => (v && typeof v === "object" ? [num(v.X, d[0]), num(v.Y, d[1])] : d.slice());
export function margin(m, d = [0, 0, 0, 0]) {
  if (!m || typeof m !== "object") return { l: d[0], t: d[1], r: d[2], b: d[3] };
  return { l: num(m.Left, d[0]), t: num(m.Top, d[1]), r: num(m.Right, d[2]), b: num(m.Bottom, d[3]) };
}
export function lin(c, d = [1, 1, 1, 1]) {
  if (!c || typeof c !== "object") return d.slice();
  if (c.SpecifiedColor) c = c.SpecifiedColor;
  return [num(c.R, d[0]), num(c.G, d[1]), num(c.B, d[2]), num(c.A, d[3])];
}
const toSrgb = (x) => (x <= 0.0031308 ? x * 12.92 : 1.055 * Math.pow(x, 1 / 2.4) - 0.055);
export function css(c) {
  const [r, g, b, a] = c.map((v, i) => (i < 3 ? Math.round(Math.max(0, Math.min(1, toSrgb(v))) * 255) : v));
  return `rgba(${r},${g},${b},${+Math.max(0, Math.min(1, a)).toFixed(4)})`;
}
export function hex(c) {
  return c.slice(0, 3).map((v) => Math.round(Math.max(0, Math.min(1, toSrgb(v))) * 255).toString(16).padStart(2, "0")).join("").toUpperCase();
}
const mul = (a, b) => a.map((v, i) => v * b[i]);
const align = (s, d) => (typeof s === "string" ? s.replace(/^[HV]Align_/, "") : d);
export function textOf(v) {
  if (v && typeof v === "object" && "$text" in v) return v.$text;
  return typeof v === "string" ? v : "";
}
export function assetName(ref) {
  // "/Script/Engine.Texture2D'/Game/UI/HUD/Textures/T_Ico_Up.T_Ico_Up'" → { kind: "Texture2D", name: "T_Ico_Up" }
  if (typeof ref !== "string") return null;
  const m = /^\/Script\/[\w]+\.(\w+)'([^']+)'/.exec(ref);
  if (!m) return null;
  return { kind: m[1], name: m[2].split(".").pop(), path: m[2] };
}

// ─── значения по умолчанию слотов UMG ───
const FILL = { h: "Fill", v: "Fill" };
const SLOT_DEF = {
  CanvasPanelSlot: {},
  HorizontalBoxSlot: { pad: [0, 0, 0, 0], ...FILL },
  VerticalBoxSlot: { pad: [0, 0, 0, 0], ...FILL },
  OverlaySlot: { pad: [0, 0, 0, 0], h: "Left", v: "Top" },
  SizeBoxSlot: { pad: [0, 0, 0, 0], ...FILL },
  BorderSlot: { pad: [4, 2, 4, 2], ...FILL },
  BackgroundBlurSlot: { pad: [4, 2, 4, 2], ...FILL },
  ButtonSlot: { pad: [4, 2, 4, 2], h: "Center", v: "Center" },
  ScaleBoxSlot: { pad: [0, 0, 0, 0], h: "Center", v: "Center" },
  UniformGridSlot: { pad: [0, 0, 0, 0], h: "Left", v: "Top" },
  GridSlot: { pad: [0, 0, 0, 0], h: "Left", v: "Top" },
  ScrollBoxSlot: { pad: [0, 0, 0, 0], ...FILL },
  WrapBoxSlot: { pad: [0, 0, 0, 0], h: "Left", v: "Top" },
  SafeZoneSlot: { pad: [0, 0, 0, 0], ...FILL },
  PanelSlot: { pad: [0, 0, 0, 0], ...FILL },
};
function slotInfo(n) {
  const s = n.slot || {};
  const d = SLOT_DEF[s.cls] || SLOT_DEF.PanelSlot;
  return {
    pad: margin(s.Padding, d.pad || [0, 0, 0, 0]),
    h: align(s.HorizontalAlignment, d.h || "Fill"),
    v: align(s.VerticalAlignment, d.v || "Fill"),
    fill: s.Size && s.Size.SizeRule === "Fill",
    fillValue: s.Size ? num(s.Size.Value, 1) : 1,
    row: num(s.Row, 0), col: num(s.Column, 0),
    rowSpan: num(s.RowSpan, 1), colSpan: num(s.ColumnSpan, 1),
  };
}
function canvasInfo(n) {
  const ld = (n.slot && n.slot.LayoutData) || {};
  const o = ld.Offsets || {};
  const an = ld.Anchors || {};
  return {
    off: { l: num(o.Left, 0), t: num(o.Top, 0), r: num(o.Right, 100), b: num(o.Bottom, 30) },
    amin: vec(an.Minimum, [0, 0]), amax: vec(an.Maximum, [0, 0]),
    alignment: vec(ld.Alignment, [0, 0]),
    auto: !!(n.slot && n.slot.bAutoSize),
    z: num(n.slot && n.slot.ZOrder, 0),
  };
}

// ─── Slate: выравнивание ребёнка в выделенном месте (LayoutUtils.h AlignmentArrangeResult) ───
function alignAxis(alloc, desired, pre, post, a) {
  const total = pre + post;
  const size = Math.max(0, a === "Fill" ? alloc - total : Math.min(desired, alloc - total));
  switch (a) {
    case "Left": case "Top": case "Fill": return [pre, size];
    case "Center": return [(alloc - size) / 2 + pre - post, size];
    case "Right": case "Bottom": return [alloc - size - post, size];
  }
  return [pre, size];
}

// ─── шрифт ───
const FACE = {
  Thin: [100, "normal"], ExtraLight: [200, "normal"], Light: [300, "normal"], Regular: [400, "normal"],
  Medium: [500, "normal"], SemiBold: [600, "normal"], Bold: [700, "normal"], ExtraBold: [800, "normal"],
  Black: [900, "normal"],
};
export function fontOf(n) {
  const f = n.props.Font || {};
  const obj = typeof f.FontObject === "string" ? f.FontObject : "";
  const hud = obj.includes("F_HUD");
  const face = typeof f.TypefaceFontName === "string" ? f.TypefaceFontName : (hud ? "Regular" : "Bold");
  const italic = /Italic/.test(face);
  const [weight] = FACE[face.replace("Italic", "") || "Regular"] || [400];
  const size = num(f.Size, 24);
  const px = size * PX_PER_PT;
  const family = hud ? "F_HUD" : '"Roboto", "Segoe UI", Arial, sans-serif';
  return {
    size, px, face, weight, italic, hud,
    ls: (num(f.LetterSpacing, 0) / 1000) * px,
    css: `${italic ? "italic " : ""}${weight} ${px}px ${family}`,
    family,
    lineH: Math.ceil(px * ASC) + Math.ceil(px * DESC),
  };
}
function transformText(n, t) {
  const p = n.props.TextTransformPolicy;
  return p === "ToUpper" ? t.toUpperCase() : p === "ToLower" ? t.toLowerCase() : t;
}

// ─── движок ───
export class Engine {
  constructor(opts = {}) {
    this.vis = opts.vis || {};             // переопределения Visibility из интерфейса: {имя: "Visible"|"Collapsed"}
    this.texts = opts.texts || {};         // переопределения текста (состояния)
    this.nested = opts.nested || {};       // WBP_X → корень IR вложенного виджета
    this.images = opts.images || {};       // T_X → HTMLImageElement | null
    this.materials = opts.materials || {}; // данные мастеров и MI (см. materials.js)
    this.measureCtx = document.createElement("canvas").getContext("2d");
    this.warnings = [];
  }

  visibility(n) {
    return this.vis[n.name] || n.props.Visibility || "Visible";
  }
  collapsed(n) { return this.visibility(n) === "Collapsed"; }
  kids(n) { return n.children.filter((c) => !this.collapsed(c)); }

  measure(text, f) {
    const c = this.measureCtx;
    c.font = f.css;
    if ("letterSpacing" in c) c.letterSpacing = `${f.ls}px`;
    return c.measureText(text).width;
  }

  displayText(n) {
    const t = n.name in this.texts ? this.texts[n.name] : textOf(n.props.Text);
    return transformText(n, t);
  }

  userWidget(n) {
    if (!n.path || !n.path.startsWith("/") || n.path.startsWith("/Script/")) return null;
    const name = n.path.split(".").pop().replace(/_C$/, "");
    // своя копия дерева на каждый экземпляр: у экземпляров разные размеры и раскладка
    if (n._uw === undefined) n._uw = this.nested[name] ? structuredClone(this.nested[name]) : null;
    return { name, root: n._uw };
  }

  // ─── проход 1: желаемый размер ───
  desired(n) {
    if (n._d) return n._d;
    const d = this._desired(n);
    n._d = d;
    return d;
  }

  childDesired(c) {
    const s = slotInfo(c), d = this.desired(c);
    return [d[0] + s.pad.l + s.pad.r, d[1] + s.pad.t + s.pad.b];
  }

  _desired(n) {
    const P = n.props;
    const kids = this.kids(n);
    const one = () => (kids.length ? this.childDesired(kids[0]) : [0, 0]);
    switch (n.cls) {
      case "TextBlock": case "RichTextBlock": {
        const f = fontOf(n);
        const lines = this.displayText(n).split("\n");
        let w = 0;
        for (const l of lines) w = Math.max(w, this.measure(l, f));
        let h = lines.length * f.lineH * num(P.LineHeightPercentage, 1);
        const sh = lin(P.ShadowColorAndOpacity, [0, 0, 0, 0]);
        if (sh[3] > 0) {
          const so = vec(P.ShadowOffset, [1, 1]);
          w += Math.abs(so[0]); h += Math.abs(so[1]);
        }
        const m = margin(P.Margin);
        w += m.l + m.r; h += m.t + m.b;
        return [Math.max(w, num(P.MinDesiredWidth, 0)), h];
      }
      case "Image": {
        return vec((P.Brush || {}).ImageSize, [32, 32]);
      }
      case "Spacer": return vec(P.Size, [1, 1]);
      case "SizeBox": {
        const c = one();
        const ov = (k) => P[k] !== undefined && P["bOverride_" + k] !== false;
        let w = ov("WidthOverride") ? P.WidthOverride : c[0];
        let h = ov("HeightOverride") ? P.HeightOverride : c[1];
        if (!ov("WidthOverride")) {
          if (ov("MinDesiredWidth")) w = Math.max(w, P.MinDesiredWidth);
          if (ov("MaxDesiredWidth")) w = Math.min(w, P.MaxDesiredWidth);
        }
        if (!ov("HeightOverride")) {
          if (ov("MinDesiredHeight")) h = Math.max(h, P.MinDesiredHeight);
          if (ov("MaxDesiredHeight")) h = Math.min(h, P.MaxDesiredHeight);
        }
        return [w, h];
      }
      case "HorizontalBox": case "VerticalBox": case "ScrollBox": {
        const horiz = n.cls === "HorizontalBox" || (n.cls === "ScrollBox" && P.Orientation === "Orient_Horizontal");
        let a = 0, b = 0;
        for (const c of kids) {
          const d = this.childDesired(c);
          if (horiz) { a += d[0]; b = Math.max(b, d[1]); } else { a = Math.max(a, d[0]); b += d[1]; }
        }
        return [a, b];
      }
      case "WrapBox": {
        let a = 0, b = 0;
        for (const c of kids) { const d = this.childDesired(c); a += d[0]; b = Math.max(b, d[1]); }
        return [a, b];
      }
      case "CanvasPanel": {
        // SConstraintCanvas::ComputeDesiredSize
        let w = 0, h = 0;
        for (const c of kids) {
          const ci = canvasInfo(c);
          const size = ci.auto ? this.desired(c) : [ci.off.r, ci.off.b];
          const dockH = ci.amin[0] === ci.amax[0] && (ci.amin[0] === 0 || ci.amin[0] === 1);
          const dockV = ci.amin[1] === ci.amax[1] && (ci.amin[1] === 0 || ci.amin[1] === 1);
          w = Math.max(w, size[0] + (dockH ? Math.abs(ci.off.l) : 0));
          h = Math.max(h, size[1] + (dockV ? Math.abs(ci.off.t) : 0));
        }
        return [w, h];
      }
      case "UniformGridPanel": {
        const sp = margin(P.SlotPadding);
        let cw = num(P.MinDesiredSlotWidth, 0), ch = num(P.MinDesiredSlotHeight, 0), rows = 0, cols = 0;
        for (const c of kids) {
          const s = slotInfo(c), d = this.desired(c);
          cw = Math.max(cw, d[0] + sp.l + sp.r); ch = Math.max(ch, d[1] + sp.t + sp.b);
          rows = Math.max(rows, s.row + 1); cols = Math.max(cols, s.col + 1);
        }
        return [cw * cols, ch * rows];
      }
      case "GridPanel": {
        const g = this.gridSizes(n, kids);
        return [g.cols.reduce((a, b) => a + b, 0), g.rows.reduce((a, b) => a + b, 0)];
      }
      case "Overlay": case "RetainerBox": case "InvalidationBox": case "NamedSlot": case "SafeZone":
      case "ScaleBox": case "Border": case "BackgroundBlur": case "Button": case "CheckBox": case "MenuAnchor": {
        let w = 0, h = 0;
        for (const c of kids) { const d = this.childDesired(c); w = Math.max(w, d[0]); h = Math.max(h, d[1]); }
        if (n.cls === "Border") {
          const ds = vec(P.DesiredSizeScale, [1, 1]);
          w *= ds[0]; h *= ds[1];
        }
        return [w, h];
      }
    }
    const uw = this.userWidget(n);
    if (uw) return uw.root && !this.collapsed(uw.root) ? this.desired(uw.root) : [120, 40];
    let w = 0, h = 0;
    for (const c of kids) { const d = this.childDesired(c); w = Math.max(w, d[0]); h = Math.max(h, d[1]); }
    return [w, h];
  }

  gridSizes(n, kids) {
    const cols = [], rows = [];
    for (const c of kids) {
      const s = slotInfo(c), d = this.childDesired(c);
      if (s.colSpan === 1) cols[s.col] = Math.max(cols[s.col] || 0, d[0]);
      if (s.rowSpan === 1) rows[s.row] = Math.max(rows[s.row] || 0, d[1]);
    }
    for (let i = 0; i < cols.length; i++) cols[i] = cols[i] || 0;
    for (let i = 0; i < rows.length; i++) rows[i] = rows[i] || 0;
    return { cols, rows };
  }

  // ─── проход 2: раскладка детей в локальных координатах родителя ───
  arrange(n, w, h) {
    n._size = [w, h];
    const kids = this.kids(n);
    const P = n.props;
    const place = (c, x, y, cw, ch, extra) => { c._r = { x, y, w: cw, h: ch, ...(extra || {}) }; this.arrange(c, cw, ch); };
    const aligned = (c, aw, ah, ox = 0, oy = 0) => {
      const s = slotInfo(c), d = this.desired(c);
      const [x, cw] = alignAxis(aw, d[0], s.pad.l, s.pad.r, s.h);
      const [y, ch] = alignAxis(ah, d[1], s.pad.t, s.pad.b, s.v);
      place(c, ox + x, oy + y, cw, ch);
    };
    switch (n.cls) {
      case "CanvasPanel": {
        for (const c of kids) {
          const ci = canvasInfo(c);
          const size = ci.auto ? this.desired(c) : [ci.off.r, ci.off.b];
          const ax = [ci.amin[0] * w, ci.amax[0] * w], ay = [ci.amin[1] * h, ci.amax[1] * h];
          let x, y, cw, ch;
          if (ci.amin[0] !== ci.amax[0]) { x = ax[0] + ci.off.l; cw = ax[1] - x - ci.off.r; }
          else { cw = size[0]; x = ax[0] + ci.off.l - cw * ci.alignment[0]; }
          if (ci.amin[1] !== ci.amax[1]) { y = ay[0] + ci.off.t; ch = ay[1] - y - ci.off.b; }
          else { ch = size[1]; y = ay[0] + ci.off.t - ch * ci.alignment[1]; }
          place(c, x, y, cw, ch, { z: ci.z });
        }
        return;
      }
      case "HorizontalBox": case "VerticalBox": case "ScrollBox": {
        const horiz = n.cls === "HorizontalBox" || (n.cls === "ScrollBox" && P.Orientation === "Orient_Horizontal");
        const along = horiz ? w : h;
        let fixed = 0, fillTotal = 0;
        const info = kids.map((c) => {
          const s = slotInfo(c), d = this.desired(c);
          const m = horiz ? s.pad.l + s.pad.r : s.pad.t + s.pad.b;
          const fill = s.fill && n.cls !== "ScrollBox";
          if (fill) { fillTotal += s.fillValue; fixed += m; } else fixed += (horiz ? d[0] : d[1]) + m;
          return { c, s, d, m, fill };
        });
        const free = Math.max(0, along - fixed);
        let pos = 0;
        for (const it of info) {
          const size = it.fill ? (fillTotal > 0 ? (free * it.s.fillValue) / fillTotal : 0) : (horiz ? it.d[0] : it.d[1]);
          const slot = size + it.m;
          if (horiz) {
            const [x, cw] = alignAxis(slot, it.d[0], it.s.pad.l, it.s.pad.r, it.s.h);
            const [y, ch] = alignAxis(h, it.d[1], it.s.pad.t, it.s.pad.b, it.s.v);
            place(it.c, pos + x, y, cw, ch);
          } else {
            const [x, cw] = alignAxis(w, it.d[0], it.s.pad.l, it.s.pad.r, it.s.h);
            const [y, ch] = alignAxis(slot, it.d[1], it.s.pad.t, it.s.pad.b, it.s.v);
            place(it.c, x, pos + y, cw, ch);
          }
          pos += slot;
        }
        return;
      }
      case "WrapBox": {
        let x = 0, y = 0, rowH = 0;
        for (const c of kids) {
          const s = slotInfo(c), d = this.childDesired(c);
          if (x > 0 && x + d[0] > w) { x = 0; y += rowH; rowH = 0; }
          place(c, x + s.pad.l, y + s.pad.t, d[0] - s.pad.l - s.pad.r, d[1] - s.pad.t - s.pad.b);
          x += d[0]; rowH = Math.max(rowH, d[1]);
        }
        return;
      }
      case "UniformGridPanel": {
        const sp = margin(P.SlotPadding);
        let rows = 0, cols = 0;
        for (const c of kids) { const s = slotInfo(c); rows = Math.max(rows, s.row + 1); cols = Math.max(cols, s.col + 1); }
        const cw = cols ? w / cols : 0, ch = rows ? h / rows : 0;
        for (const c of kids) {
          const s = slotInfo(c), d = this.desired(c);
          const [x, ww] = alignAxis(cw, d[0], sp.l, sp.r, s.h);
          const [y, hh] = alignAxis(ch, d[1], sp.t, sp.b, s.v);
          place(c, s.col * cw + x, s.row * ch + y, ww, hh);
        }
        return;
      }
      case "GridPanel": {
        const g = this.gridSizes(n, kids);
        const fillOf = (arr, i) => (Array.isArray(arr) ? num(arr[i], 0) : 0);
        const distribute = (sizes, fills, total) => {
          const fixed = sizes.reduce((a, b, i) => a + (fillOf(fills, i) > 0 ? 0 : b), 0);
          const ft = sizes.reduce((a, b, i) => a + fillOf(fills, i), 0);
          return sizes.map((s, i) => (fillOf(fills, i) > 0 && ft > 0 ? (Math.max(0, total - fixed) * fillOf(fills, i)) / ft : s));
        };
        const cs = distribute(g.cols, P.ColumnFill, w), rs = distribute(g.rows, P.RowFill, h);
        const at = (arr, i) => arr.slice(0, i).reduce((a, b) => a + b, 0);
        for (const c of kids) {
          const s = slotInfo(c);
          const cw = at(cs, s.col + s.colSpan) - at(cs, s.col), ch = at(rs, s.row + s.rowSpan) - at(rs, s.row);
          aligned(c, cw, ch, at(cs, s.col), at(rs, s.row));
        }
        return;
      }
      case "ScaleBox": {
        const c = kids[0];
        if (!c) return;
        const s = slotInfo(c), d = this.desired(c);
        const sw = d[0] > 0 ? w / d[0] : 1, sh = d[1] > 0 ? h / d[1] : 1;
        let k = { ScaleToFit: Math.min(sw, sh), ScaleToFill: Math.max(sw, sh), ScaleToFitX: sw, ScaleToFitY: sh,
          None: 1, UserSpecified: num(P.UserSpecifiedScale, 1) }[P.Stretch || "ScaleToFit"];
        if (P.StretchDirection === "DownOnly") k = Math.min(1, k);
        if (P.StretchDirection === "UpOnly") k = Math.max(1, k);
        const [x] = alignAxis(w, d[0] * k, 0, 0, s.h === "Fill" ? "Center" : s.h);
        const [y] = alignAxis(h, d[1] * k, 0, 0, s.v === "Fill" ? "Center" : s.v);
        place(c, x, y, d[0], d[1], { scale: k });
        return;
      }
    }
    const uw = this.userWidget(n);
    if (uw) {
      if (uw.root && !this.collapsed(uw.root)) { uw.root._r = { x: 0, y: 0, w, h }; this.arrange(uw.root, w, h); }
      return;
    }
    // Overlay, SizeBox, Border, Retainer и прочие с одним/несколькими детьми — каждый выровнен во всей площади
    for (const c of kids) aligned(c, w, h);
  }

  // ─── отрисовка ───
  paint(n, parentEl, opts = {}) {
    const r = n._r;
    const el = document.createElement("div");
    el.className = "w w-" + n.cls;
    el.dataset.name = n.name;
    const st = el.style;
    st.left = r.x + "px"; st.top = r.y + "px"; st.width = Math.max(0, r.w) + "px"; st.height = Math.max(0, r.h) + "px";
    const vis = this.visibility(n);
    if (vis === "Hidden" || n.props.bHiddenInDesigner) st.visibility = "hidden";
    const tf = this.renderTransform(n, r);
    if (tf) { st.transform = tf.css; st.transformOrigin = tf.origin; }
    if (r.scale && r.scale !== 1) { st.transform = `scale(${r.scale})` + (st.transform ? " " + st.transform : ""); st.transformOrigin = "0 0"; }
    if (n.props.RenderOpacity !== undefined) st.opacity = n.props.RenderOpacity;
    if (n.props.Clipping === "ClipToBounds" || n.props.Clipping === "ClipToBoundsAlways") st.overflow = "hidden";
    if (typeof n.props.bIsVariable === "boolean" && n.props.bIsVariable) el.classList.add("is-var");
    parentEl.appendChild(el);
    this.paintSelf(n, el, r);
    let kids = this.kids(n).filter((c) => c._r);
    if (n.cls === "CanvasPanel") kids = kids.map((c, i) => [c, i]).sort((a, b) => (a[0]._r.z || 0) - (b[0]._r.z || 0) || a[1] - b[1]).map((x) => x[0]);
    for (const c of kids) this.paint(c, el, opts);
    const uw = this.userWidget(n);
    if (uw && uw.root && uw.root._r) this.paint(uw.root, el, opts);
    else if (uw) {
      el.classList.add("ph-user");
      el.innerHTML = `<span class="ph-label">${uw.name}</span>`;
      this.warnings.push(`${n.name}: нет вёрстки ${uw.name} (нужна спецификация, copy.txt или paste.txt)`);
    }
    return el;
  }

  renderTransform(n, r) {
    const t = n.props.RenderTransform;
    if (!t || typeof t !== "object") return null;
    const tr = vec(t.Translation, [0, 0]), sc = vec(t.Scale, [1, 1]), sh = vec(t.Shear, [0, 0]);
    const ang = num(t.Angle, 0);
    const pv = vec(n.props.RenderTransformPivot, [0.5, 0.5]);
    // Slate: Scale → Shear → Rotate → Translate (CSS применяет справа налево)
    const css = `translate(${tr[0]}px,${tr[1]}px) rotate(${ang}deg) skew(${-sh[0]}deg,${-sh[1]}deg) scale(${sc[0]},${sc[1]})`;
    return { css, origin: `${pv[0] * 100}% ${pv[1] * 100}%` };
  }

  paintSelf(n, el, r) {
    const P = n.props;
    switch (n.cls) {
      case "TextBlock": case "RichTextBlock": {
        const f = fontOf(n);
        const t = document.createElement("div");
        t.className = "txt";
        t.textContent = this.displayText(n);
        const ts = t.style;
        ts.font = f.css; ts.letterSpacing = f.ls + "px"; ts.lineHeight = f.lineH * num(P.LineHeightPercentage, 1) + "px";
        ts.color = css(lin(P.ColorAndOpacity));
        const sh = lin(P.ShadowColorAndOpacity, [0, 0, 0, 0]);
        if (sh[3] > 0) { const so = vec(P.ShadowOffset, [1, 1]); ts.textShadow = `${so[0]}px ${so[1]}px 0 ${css(sh)}`; }
        const m = margin(P.Margin);
        ts.padding = `${m.t}px ${m.r}px ${m.b}px ${m.l}px`;
        const j = P.Justification;
        ts.textAlign = j === "Center" ? "center" : j === "Right" ? "right" : "left";
        if (P.AutoWrapText) ts.whiteSpace = "pre-wrap";
        el.appendChild(t);
        return;
      }
      case "Image":
        this.paintBrush(el, P.Brush || {}, lin(P.ColorAndOpacity), r, n);
        return;
      case "Border": {
        const bg = P.Background || {};
        this.paintBrush(el, bg, lin(P.BrushColor), r, n);
        return;
      }
      case "BackgroundBlur": {
        const s = num(P.BlurStrength, 0);
        if (s > 0) { el.style.backdropFilter = `blur(${s}px)`; el.style.webkitBackdropFilter = `blur(${s}px)`; }
        return;
      }
      case "RetainerBox": {
        const mat = assetName(P.EffectMaterial);
        if (mat && P.bRetainRender !== false) {
          const info = materialInfo(mat.name, this.materials);
          if (info.master === "M_UI_TextGlow") {
            const p = info.params;
            const c = lin(p.GlowColor, [1, 0.26, 0.01, 0.35]);
            const rad = num(p.Radius, 40);
            el.style.filter = `drop-shadow(0 0 ${rad * 0.35}px ${css([c[0], c[1], c[2], Math.min(1, c[3] * 2.2)])})`;
            el.classList.add("approx");
          }
        }
        return;
      }
      case "Button":
        el.style.background = "rgba(60,60,60,0.9)";
        el.style.borderRadius = "4px";
        return;
    }
  }

  paintBrush(el, brush, color, r, n) {
    const drawAs = brush.DrawAs || "Image";
    if (drawAs === "NoDrawType") return;
    const tint = mul(lin(brush.TintColor), color);
    const res = assetName(brush.ResourceObject);
    if (drawAs === "RoundedBox") {
      const os = brush.OutlineSettings || {};
      const cr = os.CornerRadii || {};
      const rad = [num(cr.X), num(cr.Y), num(cr.Z), num(cr.W)];
      if (os.RoundingType === "HalfHeightRadius") rad.fill(Math.min(r.w, r.h) / 2);
      el.style.borderRadius = rad.map((v) => v + "px").join(" ");
      const ow = num(os.Width, 0);
      if (ow > 0) {
        const oc = mul(lin(os.Color), os.bUseBrushTransparency ? [1, 1, 1, tint[3]] : [1, 1, 1, 1]);
        el.style.boxShadow = `inset 0 0 0 ${ow}px ${css(oc)}`;
      }
    }
    if (!res) {
      if (tint[3] > 0) el.style.backgroundColor = css(tint);
      return;
    }
    if (res.kind === "Texture2D") {
      const img = this.images[res.name];
      if (img) {
        const cv = document.createElement("canvas");
        cv.className = "fill";
        const k = 2;
        cv.width = Math.max(1, Math.round(r.w * k)); cv.height = Math.max(1, Math.round(r.h * k));
        const c = cv.getContext("2d");
        c.drawImage(img, 0, 0, cv.width, cv.height);
        c.globalCompositeOperation = "multiply";
        c.fillStyle = css([tint[0], tint[1], tint[2], 1]);
        c.fillRect(0, 0, cv.width, cv.height);
        c.globalCompositeOperation = "destination-in";
        c.drawImage(img, 0, 0, cv.width, cv.height);
        cv.style.opacity = tint[3];
        el.appendChild(cv);
      } else {
        el.classList.add("ph-tex");
        el.style.setProperty("--tint", css([tint[0], tint[1], tint[2], 1]));
        el.style.opacity = Math.max(0.35, tint[3]);
        el.title = res.name;
      }
      return;
    }
    if (res.kind === "MaterialInstanceConstant" || res.kind === "Material" || res.kind === "MaterialInstanceDynamic") {
      const info = materialInfo(res.name, this.materials);
      if (info.mismatch(r)) this.warnings.push(`${n.name}: Size в ${res.name} = ${info.size.join("×")}, а Image ${Math.round(r.w)}×${Math.round(r.h)} — скосы/свечение поплывут`);
      const cv = document.createElement("canvas");
      cv.className = "fill";
      const k = 2;
      cv.width = Math.max(1, Math.round(r.w * k)); cv.height = Math.max(1, Math.round(r.h * k));
      const ok = drawMaterial(cv.getContext("2d"), info, r.w, r.h, k, tint);
      if (!ok) { el.classList.add("ph-mat"); el.innerHTML = `<span class="ph-label">${res.name}</span>`; return; }
      if (!info.exact) el.classList.add("approx");
      el.appendChild(cv);
      return;
    }
    el.classList.add("ph-mat");
    el.innerHTML = `<span class="ph-label">${res.name}</span>`;
  }
}

// Сбросить кэш размеров (после смены состояний)
export function resetLayout(root) {
  const stack = [root];
  while (stack.length) {
    const n = stack.pop();
    delete n._d; delete n._r; delete n._size;
    stack.push(...n.children);
    if (n._uw) stack.push(n._uw);
  }
}

// Корень: Canvas → экран (1920×1080 по умолчанию), иначе — желаемый размер (как Desired on Screen)
export function layoutRoot(engine, root, screen) {
  const d = engine.desired(root);
  const fillScreen = screen.mode === "screen" || (screen.mode === "auto" && root.cls === "CanvasPanel");
  const size = screen.mode === "custom" ? [screen.w, screen.h] : fillScreen ? [screen.w, screen.h] : d;
  root._r = { x: 0, y: 0, w: size[0], h: size[1] };
  engine.arrange(root, size[0], size[1]);
  return size;
}
