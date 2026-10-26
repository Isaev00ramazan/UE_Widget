// Двойники UI-мастер-материалов для превью (Canvas 2D).
// Пока это приближения по смыслу параметров из Scripts/ue_setup_hud.py (MATERIALS) — точные копии появятся,
// когда будут .hlsl. Параметры: значения по умолчанию мастера ⊕ значения MI из выгрузки ue/export_hud_assets.py.
// Рисуем в пространстве Size (как шейдер: UV × Size) и растягиваем на прямоугольник Image — поэтому несовпадение
// Size и фактического размера видно в превью так же, как в игре.

const PREFIX = [
  ["MI_Panel", "M_UI_Panel"], ["MI_SegBar", "M_UI_SegBar"], ["MI_Ring", "M_UI_Ring"], ["MI_Pips", "M_UI_Pips"],
  ["MI_Glow", "M_UI_Glow"], ["MI_Radar", "M_UI_Radar"], ["MI_Marker", "M_UI_Marker"], ["MI_RadialGlow", "M_UI_RadialGlow"],
  ["MI_Gradient", "M_UI_Gradient"], ["MI_RadialDim", "M_UI_RadialDim"], ["MI_TextGlow", "M_UI_TextGlow"],
  ["MI_Fisheye", "M_UI_FisheyePulse"], ["MI_WarnRing", "M_UI_WarnRing"], ["MI_WarnArc", "M_UI_WarnArc"],
  ["MI_Chevron", "M_UI_Chevron"],
];
const SQUARE = new Set(["M_UI_Ring", "M_UI_Radar", "M_UI_Marker", "M_UI_RadialGlow", "M_UI_WarnRing", "M_UI_WarnArc"]);

export function materialInfo(name, data) {
  const masters = (data && data.masters) || {};
  const inst = (data && data.instances && data.instances[name]) || null;
  let master = name.startsWith("M_") ? name : inst && inst.parent;
  if (!master) for (const [p, m] of PREFIX) if (name.startsWith(p)) { master = m; break; }
  const params = Object.assign({}, masters[master] || {}, inst ? inst.params : {});
  let size = null;
  if (inst && "Size" in inst.params) {
    const s = inst.params.Size;
    size = Array.isArray(s) ? [s[0], s[1]] : [s, s];
  }
  return {
    name, master, params, size, known: !!inst, exact: false,
    mismatch(r) { return !!size && (Math.abs(size[0] - r.w) > 1.5 || Math.abs(size[1] - r.h) > 1.5); },
  };
}

