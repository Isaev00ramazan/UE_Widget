"""
UMG Studio.

	py -m umgstudio                      — окно программы (pywebview; без него — откроется браузер)
	py -m umgstudio serve                — только сервер, интерфейс в браузере
	py -m umgstudio build <экран.py>     — записать *.paste.txt (как `py <экран>.py`)
	py -m umgstudio tree <файл>          — дерево спецификации / paste.txt / copy.txt в консоль
	py -m umgstudio smoke [отчёт.json]   — проверка сборки без окна (код возврата 0 — всё собирается)

Папки берутся из umgstudio.json (рядом с UMGStudio.bat или в текущей папке) или из ключей:
	--specs <папка>     спецификации и тексты вставки/копии (можно несколько раз)
	--textures <папка>  PNG текстур для превью (T_Ico_*.png), можно несколько раз
	--port <N>          порт (по умолчанию 8765)
	--setup-hud <файл>  Scripts/ue_setup_hud.py — параметры мастер-материалов для превью
	--assets <файл>     hud_assets.json — выгрузка MI из UE (ue/export_hud_assets.py)
	--design <папка>    снимок дизайн-системы Claude Design (по умолчанию design/RacingHud)
	--materials <папка> .hlsl UI-мастеров (HUD_UE57_Kit/Materials; по умолчанию Materials/ в репозитории)
	--ue <url>          мост в редакторе UE (плагин ue/UMGStudio), по умолчанию http://127.0.0.1:30110
	--window <режим>    auto | webview | edge | browser — чем открывать окно (auto: webview → Edge --app → браузер)
"""
import json
import os
import sys
import threading
import webbrowser

from . import server, t3d

# Корень с design/, examples/, Materials/…: папка exe в сборке, корень репозитория при запуске из исходников
REPO = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else \
	os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_config(argv):
	cfg = {"specs": [], "textures": [], "port": 8765, "setup_hud": None, "assets": None, "design": None, "materials": None, "ue": None, "window": None}
	for base in (os.getcwd(), REPO):
		p = os.path.join(base, "umgstudio.json")
		if os.path.isfile(p):
			with open(p, encoding="utf-8") as f:
				data = json.load(f)
			for k in ("specs", "textures"):
				cfg[k] += [os.path.join(base, d) for d in data.get(k, [])]
			cfg["port"] = data.get("port", cfg["port"])
			if data.get("ue"):
				cfg["ue"] = data["ue"]
			if data.get("window"):
				cfg["window"] = data["window"]
			for k in ("setup_hud", "assets", "design", "materials"):
				if data.get(k):
					cfg[k] = os.path.join(base, data[k])
			break
	rest, it = [], iter(argv)
	for a in it:
		if a in ("--specs", "--textures"):
			cfg[a[2:]].append(next(it))
		elif a == "--port":
			cfg["port"] = int(next(it))
		elif a == "--ue":
			cfg["ue"] = next(it)
		elif a == "--window":
			cfg["window"] = next(it)
		elif a in ("--setup-hud", "--assets", "--design", "--materials"):
			cfg[a[2:].replace("-", "_")] = next(it)
		else:
			rest.append(a)
	if not cfg["specs"]:
		cfg["specs"] = [os.path.join(REPO, "examples", "UMGPaste")]
	if not cfg["design"]:
		cfg["design"] = os.path.join(REPO, "design", "RacingHud")
	if not cfg["materials"]:
		cfg["materials"] = os.path.join(REPO, "Materials")
	if not cfg["setup_hud"]:
		cfg["setup_hud"] = os.path.join(REPO, "Skills", "ue_setup_hud.py")
	return cfg, rest


def start_server(cfg):
	studio = server.Studio(cfg["specs"], cfg["textures"], cfg["setup_hud"], cfg["assets"], cfg["design"], cfg["materials"],
						   cfg["ue"] or "http://127.0.0.1:30110")
	httpd = server.serve(studio, cfg["port"])
	threading.Thread(target=httpd.serve_forever, daemon=True).start()
	return "http://127.0.0.1:%d/" % httpd.server_address[1]


