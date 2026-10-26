"""
Настройки проекта (umgstudio.json рядом с программой). Пустое поле = значение по умолчанию от папки проекта UE.

	project           папка проекта UE (где .uproject) — подставляется сама из открытого редактора
	specs             папки спецификаций (.py) и текстов (paste/copy); первая — рабочая: туда пишутся новые файлы
	widgets           Content-папка виджетов: save() по умолчанию, новые WBP        (/Game/UI/HUD/Widgets)
	font              шрифт текста в text()                                         (/Game/UI/HUD/Fonts/F_HUD)
	materials_content Content-папка MI для MAT.format(...)                          (/Game/UI/HUD/Materials)
	textures_content  Content-папка текстур для TEX.format(...)                     (/Game/UI/HUD/Textures)
	materials         .hlsl мастер-материалов для превью
	setup_hud         Scripts/ue_setup_hud.py — параметры мастеров
	assets            hud_assets.json — выгрузка MI из UE (ue/export_hud_assets.py)
	textures          папки PNG текстур для превью
	design            снимок дизайн-системы Claude Design
	ue                адрес моста в редакторе (плагин UMG Studio Bridge)
	window            auto | webview | edge | browser
	ai_engine         ИИ в программе: claude (Claude Code) | codex (OpenAI Codex CLI) — выбирается и в окне чата
	claude, codex     пути к CLI (claude.exe / claude.cmd, codex.cmd); пусто — найти самому
	claude_model      модель Claude (opus, sonnet, haiku…), codex_model — модель Codex; пусто — как в самом CLI
"""
import json
import os
import sys

REPO = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else \
	os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_DEFAULTS = {
	"widgets": "/Game/UI/HUD/Widgets",
	"font": "/Game/UI/HUD/Fonts/F_HUD",
	"materials_content": "/Game/UI/HUD/Materials",
	"textures_content": "/Game/UI/HUD/Textures",
}
KEYS = ("project", "specs", "widgets", "font", "materials_content", "textures_content", "materials", "setup_hud",
		"assets", "textures", "design", "ue", "window", "port", "claude", "claude_model", "codex",
		"codex_model", "ai_engine")
LISTS = ("specs", "textures")


def settings_path():
	for base in (os.getcwd(), REPO):
		p = os.path.join(base, "umgstudio.json")
		if os.path.isfile(p):
			return p
	return os.path.join(REPO, "umgstudio.json")


def load_settings():
	p = settings_path()
	data = {}
	if os.path.isfile(p):
		with open(p, encoding="utf-8") as f:
			data = json.load(f)
	base = os.path.dirname(p)
	out = {k: data.get(k) for k in KEYS}
	# относительные пути — от папки umgstudio.json
	for k in ("project", "materials", "setup_hud", "assets", "design"):
		if out[k]:
			out[k] = os.path.normpath(os.path.join(base, out[k]))
	for k in LISTS:
		v = out[k] or []
		out[k] = [os.path.normpath(os.path.join(base, d)) for d in ([v] if isinstance(v, str) else v)]
	return out


def save_settings(settings):
	p = settings_path()
	data = {}
	if os.path.isfile(p):
		with open(p, encoding="utf-8") as f:
			data = json.load(f)
	for k in KEYS:
		v = settings.get(k)
		if v in (None, "", []):
			data.pop(k, None)
		else:
			data[k] = v
	with open(p, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=2)
	return p


def _first(*cands):
	for c in cands:
		if c and os.path.exists(c):
			return c
	return cands[-1] if cands else None


def resolve(s):
	"""Настройки → рабочие пути (пустое — по умолчанию от проекта UE, иначе — от папки программы)."""
	proj = s.get("project")
	cfg = {}
	work = os.path.join(proj, "UMGStudio") if proj else os.path.join(REPO, "specs")
	cfg["specs"] = list(s.get("specs") or []) or ([work] + ([os.path.join(REPO, "examples", "UMGPaste")] if not proj else []))
	cfg["work_dir"] = cfg["specs"][0]
	saved = os.path.join(proj, "Saved", "UMGStudio") if proj else None
	cfg["assets"] = s.get("assets") or (os.path.join(saved, "hud_assets.json") if saved else None)
	cfg["textures"] = list(s.get("textures") or []) or ([os.path.join(saved, "Textures")] if saved else [])
	cfg["setup_hud"] = s.get("setup_hud") or _first(proj and os.path.join(proj, "Scripts", "ue_setup_hud.py"),
													 os.path.join(REPO, "Skills", "ue_setup_hud.py"))
	cfg["materials"] = s.get("materials") or _first(proj and os.path.join(proj, "SourceArt", "UI", "HUD", "HUD_UE57_Kit", "Materials"),
													 os.path.join(REPO, "Materials"))
	cfg["design"] = s.get("design") or os.path.join(REPO, "design", "RacingHud")
	cfg["ue"] = s.get("ue") or "http://127.0.0.1:30110"
	cfg["window"] = s.get("window") or "auto"
	cfg["port"] = int(s.get("port") or 8765)
	cfg["claude"] = s.get("claude") or ""
	cfg["claude_model"] = s.get("claude_model") or ""
	cfg["codex"] = s.get("codex") or ""
	cfg["codex_model"] = s.get("codex_model") or ""
	cfg["ai_engine"] = s.get("ai_engine") or "claude"
	cfg["project"] = proj
	cfg["content"] = {k: (s.get(k) or v).rstrip("/") for k, v in CONTENT_DEFAULTS.items()}
	return cfg


def content_env(content):
	"""Пути Content для запуска спецификации (umg.py читает UMGSTUDIO_CONTENT)."""
	return json.dumps(content, ensure_ascii=False)
