// Точные копии UI-материалов: код Custom-ноды (.hlsl из HUD_UE57_Kit/Materials) переводится в GLSL ES 3.0 и
// считается на WebGL2 тем же кодом, что в UE. Входы и их типы — таблица MATERIALS из ue_setup_hud.py.
// Выход как у UI-материала: RGB → Final Color (линейный, Slate переводит в sRGB), A → Opacity.
// Tint/Color and Opacity у Image на такой материал не действуют (он не читает Vertex Color) — как в UE.

const VERT = `#version 300 es
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const PRELUDE = `#version 300 es
precision highp float;
precision highp int;
uniform vec2 uRes;
out vec4 outColor;
float saturate(float x) { return clamp(x, 0.0, 1.0); }
vec2 saturate(vec2 x) { return clamp(x, 0.0, 1.0); }
vec3 saturate(vec3 x) { return clamp(x, 0.0, 1.0); }
vec4 saturate(vec4 x) { return clamp(x, 0.0, 1.0); }
vec3 toSrgb(vec3 c) {
  c = clamp(c, 0.0, 1.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}
`;

const RESERVED = new Set(["input", "output", "sample", "filter", "active", "common", "partition", "smooth", "flat",
  "half", "fixed", "inline", "noinline", "public", "static", "extern", "external", "interface", "long", "short",
  "double", "unsigned", "namespace", "using", "cast", "template", "this", "packed", "class", "union", "enum",
  "typedef", "goto", "sizeof", "precision", "superp", "resource"]);

// HLSL (тело Custom-ноды) → тело функции GLSL
export function hlslToGlsl(src) {
  let s = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  // float2 vs[4] = { a, b, c, d };  →  vec2 vs[4] = vec2[4](a, b, c, d);
  s = s.replace(/\b(float[234]?|int)\s+(\w+)\s*\[(\d+)\]\s*=\s*\{([^}]*)\}/g, "$1 $2[$3] = $1[$3]($4)");
  s = s.replace(/\bfloat([234])\b/g, "vec$1").replace(/\bhalf([234])\b/g, "vec$1").replace(/\bhalf\b/g, "float")
    .replace(/\bint([234])\b/g, "ivec$1").replace(/\bbool([234])\b/g, "bvec$1")
    .replace(/\bstatic\s+const\b/g, "const");
  s = s.replace(/\bTexture2DSample\s*\(\s*(\w+)\s*,\s*\w+\s*,/g, "texture($1,");
  const fn = { lerp: "mix", frac: "fract", atan2: "atan", fmod: "mod", rsqrt: "inversesqrt", ddx: "dFdx", ddy: "dFdy" };
  s = s.replace(/\b(lerp|frac|atan2|fmod|rsqrt|ddx|ddy)\s*\(/g, (m, f) => fn[f] + "(");
  // HLSL сам приводит int к float: k + 1.0, i * 2.4 — в GLSL нужно float(k)
  const ints = [...s.matchAll(/\bint\s+(\w+)/g)].map((m) => m[1]);
  const FL = String.raw`(\d+\.\d*|\.\d+)`;
  for (const v of new Set(ints)) {
    s = s.replace(new RegExp(String.raw`\b${v}\b(\s*[-+*/]\s*)${FL}`, "g"), `float(${v})$1$2`);
    s = s.replace(new RegExp(String.raw`${FL}(\s*[-+*/]\s*)\b${v}\b`, "g"), `$1$2float(${v})`);
  }
  s = s.replace(/\b[A-Za-z_]\w*\b/g, (w) => (RESERVED.has(w) ? w + "_" : w));
  return s;
}

const UNIFORM = { scalar: "float", time: "float", vector: "vec4", texobj: "sampler2D", texobj_retainer: "sampler2D" };

export class GLMaterials {
  constructor(shaders) {
    this.shaders = shaders || {};
    this.canvas = document.createElement("canvas");
    this.gl = this.canvas.getContext("webgl2", { premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: false });
    this.programs = {};
    this.errors = {};
    if (this.gl) {
      const gl = this.gl;
      this.white = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.white);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255, 255, 255, 255]));
    }
  }

  get ok() { return !!this.gl; }

  has(master) {
    const sh = this.shaders[master];
    return !!(this.gl && sh && !sh.inputs.some(([, kind]) => kind === "texobj_retainer"));
  }

  program(master) {
    if (master in this.programs) return this.programs[master];
    const gl = this.gl, sh = this.shaders[master];
    let prog = null;
    try {
      const uniforms = sh.inputs.filter(([n, k]) => k !== "uv" && UNIFORM[k])
        .map(([n, k]) => `uniform ${UNIFORM[k]} ${RESERVED.has(n) ? n + "_" : n};`).join("\n");
      const body = hlslToGlsl(sh.code);
      const frag = `${PRELUDE}${uniforms}\nvec4 materialMain(vec2 UV) {\n${body}\n}\n` +
        `void main() {\n  vec2 uv = vec2(gl_FragCoord.x / uRes.x, 1.0 - gl_FragCoord.y / uRes.y);\n` +
        `  vec4 c = clamp(materialMain(uv), 0.0, 1.0);\n  outColor = vec4(toSrgb(c.rgb) * c.a, c.a);\n}\n`;
      const compile = (type, text) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, text); gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) + "\n---\n" + text);
        return s;
      };
      prog = gl.createProgram();
      gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
      gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, frag));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    } catch (e) {
      this.errors[master] = String(e.message || e);
      console.warn("[UMG Studio] шейдер " + master + ":\n" + this.errors[master]);
      prog = null;
    }
    this.programs[master] = prog;
    return prog;
  }

  // Рисует материал в 2D-канвас target (размер w×h px сетки, k — сверхвыборка). false — не получилось.
  draw(target, master, params, w, h, k, textures = {}) {
    if (!this.has(master)) return false;
    const prog = this.program(master);
    if (!prog) return false;
    const gl = this.gl, sh = this.shaders[master];
    const W = Math.max(1, Math.round(w * k)), H = Math.max(1, Math.round(h * k));
    this.canvas.width = W; this.canvas.height = H;
    gl.viewport(0, 0, W, H);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(prog);
    gl.uniform2f(gl.getUniformLocation(prog, "uRes"), W, H);
    let unit = 0;
    for (const [name, kind, def] of sh.inputs) {
      const loc = gl.getUniformLocation(prog, RESERVED.has(name) ? name + "_" : name);
      if (!loc) continue;
      const v = name in params ? params[name] : def;
      if (kind === "scalar") gl.uniform1f(loc, Array.isArray(v) ? v[0] : +v || 0);
      else if (kind === "time") gl.uniform1f(loc, params.Time || 0);
      else if (kind === "vector") {
        const a = Array.isArray(v) ? v : [v || 0, 0, 0, 0];
        gl.uniform4f(loc, a[0] || 0, a[1] || 0, a[2] || 0, a[3] ?? 0);
      } else if (kind === "texobj") {
        gl.activeTexture(gl.TEXTURE0 + unit);
        gl.bindTexture(gl.TEXTURE_2D, textures[name] || this.white);
        gl.uniform1i(loc, unit++);
      }
    }
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    target.width = W; target.height = H;
    target.getContext("2d").drawImage(this.canvas, 0, 0);
    return true;
  }
}
