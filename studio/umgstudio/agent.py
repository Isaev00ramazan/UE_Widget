"""
ИИ внутри программы: Claude Code (CLI `claude`) на компьютере пользователя, по подписке — без ключа API.

Программа запускает `claude -p` в рабочей папке спецификаций: запрос — через stdin (так он не проходит через
командную строку Windows), ответ — поток JSON (--output-format stream-json). Claude правит .py сам
(--permission-mode acceptEdits, только файловые инструменты, только в рабочей папке); превью обновляется
слежением за файлами. Диалог продолжается через --resume <session_id>.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

TOOLS = "Read,Edit,Write,Glob,Grep"

RULES = """Ты встроен в UMG Studio — программу вёрстки UMG-виджетов для Unreal Engine 5.8. Пользователь видит превью
виджета рядом с этим чатом; после каждого сохранения .py превью пересобирается само.

Правила:
- Спецификация <экран>.py — единственный источник правды. Правь её инструментом Edit. .uasset и редактор UE не трогай:
  в UE пользователь отправит виджет кнопкой «В UE ▶».
- API спецификаций — umg.py (путь — в «Состоянии UMG Studio»; читай, не правь; sys.path.insert в спецификации
  программа игнорирует — подставляет свой umg): W(cls, name, props, slot, children, var, collapsed),
  фабрики text/image/sizebox/box/border/spacer/retainer/user_widget, слоты cslot/bs/grid, цвета hex_lin("RRGGBB").
  Значения props/slot — строки в формате UE, как в тексте вставки.
- Правила вёрстки, значения и ловушки — .claude/skills/umg-widgets/SKILL.md и references/ (прочитай, если задача
  про вёрстку, шрифты, цвета или материалы и ты их ещё не читал).
- Шрифт: Size UE = px дизайна × 0.75. Цвета в UE линейные (hex_lin переводит из sRGB HEX).
- Имена элементов не меняй без просьбы: на них завязаны BindWidget, анимации и графы.
- Строки tweak("WBP", "Элемент", …) — правки из панели свойств. Если просят встроить правки — перенеси значения в
  вызовы W()/фабрик этого элемента и удали строки tweak (и пустой заголовок блока).
- Команды не запускай: превью пользователь видит сам, программа пересобирает его после твоей правки; если
  спецификация упадёт, трассировка придёт в следующем сообщении.
