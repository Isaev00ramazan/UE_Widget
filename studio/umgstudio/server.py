"""
Локальный сервер UMG Studio: отдаёт интерфейс (web/), выполняет спецификации, следит за файлами.

	GET  /api/sources            — экраны: спецификации *.py, копии *.copy.txt, тексты *.paste.txt
	GET  /api/render?src=ID      — IR виджетов источника (+ текст вставки, состояния, ошибка спецификации)
	GET  /api/wbp?name=WBP_X     — IR виджета по имени (для вложенных user_widget)
	GET  /api/texture?name=T_X   — PNG текстуры из папок textures (404 — превью рисует заглушку)
	GET  /api/materials          — параметры мастеров (MATERIALS из ue_setup_hud.py) и MI (выгрузка из UE)
	GET  /api/design             — снимок дизайн-системы Claude Design: компоненты, README, карточки
	GET  /design/view/<Компонент> — preview.html компонента с токенами и bundle.css (для наложения на превью)
	GET  /design/<путь>          — файлы снимка дизайна (шрифты, bundle.css, сцена)
	GET  /fonts.css              — F_HUD: шрифты из дизайна + Fira Sans Condensed для кириллицы (как в UE)
	GET  /api/events             — SSE: «файлы поменялись»
	POST /api/build   {src}      — записать *.paste.txt спецификации (как `py <экран>.py`)
	POST /api/clipboard {text}   — положить текст в буфер обмена (запасной путь, если браузер не дал)
"""
import ast
import json
import mimetypes
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import clipboard, t3d
from .design import Design

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
STUDIO_ROOT = os.path.dirname(HERE)
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


def wbp_of(filename):
	return filename.split(".", 1)[0]


