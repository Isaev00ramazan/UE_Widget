"""
ИИ внутри программы: CLI-агент на компьютере пользователя, по его подписке — без ключа API в программе.

	claude — Claude Code: `claude -p --output-format stream-json --verbose`, правки — --permission-mode acceptEdits,
			 только файловые инструменты; диалог продолжается через --resume <session_id>.
	codex  — OpenAI Codex CLI: `codex exec --json --sandbox workspace-write`, правки — apply_patch в рабочей папке;
			 диалог — `codex exec … resume <thread_id>`.

Агент запускается в рабочей папке спецификаций; запрос идёт через stdin (не через командную строку Windows), ответ —
поток JSON по строкам. Превью обновляется слежением за файлами, «Отменить» — по снимку файлов до запуска (server.py).
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

CLAUDE_TOOLS = "Read,Edit,Write,Glob,Grep"

# выбор в окне чата: (движок, модель, подпись); модель None — как настроено в самом CLI
MODELS = [
	("claude", None, "Claude — по умолчанию"),
	("claude", "opus", "Claude Opus"),
	("claude", "sonnet", "Claude Sonnet"),
	("claude", "haiku", "Claude Haiku"),
	("codex", None, "Codex — по умолчанию"),
]

ENGINES = {
	"claude": {
		"title": "Claude Code",
		"names": ("claude",),
		"places": (("~", ".local", "bin", "claude.exe"), ("~", ".local", "bin", "claude"), ("%APPDATA%", "npm", "claude.cmd"),
				   ("~", ".claude", "local", "claude")),
		"missing": "Claude Code не найден. Установи его (https://claude.com/claude-code), один раз запусти `claude` "
				   "в терминале и войди в аккаунт; или укажи путь к claude в «⚙ Проект».",
		"login": "Запусти `claude` в терминале и войди в аккаунт — потом повтори.",
	},
	"codex": {
		"title": "Codex",
		"names": ("codex",),
		"places": (("%APPDATA%", "npm", "codex.cmd"), ("~", ".local", "bin", "codex.exe"), ("~", ".local", "bin", "codex")),
		"missing": "Codex не найден. Установи его (`npm install -g @openai/codex`), один раз выполни `codex login` "
				   "в терминале; или укажи путь к codex в «⚙ Проект».",
		"login": "Выполни `codex login` в терминале — потом повтори.",
	},
}

RULES = """Ты встроен в UMG Studio — программу вёрстки UMG-виджетов для Unreal Engine 5.8. Пользователь видит превью
виджета рядом с этим чатом; после каждого сохранения .py превью пересобирается само.

