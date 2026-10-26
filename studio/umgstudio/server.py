"""
Локальный сервер UMG Studio: отдаёт интерфейс (web/), выполняет спецификации, следит за файлами.

	GET  /api/sources            — экраны: спецификации *.py, копии *.copy.txt, тексты *.paste.txt
	GET  /api/render?src=ID      — IR виджетов источника (+ текст вставки, состояния, ошибка спецификации)
	GET  /api/wbp?name=WBP_X     — IR виджета по имени (для вложенных user_widget)
	GET  /api/texture?name=T_X   — PNG текстуры из папок textures (404 — превью рисует заглушку)
	GET  /api/materials          — параметры мастеров (MATERIALS из ue_setup_hud.py) и MI (выгрузка из UE)
	GET  /api/shaders            — код .hlsl мастеров и их входы (превью переводит в GLSL и считает на WebGL2)
	GET  /api/design             — снимок дизайн-системы Claude Design: компоненты, README, карточки
	GET  /design/view/<Компонент> — preview.html компонента с токенами и bundle.css (для наложения на превью)
	GET  /design/<путь>          — файлы снимка дизайна (шрифты, bundle.css, сцена)
	GET  /fonts.css              — F_HUD: шрифты из дизайна + Fira Sans Condensed для кириллицы (как в UE)
	GET  /api/events             — SSE: «файлы поменялись»
	GET  /api/ready              — интерфейс загрузился (окно программы проверяет, что оно не пустое)
	GET  /api/settings, POST /api/settings {settings} — настройки проекта (umgstudio.json)
	GET  /api/ue/list            — все Widget Blueprint открытого проекта (новый плагин)
	POST /api/ue/fetch {asset}   — забрать WBP по пути: copy.txt + спецификация .py в рабочую папку
	POST /api/spec-from-copy {src} — сделать спецификацию .py из copy.txt / paste.txt
	POST /api/log {msg}          — ошибка интерфейса → %LOCALAPPDATA%/UMGStudio/log.txt
	POST /api/build   {src}      — записать *.paste.txt спецификации (как `py <экран>.py`)
	POST /api/clipboard {text}   — положить текст в буфер обмена (запасной путь, если браузер не дал)
	GET  /api/diff?src=&wbp=     — отличия <WBP>.copy.txt (из UE) от источника
	GET  /api/ue/status          — мост в редакторе UE (плагин ue/UMGStudio) на связи?
	POST /api/ue/push {src, wbp} — «В UE»: создать/обновить WBP из текста вставки, скомпилировать, сохранить
	POST /api/ue/pull {src, wbp} — «Забрать из UE»: дерево WBP → <WBP>.copy.txt рядом со спецификацией
	POST /api/ue/open {src, wbp} — открыть WBP в редакторе
"""
import ast
import json
import re
import mimetypes
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import clipboard, codegen, config, diff, t3d, ue_bridge
from .design import Design

READY = threading.Event()   # интерфейс загрузился в окне
UI_LOG = []                 # ошибки интерфейса (для самопроверки сборки)

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
STUDIO_ROOT = os.path.dirname(HERE)
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


def wbp_of(filename):
	return filename.split(".", 1)[0]


