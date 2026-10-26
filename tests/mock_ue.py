"""
Имитация плагина UMG Studio Bridge (те же маршруты и ответы) — для тестов программы без редактора.
	python tests/mock_ue.py [порт]   (по умолчанию 30111)
WBP хранятся в памяти: import кладёт текст, export отдаёт его же.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "studio"))
from umgstudio import t3d  # noqa: E402

STORE = {}
PROJECT_DIR = None   # тест подставляет временную папку проекта
META = {}            # asset → {"parent", "designSizeMode", "designSize"}
TEXTURES = {}        # asset → PNG bytes


class H(BaseHTTPRequestHandler):
	def log_message(self, *a):
		pass

	def reply(self, obj):
		data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
		self.send_response(200)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)

	def do_GET(self):
		if self.path == "/umgstudio/ping":
			return self.reply({"ok": True, "engine": "5.8.0-mock", "project": "MadWater", "projectDir": PROJECT_DIR or "", "version": 2})
		if self.path == "/umgstudio/list":
			return self.reply({"ok": True, "widgets": [{"asset": a, "name": a.rsplit("/", 1)[1],
														"parent": META.get(a, {}).get("parent", "/Script/UMG.UserWidget")} for a in sorted(STORE)]})
		if self.path.startswith("/umgstudio/texture?"):
			from urllib.parse import parse_qs, urlparse
			asset = parse_qs(urlparse(self.path).query).get("asset", [""])[0]
			if asset in TEXTURES:
				self.send_response(200)
				self.send_header("Content-Type", "image/png")
				self.send_header("Content-Length", str(len(TEXTURES[asset])))
				self.end_headers()
				self.wfile.write(TEXTURES[asset])
				return
		self.send_error(404)

	def do_POST(self):
		body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
		if self.path == "/umgstudio/import":
			roots = t3d.parse(body.get("text", ""))
			if not roots:
				return self.reply({"ok": False, "error": "Текст не разобрался"})
			created = body["asset"] not in STORE
			STORE[body["asset"]] = body["text"]
			n = sum(1 for _ in t3d.walk(roots[0]))
			return self.reply({"ok": True, "error": "", "asset": body["asset"], "created": created, "backup": "",
							   "root": roots[0]["name"], "widgets": n, "compileErrors": 0, "compileWarnings": 0,
							   "messages": ["Инфо: mock"], "renamed": [], "received": {k: v for k, v in body.items() if k != "text"}})
		if self.path == "/umgstudio/export":
			if body.get("asset") not in STORE:
				return self.reply({"ok": False, "error": "Нет Widget Blueprint %s" % body.get("asset")})
			m = META.get(body["asset"], {})
			return self.reply({"ok": True, "asset": body["asset"], "text": STORE[body["asset"]],
							   "parent": m.get("parent", "/Script/UMG.UserWidget"),
							   "designSizeMode": m.get("designSizeMode", "FillScreen"), "designSize": m.get("designSize", [1920, 1080])})
		if self.path == "/umgstudio/open":
			return self.reply({"ok": body.get("asset") in STORE})
		self.send_error(404)


def start(port=30111):
	httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
	threading.Thread(target=httpd.serve_forever, daemon=True).start()
	return httpd


if __name__ == "__main__":
	# python tests/mock_ue.py [порт] [папка проекта] [--seed] — --seed кладёт в «проект» WBP_Key и WBP_Drive из examples
	args = [a for a in sys.argv[1:] if not a.startswith("--")]
	if len(args) > 1:
		PROJECT_DIR = os.path.abspath(args[1]) + os.sep
	if "--seed" in sys.argv:
		ex = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "UMGPaste")
		for name, asset in (("WBP_Key.copy.txt", "/Game/UI/HUD/Widgets/WBP_Key"), ("WBP_Drive.copy.txt", "/Game/UI/WBP_Drive")):
			with open(os.path.join(ex, name), encoding="utf-8-sig") as f:
				STORE[asset] = f.read()
	start(int(args[0]) if args else 30111)
	print("mock UE bridge on", sys.argv[1] if len(sys.argv) > 1 else 30111)
	threading.Event().wait()
