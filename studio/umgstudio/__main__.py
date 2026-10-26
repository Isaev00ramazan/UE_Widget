"""
UMG Studio.

	py -m umgstudio                      — окно программы (pywebview; без него — откроется браузер)
	py -m umgstudio serve                — только сервер, интерфейс в браузере
	py -m umgstudio build <экран.py>     — записать *.paste.txt (как `py <экран>.py`)
	py -m umgstudio tree <файл>          — дерево спецификации / paste.txt / copy.txt в консоль
	py -m umgstudio smoke [отчёт.json]   — проверка сборки без окна (код возврата 0 — всё собирается)
	py -m umgstudio selftest-window [отчёт.json] — открыть окно, дождаться интерфейса, закрыть

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
	--project <папка>   папка проекта UE (остальные пути — от неё; всё это задаётся и в окне: «⚙ Проект»)
"""
import json
import os
import sys
import threading
import webbrowser

from . import config, server, t3d

# Корень с design/, examples/, Materials/…: папка exe в сборке, корень репозитория при запуске из исходников
REPO = config.REPO


def load_config(argv):
	"""umgstudio.json (настройки проекта, см. config.py) + ключи командной строки поверх."""
	st = config.load_settings()
	rest, it = [], iter(argv)
	for a in it:
		if a in ("--specs", "--textures"):
			st[a[2:]] = list(st.get(a[2:]) or []) + [os.path.abspath(next(it))]
		elif a == "--port":
			st["port"] = int(next(it))
		elif a in ("--ue", "--window"):
			st[a[2:]] = next(it)
		elif a in ("--project", "--setup-hud", "--assets", "--design", "--materials"):
			st[a[2:].replace("-", "_")] = os.path.abspath(next(it))
		else:
			rest.append(a)
	cfg = config.resolve(st)
	cfg["settings"] = st
	return cfg, rest


def start_server(cfg):
	studio = server.Studio.from_config(cfg)
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
	ui = {p: urllib.request.urlopen(url + p, timeout=30).status
		  for p in ("", "app.js", "slate.js", "shaders.js", "props.js", "uevalue.js", "fonts.css")}
	out["ui"] = ui
	out["edit"] = smoke_edit()
	agent = get("/api/agent/status")   # маршрут ИИ отвечает; Claude Code на CI не установлен — это не ошибка
	out["agent"] = {"found": agent["ok"], "path": agent.get("path", "")}
	base = getattr(sys, "_MEIPASS", None)
	out["agent_kit"] = not base or os.path.isfile(os.path.join(base, "umgstudio", "agent_kit", "umg-widgets", "SKILL.md"))
	ok = out["sources"] > 0 and out["specs"] and all(isinstance(v, list) for v in out["specs"].values()) \
		and out["shaders"] > 0 and out["design"] and all(v == 200 for v in ui.values()) and out["edit"] is True \
		and out["agent_kit"]
	out["ok"] = bool(ok)
	with open(report, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1)
	return 0 if ok else 1


def smoke_edit():
	"""Правка свойств в спецификации на фабриках (строка tweak) собирается в exe и попадает в текст вставки."""
	import shutil
	import tempfile
	from . import specedit
	tmp = tempfile.mkdtemp(prefix="umgstudio-smoke-")
	try:
		src = os.path.join(REPO, "examples", "UMGPaste", "pickup_banner.py")
		dst = os.path.join(tmp, "pickup_banner.py")
		shutil.copy(src, dst)
		specedit.edit_file(dst, "WBP_PickupBanner", [{"name": "Title", "props": {"RenderOpacity": "0.500000"}}])
		r = server.Studio([tmp]).run_spec(dst)
		if not r.get("ok"):
			return r.get("error", "не собралась")[-500:]
		return True if "RenderOpacity=0.500000" in r["widgets"][0]["text"] else "tweak не дошёл до текста вставки"
	except Exception as e:  # noqa: BLE001
		return repr(e)
	finally:
		shutil.rmtree(tmp, ignore_errors=True)


def version():
	p = os.path.join(REPO, "VERSION")
	if os.path.isfile(p):
		with open(p, encoding="utf-8") as f:
			return f.read().strip()
	return "dev"


def selftest_window(cfg, report):
	"""Открыть настоящее окно (как при запуске), дождаться загрузки интерфейса, закрыть. Код 0 — интерфейс загрузился."""
	import time
	from . import window
	url = start_server(cfg)
	out = {"url": url, "version": version()}

	def closer():
		out["ready"] = server.READY.wait(120)
		time.sleep(2)
		window.close_any()

	threading.Thread(target=closer, daemon=True).start()
	out["kind"] = window.open_window(url, cfg.get("window") or "auto", server.READY, timeout=45, browser_fallback=False)
	out["ready"] = server.READY.is_set()
	out["ui_errors"] = list(server.UI_LOG)
	with open(window.log_path(), encoding="utf-8") as f:
		out["log"] = f.read().splitlines()[-30:]
	with open(report, "w", encoding="utf-8") as f:
		json.dump(out, f, ensure_ascii=False, indent=1)
	return 0 if out["ready"] and not out["ui_errors"] else 1


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
	if cmd == "selftest-window":
		return selftest_window(cfg, rest[1] if len(rest) > 1 else "selftest-window.json")
	if cmd == "check-window":
		return check_window(rest[1] if len(rest) > 1 else "check-window.json")
	url = start_server(cfg)
	print("UMG Studio:", url)
	print("Спецификации:", *cfg["specs"], sep="\n  ")
	if cmd == "app":
		from . import window
		window.log("запуск %s (%s), интерфейс %s" % (version(), "exe" if getattr(sys, "frozen", False) else "исходники", url))
		try:
			window.open_window(url, cfg.get("window") or "auto", server.READY)
		except Exception:  # noqa: BLE001
			import traceback
			window.log("сбой окна:\n" + traceback.format_exc())
			raise
		return 0
	webbrowser.open(url)
	try:
		threading.Event().wait()
	except KeyboardInterrupt:
		pass
	return 0


if __name__ == "__main__":
	sys.exit(main())
