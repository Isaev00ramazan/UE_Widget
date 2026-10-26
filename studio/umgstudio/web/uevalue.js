// Значения свойств в формате UE ((A=1,B=(X=2)), "строка", NSLOCTEXT(...), 1.000000) — разбор с сохранением
// записи (чтобы поменять одно число и записать остальное как было) и перевод в структуру, как t3d.parse_value.

const KEY = /\s*([A-Za-z_][A-Za-z0-9_]*(?:\(\d+\))?)=/y;
const LOC = /^(NSLOCTEXT|LOCTEXT|INVTEXT|LOCTABLE)\(([\s\S]*)\)$/;

// узлы: {t:"g", items:[{k, v}]} — группа (k=null у безымянных), {t:"s", v} — строка в кавычках, {t:"a", v} — как есть
export function parse(text) {
  const s = String(text ?? "");
  let i = 0;
  const ws = () => { while (i < s.length && (s[i] === " " || s[i] === "\t")) i++; };
  const str = () => {
    i++;
    let out = "";
    while (i < s.length) {
      const ch = s[i];
      if (ch === "\\" && i + 1 < s.length) { const n = s[i + 1]; out += { n: "\n", t: "\t", r: "\r" }[n] ?? n; i += 2; continue; }
      if (ch === '"') { i++; break; }
      out += ch; i++;
    }
    return out;
  };
  const value = () => {
    ws();
    if (s[i] === "(") return group();
    if (s[i] === '"') return { t: "s", v: str() };
    const start = i; let depth = 0;
    while (i < s.length) {
      const ch = s[i];
      if (ch === '"') { str(); continue; }
      if (ch === "'") { const e = s.indexOf("'", i + 1); i = e >= 0 ? e + 1 : s.length; continue; }
      if (ch === "(") depth++;
      else if (ch === ")") { if (depth === 0) break; depth--; }
      else if (ch === "," && depth === 0) break;
      i++;
    }
    return { t: "a", v: s.slice(start, i).trim() };
  };
  const group = () => {
    i++;
    const items = [];
    for (;;) {
      ws();
      if (i >= s.length) break;
      if (s[i] === ")") { i++; break; }
      KEY.lastIndex = i;
      const m = KEY.exec(s);
      if (m) { i = KEY.lastIndex; items.push({ k: m[1], v: value() }); }
      else items.push({ k: null, v: value() });
      ws();
      if (s[i] === ",") i++;
    }
    return { t: "g", items };
  };
  if (!s.trim()) return { t: "a", v: "" };
  return value();
}

export function quote(v) {
  return '"' + String(v).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n") + '"';
}

export function stringify(n) {
  if (n.t === "g") return "(" + n.items.map((it) => (it.k ? it.k + "=" : "") + stringify(it.v)).join(",") + ")";
  if (n.t === "s") return quote(n.v);
  return n.v;
}

// атом как в t3d.atom: True/False, числа, NSLOCTEXT → {$text, ns, key}
export function atom(tok) {
  if (tok === "True" || tok === "False") return tok === "True";
  if (/^-?\d+$/.test(tok)) return parseInt(tok, 10);
  if (/^-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$/.test(tok)) return parseFloat(tok);
  const m = LOC.exec(tok);
  if (m) {
    const args = locArgs(tok);
    if (m[1] === "NSLOCTEXT" && args.length >= 3) return { $text: args[2], ns: args[0], key: args[1] };
    if (m[1] === "LOCTEXT" && args.length >= 2) return { $text: args[1], key: args[0] };
    return { $text: args.length ? args[args.length - 1] : "" };
  }
  return tok;
}

export function locArgs(tok) {
  const m = LOC.exec(tok);
  if (!m) return null;
  const g = parse("(" + m[2] + ")");
  return g.t === "g" ? g.items.map((it) => (it.v.t === "s" ? it.v.v : it.v.v)) : [];
}

// NSLOCTEXT("ns", "key", "текст") с новым текстом
export function withLocText(tok, text) {
  const m = LOC.exec(tok);
  const args = locArgs(tok) || [];
  if (!m) return tok;
  args[args.length ? args.length - 1 : 0] = text;
  return `${m[1]}(${args.map(quote).join(", ")})`;
}

export function isLoc(tok) { return LOC.test(tok); }

export function toValue(n) {
  if (n.t === "g") {
    if (n.items.length && n.items.some((it) => it.k === null)) return n.items.map((it) => toValue(it.v));
    const o = {};
    for (const it of n.items) o[it.k] = toValue(it.v);
    return o;
  }
  if (n.t === "s") return n.v;
  return atom(n.v);
}

export function valueOf(text) { return toValue(parse(text)); }

// число в записи UE: дробное — 6 знаков, как пишет редактор; целое — без точки
export function num(x, likeTok) {
  if (likeTok !== undefined && !String(likeTok).includes(".") && Number.isInteger(x)) return String(x);
  return (Math.round(x * 1e6) / 1e6).toFixed(6);
}