const n = (v, d) => (typeof v === "number" ? v : Array.isArray(v) ? v[0] : d);
const toSrgb = (x) => (x <= 0.0031308 ? x * 12.92 : 1.055 * Math.pow(x, 1 / 2.4) - 0.055);
function col(c, d = [1, 1, 1, 1]) {
  const v = Array.isArray(c) ? c : d;
  const [r, g, b] = v.slice(0, 3).map((x) => Math.round(Math.max(0, Math.min(1, toSrgb(x))) * 255));
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, v[3] ?? 1))})`;
}
const alpha = (c) => (Array.isArray(c) ? c[3] ?? 1 : 1);

function poly(ctx, pts) {
  ctx.beginPath();
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
}

const DRAW = {
  M_UI_Panel(ctx, p, W, H) {
    const cut = n(p.Cut, 12);
    const c = Array.isArray(p.Corners) ? p.Corners : [1, 0, 1, 0];
    const [tl, tr, br, bl] = c.map((v) => (v > 0 ? cut : 0));
    const pts = [[tl, 0], [W - tr, 0], [W, tr], [W, H - br], [W - br, H], [bl, H], [0, H - bl], [0, tl]];
    poly(ctx, pts);
    ctx.fillStyle = col(p.Fill, [0.0044, 0.0144, 0.0194, 0.74]);
    ctx.fill();
    ctx.save();
    poly(ctx, pts);
    ctx.clip();
    const hh = n(p.HeadH, 0);
    if (hh > 0) { ctx.fillStyle = col(p.HeadColor); ctx.fillRect(0, 0, W, hh); }
    if (alpha(p.Edge) > 0) { ctx.fillStyle = col(p.Edge); ctx.fillRect(0, 0, W, 1); }
    if (alpha(p.Zone) > 0) { ctx.fillStyle = col(p.Zone); ctx.fillRect(14, 0, 32, 3); }
    ctx.restore();
    const sw = n(p.StrokeW, 0);
    if (sw > 0 && alpha(p.StrokeColor) > 0) {
      ctx.save(); poly(ctx, pts); ctx.clip();
      ctx.lineWidth = sw * 2; ctx.strokeStyle = col(p.StrokeColor); poly(ctx, pts); ctx.stroke();
      ctx.restore();
    }
  },
  M_UI_SegBar(ctx, p, W, H) {
    const N = Math.max(1, Math.round(n(p.Segments, 22))), gap = n(p.Gap, 4), sk = n(p.SkewTan, 0.364);
    const fill = Math.max(0, Math.min(1, n(p.Fill, 0.64))), ramp = n(p.Ramp, 0);
    const on = col(p.OnColor, [0.0887, 0.7913, 0.5647, 1]), off = col(p.OffColor, [0.5776, 0.8308, 0.8308, 0.14]);
    const shape = (x0, x1, h) => poly(ctx, [[x0 + sk * h, H - h], [x1 + sk * h, H - h], [x1, H], [x0, H]]);
    if (n(p.Continuous, 0) > 0.5) {
      const w = W - sk * H;
      shape(0, w, H); ctx.fillStyle = off; ctx.fill();
      if (fill > 0) {
        if (alpha(p.OnColorEnd) > 0) {
          const g = ctx.createLinearGradient(0, 0, w, 0);
          g.addColorStop(0, on); g.addColorStop(1, col(p.OnColorEnd)); ctx.fillStyle = g;
        } else ctx.fillStyle = on;
        shape(0, w * fill, H); ctx.fill();
      }
      return;
    }
    const segW = (W - sk * H - gap * (N - 1)) / N;
    const lit = Math.round(fill * N);
    for (let i = 0; i < N; i++) {
      const h = ramp > 0 ? H * (ramp + (1 - ramp) * (N > 1 ? i / (N - 1) : 1)) : H;
      const x0 = i * (segW + gap);
      shape(x0, x0 + segW, h);
      ctx.fillStyle = i < lit ? (i === lit - 1 && alpha(p.PeakColor) > 0 && n(p.Ramp, 0) > 0 ? col(p.PeakColor) : on) : off;
      ctx.fill();
    }
  },
  M_UI_Ring(ctx, p, W, H) {
    const r = Math.min(W, H) / 2 - n(p.Pad, 7) - n(p.RingW, 4) / 2;
    ctx.lineWidth = n(p.RingW, 4);
    ctx.beginPath(); ctx.arc(W / 2, H / 2, r, 0, Math.PI * 2); ctx.strokeStyle = col(p.TrackColor); ctx.stroke();
    const pr = Math.max(0, Math.min(1, n(p.Progress, 1)));
    if (pr > 0) {
      ctx.beginPath(); ctx.arc(W / 2, H / 2, r, -Math.PI / 2, -Math.PI / 2 + pr * Math.PI * 2);
      ctx.strokeStyle = col(p.FillColor); ctx.stroke();
    }
  },
  M_UI_Glow(ctx, p, W, H) {
    const pad = n(p.Pad, 14), fill = n(p.Fill, 0.76);
    ctx.filter = `blur(${Math.max(2, pad / 2)}px)`;
    ctx.fillStyle = col(p.Color, [0.063, 0.5776, 1, 0.75]);
    ctx.fillRect(pad, pad, (W - 2 * pad) * fill, H - 2 * pad);
    ctx.filter = "none";
  },
  M_UI_Pips(ctx, p, W, H) {
    const cnt = Math.max(1, Math.round(n(p.Count, 6))), gap = n(p.Gap, 3);
    const pw = (W - gap * (cnt - 1)) / cnt, lit = Math.round(n(p.Fill, 0.75) * cnt);
    for (let i = 0; i < cnt; i++) {
      ctx.fillStyle = i < lit ? col(p.OnColor) : col(p.OffColor);
      ctx.fillRect(i * (pw + gap), 0, pw, H);
    }
  },
  M_UI_Gradient(ctx, p, W, H) {
    const g = ctx.createLinearGradient(0, 0, W, 0);
    const p1 = Math.max(0, Math.min(1, n(p.P1, 0.55))), p2 = Math.max(p1, Math.min(1, n(p.P2, 1)));
    g.addColorStop(0, col(p.C0)); g.addColorStop(p1, col(p.C1)); g.addColorStop(p2, col(p.C2)); g.addColorStop(1, col(p.C3));
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  },
  M_UI_RadialDim(ctx, p, W, H) {
    const c = Array.isArray(p.Center) ? p.Center : [0.4, 0.45], r = Array.isArray(p.Radius) ? p.Radius : [1.2, 0.9];
    ctx.save();
    ctx.translate(c[0] * W, c[1] * H);
    ctx.scale(r[0] * W, r[1] * H);
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
    g.addColorStop(0, col(p.Inner)); g.addColorStop(1, col(p.Outer));
    ctx.fillStyle = g;
    ctx.fillRect(-10, -10, 20, 20);
    ctx.restore();
  },
  M_UI_WarnRing(ctx, p, W, H) {
    const R = n(p.Radius, 264), cx = W / 2, cy = H / 2;
    ctx.lineWidth = n(p.RingW, 2); ctx.strokeStyle = col(p.TrackColor);
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
    const tc = Math.round(n(p.TickCount, 12)), tl = n(p.TickLen, 10);
    ctx.lineWidth = n(p.TickW, 2); ctx.strokeStyle = col(p.TickColor);
    for (let i = 0; i < tc; i++) {
      const a = (i / tc) * Math.PI * 2;
      ctx.beginPath(); ctx.moveTo(cx + Math.sin(a) * (R - tl / 2), cy - Math.cos(a) * (R - tl / 2));
      ctx.lineTo(cx + Math.sin(a) * (R + tl / 2), cy - Math.cos(a) * (R + tl / 2)); ctx.stroke();
    }
  },
  M_UI_WarnArc(ctx, p, W, H) {
    const R = n(p.Radius, 264), cx = W / 2, cy = H / 2, half = (n(p.ArcDeg, 18) * Math.PI) / 360;
    const c = Array.isArray(p.Color) ? p.Color.slice() : [0.9131, 0.5583, 0.147, 1];
    c[3] = (c[3] ?? 1) * n(p.Opacity, 1);
    ctx.shadowColor = col(c); ctx.shadowBlur = n(p.GlowPx, 8);
    ctx.lineWidth = n(p.Width, 6); ctx.strokeStyle = col(c);
    ctx.beginPath(); ctx.arc(cx, cy, R, -Math.PI / 2 - half, -Math.PI / 2 + half); ctx.stroke();
    const cw = n(p.ChevW, 18), ch = n(p.ChevH, 12), y0 = cy - R + n(p.Width, 6);
    ctx.fillStyle = col(c);
    poly(ctx, [[cx - cw / 2, y0], [cx + cw / 2, y0], [cx, y0 + ch]]); ctx.fill();
    ctx.shadowBlur = 0;
  },
  M_UI_Chevron(ctx, p, W, H) {
    const sk = n(p.SkewTan, 0.364) * H, c = Array.isArray(p.Color) ? p.Color : [0.624, 0.896, 1, 1];
    const pts = [[sk, 0], [W, 0], [W - sk, H], [0, H]];
    poly(ctx, pts);
    ctx.fillStyle = col([c[0], c[1], c[2], n(p.FillAlpha, 0.16)]); ctx.fill();
    ctx.save(); poly(ctx, pts); ctx.clip();
    const per = n(p.StripePeriod, 24);
    ctx.strokeStyle = col([c[0], c[1], c[2], n(p.StripeAlpha, 0.1)]); ctx.lineWidth = per / 2;
    for (let x = -H; x < W + H; x += per) { ctx.beginPath(); ctx.moveTo(x + sk, 0); ctx.lineTo(x, H); ctx.stroke(); }
    ctx.restore();
    const bw = n(p.BorderW, 4);
    ctx.fillStyle = col(c);
    poly(ctx, [[sk, 0], [sk + bw, 0], [bw, H], [0, H]]); ctx.fill();
    poly(ctx, [[W - bw, 0], [W, 0], [W - sk, H], [W - sk - bw, H]]); ctx.fill();
  },
  M_UI_Marker(ctx, p, W, H) {
    const r = n(p.Radius, 12.3);
    ctx.shadowColor = col(p.GlowColor); ctx.shadowBlur = n(p.GlowPx, 6);
    ctx.beginPath(); ctx.arc(W / 2, H / 2, r, 0, Math.PI * 2); ctx.fillStyle = col(p.FillColor); ctx.fill();
    ctx.shadowBlur = 0; ctx.lineWidth = n(p.OutlineW, 1.45); ctx.strokeStyle = col(p.OutlineColor); ctx.stroke();
  },
  M_UI_RadialGlow(ctx, p, W, H) {
    const g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, W / 2);
    g.addColorStop(0, col(p.Color)); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  },
  M_UI_Radar(ctx, p, W, H) {
    const R = n(p.RadarR, 116) * (W / n(p.Size, 250)) || W / 2;
    const g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, R);
    g.addColorStop(0, col(p.BgCenter)); g.addColorStop(1, col(p.BgEdge));
    ctx.beginPath(); ctx.arc(W / 2, H / 2, R, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
    ctx.lineWidth = n(p.LineW, 0.75); ctx.strokeStyle = col(p.LineColor); ctx.stroke();
  },
};

// true — нарисовано; false — мастер неизвестен или это эффект Retainer (рисуется заглушкой)
export function drawMaterial(ctx, info, w, h, k, tint) {
  const fn = DRAW[info.master];
  if (!fn) return false;
  const S = info.size || (SQUARE.has(info.master) ? [Math.min(w, h), Math.min(w, h)] : [w, h]);
  ctx.save();
  ctx.scale((k * w) / S[0], (k * h) / S[1]);
  fn(ctx, info.params, S[0], S[1]);
  ctx.restore();
  if (tint && (tint[0] !== 1 || tint[1] !== 1 || tint[2] !== 1)) {
    const copy = document.createElement("canvas");
    copy.width = ctx.canvas.width; copy.height = ctx.canvas.height;
    copy.getContext("2d").drawImage(ctx.canvas, 0, 0);
    ctx.globalCompositeOperation = "multiply";
    ctx.fillStyle = col([tint[0], tint[1], tint[2], 1]);
    ctx.fillRect(0, 0, copy.width, copy.height);
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(copy, 0, 0);
    ctx.globalCompositeOperation = "source-over";
  }
  if (tint && tint[3] < 1) ctx.canvas.style.opacity = tint[3];
  return true;
}