class Studio:
	def __init__(self, spec_dirs, texture_dirs=(), setup_hud=None, assets_dump=None, design=None):
		self.design = Design(design)
		self.spec_dirs = [os.path.abspath(d) for d in spec_dirs]
		self.texture_dirs = [os.path.abspath(d) for d in texture_dirs]
		self.setup_hud = setup_hud
		self.assets_dump = assets_dump
		self.cache = {}
		self.lock = threading.Lock()
		self.clients = []
		self.version = 0

	# ─── источники ───
	def sources(self):
		out = []
		for i, d in enumerate(self.spec_dirs):
			if not os.path.isdir(d):
				continue
			for f in sorted(os.listdir(d)):
				kind = "spec" if f.endswith(".py") else "copy" if f.endswith(".copy.txt") else \
					"paste" if f.endswith(".paste.txt") else None
				if kind and not f.startswith("__"):
					out.append({"id": "%d/%s" % (i, f), "kind": kind, "file": f, "dir": d,
								"wbp": None if kind == "spec" else wbp_of(f)})
		return out

	def path_of(self, src):
		i, _, f = src.partition("/")
		d = self.spec_dirs[int(i)]
		p = os.path.normpath(os.path.join(d, f))
		if os.path.dirname(p) != d:
			raise ValueError("bad source")
		return p

	def _umg_mtime(self):
		return os.path.getmtime(os.path.join(HERE, "umg.py"))

	def run_spec(self, path, write=False):
		env = dict(os.environ, PYTHONPATH=STUDIO_ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""),
				   PYTHONIOENCODING="utf-8")
		cmd = [sys.executable, "-m", "umgstudio.runner", path] + (["--write"] if write else [])
		p = subprocess.run(cmd, capture_output=True, cwd=os.path.dirname(path), env=env, timeout=60)
		try:
			return json.loads(p.stdout.decode("utf-8"))
		except ValueError:
			return {"ok": False, "error": (p.stderr or p.stdout).decode("utf-8", "replace"), "log": ""}

	def render(self, src):
		path = self.path_of(src)
		kind = "spec" if path.endswith(".py") else "text"
		key = (path, os.path.getmtime(path), self._umg_mtime() if kind == "spec" else 0)
		with self.lock:
			hit = self.cache.get(path)
			if hit and hit[0] == key:
				return hit[1]
		if kind == "spec":
			res = self.run_spec(path)
		else:
			with open(path, encoding="utf-8-sig") as f:
				text = f.read()
			try:
				roots = t3d.parse(text)
				res = {"ok": True, "widgets": [{"wbp": wbp_of(os.path.basename(path)), "path": path,
											   "text": text, "roots": roots}], "states": [], "log": ""}
			except Exception as e:  # noqa: BLE001
				res = {"ok": False, "error": "Не разобрал текст: %r" % e, "log": ""}
		res["src"] = src
		with self.lock:
			self.cache[path] = (key, res)
		return res

	def find_wbp(self, name):
		"""Вложенный виджет: спецификация > копия из UE > текст вставки."""
		srcs = self.sources()
		for s in srcs:
			if s["kind"] == "spec":
				r = self.render(s["id"])
				for w in r.get("widgets", []):
					if w["wbp"] == name:
						return {"src": s["id"], "kind": "spec", "roots": w["roots"]}
		for kind in ("copy", "paste"):
			for s in srcs:
				if s["kind"] == kind and s["wbp"] == name:
					r = self.render(s["id"])
					if r.get("ok"):
						return {"src": s["id"], "kind": kind, "roots": r["widgets"][0]["roots"]}
		return None

	def texture(self, name):
		for d in self.texture_dirs:
			for cand in (name + ".png", name.replace("T_", "", 1) + ".png"):
				p = os.path.join(d, cand)
				if os.path.isfile(p):
					return p
		return None

	def materials(self):
		"""{"masters": {M_UI_X: {параметр: значение}}, "instances": {MI_X: {"parent", "params"}}}"""
		out = {"masters": {}, "instances": {}}
		if self.setup_hud and os.path.isfile(self.setup_hud):
			out["masters"] = read_masters(self.setup_hud)
		if self.assets_dump and os.path.isfile(self.assets_dump):
			with open(self.assets_dump, encoding="utf-8") as f:
				out["instances"] = json.load(f).get("materials", {})
		return out

	# ─── слежение за файлами ───
	def watch(self, interval=0.4):
		def snapshot():
			snap = {}
			dirs = self.spec_dirs + [WEB, HERE]
			if self.design.ok:
				dirs += [self.design.root] + [os.path.join(self.design.root, "components", c)
											  for c in os.listdir(os.path.join(self.design.root, "components"))]
			for d in dirs:
				if not os.path.isdir(d):
					continue
				for f in os.listdir(d):
					if f.endswith((".py", ".txt", ".js", ".css", ".html")):
						p = os.path.join(d, f)
						try:
							snap[p] = os.path.getmtime(p)
						except OSError:
							pass
			return snap

		def loop():
			prev = snapshot()
			while True:
				time.sleep(interval)
				cur = snapshot()
				if cur != prev:
					changed = sorted(p for p in set(cur) | set(prev) if cur.get(p) != prev.get(p))
					prev = cur
					self.version += 1
					ui = any(p.startswith(WEB) for p in changed)
					self.broadcast({"version": self.version, "files": [os.path.basename(p) for p in changed],
									"reload": ui})

		threading.Thread(target=loop, daemon=True).start()

	def broadcast(self, msg):
		for q in list(self.clients):
			q.put(msg)


FIRA = [("500", "normal"), ("600", "normal"), ("700", "normal"), ("600", "italic"), ("700", "italic")]


def fonts_css(studio):
	"""F_HUD как Composite Font в UE: латиница — шрифты дизайна, кириллица (U+0400–04FF) — Fira Sans Condensed."""
	rules = [studio.design.fonts_css()] if studio.design.ok else []
	for w, st in FIRA:
		rules.append('@font-face { font-family: "F_HUD"; src: url("/fonts/FiraSansCondensed-%s-%s-cyrillic.woff2") '
					 'format("woff2"); font-weight: %s; font-style: %s; unicode-range: U+0400-04FF; }' % (w, st, w, st))
	return "\n".join(rules)


def read_masters(path):
	"""Таблица MATERIALS из Scripts/ue_setup_hud.py без запуска скрипта (он импортирует unreal)."""
	with open(path, encoding="utf-8") as f:
		tree = ast.parse(f.read())
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "MATERIALS" for t in node.targets):
			table = ast.literal_eval(node.value)
			return {m: {n: (list(v) if isinstance(v, tuple) else v) for n, kind, v in params
						if kind in ("scalar", "vector")} for m, params in table.items()}
	return {}