class Studio:
	def __init__(self, spec_dirs, texture_dirs=(), setup_hud=None, assets_dump=None, design=None, materials_dir=None,
				 ue_url=ue_bridge.DEFAULT_URL, content=None, work_dir=None):
		self.design = Design(design)
		self.ue_url = ue_url
		self.materials_dir = materials_dir
		self.spec_dirs = [os.path.abspath(d) for d in spec_dirs]
		self.texture_dirs = [os.path.abspath(d) for d in texture_dirs]
		self.setup_hud = setup_hud
		self.assets_dump = assets_dump
		self.content = content
		self.work_dir = os.path.abspath(work_dir) if work_dir else (self.spec_dirs[0] if self.spec_dirs else None)
		self.settings = None
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
				if kind and not f.startswith("__") and f != "umg.py":
					item = {"id": "%d/%s" % (i, f), "kind": kind, "file": f, "dir": d,
							"wbp": None if kind == "spec" else wbp_of(f)}
					if kind == "spec":
						try:
							with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
								item["generated"] = codegen.MARK in fh.read(400)
						except OSError:
							pass
					out.append(item)
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
		"""Спецификация — в отдельном процессе (чистый umg и TEXT_NAMESPACE на каждый запуск, ошибка не роняет сервер).
		Собранный exe запускает сам себя с --run-spec; результат — через временный файл (у оконного exe нет stdout)."""
		env = dict(os.environ, PYTHONPATH=STUDIO_ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""),
				   PYTHONIOENCODING="utf-8")
		if self.content:
			env["UMGSTUDIO_CONTENT"] = config.content_env(self.content)
		fd, out = tempfile.mkstemp(prefix="umgstudio-", suffix=".json")
		os.close(fd)
		if getattr(sys, "frozen", False):
			cmd = [sys.executable, "--run-spec", path]
		else:
			cmd = [sys.executable, "-m", "umgstudio.runner", path]
		cmd += ["--out", out] + (["--write"] if write else [])
		flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
		try:
			p = subprocess.run(cmd, capture_output=True, cwd=os.path.dirname(path), env=env, timeout=60,
							   creationflags=flags)
			with open(out, encoding="utf-8") as f:
				text = f.read()
			if text:
				return json.loads(text)
			return {"ok": False, "error": (p.stderr or p.stdout or b"").decode("utf-8", "replace") or "спецификация не ответила", "log": ""}
		except (ValueError, OSError, subprocess.SubprocessError) as e:
			return {"ok": False, "error": "Не удалось выполнить спецификацию: %r" % e, "log": ""}
		finally:
			try:
				os.remove(out)
			except OSError:
				pass

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

	def find_wbp_ue(self, asset):
		"""Вложенного виджета нет на диске — взять дерево прямо из открытого редактора (файлы не пишутся)."""
		if not asset or not asset.startswith("/Game/"):
			return None
		key = ("ue", asset)
		with self.lock:
			hit = self.cache.get(key)
		if hit:
			return hit
		r = ue_bridge.call(self.ue_url, "/umgstudio/export", {"asset": asset}, timeout=5)
		if not r.get("ok"):
			return None
		out = {"src": None, "kind": "ue", "asset": asset, "roots": t3d.parse(r["text"])}
		with self.lock:
			self.cache[key] = out
		return out

	def texture(self, name):
		for d in self.texture_dirs:
			for cand in (name + ".png", name.replace("T_", "", 1) + ".png"):
				p = os.path.join(d, cand)
				if os.path.isfile(p):
					return p
		return None

	def texture_bytes(self, name, asset=None):
		"""PNG текстуры: из папок textures, иначе прямо из открытого UE (плагин /umgstudio/texture), с кэшем."""
		p = self.texture(name)
		if p:
			with open(p, "rb") as f:
				return f.read()
		if not asset or not asset.startswith("/Game/"):
			return None
		key = ("tex", asset)
		with self.lock:
			if key in self.cache:
				return self.cache[key]
		data = ue_bridge.get_bytes(self.ue_url, "/umgstudio/texture", {"asset": asset, "max": 1024})
		with self.lock:
			self.cache[key] = data
		return data

	def materials(self):
		"""{"masters": {M_UI_X: {параметр: значение}}, "instances": {MI_X: {"parent", "params"}}}"""
		out = {"masters": {}, "instances": {}}
		if self.setup_hud and os.path.isfile(self.setup_hud):
			out["masters"] = read_masters(self.setup_hud)
		if self.assets_dump and os.path.isfile(self.assets_dump):
			with open(self.assets_dump, encoding="utf-8") as f:
				out["instances"] = json.load(f).get("materials", {})
		return out

	def shaders(self):
		"""{M_UI_X: {"code": тело Custom-ноды, "inputs": [[имя, тип, по умолчанию]]}} — только мастера с .hlsl."""
		out = {}
		if not (self.setup_hud and os.path.isfile(self.setup_hud) and self.materials_dir):
			return out
		for name, inputs in read_material_table(self.setup_hud).items():
			p = os.path.join(self.materials_dir, name + ".hlsl")
			if os.path.isfile(p):
				with open(p, encoding="utf-8") as f:
					out[name] = {"code": f.read(), "inputs": [[n, k, list(v) if isinstance(v, tuple) else v] for n, k, v in inputs]}
		return out

	# ─── настройки проекта ───
	@classmethod
	def from_config(cls, cfg):
		st = cls(cfg["specs"], cfg["textures"], cfg["setup_hud"], cfg["assets"], cfg["design"], cfg["materials"],
				 cfg["ue"], cfg["content"], cfg["work_dir"])
		st.settings = cfg.get("settings")
		return st

	def apply(self, settings):
		"""Новые настройки без перезапуска: пути, папки, адрес моста; кэш превью сбрасывается."""
		cfg = config.resolve(settings)
		with self.lock:
			self.spec_dirs = [os.path.abspath(d) for d in cfg["specs"]]
			self.texture_dirs = [os.path.abspath(d) for d in cfg["textures"]]
			self.setup_hud, self.assets_dump, self.materials_dir = cfg["setup_hud"], cfg["assets"], cfg["materials"]
			self.design = Design(cfg["design"])
			self.ue_url, self.content, self.work_dir = cfg["ue"], cfg["content"], os.path.abspath(cfg["work_dir"])
			self.settings = settings
			self.cache = {}
		self.broadcast({"version": self.version, "files": [], "reload": False, "settings": True})
		return cfg

	def settings_info(self):
		s = self.settings or config.load_settings()
		cfg = config.resolve(s)
		paths = {"project": cfg["project"], "work_dir": cfg["work_dir"], "setup_hud": cfg["setup_hud"],
				 "assets": cfg["assets"], "materials": cfg["materials"], "design": cfg["design"]}
		exists = {k: bool(v and os.path.exists(v)) for k, v in paths.items()}
		return {"settings": s, "resolved": {k: v for k, v in cfg.items() if k != "content"}, "content": cfg["content"],
				"exists": exists, "file": config.settings_path(), "defaults": config.CONTENT_DEFAULTS}

	def save_settings(self, settings):
		clean = {k: settings.get(k) for k in config.KEYS}
		for k in config.LISTS:
			v = clean.get(k)
			clean[k] = [x for x in ([v] if isinstance(v, str) else (v or [])) if x]
		config.save_settings(clean)
		self.apply(clean)
		return self.settings_info()

	def adopt_project(self, project_dir):
		"""Мост сообщил папку открытого проекта: если в настройках проект не задан — взять её (файлы — в <проект>/UMGStudio)."""
		s = dict(self.settings or config.load_settings())
		if s.get("project") or not project_dir:
			return False
		s["project"] = os.path.normpath(project_dir)
		config.save_settings({k: s.get(k) for k in config.KEYS})
		self.apply(s)
		return True

	def ensure_work_dir(self):
		d = self.work_dir
		os.makedirs(d, exist_ok=True)
		if d not in self.spec_dirs:
			self.spec_dirs.insert(0, d)
		# umg.py рядом со спецификациями: их можно запускать и без программы (py экран.py)
		umg_copy = os.path.join(d, "umg.py")
		if not os.path.isfile(umg_copy):
			import shutil
			shutil.copy2(os.path.join(HERE, "umg.py"), umg_copy)
		return d

	def src_id(self, path):
		path = os.path.abspath(path)
		for i, d in enumerate(self.spec_dirs):
			if os.path.dirname(path) == d:
				return "%d/%s" % (i, os.path.basename(path))
		return None

	def spec_for(self, wbp):
		"""Спецификация, которая сохраняет этот WBP (ищем save(…, "WBP_X") в .py рабочих папок)."""
		pat = re.compile(r"""save\([^)]*['"]%s['"]""" % re.escape(wbp), re.S)
		for d in self.spec_dirs:
			if not os.path.isdir(d):
				continue
			for f in sorted(os.listdir(d)):
				if f.endswith(".py") and f != "umg.py":
					with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
						if pat.search(fh.read()):
							return os.path.join(d, f)
		return None

	def write_spec(self, text, wbp, asset, parent=None, design=None, source=""):
		d = self.ensure_work_dir()
		path = os.path.join(d, codegen.snake(wbp) + ".py")
		n = 2
		while os.path.exists(path):
			path = os.path.join(d, "%s_%d.py" % (codegen.snake(wbp), n))
			n += 1
		folder = asset.rsplit("/", 1)[0]
		code = codegen.spec_from_text(text, wbp, folder, parent=parent, design=design, source=source)
		with open(path, "w", encoding="utf-8") as f:
			f.write(code)
		return path

	def spec_from_copy(self, src):
		path = self.path_of(src)
		with open(path, encoding="utf-8-sig") as f:
			text = f.read()
		wbp = wbp_of(os.path.basename(path))
		asset = ue_bridge.asset_from_text(text) or "%s/%s" % ((self.content or config.CONTENT_DEFAULTS)["widgets"], wbp)
		spec = self.write_spec(text, wbp, asset, source=os.path.basename(path))
		return {"ok": True, "src": self.src_id(spec), "path": spec}

	def ue_list(self):
		r = ue_bridge.call(self.ue_url, "/umgstudio/list", timeout=10)
		if not r.get("ok"):
			if r.get("status") == 404:
				r["error"] = "Плагин старой версии не умеет показывать список виджетов — обнови его (ue\\install_plugin.bat) и пересобери проект. Пока можно забрать виджет по пути."
			return r
		for w in r["widgets"]:
			spec = self.spec_for(w["name"])
			w["spec"] = self.src_id(spec) if spec else None
		return r

	def ue_fetch(self, asset, regenerate=False):
		"""Забрать WBP из UE по пути: copy.txt в рабочую папку + спецификация .py, если её ещё нет.
		regenerate — пересоздать .py из дерева UE (старый файл сохраняется как .py.bak)."""
		asset = asset.strip().split(".")[0]
		if not asset.startswith("/Game/"):
			return {"ok": False, "error": "Путь ассета вида /Game/Папка/WBP_Имя (в Content Browser: ПКМ → Copy Reference)"}
		r = ue_bridge.call(self.ue_url, "/umgstudio/export", {"asset": asset})
		if not r.get("ok"):
			return r
		wbp = asset.rsplit("/", 1)[1]
		d = self.ensure_work_dir()
		copy_path = os.path.join(d, wbp + ".copy.txt")
		with open(copy_path, "w", encoding="utf-8", newline="") as f:
			f.write(r["text"])
		missing = [n["name"] for root in t3d.parse(r["text"]) for n, _ in t3d.walk(root) if n.get("missing")]
		if missing:
			return {"ok": False, "error": "UE отдал неполное дерево (нет %s) — обнови плагин: ue\\install_plugin.bat и пересборка" % ", ".join(missing[:5])}
		spec = self.spec_for(wbp)
		created, old_spec = False, None
		if spec and regenerate:
			import shutil
			shutil.copy2(spec, spec + ".bak")
			os.remove(spec)
			old_spec, spec = spec, None
		if not spec:
			design = None
			mode, size = r.get("designSizeMode") or "", r.get("designSize") or [0, 0]
			if mode in ("Custom", "CustomOnScreen") and size[0] > 0:
				design = [round(size[0], 3), round(size[1], 3)]
			elif mode in ("FillScreen",):
				design = "screen"
			elif mode in ("Desired", "DesiredOnScreen"):
				design = "desired"
			parent = r.get("parent") or None
			if parent and parent.endswith(".UserWidget"):
				parent = None
			spec = self.write_spec(r["text"], wbp, asset, parent=parent, design=design, source="забран из UE")
			if old_spec and old_spec != spec:
				os.replace(spec, old_spec)
				spec = old_spec
			created = True
		with self.lock:
			self.cache = {}
		return {"ok": True, "src": self.src_id(spec), "copy": self.src_id(copy_path), "created": created,
				"path": spec, "asset": asset}

	# ─── редактор UE ───
	def widget(self, src, wbp):
		res = self.render(src)
		if not res.get("ok"):
			raise ValueError("Источник не собрался: " + (res.get("error") or "")[-400:])
		for w in res["widgets"]:
			if w["wbp"] == wbp:
				asset = w.get("asset") or ue_bridge.asset_from_text(w["text"])
				if not asset:
					raise ValueError("Не понял путь ассета для %s" % wbp)
				return w, asset
		raise ValueError("В источнике нет %s" % wbp)

	def ue_push(self, src, wbp):
		w, asset = self.widget(src, wbp)
		if w.get("fragment"):
			return {"ok": False, "error": "%s — фрагмент (save(..., suffix=…)): его вставляют в готовый виджет руками" % wbp}
		body = {"asset": asset, "text": w["text"], "backup": True}
		if w.get("parent"):
			body["parent"] = w["parent"]
		body.update(ue_bridge.design_options(w.get("design")))
		return ue_bridge.call(self.ue_url, "/umgstudio/import", body)

	def ue_pull(self, src, wbp):
		_, asset = self.widget(src, wbp)
		r = ue_bridge.call(self.ue_url, "/umgstudio/export", {"asset": asset})
		if not r.get("ok"):
			return r
		folder = os.path.dirname(self.path_of(src))
		path = os.path.join(folder, wbp + ".copy.txt")
		with open(path, "w", encoding="utf-8", newline="") as f:
			f.write(r["text"])
		return {"ok": True, "path": path, "asset": asset}

	def diff(self, src, wbp):
		w, _ = self.widget(src, wbp)
		path = os.path.join(os.path.dirname(self.path_of(src)), wbp + ".copy.txt")
		if not os.path.isfile(path):
			return {"ok": False, "error": "Нет %s.copy.txt — нажми «Забрать из UE» (или Ctrl+C корня в Hierarchy и сохрани в файл)" % wbp}
		if os.path.abspath(path) == os.path.abspath(self.path_of(src)):
			return {"ok": False, "error": "Это и есть копия из UE — сравнивать её надо со спецификацией или paste.txt"}
		with open(path, encoding="utf-8-sig") as f:
			copy_roots = t3d.parse(f.read())
		if not copy_roots or not w["roots"]:
			return {"ok": False, "error": "Пустое дерево"}
		items = diff.diff(w["roots"][0], copy_roots[0])
		return {"ok": True, "copy": os.path.basename(path), "items": items}

	def ue_open(self, src, wbp):
		_, asset = self.widget(src, wbp)
		return ue_bridge.call(self.ue_url, "/umgstudio/open", {"asset": asset})

	# ─── слежение за файлами ───
	def watch(self, interval=0.4):
		def snapshot():
			snap = {}
			dirs = self.spec_dirs + [WEB, HERE] + ([self.materials_dir] if self.materials_dir else [])
			if self.design.ok:
				dirs += [self.design.root] + [os.path.join(self.design.root, "components", c)
											  for c in os.listdir(os.path.join(self.design.root, "components"))]
			for d in dirs:
				if not os.path.isdir(d):
					continue
				for f in os.listdir(d):
					if f.endswith((".py", ".txt", ".js", ".css", ".html", ".hlsl", ".json", ".md")):
						p = os.path.join(d, f)
						try:
							snap[p] = os.path.getmtime(p)
						except OSError:
							pass
			return snap

		def loop():
			prev, prev_dirs = snapshot(), list(self.spec_dirs)
			while True:
				time.sleep(interval)
				cur = snapshot()
				if self.spec_dirs != prev_dirs:
					# сменились папки (настройки проекта) — это не правка файлов, экран обновит событие settings
					prev, prev_dirs = cur, list(self.spec_dirs)
					continue
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


