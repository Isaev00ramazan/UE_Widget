"""
UMG Studio.

	py -m umgstudio                      — окно программы (pywebview; без него — откроется браузер)
	py -m umgstudio serve                — только сервер, интерфейс в браузере
	py -m umgstudio build <экран.py>     — записать *.paste.txt (как `py <экран>.py`)
	py -m umgstudio tree <файл>          — дерево спецификации / paste.txt / copy.txt в консоль

Папки берутся из umgstudio.json (рядом с UMGStudio.bat или в текущей папке) или из ключей:
	--specs <папка>     спецификации и тексты вставки/копии (можно несколько раз)
	--textures <папка>  PNG текстур для превью (T_Ico_*.png), можно несколько раз
	--port <N>          порт (по умолчанию 8765)
	--setup-hud <файл>  Scripts/ue_setup_hud.py — параметры мастер-материалов для превью
	--assets <файл>     hud_assets.json — выгрузка MI из UE (ue/export_hud_assets.py)
	--design <папка>    снимок дизайн-системы Claude Design (по умолчанию design/RacingHud)
	--materials <папка> .hlsl UI-мастеров (HUD_UE57_Kit/Materials; по умолчанию Materials/ в репозитории)
	--ue <url>          мост в редакторе UE (плагин ue/UMGStudio), по умолчанию http://127.0.0.1:30110
"""
import json
import os
import sys
import threading
import webbrowser

from . import server, t3d

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_config(argv):
	cfg = {"specs": [], "textures": [], "port": 8765, "setup_hud": None, "assets": None, "design": None, "materials": None, "ue": None}
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


def main(argv=None):
	sys.stdout.reconfigure(encoding="utf-8")
	cfg, rest = load_config(sys.argv[1:] if argv is None else argv)
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
	url = start_server(cfg)
	print("UMG Studio:", url)
	print("Спецификации:", *cfg["specs"], sep="\n  ")
	if cmd == "app":
		try:
			import webview  # pywebview: окно на системном WebView2 (Windows) / WebKit
		except ImportError:
			print("pywebview не установлен — открываю в браузере (pip install pywebview)")
		else:
			webview.create_window("UMG Studio", url, width=1600, height=980, min_size=(1000, 640),
								  background_color="#071114")
			webview.start()
			return 0
	webbrowser.open(url)
	try:
		threading.Event().wait()
	except KeyboardInterrupt:
		pass
	return 0


if __name__ == "__main__":
	sys.exit(main())