def make_handler(studio):
	class H(BaseHTTPRequestHandler):
		def log_message(self, *a):
			pass

		def send(self, code, body, ctype="application/json; charset=utf-8"):
			if isinstance(body, (dict, list)):
				body = json.dumps(body, ensure_ascii=False).encode("utf-8")
			elif isinstance(body, str):
				body = body.encode("utf-8")
			self.send_response(code)
			self.send_header("Content-Type", ctype)
			self.send_header("Content-Length", str(len(body)))
			self.send_header("Cache-Control", "no-store")
			self.end_headers()
			self.wfile.write(body)

		def do_GET(self):
			u = urlparse(self.path)
			q = {k: v[0] for k, v in parse_qs(u.query).items()}
			try:
				if u.path == "/api/sources":
					return self.send(200, {"sources": studio.sources(), "dirs": studio.spec_dirs})
				if u.path == "/api/render":
					return self.send(200, studio.render(q["src"]))
				if u.path == "/api/wbp":
					r = studio.find_wbp(q["name"])
					return self.send(200 if r else 404, r or {"error": "нет такого виджета"})
				if u.path == "/api/texture":
					p = studio.texture(q["name"])
					if not p:
						return self.send(404, {"error": "нет текстуры"})
					with open(p, "rb") as f:
						return self.send(200, f.read(), "image/png")
				if u.path == "/api/materials":
					return self.send(200, studio.materials())
				if u.path == "/api/design":
					d = studio.design
					return self.send(200, {"ok": d.ok, "meta": d.meta(), "components": d.components()} if d.ok else {"ok": False})
				if u.path.startswith("/design/view/"):
					return self.send(200, studio.design.page(u.path.rsplit("/", 1)[1]), "text/html; charset=utf-8")
				if u.path.startswith("/design/") and studio.design.ok:
					return self.static(u.path[len("/design"):], studio.design.root)
				if u.path == "/fonts.css":
					return self.send(200, fonts_css(studio), "text/css; charset=utf-8")
				if u.path == "/api/events":
					return self.events()
				return self.static(u.path)
			except Exception as e:  # noqa: BLE001
				return self.send(500, {"error": repr(e)})

		def do_POST(self):
			u = urlparse(self.path)
			n = int(self.headers.get("Content-Length") or 0)
			body = json.loads(self.rfile.read(n) or b"{}")
			try:
				if u.path == "/api/build":
					path = studio.path_of(body["src"])
					r = studio.run_spec(path, write=True)
					return self.send(200, {"ok": r.get("ok"), "error": r.get("error"),
										   "written": [w["path"] for w in r.get("widgets", [])]})
				if u.path == "/api/clipboard":
					return self.send(200, {"ok": clipboard.copy(body["text"])})
				return self.send(404, {"error": "нет такого метода"})
			except Exception as e:  # noqa: BLE001
				return self.send(500, {"error": repr(e)})

		def static(self, path, base=WEB):
			rel = "index.html" if path in ("", "/") else path.lstrip("/")
			p = os.path.normpath(os.path.join(base, rel))
			if not p.startswith(base + os.sep) or not os.path.isfile(p):
				return self.send(404, "not found", "text/plain")
			ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
			if ctype.startswith("text/"):
				ctype += "; charset=utf-8"
			with open(p, "rb") as f:
				return self.send(200, f.read(), ctype)

		def events(self):
			self.send_response(200)
			self.send_header("Content-Type", "text/event-stream")
			self.send_header("Cache-Control", "no-store")
			self.end_headers()
			qq = queue.Queue()
			studio.clients.append(qq)
			try:
				self.wfile.write(b": hi\n\n")
				self.wfile.flush()
				while True:
					try:
						msg = qq.get(timeout=15)
						self.wfile.write(("data: %s\n\n" % json.dumps(msg, ensure_ascii=False)).encode("utf-8"))
					except queue.Empty:
						self.wfile.write(b": ping\n\n")
					self.wfile.flush()
			except (BrokenPipeError, ConnectionResetError, OSError):
				pass
			finally:
				studio.clients.remove(qq)

	return H


def serve(studio, port=8765, host="127.0.0.1"):
	studio.watch()
	httpd = ThreadingHTTPServer((host, port), make_handler(studio))
	httpd.daemon_threads = True
	return httpd
