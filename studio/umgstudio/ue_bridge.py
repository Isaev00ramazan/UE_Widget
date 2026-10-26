"""
Связь с плагином UMG Studio Bridge в редакторе UE (ue/UMGStudio): локальный HTTP, по умолчанию порт 30110.
Браузер к редактору не ходит — запросы делает сервер программы (нет проблем с CORS).
"""
import json
import re
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:30110"
_EXPORT_PATH = re.compile(r"ExportPath=\"[^']*'(/Game/[^.']+)\.[^:']+:WidgetTree")


def call(base, path, body=None, timeout=60):
	data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
	req = urllib.request.Request(base.rstrip("/") + path, data=data, method="POST" if data else "GET",
								 headers={"Content-Type": "application/json; charset=utf-8"})
	try:
		with urllib.request.urlopen(req, timeout=timeout) as r:
			return json.loads(r.read().decode("utf-8"))
	except urllib.error.URLError as e:
		return {"ok": False, "offline": True, "error": "Редактор UE не отвечает (%s). Открыт ли проект с плагином UMG Studio Bridge?" % getattr(e, "reason", e)}
	except (OSError, ValueError) as e:
		return {"ok": False, "offline": True, "error": "Нет связи с редактором: %r" % e}


def asset_from_text(text):
	"""Путь ассета из ExportPath текста буфера: …'/Game/UI/HUD/Widgets/WBP_X.WBP_X:WidgetTree.Root' → /Game/…/WBP_X"""
	m = _EXPORT_PATH.search(text)
	return m.group(1) if m else None


def design_options(design):
	if design is None:
		return {}
	if design == "screen":
		return {"designSizeMode": "FillScreen"}
	if design == "desired":
		return {"designSizeMode": "Desired"}
	if isinstance(design, (list, tuple)) and len(design) == 2:
		return {"designSizeMode": "Custom", "designSize": [float(design[0]), float(design[1])]}
	return {}