def print_tree(path):
	if path.endswith(".py"):
		studio = server.Studio([os.path.dirname(os.path.abspath(path))])
		res = studio.run_spec(os.path.abspath(path))
		if not res.get("ok"):
			print(res.get("error"))
			return 1
		widgets = res["widgets"]
	else:
		with open(path, encoding="utf-8-sig") as f:
			widgets = [{"wbp": os.path.basename(path), "roots": t3d.parse(f.read())}]
	for w in widgets:
		print("═══", w["wbp"])
		for r in w["roots"]:
			for n, depth in t3d.walk(r):
				flags = " ✎" if n["props"].get("bIsVariable") else ""
				if n["props"].get("Visibility") == "Collapsed":
					flags += " [Collapsed]"
				print("  " * depth + "%s  %s%s" % (n["cls"], n["name"], flags))
	return 0


def smoke(cfg, report):
	"""Проверка сборки без окна: сервер, список экранов, каждая спецификация собирается, шейдеры читаются."""
	import urllib.request
	url = start_server(cfg)
	get = lambda p: json.loads(urllib.request.urlopen(url + p.lstrip("/"), timeout=60).read().decode("utf-8"))
	out = {"url": url, "sources": 0, "specs": {}, "shaders": 0, "design": False}
	srcs = get("/api/sources")["sources"]
	out["sources"] = len(srcs)
	for s in srcs:
		if s["kind"] == "spec":
			r = get("/api/render?src=" + s["id"])
			out["specs"][s["file"]] = [w["wbp"] for w in r.get("widgets", [])] if r.get("ok") else r.get("error")
	out["shaders"] = len(get("/api/shaders"))
	out["design"] = get("/api/design").get("ok", False)
	ui = {p: urllib.request.urlopen(url + p, timeout=30).status for p in ("", "slate.js", "shaders.js", "fonts.css")}
	out["ui"] = ui
	ok = out["sources"] > 0 and out["specs"] and all(isinstance(v, list) for v in out["specs"].values()) \
		and out["shaders"] > 0 and out["design"] and all(v == 200 for v in ui.values())
	out["ok"] = bool(ok)
	with open(report, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1)
	return 0 if ok else 1


def check_window(report):
	"""Окно pywebview на Windows: снять пометку «из интернета» и загрузить .NET-часть (pythonnet + WinForms), без окна."""
	import traceback
	from . import window
	out = {"unblocked": window.unblock(os.path.dirname(sys.executable)) if getattr(sys, "frozen", False) else 0,
		   "stage": "до загрузки .NET"}
	with open(report, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False)
	try:
		import webview.platforms.winforms  # noqa: F401 — тянет clr (pythonnet) и сборки WebView2
		out["ok"] = True
		out["stage"] = ".NET и WinForms загружены"
	except Exception:  # noqa: BLE001
		out["ok"] = False
		out["error"] = traceback.format_exc()
	with open(report, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1)
	return 0 if out["ok"] else 1


def main(argv=None):
	argv = sys.argv[1:] if argv is None else argv
	if argv and argv[0] == "--run-spec":
		from . import runner
		runner.main(argv[1:])
		return 0
	if sys.stdout is not None:
		sys.stdout.reconfigure(encoding="utf-8")
	cfg, rest = load_config(argv)
	cmd = rest[0] if rest else "app"
	if cmd == "build":
		studio = server.Studio([os.path.dirname(os.path.abspath(rest[1]))])
		res = studio.run_spec(os.path.abspath(rest[1]), write=True)
		if not res.get("ok"):
			print(res.get("error"))
			return 1
		for w in res["widgets"]:
			print("saved", w["path"])
		return 0
	if cmd == "tree":
		return print_tree(rest[1])
	if cmd == "smoke":
		return smoke(cfg, rest[1] if len(rest) > 1 else "smoke.json")
	if cmd == "check-window":
		return check_window(rest[1] if len(rest) > 1 else "check-window.json")
	url = start_server(cfg)
	print("UMG Studio:", url)
	print("Спецификации:", *cfg["specs"], sep="\n  ")
	if cmd == "app":
		from . import window
		window.open_window(url, cfg.get("window") or "auto")
		return 0
	webbrowser.open(url)
	try:
		threading.Event().wait()
	except KeyboardInterrupt:
		pass
	return 0


if __name__ == "__main__":
	sys.exit(main())
