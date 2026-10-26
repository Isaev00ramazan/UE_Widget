"""
Сравнение двух деревьев IR (спецификация ↔ копия из UE) по именам виджетов.

Шум не считается отличием: bExpandedInDesigner, DisplayLabel, ключи локализации текста (сравнивается сам текст),
порядок строк свойств, разница чисел < 1e-4. Значения по умолчанию UE в копию не пишет — поэтому «свойства нет»
с одной стороны и значение с другой показывается как есть: это и есть правка, которую надо перенести.
"""
from . import t3d

NOISE = {"bExpandedInDesigner", "DisplayLabel"}


def norm(v):
	if isinstance(v, dict):
		if "$text" in v:
			return {"$text": v["$text"]}
		return {k: norm(x) for k, x in v.items()}
	if isinstance(v, list):
		return [norm(x) for x in v]
	if isinstance(v, float):
		return round(v, 4)
	return v


def index(root):
	out = {}
	for n, depth in t3d.walk(root):
		out[n["name"]] = n
	parents = {}
	for n, _ in t3d.walk(root):
		for i, c in enumerate(n["children"]):
			parents[c["name"]] = (n["name"], i)
	return out, parents


def diff_props(a, b):
	"""[(ключ, значение_в_a, значение_в_b)] — None, если ключа нет."""
	out = []
	for k in sorted(set(a) | set(b)):
		if k in NOISE or k == "cls" or k.startswith("$"):
			continue
		va, vb = norm(a.get(k)), norm(b.get(k))
		if va != vb:
			out.append((k, a.get(k), b.get(k)))
	return out


def diff(spec_root, copy_root):
	"""Отличия копии (UE — правда) от спецификации. Список словарей {kind, name, ...}."""
	sa, pa = index(spec_root)
	sb, pb = index(copy_root)
	out = []
	for name in sb:
		if name not in sa:
			out.append({"kind": "added", "name": name, "cls": sb[name]["cls"], "parent": pb.get(name, (None,))[0]})
	for name in sa:
		if name not in sb:
			out.append({"kind": "removed", "name": name, "cls": sa[name]["cls"]})
	for name in sa:
		if name not in sb:
			continue
		a, b = sa[name], sb[name]
		if a["cls"] != b["cls"] or a["path"] != b["path"]:
			out.append({"kind": "class", "name": name, "spec": a["path"] or a["cls"], "ue": b["path"] or b["cls"]})
		if pa.get(name, (None,))[0] != pb.get(name, (None,))[0]:
			out.append({"kind": "parent", "name": name, "spec": pa.get(name, (None,))[0], "ue": pb.get(name, (None,))[0]})
		elif pa.get(name) != pb.get(name):
			out.append({"kind": "order", "name": name, "spec": pa[name][1], "ue": pb[name][1]})
		for k, va, vb in diff_props(a["props"], b["props"]):
			out.append({"kind": "prop", "name": name, "key": k, "spec": a["raw"].get(k), "ue": b["raw"].get(k)})
		if pa.get(name) and pb.get(name):
			ra, rb = (a["slot"] or {}).get("$raw", {}), (b["slot"] or {}).get("$raw", {})
			for k, va, vb in diff_props(a["slot"] or {}, b["slot"] or {}):
				out.append({"kind": "slot", "name": name, "key": k, "spec": ra.get(k), "ue": rb.get(k)})
	return out
