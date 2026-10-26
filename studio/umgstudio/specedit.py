"""
Правки из панели свойств → в файл спецификации .py.

Правка элемента = {"name", "props": {свойство: строка UE | None}, "slot": {...}, "var": bool | None,
"collapsed": bool | None} (None в props/slot — убрать свойство, в var/collapsed — не трогать).

Куда пишется:
  - прямо в вызов W(...) / box(...) / user_widget(...) с этим именем, если его props/slot — словарь-литерал
	(так устроены спецификации, собранные из UE): меняется одна строка словаря, остальной код не трогается;
  - иначе (фабрики text(), image(), слоты bs()/cslot(), элементы из цикла) — строкой tweak("WBP", "Имя", …)
	в блоке правок под импортом umg. Перенести их в вызовы — просьба к ИИ («встроить правки»).
"""
import ast
import re

# фабрика → индекс аргумента «имя»
NAME_ARG = {"W": 1, "box": 1, "text": 0, "image": 0, "sizebox": 0, "spacer": 0, "border": 0, "retainer": 0,
			"user_widget": 0}
# где props/slot можно править прямо в вызове: фабрика → (индекс props, индекс slot) позиционно
LITERAL = {"W": (2, 3), "box": (6, 3), "user_widget": (2, 3)}
# индекс позиционного slot у фабрик (передан позиционно — правим через tweak, чтобы не задвоить аргумент)
SLOT_POS = {"W": 3, "box": 3, "text": 9, "image": 5, "sizebox": 6, "spacer": 3, "border": 4, "retainer": 4,
			"user_widget": 3}
# фабрики с аргументами var / collapsed
FLAGS = {"W": ("var", "collapsed"), "box": ("var", "collapsed"), "text": ("var", "collapsed"),
		 "image": ("var", "collapsed"), "sizebox": ("var", "collapsed"), "border": ("var", "collapsed"),
		 "user_widget": ("var", "collapsed"), "retainer": ("var",)}
HEADER = "# ─── правки из панели свойств UMG Studio: tweak(WBP, элемент, …) поверх вызовов ниже ───"


class _Src:
	"""Позиции ast (строка, смещение в байтах UTF-8) → индекс символа в тексте."""

	def __init__(self, text):
		self.text = text
		self.lines = text.splitlines(keepends=True)
		self.starts = [0]
		for ln in self.lines:
			self.starts.append(self.starts[-1] + len(ln))

	def pos(self, lineno, col):
		line = self.lines[lineno - 1] if lineno - 1 < len(self.lines) else ""
		return self.starts[lineno - 1] + len(line.encode("utf-8")[:col].decode("utf-8", "ignore"))

	def span(self, node):
		return self.pos(node.lineno, node.col_offset), self.pos(node.end_lineno, node.end_col_offset)

	def seg(self, node):
		a, b = self.span(node)
		return self.text[a:b]

	def indent_of(self, node):
		line = self.lines[node.lineno - 1]
		return line[:len(line) - len(line.lstrip(" \t"))]


def _fname(call):
	f = call.func
	return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _name_of(call):
	fn = _fname(call)
	if fn not in NAME_ARG:
		return None
	for kw in call.keywords:
		if kw.arg == "name":
			node = kw.value
			break
	else:
		i = NAME_ARG[fn]
		node = call.args[i] if len(call.args) > i else None
	return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _arg(call, kw_name, index):
	for kw in call.keywords:
		if kw.arg == kw_name:
			return kw.value
	return call.args[index] if index is not None and len(call.args) > index else None


def _literal_dict(node):
	return isinstance(node, ast.Dict) and all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in node.keys)


def _dict_text(entries, pad=None, close=""):
	"""pad=None — в одну строку; иначе по записи на строку с отступом pad, закрывающая скобка с отступом close."""
	if not entries:
		return "{}"
	if pad is None:
		return "{%s}" % ", ".join("%s: %s" % (k, v) for k, v in entries)
	return "{\n%s%s}" % ("".join("%s%s: %s,\n" % (pad, k, v) for k, v in entries), close)