Правила:
- Спецификация <экран>.py — единственный источник правды. Правь её. .uasset и редактор UE не трогай:
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
- <WBP>.copy.txt рядом — дерево виджета, забранное из редактора UE (если просят перенести отличия из UE — правда там).
- %s
- Отвечай по-русски, коротко: что изменил и где."""

RUN_RULE = {
	"claude": "Команды не запускай: превью пользователь видит сам, программа пересобирает его после твоей правки; если "
			  "спецификация упадёт, трассировка придёт в следующем сообщении.",
	"codex": "Команды — только чтобы читать файлы; правь через apply_patch. Спецификацию и сборку не запускай: превью "
			 "пользователь видит сам, программа пересобирает его после твоей правки.",
}


def _expand(parts):
	out = []
	for p in parts:
		if p == "~":
			p = os.path.expanduser("~")
		elif p.startswith("%") and p.endswith("%"):
			p = os.environ.get(p[1:-1], "")
			if not p:
				return None
		out.append(p)
	return os.path.join(*out)


def find_cli(engine, configured=None):
	"""Путь к CLI: из настроек → PATH → обычные места установки."""
	if configured:
		return configured if os.path.isfile(configured) else shutil.which(configured)
	e = ENGINES[engine]
	for n in e["names"]:
		p = shutil.which(n)
		if p:
			return p
	for parts in e["places"]:
		c = _expand(parts)
		if c and os.path.isfile(c):
			return c
	return None


def find_claude(configured=None):
	return find_cli("claude", configured)


def _short(path, root):
	try:
		rel = os.path.relpath(path, root)
		return path if rel.startswith("..") else rel
	except ValueError:
		return path


class Agent:
	def __init__(self, broadcast):
		self.broadcast = broadcast      # fn(dict) → SSE всем окнам
		self.engine = "claude"
		self.paths = {"claude": None, "codex": None}    # пути из настроек (пусто — искать)
		self.models = {"claude": None, "codex": None}
		self.session = None             # session_id (claude) / thread_id (codex) для продолжения диалога
		self.session_key = None         # (движок, модель, папка), к которым относится session
		self.proc = None
		self.log = []                   # реплики текущего диалога (для перезагрузки окна)
		self.lock = threading.Lock()
		self._version = {}
		self._stopped = False

	# ─── выбор движка и модели ───
	@property
	def model(self):
		return self.models.get(self.engine)

	def configure(self, engine=None, model=None, paths=None, models=None):
		if paths:
			self.paths.update({k: v or None for k, v in paths.items() if k in self.paths})
		if models:
			self.models.update({k: v or None for k, v in models.items() if k in self.models})
		if engine in ENGINES:
			self.engine = engine
		if model is not None:
			self.models[self.engine] = model or None

	def choices(self):
		out = [{"engine": e, "model": m, "label": label} for e, m, label in MODELS]
		for e in ENGINES:   # своя модель из настроек — тоже в списке
			m = self.models.get(e)
			if m and not any(c["engine"] == e and c["model"] == m for c in out):
				out.append({"engine": e, "model": m, "label": "%s — %s" % (ENGINES[e]["title"], m)})
		return out

	# ─── состояние ───
	def status(self):
		e = ENGINES[self.engine]
		path = find_cli(self.engine, self.paths.get(self.engine))
		out = {"ok": bool(path), "path": path or "", "running": self.running(), "session": self.session,
			   "engine": self.engine, "model": self.model, "title": e["title"], "choices": self.choices()}
		if not path:
			out["error"] = e["missing"]
			return out
		if path not in self._version:
			try:
				p = subprocess.run(self._cmd(path, ["--version"]), capture_output=True, timeout=20, stdin=subprocess.DEVNULL,
								   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
				self._version[path] = p.stdout.decode("utf-8", "replace").strip() or p.stderr.decode("utf-8", "replace").strip()
			except (OSError, subprocess.SubprocessError) as ex:
				self._version[path] = ""
				out["ok"] = False
				out["error"] = "Не запускается %s: %s" % (path, ex)
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
		# claude.cmd / codex.cmd (установка через npm) Windows запускает сама через cmd.exe; аргументы — только флаги
		# без текста пользователя (запрос идёт через stdin), так что разбор строки в cmd им не страшен
		if path.lower().endswith(".py"):
			return [sys.executable, path] + args
		return [path] + args

	def _args(self, session):
		m = self.model
		if self.engine == "codex":
			args = ["exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write"]
			if m:
				args += ["--model", m]
			if session:
				args += ["resume", session]
			return args + ["-"]
		args = ["-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
				"--allowedTools", CLAUDE_TOOLS]
		if m:
			args += ["--model", m]
		if session:
			args += ["--resume", session]
		return args

	# ─── запрос ───
	def prompt(self, text, ctx, first=None):
		"""Текст для stdin: правила (в начале диалога) + что открыто в программе + запрос пользователя."""
		parts = []
		if first if first is not None else not self.session:
			parts.append(RULES % RUN_RULE[self.engine])
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
		"""Запустить агента; события — в broadcast({"agent": …}); on_done(изменённые файлы) → доп. поля «готово»."""
		with self.lock:
			if self.running():
				return {"ok": False, "error": "ИИ ещё работает — дождись ответа или нажми «Стоп»"}
			path = find_cli(self.engine, self.paths.get(self.engine))
			if not path:
				return {"ok": False, "error": ENGINES[self.engine]["missing"]}
			cwd = ctx["work_dir"]
			key = (self.engine, self.model, cwd)
			if self.session and self.session_key != key:
				self.session = None   # другой движок, модель или папка (проект) — новый диалог
			self.session_key = key
			self._stopped = False
			self._emit({"kind": "user", "text": text, "engine": self.engine, "model": self.model})
			job = {"path": path, "cwd": cwd, "text": text, "ctx": ctx, "on_done": on_done, "session": self.session}
			err = self._start(job)
			if err:
				self._emit({"kind": "done", "error": err, "changed": [], "seconds": 0})
				return {"ok": False, "error": err}
		return {"ok": True}

	def _start(self, job):
		try:
			self.proc = subprocess.Popen(self._cmd(job["path"], self._args(job["session"])), cwd=job["cwd"], stdin=subprocess.PIPE,
										 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
										 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
		except OSError as e:
			return "Не запустился %s (%s): %s" % (ENGINES[self.engine]["title"], job["path"], e)
		data = self.prompt(job["text"], job["ctx"], first=not job["session"]).encode("utf-8")
		proc = self.proc
		threading.Thread(target=self._feed, args=(proc, data), daemon=True).start()
		threading.Thread(target=self._read, args=(proc, job), daemon=True).start()
		return None

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

	# ─── разбор потока ───
	def _claude_event(self, ev, st):
		kind = ev.get("type")
		if kind == "system" and ev.get("subtype") == "init" and ev.get("session_id"):
			self.session = ev["session_id"]
		elif kind == "assistant":
			for block in (ev.get("message") or {}).get("content") or []:
				if block.get("type") == "text" and block.get("text", "").strip():
					self._emit({"kind": "text", "text": block["text"]})
					st["said"] = True
				elif block.get("type") == "tool_use":
					inp = block.get("input") or {}
					target = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
					if block.get("name") in ("Edit", "Write", "MultiEdit") and inp.get("file_path"):
						st["changed"].append(inp["file_path"])
					self._emit({"kind": "tool", "name": block.get("name", ""), "target": _short(target, st["cwd"])})
					st["said"] = True
		elif kind == "result":
			st["result"] = ev
			if ev.get("session_id"):
				self.session = ev["session_id"]
			if ev.get("is_error"):
				st["error"] = ev.get("result") or "ошибка"

	def _codex_event(self, ev, st):
		kind = ev.get("type")
		if kind == "thread.started" and ev.get("thread_id"):
			self.session = ev["thread_id"]
		elif kind in ("item.started", "item.completed", "item.updated"):
			it = ev.get("item") or {}
			t = it.get("type") or it.get("item_type")
			if t in ("agent_message", "assistant_message") and kind == "item.completed":
				if (it.get("text") or "").strip():
					self._emit({"kind": "text", "text": it["text"]})
					st["said"] = True
			elif t == "command_execution" and kind == "item.started":
				self._emit({"kind": "tool", "name": "Команда", "target": (it.get("command") or "")[:120]})
				st["said"] = True
			elif t == "file_change" and kind == "item.completed":
				for ch in it.get("changes") or []:
					p = ch.get("path") or ""
					st["changed"].append(p if os.path.isabs(p) else os.path.join(st["cwd"], p))
					self._emit({"kind": "tool", "name": "Edit", "target": _short(p, st["cwd"])})
				st["said"] = True
			elif t == "error" and kind == "item.completed":
				st["error"] = it.get("message") or "ошибка"
		elif kind == "turn.completed":
			st["result"] = ev
		elif kind == "turn.failed":
			st["error"] = ((ev.get("error") or {}).get("message")) or "ошибка"
		elif kind == "error":
			st["error"] = ev.get("message") or "ошибка"
		elif "msg" in ev:   # старый формат codex exec --json
			m = ev["msg"] or {}
			t = m.get("type")
			if t == "session_configured" and m.get("session_id"):
				self.session = m["session_id"]
			elif t == "agent_message" and (m.get("message") or "").strip():
				self._emit({"kind": "text", "text": m["message"]})
				st["said"] = True
			elif t == "exec_command_begin":
				cmd = m.get("command")
				self._emit({"kind": "tool", "name": "Команда", "target": (" ".join(cmd) if isinstance(cmd, list) else str(cmd or ""))[:120]})
			elif t == "patch_apply_begin":
				for p in (m.get("changes") or {}):
					st["changed"].append(p if os.path.isabs(p) else os.path.join(st["cwd"], p))
					self._emit({"kind": "tool", "name": "Edit", "target": _short(p, st["cwd"])})
			elif t == "task_complete":
				st["result"] = m
			elif t in ("error", "stream_error"):
				st["error"] = m.get("message") or "ошибка"

	def _read(self, proc, job):
		cwd = job["cwd"]
		st = {"changed": [], "result": None, "error": None, "said": False, "cwd": cwd}
		started = time.time()
		err = []
		err_thread = threading.Thread(target=lambda: err.extend(proc.stderr.read().decode("utf-8", "replace").splitlines()),
									  daemon=True)
		err_thread.start()
		handle = self._codex_event if self.engine == "codex" else self._claude_event
		for raw in proc.stdout:
			try:
				ev = json.loads(raw.decode("utf-8", "replace"))
			except ValueError:
				continue
			if isinstance(ev, dict):
				handle(ev, st)
		code = proc.wait()
		err_thread.join(5)
		for pipe in (proc.stdout, proc.stderr):
			try:
				pipe.close()
			except OSError:
				pass
		# продолжение диалога не удалось (сессия устарела) — один раз начать заново
		if job["session"] and not st["said"] and not self._stopped and (code != 0 or st["error"]):
			self.session = None
			job = dict(job, session=None)
			if not self._start(job):
				return
		changed = list(dict.fromkeys(st["changed"]))
		item = {"kind": "done", "changed": [_short(p, cwd) for p in changed], "seconds": round(time.time() - started, 1)}
		if self._stopped:
			item["error"] = "Остановлено"
		elif st["error"] or code != 0 or (st["result"] is None and not st["said"]):
			msg = st["error"] or "\n".join(err[-15:]) or "%s завершился с кодом %s" % (ENGINES[self.engine]["title"], code)
			low = msg.lower()
			if any(w in low for w in ("login", "log in", "auth", "api key", "not logged", "unauthorized")):
				msg += "\n\n" + ENGINES[self.engine]["login"]
			item["error"] = msg
		try:
			item.update(job["on_done"](changed) or {})
		except Exception as e:  # noqa: BLE001
			item["note"] = "не записал историю для «Отменить»: %r" % e
		self._emit(item)