- Отвечай по-русски, коротко: что изменил и где."""


def find_claude(configured=None):
	"""Путь к CLI: из настроек → PATH → обычные места установки на Windows."""
	if configured:
		return configured if os.path.isfile(configured) else shutil.which(configured)
	p = shutil.which("claude")
	if p:
		return p
	home = os.path.expanduser("~")
	for c in (os.path.join(home, ".local", "bin", "claude.exe"), os.path.join(home, ".local", "bin", "claude"),
			  os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
			  os.path.join(home, ".claude", "local", "claude")):
		if c and os.path.isfile(c):
			return c
	return None


def _short(path, root):
	try:
		rel = os.path.relpath(path, root)
		return path if rel.startswith("..") else rel
	except ValueError:
		return path


class Agent:
	def __init__(self, broadcast):
		self.broadcast = broadcast      # fn(dict) → SSE всем окнам
		self.claude = None              # путь из настроек (пусто — искать)
		self.model = None
		self.session = None             # session_id для --resume
		self.session_cwd = None
		self.proc = None
		self.log = []                   # реплики текущего диалога (для перезагрузки окна)
		self.lock = threading.Lock()
		self._version = {}
		self._stopped = False

	# ─── состояние ───
	def status(self):
		path = find_claude(self.claude)
		out = {"ok": bool(path), "path": path or "", "running": self.running(), "session": self.session}
		if not path:
			out["error"] = ("Claude Code не найден. Установи его (https://claude.com/claude-code), один раз запусти "
							"`claude` в терминале и войди в аккаунт; или укажи путь к claude в «⚙ Проект».")
			return out
		if path not in self._version:
			try:
				p = subprocess.run(self._cmd(path, ["--version"]), capture_output=True, timeout=20, stdin=subprocess.DEVNULL,
								   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
				self._version[path] = p.stdout.decode("utf-8", "replace").strip() or p.stderr.decode("utf-8", "replace").strip()
			except (OSError, subprocess.SubprocessError) as e:
				self._version[path] = ""
				out["ok"] = False
				out["error"] = "Не запускается %s: %s" % (path, e)
		out["version"] = self._version.get(path, "")
		return out

	def running(self):
		return self.proc is not None and self.proc.poll() is None

	def reset(self):
		self.stop()
		self.session = None
		self.log = []

	def stop(self):
		p = self.proc
		if p is not None and p.poll() is None:
			self._stopped = True
			try:
				p.kill()
			except OSError:
				pass

	@staticmethod
	def _cmd(path, args):
		# claude.cmd (установка через npm) Windows запускает сама через cmd.exe; аргументы — только флаги без текста
		# пользователя (запрос идёт через stdin), так что разбор строки в cmd им не страшен
		if path.lower().endswith(".py"):
			return [sys.executable, path] + args
		return [path] + args

	# ─── запрос ───
	def prompt(self, text, ctx):
		"""Текст для stdin: правила (в начале диалога) + что открыто в программе + запрос пользователя."""
		parts = []
		if not self.session:
			parts.append(RULES)
		c = ["Рабочая папка: %s" % ctx.get("work_dir", "")]
		if ctx.get("umg"):
			c.append("Библиотека umg.py: %s" % ctx["umg"])
		if ctx.get("file"):
			c.append("Открыт экран: %s (виджет %s)" % (ctx["file"], ctx.get("wbp") or "?"))
		sel = ctx.get("selected")
		if sel:
			c.append("Выбран элемент: %s (%s)" % (sel.get("name"), sel.get("cls")))
			for part in ("props", "slot"):
				if sel.get(part):
					c.append("  %s: %s" % (part, json.dumps(sel[part], ensure_ascii=False)))
		if ctx.get("error"):
			c.append("Последний запуск спецификации упал:\n%s" % ctx["error"][-2500:])
		if ctx.get("tweaks"):
			c.append("В файле есть строки tweak(...) из панели свойств.")
		parts.append("[Состояние UMG Studio]\n" + "\n".join(c))
		parts.append("[Запрос пользователя]\n" + text)
		return "\n\n".join(parts)

	def send(self, text, ctx, on_done):
		"""Запустить Claude Code; события — в broadcast({"agent": …}); on_done(список изменённых файлов) по завершении."""
		with self.lock:
			if self.running():
				return {"ok": False, "error": "ИИ ещё работает — дождись ответа или нажми «Стоп»"}
			path = find_claude(self.claude)
			if not path:
				return {"ok": False, "error": self.status()["error"]}
			cwd = ctx["work_dir"]
			if self.session and self.session_cwd != cwd:
				self.session = None   # другая рабочая папка (другой проект) — новый диалог
			self.session_cwd = cwd
			args = ["-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
					"--allowedTools", TOOLS]
			if self.model:
				args += ["--model", self.model]
			if self.session:
				args += ["--resume", self.session]
			try:
				self.proc = subprocess.Popen(self._cmd(path, args), cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
											 stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
			except OSError as e:
				return {"ok": False, "error": "Не запустился Claude Code (%s): %s" % (path, e)}
			self._stopped = False
			self._emit({"kind": "user", "text": text})
			proc = self.proc
		data = self.prompt(text, ctx).encode("utf-8")
		threading.Thread(target=self._feed, args=(proc, data), daemon=True).start()
		threading.Thread(target=self._read, args=(proc, cwd, on_done), daemon=True).start()
		return {"ok": True}

	def _emit(self, item):
		item["t"] = time.time()
		self.log.append(item)
		del self.log[:-200]
		self.broadcast({"agent": item})

	@staticmethod
	def _feed(proc, data):
		try:
			proc.stdin.write(data)
			proc.stdin.close()
		except OSError:
			pass

	def _read(self, proc, cwd, on_done):
		changed, result, started = [], None, time.time()
		err = []
		threading.Thread(target=lambda: err.extend(proc.stderr.read().decode("utf-8", "replace").splitlines()),
						 daemon=True).start()
		for raw in proc.stdout:
			try:
				ev = json.loads(raw.decode("utf-8", "replace"))
			except ValueError:
				continue
			kind = ev.get("type")
			if kind == "system" and ev.get("subtype") == "init" and ev.get("session_id"):
				self.session = ev["session_id"]
			elif kind == "assistant":
				for block in (ev.get("message") or {}).get("content") or []:
					if block.get("type") == "text" and block.get("text", "").strip():
						self._emit({"kind": "text", "text": block["text"]})
					elif block.get("type") == "tool_use":
						inp = block.get("input") or {}
						target = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
						if block.get("name") in ("Edit", "Write", "MultiEdit") and inp.get("file_path"):
							if inp["file_path"] not in changed:
								changed.append(inp["file_path"])
						self._emit({"kind": "tool", "name": block.get("name", ""), "target": _short(target, cwd)})
			elif kind == "result":
				result = ev
				if ev.get("session_id"):
					self.session = ev["session_id"]
		code = proc.wait()
		item = {"kind": "done", "changed": [_short(p, cwd) for p in changed], "seconds": round(time.time() - started, 1)}
		if self._stopped:
			item["error"] = "Остановлено"
		elif result is None or result.get("is_error") or code != 0:
			msg = (result or {}).get("result") or "\n".join(err[-15:]) or "Claude Code завершился с кодом %s" % code
			low = msg.lower()
			if "login" in low or "log in" in low or "auth" in low or "api key" in low:
				msg += "\n\nЗапусти `claude` в терминале и войди в аккаунт — потом повтори."
			item["error"] = msg
		try:
			item.update(on_done(changed) or {})
		except Exception as e:  # noqa: BLE001
			item["note"] = "не записал историю для «Отменить»: %r" % e
		self._emit(item)