class _Patch:
	def __init__(self, text):
		self.src = _Src(text)
		self.repl = []   # (начало, конец, текст)

	def add(self, a, b, s):
		self.repl.append((a, b, s))

	def result(self):
		out = self.src.text
		for a, b, s in sorted(self.repl, key=lambda r: r[0], reverse=True):
			out = out[:a] + s + out[b:]
		return out


def _unit(text):
	return "\t" if "\n\t" in text else "    "


def _patch_dict(p, node, edits, unit):
	"""Словарь-литерал: поменять/убрать/добавить ключи, остальные записи — как были в файле."""
	src = p.src
	entries, seen = [], set()
	for k, v in zip(node.keys, node.values):
		key = k.value
		seen.add(key)
		if key in edits:
			if edits[key] is None:
				continue
			entries.append((src.seg(k), repr(edits[key])))
		else:
			entries.append((src.seg(k), src.seg(v)))
	for key, val in edits.items():
		if key not in seen and val is not None:
			entries.append((repr(key), repr(val)))
	a, b = src.span(node)
	if "\n" not in src.text[a:b]:
		p.add(a, b, _dict_text(entries))
		return
	close_line = src.lines[node.end_lineno - 1]
	close = close_line[:len(close_line) - len(close_line.lstrip(" \t"))]
	if node.keys:
		first = src.lines[node.keys[0].lineno - 1]
		pad = first[:len(first) - len(first.lstrip(" \t"))]
	else:
		pad = close + unit
	p.add(a, b, _dict_text(entries, pad, close))


def _insert_kw(p, call, text):
	"""Добавить аргумент-ключ в вызов: перед children= (если есть), иначе в конец."""
	src = p.src
	kids = next((kw for kw in call.keywords if kw.arg == "children"), None)
	if kids is not None:
		a = src.pos(kids.lineno, kids.col_offset)
		p.add(a, a, text + ", ")
		return
	last = (call.args + [kw.value for kw in call.keywords])
	end = src.pos(call.end_lineno, call.end_col_offset) - 1   # закрывающая скобка
	if last:
		_, b = src.span(max(last, key=lambda n: (n.end_lineno, n.end_col_offset)))
		p.add(b, b, ", " + text)
	else:
		p.add(end, end, text)


def _set_flag(p, call, flag, value):
	src = p.src
	kw = next((k for k in call.keywords if k.arg == flag), None)
	if kw is not None:
		a, b = src.span(kw.value)
		p.add(a, b, "True" if value else "False")
	elif value:
		_insert_kw(p, call, "%s=True" % flag)


def calls_by_name(tree):
	found = {}
	for node in ast.walk(tree):
		if isinstance(node, ast.Call):
			n = _name_of(node)
			if n is not None:
				found.setdefault(n, []).append(node)
	return found


def apply(text, wbp, edits):
	"""Текст спецификации + правки → (новый текст, отчёт {"inplace": [имена], "tweak": [имена]})."""
	tree = ast.parse(text)
	calls = calls_by_name(tree)
	p = _Patch(text)
	unit = _unit(text)
	report = {"inplace": [], "tweak": []}
	tweaks = {}
	for e in edits:
		name = e["name"]
		props = dict(e.get("props") or {})
		slot = dict(e.get("slot") or {})
		flags = {k: e.get(k) for k in ("var", "collapsed") if e.get(k) is not None}
		cands = calls.get(name, [])
		call = cands[0] if len(cands) == 1 else None
		rest = {"props": {}, "slot": {}}
		if call is not None:
			fn = _fname(call)
			lit = LITERAL.get(fn)
			for part, edits_part in (("props", props), ("slot", slot)):
				if not edits_part:
					continue
				# props в вызове правятся только у W/box/user_widget; slot= есть у всех фабрик
				if part == "props" and not lit:
					rest[part] = edits_part
					continue
				idx = lit[0] if part == "props" else SLOT_POS[fn]
				node = _arg(call, part, idx)
				if node is not None and _literal_dict(node):
					_patch_dict(p, node, edits_part, unit)
				elif node is None:
					entries = [(repr(k), repr(v)) for k, v in edits_part.items() if v is not None]
					if entries:
						_insert_kw(p, call, "%s=%s" % (part, _dict_text(entries)))
				else:
					rest[part] = edits_part
			for flag, value in list(flags.items()):
				if flag in FLAGS.get(fn, ()):
					_set_flag(p, call, flag, value)
					flags.pop(flag)
		else:
			rest = {"props": props, "slot": slot}
		if rest["props"] or rest["slot"] or flags:
			t = tweaks.setdefault(name, {"props": {}, "slot": {}, "var": None, "collapsed": None})
			t["props"].update(rest["props"])
			t["slot"].update(rest["slot"])
			t.update(flags)
			report["tweak"].append(name)
		if call is not None and name not in report["tweak"]:
			report["inplace"].append(name)
	out = p.result()
	if tweaks:
		out = _write_tweaks(out, wbp, tweaks)
	return out, report


