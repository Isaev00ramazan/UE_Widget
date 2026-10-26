"""
Спецификация .py из дерева, которое отдал UE (copy.txt / «Забрать из UE»).

Свойства и слоты переносятся как есть (строки формата UE) через W(...): повторная генерация даёт то же дерево,
что в редакторе (проверяется тестом: дифф копия ↔ спецификация пустой). Дальше спецификацию правят руками или
агентом — например, заменяют W("TextBlock", …) на text(…) из umg.py.
"""
import re

from . import t3d

SKIP = {"bExpandedInDesigner", "DisplayLabel", "bIsVariable"}


def snake(wbp):
	"""WBP_RaceResults → race_results"""
	base = re.sub(r"^WBP_", "", wbp)
	return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", base).lower() or "widget"


def _cls(n):
	return n["cls"] if n["path"] == "/Script/UMG." + n["cls"] else n["path"]


def _dict(d, ind):
	if not d:
		return "{}"
	pad = "\t" * (ind + 1)
	body = "".join("%s%r: %r,\n" % (pad, k, v) for k, v in d.items())
	return "{\n%s%s}" % (body, "\t" * ind)


def _node(n, ind):
	props = {k: v for k, v in n["raw"].items() if k not in SKIP and not (k == "Visibility" and v == "Collapsed")}
	args = ["%r" % _cls(n), "%r" % n["name"]]
	if props:
		args.append("props=" + _dict(props, ind))
	slot = dict((n.get("slot") or {}).get("$raw", {}))
	if slot:
		args.append("slot=" + _dict(slot, ind))
	if n["props"].get("bIsVariable") is True:
		args.append("var=True")
	if n["raw"].get("Visibility") == "Collapsed":
		args.append("collapsed=True")
	label = n["props"].get("DisplayLabel")
	if isinstance(label, str) and label and label != n["name"]:
		args.append("label=%r" % label)
	kids = n["children"]
	if kids:
		slot_cls = kids[0]["slot"]["cls"] if kids[0].get("slot") else None
		from .umg import SLOT_OF
		if slot_cls and SLOT_OF.get(n["cls"]) != slot_cls:
			args.append("slot_cls=%r" % slot_cls)
		pad = "\t" * (ind + 1)
		args.append("children=[\n%s%s]" % ("".join(pad + _node(c, ind + 1) + ",\n" for c in kids), "\t" * ind))
	return "W(%s)" % ", ".join(args)


def spec_from_text(text, wbp, folder, parent=None, design=None, source=""):
	roots = t3d.parse(text)
	if not roots:
		raise ValueError("в тексте нет виджетов")
	root = roots[0]
	extra = ""
	if parent:
		extra += ", parent=%r" % parent
	if design:
		extra += ", design=%r" % (tuple(design) if isinstance(design, list) else design,)
	return '''"""
%(wbp)s — спецификация, собранная UMG Studio из дерева в UE%(source)s.
Правьте здесь и жмите «В UE ▶»: виджет в редакторе обновится по этому файлу.
Свойства пока в формате UE (W(...)); их можно постепенно заменить фабриками umg.py: text(), image(), box()…
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import umg  # noqa: E402,F401
from umg import *  # noqa: E402,F401,F403

root = %(tree)s

save(root, %(wbp)r, os.path.dirname(os.path.abspath(__file__)), folder=%(folder)r%(extra)s)
''' % {"wbp": wbp, "source": (" (" + source + ")") if source else "", "tree": _node(root, 0), "folder": folder, "extra": extra}