def window_log(msg):
	from . import window
	window.log(msg)


FIRA = [("500", "normal"), ("600", "normal"), ("700", "normal"), ("600", "italic"), ("700", "italic")]


def fonts_css(studio):
	"""F_HUD как Composite Font в UE: латиница — шрифты дизайна, кириллица (U+0400–04FF) — Fira Sans Condensed."""
	rules = [studio.design.fonts_css()] if studio.design.ok else []
	for w, st in FIRA:
		rules.append('@font-face { font-family: "F_HUD"; src: url("/fonts/FiraSansCondensed-%s-%s-cyrillic.woff2") '
					 'format("woff2"); font-weight: %s; font-style: %s; unicode-range: U+0400-04FF; }' % (w, st, w, st))
	return "\n".join(rules)


def read_material_table(path):
	"""Таблица MATERIALS из Scripts/ue_setup_hud.py без запуска скрипта (он импортирует unreal)."""
	with open(path, encoding="utf-8") as f:
		tree = ast.parse(f.read())
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "MATERIALS" for t in node.targets):
			return ast.literal_eval(node.value)
	return {}


def read_masters(path):
	"""{мастер: {параметр: значение по умолчанию}} — только scalar и vector."""
	return {m: {n: (list(v) if isinstance(v, tuple) else v) for n, kind, v in params if kind in ("scalar", "vector")}
			for m, params in read_material_table(path).items()}


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
				if u.path == "/api/ready":
					if not READY.is_set():
						window_log("интерфейс загрузился: %s" % q.get("info", ""))
					READY.set()
					return self.send(200, {"ok": True})
				if u.path == "/api/sources":
					return self.send(200, {"sources": studio.sources(), "dirs": studio.spec_dirs})
				if u.path == "/api/render":
					return self.send(200, studio.render(q["src"]))
				if u.path == "/api/wbp":
					r = studio.find_wbp(q["name"]) or studio.find_wbp_ue(q.get("asset", ""))
					return self.send(200 if r else 404, r or {"error": "нет такого виджета"})
				if u.path == "/api/texture":
					data = studio.texture_bytes(q["name"], q.get("asset"))
					if not data:
						return self.send(404, {"error": "нет текстуры"})
					return self.send(200, data, "image/png")
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
				if u.path == "/api/diff":
					try:
						return self.send(200, studio.diff(q["src"], q["wbp"]))
					except ValueError as e:
						return self.send(200, {"ok": False, "error": str(e)})
				if u.path == "/api/ue/status":
					r = ue_bridge.call(studio.ue_url, "/umgstudio/ping", timeout=1.5)
					if r.get("ok") and r.get("projectDir"):
						r["adopted"] = studio.adopt_project(r["projectDir"])
						proj = (studio.settings or {}).get("project")
						r["otherProject"] = bool(proj) and os.path.normcase(os.path.normpath(proj)) != \
							os.path.normcase(os.path.normpath(r["projectDir"]))
					return self.send(200, r)
				if u.path == "/api/ue/list":
					return self.send(200, studio.ue_list())
				if u.path == "/api/settings":
					return self.send(200, studio.settings_info())
				if u.path == "/api/shaders":
					return self.send(200, studio.shaders())
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
				if u.path in ("/api/ue/push", "/api/ue/pull", "/api/ue/open"):
					fn = {"push": studio.ue_push, "pull": studio.ue_pull, "open": studio.ue_open}[u.path.rsplit("/", 1)[1]]
					try:
						return self.send(200, fn(body["src"], body["wbp"]))
					except ValueError as e:
						return self.send(200, {"ok": False, "error": str(e)})
				if u.path == "/api/settings":
					return self.send(200, studio.save_settings(body.get("settings") or {}))
				if u.path == "/api/ue/fetch":
					return self.send(200, studio.ue_fetch(body.get("asset", ""), bool(body.get("regenerate"))))
				if u.path == "/api/spec-from-copy":
					return self.send(200, studio.spec_from_copy(body["src"]))
				if u.path == "/api/log":
					msg = str(body.get("msg", ""))[:4000]
					UI_LOG.append(msg)
					window_log("UI: " + msg)
					return self.send(200, {"ok": True})
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
	try:
		httpd = ThreadingHTTPServer((host, port), make_handler(studio))
	except OSError:
		# порт занят (второе окно программы) — любой свободный
		httpd = ThreadingHTTPServer((host, 0), make_handler(studio))
	httpd.daemon_threads = True
	return httpd
