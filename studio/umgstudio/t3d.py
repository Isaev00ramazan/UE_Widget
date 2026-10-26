"""
Разбор текста буфера обмена UMG (Ctrl+C в Designer или *.paste.txt из umg.py) в дерево IR.

IR-узел (dict, готов к JSON):
	name, cls (короткое имя класса), path (полный путь класса),
	props  — {свойство: значение-структура}, raw — {свойство: строка как в тексте},
	slot   — {"cls": класс слота, свойства слота-структуры...} (у корня — из WidgetSlotPair, если есть),
	children — [IR-узлы] в порядке Slots(i).

Значения разбираются в структуры: (A=1,B=(X=2)) → {"A": 1, "B": {"X": 2}}; (1,2) → [1, 2];
NSLOCTEXT("ns","key","текст") → {"$text": "текст", "ns": "ns", "key": "key"}; True/False → bool; числа → float/int.
Отсутствующие свойства = значения по умолчанию UE (их подставляет превью).
"""
import re

OBJ = re.compile(r'^Begin Object(?: Class=(\S+))? Name="([^"]+)"')
REF = re.compile(r"'([^']+)'")
KEY = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*(?:\(\d+\))?)=")


class _Parser:
	def __init__(self, text):
		self.t = text
		self.i = 0

	def peek(self):
		self.ws()
		return self.t[self.i] if self.i < len(self.t) else ""

	def ws(self):
		while self.i < len(self.t) and self.t[self.i] in " \t":
			self.i += 1

	def string(self):
		assert self.t[self.i] == '"'
		self.i += 1
		out = []
		while self.i < len(self.t):
			ch = self.t[self.i]
			if ch == "\\" and self.i + 1 < len(self.t):
				nxt = self.t[self.i + 1]
				out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
				self.i += 2
				continue
			if ch == '"':
				self.i += 1
				return "".join(out)
			out.append(ch)
			self.i += 1
		return "".join(out)

	def value(self):
		c = self.peek()
		if c == "(":
			return self.group()
		if c == '"':
			s = self.string()
			# строка-значение может продолжаться (редко), остаток — как токен
			return s
		start, depth = self.i, 0
		while self.i < len(self.t):
			ch = self.t[self.i]
			if ch == '"':
				self.string()
				continue
			if ch == "'":
				end = self.t.find("'", self.i + 1)
				self.i = (end + 1) if end >= 0 else len(self.t)
				continue
			if ch == "(":
				depth += 1
			elif ch == ")":
				if depth == 0:
					break
				depth -= 1
			elif ch == "," and depth == 0:
				break
			self.i += 1
		return atom(self.t[start:self.i].strip())

	def group(self):
		self.i += 1
		items, keyed = [], True
		while True:
			c = self.peek()
			if c == "":
				break
			if c == ")":
				self.i += 1
				break
			m = KEY.match(self.t, self.i)
			if m:
				self.i = m.end()
				items.append((m.group(1), self.value()))
			else:
				keyed = False
				items.append((None, self.value()))
			if self.peek() == ",":
				self.i += 1
		if keyed:
			return dict(items)
		return [v for _, v in items]


_LOC = re.compile(r'^(NSLOCTEXT|LOCTEXT|INVTEXT|LOCTABLE)\((.*)\)$', re.S)


def atom(tok):
	if tok in ("True", "False"):
		return tok == "True"
	if re.fullmatch(r"-?\d+", tok):
		return int(tok)
	if re.fullmatch(r"-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?", tok):
		return float(tok)
	m = _LOC.match(tok)
	if m:
		p = _Parser("(" + m.group(2) + ")")
		args = p.value()
		args = args if isinstance(args, list) else [args]
		if m.group(1) == "NSLOCTEXT" and len(args) >= 3:
			return {"$text": args[2], "ns": args[0], "key": args[1]}
		if m.group(1) == "LOCTEXT" and len(args) >= 2:
			return {"$text": args[1], "key": args[0]}
		return {"$text": args[-1] if args else ""}
	return tok


def parse_value(s):
	s = s.strip()
	if not s:
		return ""
	p = _Parser(s)
	v = p.value()
	return v


def short_cls(c):
	return (c or "?").rsplit(".", 1)[-1]


def parse_objects(text):
	"""Плоский разбор: {имя: {cls, props[(k, raw)], slots{имя: {cls, props, content}}, order[]}}, порядок верхних объектов."""
	objs, order, stack = {}, [], []
	for raw in text.splitlines():
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
			if stack:
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
			if re.match(r"Slots\(\d+\)$", k):
				o["order"].append(REF.search(v).group(1).split(".")[-1])
			else:
				o["props"].append((k, v))
	return objs, order


def _slot_ir(cls, props):
	d = {"cls": short_cls(cls), "$raw": {k: v for k, v in props}}
	for k, v in props:
		d[k] = parse_value(v)
	return d


def parse(text):
	"""Текст буфера → список корней IR (обычно один)."""
	objs, order = parse_objects(text)
	pairs = {}
	for n in order:
		o = objs[n]
		if short_cls(o["cls"]) != "WidgetSlotPair":
			continue
		p = dict(o["props"])
		wname = parse_value(p.get("WidgetName", '""'))
		names, values = {}, {}
		for k, v in o["props"]:
			m = re.match(r"SlotProperty(Names|Values)\((\d+)\)$", k)
			if m:
				(names if m.group(1) == "Names" else values)[int(m.group(2))] = parse_value(v)
		pairs[wname] = [(names[i], values.get(i, "")) for i in sorted(names)]

	children = {s["content"] for o in objs.values() for s in o["slots"].values() if s["content"]}

	def build(name, slot, seen):
		o = objs.get(name)
		if o is None or name in seen:
			return {"name": name, "cls": "?", "path": "", "props": {}, "raw": {}, "slot": slot, "children": [], "missing": True}
		seen = seen | {name}
		node = {
			"name": name,
			"cls": short_cls(o["cls"]),
			"path": o["cls"] or "",
			"props": {k: parse_value(v) for k, v in o["props"]},
			"raw": {k: v for k, v in o["props"]},
			"slot": slot,
			"children": [],
		}
		for sn in (o["order"] or list(o["slots"])):
			s = o["slots"].get(sn)
			if s and s["content"]:
				node["children"].append(build(s["content"], _slot_ir(s["cls"], s["props"]), seen))
		return node

	roots = []
	for n in order:
		o = objs[n]
		if n in children or short_cls(o["cls"]) == "WidgetSlotPair":
			continue
		slot = None
		if n in pairs and pairs[n]:
			slot = {"cls": "CanvasPanelSlot"}
			for k, v in pairs[n]:
				slot[k] = parse_value(v) if isinstance(v, str) else v
		roots.append(build(n, slot, frozenset()))
	return roots


def walk(node, depth=0):
	yield node, depth
	for c in node["children"]:
		yield from walk(c, depth + 1)
