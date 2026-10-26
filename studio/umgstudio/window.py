"""
Окно программы. По порядку, пока что-то не откроется:
	1. pywebview (WebView2) — родное окно;
	2. Edge / Chrome в режиме приложения (--app): отдельное окно без адресной строки;
	3. браузер по умолчанию.

Скачанный из интернета ZIP Windows помечает (Zone.Identifier), и .NET Framework не грузит такие DLL —
pywebview падает на Python.Runtime.dll. Поэтому перед стартом снимаем пометку со своих файлов.
"""
import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

MODES = ("auto", "webview", "edge", "browser")


def log_path():
	base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
	d = os.path.join(base, "UMGStudio")
	os.makedirs(d, exist_ok=True)
	return os.path.join(d, "log.txt")


def log(msg):
	try:
		with open(log_path(), "a", encoding="utf-8") as f:
			f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
	except OSError:
		pass


def unblock(root, exts=(".dll", ".exe", ".pyd")):
	"""Снять пометку «скачано из интернета» (поток NTFS Zone.Identifier). Возвращает число разблокированных файлов."""
	if sys.platform != "win32" or not os.path.isdir(root):
		return 0
	n = 0
	for base, _, files in os.walk(root):
		for f in files:
			if f.lower().endswith(exts):
				try:
					os.remove(os.path.join(base, f) + ":Zone.Identifier")
					n += 1
				except OSError:
					pass
	return n


def _webview(url):
	if getattr(sys, "frozen", False):
		n = unblock(os.path.dirname(sys.executable))
		if n:
			log("снята пометка «из интернета» с %d файлов" % n)
	import webview  # noqa: импорт здесь — ошибка .NET ловится выше
	webview.create_window("UMG Studio", url, width=1600, height=980, min_size=(1000, 640), background_color="#071114")
	icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "favicon.png")
	webview.start(icon=icon)  # на Windows значок окна берётся из exe; icon — для GTK/Qt


def find_app_browser():
	env = os.environ
	cands = []
	for root in (env.get("ProgramFiles(x86)"), env.get("ProgramFiles"), env.get("LOCALAPPDATA")):
		if root:
			cands.append(os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"))
			cands.append(os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"))
	for c in cands:
		if os.path.isfile(c):
			return c
	return None


def _app_browser(url):
	exe = find_app_browser()
	if not exe:
		raise RuntimeError("нет Edge/Chrome")
	# свой профиль: отдельный процесс, который живёт, пока открыто окно (иначе Edge отдаст окно уже запущенному и выйдет)
	profile = os.path.join(os.path.dirname(log_path()), "browser-profile")
	p = subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + profile, "--window-size=1600,980",
						  "--no-first-run", "--no-default-browser-check"])
	p.wait()


def open_window(url, mode="auto"):
	"""Блокирует, пока окно открыто."""
	order = {"auto": ("webview", "edge", "browser"), "webview": ("webview", "browser"),
			 "edge": ("edge", "browser"), "browser": ("browser",)}.get(mode, ("webview", "edge", "browser"))
	for kind in order:
		try:
			if kind == "webview":
				_webview(url)
				return
			if kind == "edge":
				_app_browser(url)
				return
		except Exception:  # noqa: BLE001 — любой сбой окна: пробуем следующий способ
			log("окно %s не открылось:\n%s" % (kind, traceback.format_exc()))
			continue
	webbrowser.open(url)
	try:
		threading.Event().wait()
	except KeyboardInterrupt:
		pass
