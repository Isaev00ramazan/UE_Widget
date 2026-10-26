"""
Снимок дизайн-системы из Claude Design (папка design/<Имя>/): токены, шрифты, компоненты с preview.html.

Claude Design сам подставляет в превью компонентов CSS-переменные токенов (--ink, --glass…) и классы
типографики (.t-speed, .t-label…). Здесь они собираются из tokens.json, поэтому preview.html открывается
вне Claude Design так же, как там, — и его можно наложить на превью UMG.
"""
import json
import os
import re

CARD = re.compile(r"<!--\s*@dsCard(.*?)-->", re.S)


class Design:
	def __init__(self, root):
		self.root = os.path.abspath(root) if root else None

	@property
	def ok(self):
		return bool(self.root) and os.path.isfile(os.path.join(self.root, "tokens.json"))

	def tokens(self):
		with open(os.path.join(self.root, "tokens.json"), encoding="utf-8") as f:
			return json.load(f)

	def meta(self):
		p = os.path.join(self.root, "design.json")
		if os.path.isfile(p):
			with open(p, encoding="utf-8") as f:
				return json.load(f)
		return {"name": os.path.basename(self.root)}

	def components(self):
		out = []
		cdir = os.path.join(self.root, "components")
		for name in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
			prev = os.path.join(cdir, name, "preview.html")
			if not os.path.isfile(prev):
				continue
			with open(prev, encoding="utf-8") as f:
				m = CARD.search(f.read(4000))
			card = parse_card(m.group(1)) if m else {}
			readme = os.path.join(cdir, name, "README.md")
			text = ""
			if os.path.isfile(readme):
				with open(readme, encoding="utf-8") as f:
					text = f.read()
			out.append({"name": name, "card": card, "readme": text})
		return out

	def fonts_css(self, family="F_HUD", exclude_range="U+0000-03FF, U+0500-10FFFF"):
		"""@font-face шрифтов дизайна под именем F_HUD (кириллицу в UE даёт Fira Sans Condensed — её не трогаем)."""
		rules = []
		for f in self.tokens().get("type", {}).get("fonts", []):
			rules.append('@font-face { font-family: "%s"; src: url("/design/%s") format("woff2"); font-weight: %s; '
						 'font-style: %s; unicode-range: %s; }' % (family, f["file"], f.get("weight", 400),
																 f.get("style", "normal"), exclude_range))
			rules.append('@font-face { font-family: "%s"; src: url("/design/%s") format("woff2"); font-weight: %s; '
						 'font-style: %s; }' % (f["family"], f["file"], f.get("weight", 400), f.get("style", "normal")))
		return "\n".join(rules)

	def tokens_css(self, theme="default"):
		t = self.tokens()
		lines = [":root {"]
		for tok in t.get("color", {}).get("tokens", []):
			v = tok["value"]
			lines.append("  --%s: %s;" % (tok["name"], v.get(theme, next(iter(v.values()))) if isinstance(v, dict) else v))
		typ = t.get("type", {})
		for k, v in typ.get("families", {}).items():
			lines.append("  --font-%s: %s;" % (k, v))
		for group in ("spacing", "radius", "size", "shadow"):
			for tok in t.get(group, {}).get("tokens", []):
				lines.append("  --%s: %s;" % (tok["name"], tok["value"]))
		lines.append("}")
		for g in typ.get("groups", []):
			fam = "var(--font-%s)" % g.get("family", "hud")
			for s in g.get("styles", []):
				decl = ["font-family: %s" % fam]
				for key, css in (("fontSize", "font-size"), ("lineHeight", "line-height"), ("fontWeight", "font-weight"),
								 ("fontStyle", "font-style"), ("letterSpacing", "letter-spacing")):
					if key in s:
						decl.append("%s: %s" % (css, s[key]))
				lines.append(".%s { %s; }" % (s["name"], "; ".join(decl)))
		return "\n".join(lines)

	def page(self, component):
		"""preview.html компонента с подключёнными токенами, шрифтами и bundle.css."""
		if not re.fullmatch(r"[\w-]+", component):
			raise ValueError("bad component")
		with open(os.path.join(self.root, "components", component, "preview.html"), encoding="utf-8") as f:
			html = f.read()
		inject = ('<base href="/design/components/%s/">\n<style>\n%s\n%s\n</style>\n'
				  '<link rel="stylesheet" href="/design/components/bundle.css">\n') % (
			component, self.fonts_css(), self.tokens_css())
		if "<head>" in html:
			return html.replace("<head>", "<head>\n" + inject, 1)
		return inject + html


def parse_card(s):
	"""group="Screen" width=1280 height=720 page subtitle="…" → dict."""
	out = {}
	for m in re.finditer(r'(\w+)(?:=("([^"]*)"|\S+))?', s):
		key, raw, quoted = m.group(1), m.group(2), m.group(3)
		if raw is None:
			out[key] = True
		elif quoted is not None:
			out[key] = quoted
		else:
			out[key] = int(raw) if raw.isdigit() else raw
	return out
