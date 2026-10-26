"""
Окно программы. По порядку, пока интерфейс не загрузится:
	1. pywebview (WebView2) — родное окно;
	2. Edge / Chrome в режиме приложения (--app): отдельное окно без адресной строки;
	3. браузер по умолчанию.

«Загрузился» = страница сама позвала /api/ready (server.READY). Окно, которое молча не показалось или
не загрузило интерфейс за READY_TIMEOUT секунд, закрывается, и пробуется следующий способ.

Скачанный из интернета ZIP Windows помечает (Zone.Identifier), и .NET Framework не грузит такие DLL —
pywebview падает на Python.Runtime.dll. Поэтому перед стартом снимаем пометку со своих файлов.
Всё пишется в %LOCALAPPDATA%/UMGStudio/log.txt.
"""
import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

MODES = ("auto", "webview", "edge", "browser")
READY_TIMEOUT = 20

_proc = None       # процесс Edge/Chrome (--app)
_window = None     # окно pywebview


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


def _webview(url, ready, timeout):
	"""True — интерфейс загрузился (и окно потом закрыли); False — окно не показало интерфейс."""
	global _window
	if getattr(sys, "frozen", False):
		n = unblock(os.path.dirname(sys.executable))
		if n:
			log("снята пометка «из интернета» с %d файлов" % n)
	import webview  # noqa: импорт здесь — ошибка .NET ловится в open_window
	_window = webview.create_window("UMG Studio", url, width=1600, height=980, min_size=(1000, 640),
									background_color="#071114")
	returned = threading.Event()

	def watchdog():
		if ready.wait(timeout):
			return
		log("pywebview не загрузил интерфейс за %d с — закрываю окно, пробую Edge" % timeout)
		try:
			_window.destroy()
		except Exception:  # noqa: BLE001
			log("destroy: " + traceback.format_exc())
		# webview.start() не вернулся — дальше из этого потока, процесс завершим сами
		if not returned.wait(5):
			log("pywebview завис — открываю Edge из сторожа")
			if not _app_browser(url, ready, timeout):
				webbrowser.open(url)
				threading.Event().wait()
			os._exit(0)

	threading.Thread(target=watchdog, daemon=True).start()
	icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "favicon.png")
	webview.start(icon=icon)  # на Windows значок окна берётся из exe; icon — для GTK/Qt
	returned.set()
	return ready.is_set()


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


def _app_browser(url, ready, timeout):
	"""Edge/Chrome --app. True — интерфейс загрузился (и окно потом закрыли)."""
	global _proc
	exe = find_app_browser()
	if not exe:
		log("Edge/Chrome не найдены")
		return False
	# свой профиль: отдельный процесс, который живёт, пока открыто окно (иначе Edge отдаст окно уже запущенному и выйдет)
	profile = os.path.join(os.path.dirname(log_path()), "browser-profile")
	log("открываю %s --app" % exe)
	_proc = subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + profile, "--window-size=1600,980",
							  "--no-first-run", "--no-default-browser-check"])
	_proc.wait()
	return ready.is_set()


def open_window(url, mode="auto", ready=None, timeout=READY_TIMEOUT, browser_fallback=True):
	"""Блокирует, пока окно открыто. Возвращает способ, которым интерфейс открылся ('webview' / 'edge' / 'browser')."""
	ready = ready or threading.Event()
	order = {"auto": ("webview", "edge"), "webview": ("webview",), "edge": ("edge",), "browser": ()}.get(mode, ("webview", "edge"))
	for kind in order:
		log("окно: пробую %s" % kind)
		try:
			ok = _webview(url, ready, timeout) if kind == "webview" else _app_browser(url, ready, timeout)
		except Exception:  # noqa: BLE001 — любой сбой окна: пробуем следующий способ
			log("окно %s не открылось:\n%s" % (kind, traceback.format_exc()))
			continue
		if ok:
			log("окно %s закрыто" % kind)
			return kind
		log("окно %s не загрузило интерфейс" % kind)
	if not browser_fallback:
		return None
	log("открываю браузер по умолчанию: %s" % url)
	webbrowser.open(url)
	try:
		threading.Event().wait()
	except KeyboardInterrupt:
		pass
	return "browser"


def close_any():
	"""Закрыть открытое окно (для самопроверки сборки)."""
	try:
		if _window is not None:
			_window.destroy()
	except Exception:  # noqa: BLE001
		pass
	if _proc is not None and _proc.poll() is None:
		_proc.terminate()