def _tweak_call(wbp, name, t):
	args = [repr(wbp), repr(name)]
	for part in ("props", "slot"):
		if t[part]:
			args.append("%s=%s" % (part, _dict_text([(repr(k), repr(v)) for k, v in t[part].items()])))
	for flag in ("var", "collapsed"):
		if t.get(flag) is not None:
			args.append("%s=%r" % (flag, t[flag]))
	return "tweak(%s)" % ", ".join(args)


def _const(node):
	try:
		return ast.literal_eval(node)
	except ValueError:
		return None


def _write_tweaks(text, wbp, tweaks):
	"""Слить с существующими tweak(wbp, имя, …) или добавить строки в блок правок под импортом umg."""
	tree = ast.parse(text)
	p = _Patch(text)
	src = p.src
	last_tweak = None
	for st in tree.body:
		if not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and _fname(st.value) == "tweak"):
			continue
		last_tweak = st
		c = st.value
		if len(c.args) < 2 or _const(c.args[0]) != wbp or _const(c.args[1]) not in tweaks:
			continue
		name = _const(c.args[1])
		new = tweaks.pop(name)
		old = {"props": {}, "slot": {}, "var": None, "collapsed": None}
		for kw in c.keywords:
			if kw.arg in old:
				old[kw.arg] = _const(kw.value)
		merged = {"props": dict(old["props"] or {}), "slot": dict(old["slot"] or {}),
				  "var": new["var"] if new["var"] is not None else old["var"],
				  "collapsed": new["collapsed"] if new["collapsed"] is not None else old["collapsed"]}
		merged["props"].update(new["props"])
		merged["slot"].update(new["slot"])
		a, b = src.span(st)
		p.add(a, b, _tweak_call(wbp, name, merged))
	if tweaks:
		lines = "".join(_tweak_call(wbp, n, t) + "\n" for n, t in tweaks.items())
		if last_tweak is not None:
			b = src.pos(last_tweak.end_lineno + 1, 0) if last_tweak.end_lineno < len(src.lines) else len(text)
			p.add(b, b, lines)
		else:
			anchor = None
			for st in tree.body:
				if isinstance(st, ast.ImportFrom) and st.module == "umg":
					anchor = st
			if anchor is None:
				imports = [st for st in tree.body if isinstance(st, (ast.Import, ast.ImportFrom))]
				anchor = imports[-1] if imports else None
			at = src.pos(anchor.end_lineno + 1, 0) if anchor is not None and anchor.end_lineno < len(src.lines) else \
				(len(text) if anchor is not None else 0)
			block = "\n" + HEADER + "\n" + lines
			if at == len(text) and not text.endswith("\n"):
				block = "\n" + block
			p.add(at, at, block)
	return p.result()


def edit_file(path, wbp, edits):
	"""Записать правки в файл. Возвращает (старый текст, отчёт)."""
	with open(path, encoding="utf-8") as f:
		old = f.read()
	new, report = apply(old, wbp, edits)
	compile(new, path, "exec")   # не записывать сломанный файл
	if new != old:
		with open(path, "w", encoding="utf-8", newline="") as f:
			f.write(new)
	return old, report


_TWEAK_LINE = re.compile(r"^tweak\(", re.M)


def has_tweaks(text):
	return bool(_TWEAK_LINE.search(text))
