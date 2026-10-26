"""
Разбор текста, скопированного из UMG Designer (Ctrl+C), в читаемое дерево: класс, имя, свойства, свойства слота.
Нужен, чтобы видеть реальное состояние виджета пользователя, а не гадать по скриншоту.

	py umg_dump.py <файл.txt>          — дерево
	py umg_dump.py <файл.txt> --raw    — дерево + все свойства как есть
	(без файла — читает stdin)

Размер шрифта показывается и в UE (Size), и в px дизайна (÷0.75); цвета — линейные + sRGB HEX.
"""
import re
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
from umg import lin_hex, PT  # noqa: E402

OBJ = re.compile(r'^Begin Object(?: Class=(\S+))? Name="([^"]+)"')
REF = re.compile(r"'([^']+)'")


def parse(lines):
	objs, order = {}, []
	stack = []
	for raw in lines:
		s = raw.strip()
		if not s:
			continue
		m = OBJ.match(s)
		if m:
			cls, name = m.groups()
			if not stack:
				o = objs.setdefault(name, {"cls": cls, "name": name, "props": [], "slots": {}, "order": []})
				if cls:
					o["cls"] = cls
				order.append(name)
				stack.append(("obj", o))
			else:
				parent = stack[0][1]
				sl = parent["slots"].setdefault(name, {"cls": cls, "props": [], "content": None})
				if cls:
					sl["cls"] = cls
				stack.append(("slot", sl))
			continue
		if s == "End Object":
			stack.pop()
			continue
		if not stack:
			continue
		kind, o = stack[-1]
		k, _, v = s.partition("=")
		if kind == "slot":
			if k == "Content":
				o["content"] = REF.search(v).group(1).split(".")[-1]
			elif k != "Parent":
				o["props"].append((k, v))
		else:
			if re.match(r"Slots\(\d+\)", k):
				o["order"].append(REF.search(v).group(1).split(".")[-1])
			else:
				o["props"].append((k, v))
	return objs, order


def short_cls(c):
	return (c or "?").rsplit(".", 1)[-1]


def pretty(k, v):
	if k == "Font":
		face = re.search(r'TypefaceFontName="([^"]*)"', v)
		size = re.search(r"Size=([\d.]+)", v)
		ls = re.search(r"LetterSpacing=(-?\d+)", v)
		sz = float(size.group(1)) if size else 0
		return "Font %s %g (=%gpx)%s" % (face.group(1) if face else "?", sz, round(sz / PT, 2),
										 (" LS %s" % ls.group(1)) if ls else "")
	m = re.search(r"R=([\d.]+),G=([\d.]+),B=([\d.]+),A=([\d.]+)", v)
	if m and k in ("ColorAndOpacity", "BrushColor", "ShadowColorAndOpacity", "Brush", "ContentColorAndOpacity"):
		r, g, b, a = map(float, m.groups())
		res = re.search(r"ResourceObject=\"[^']*'([^']+)'", v)
		size = re.search(r"ImageSize=\(X=([\d.]+),Y=([\d.]+)\)", v)
		extra = ""
		if k == "Brush":
			extra = " %sx%s %s" % (size.group(1), size.group(2), res.group(1).split(".")[-1] if res else "") if size else ""
			return "Brush tint #%s a%.2f%s" % (lin_hex(r, g, b), a, extra)
		return "%s #%s a%.2f" % (k, lin_hex(r, g, b), a)
	if k == "Brush":
		res = re.search(r"ResourceObject=\"[^']*'([^']+)'", v)
		size = re.search(r"ImageSize=\(X=([\d.]+),Y=([\d.]+)\)", v)
		return "Brush %s %s" % ("%sx%s" % size.groups() if size else "", res.group(1).split(".")[-1] if res else "")
	if k == "Text":
		t = re.findall(r'"((?:[^"\\]|\\.)*)"', v)
		return "Text %r" % (t[-1] if t else v)
	return "%s=%s" % (k, v)


SKIP = {"bExpandedInDesigner", "DisplayLabel", "ShadowOffset", "StrikeBrush"}


def dump(objs, order, raw=False):
	children = {c for o in objs.values() for c in (s["content"] for s in o["slots"].values())}
	roots = [n for n in order if n in objs and n not in children and short_cls(objs[n]["cls"]) != "WidgetSlotPair"]

	def walk(name, depth, slot_props):
		o = objs.get(name)
		if not o:
			print("  " * depth + "? " + name)
			return
		props = dict(o["props"])
		label = props.get("DisplayLabel", "").strip('"')
		head = "%s%s  %s%s" % ("  " * depth, short_cls(o["cls"]), name, (' "%s"' % label) if label and label != name else "")
		flags = [f for f, k in (("✎", "bIsVariable"), ("Collapsed", "Visibility")) if k in props]
		print(head + ("  [" + ", ".join(flags) + "]" if flags else ""))
		pad = "  " * depth + "    "
		if slot_props:
			print(pad + "slot: " + ", ".join("%s=%s" % kv for kv in slot_props))
		for k, v in o["props"]:
			if raw:
				print(pad + "%s=%s" % (k, v))
			elif k not in SKIP and k not in ("bIsVariable", "Visibility"):
				print(pad + pretty(k, v))
		by_name = {s: o["slots"][s] for s in o["slots"]}
		for sn in o["order"] or list(by_name):
			s = by_name.get(sn)
			if s and s["content"]:
				walk(s["content"], depth + 1, s["props"])

	for r in roots:
		walk(r, 0, [])


if __name__ == "__main__":
	sys.stdout.reconfigure(encoding="utf-8")
	args = [a for a in sys.argv[1:] if not a.startswith("--")]
	text = open(args[0], encoding="utf-8-sig").read() if args else sys.stdin.read()
	dump(*parse(text.splitlines()), raw="--raw" in sys.argv)
