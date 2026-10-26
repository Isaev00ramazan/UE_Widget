"""
Запуск спецификации экрана в отдельном процессе: python -m umgstudio.runner <spec.py> [--write]

Спецификация делает `import umg` — подменяем его на umgstudio.umg (тот же API), поэтому строка
sys.path.insert(...) в спецификации ни на что не влияет. Результат — JSON в stdout:
	{"ok": true, "widgets": [{"wbp", "path", "text", "roots": [IR]}], "states": [...], "log": "..."}
	{"ok": false, "error": "трассировка", "log": "..."}
"""
import contextlib
import io
import json
import os
import runpy
import sys
import traceback


def run(spec, write=False):
	from . import umg, t3d
	sys.modules["umg"] = umg
	umg.WRITE = write
	umg.SAVED.clear()
	umg.STATES.clear()
	umg.TEXT_NAMESPACE = "Widgets"
	log = io.StringIO()
	spec = os.path.abspath(spec)
	try:
		with contextlib.redirect_stdout(log):
			runpy.run_path(spec, run_name="__main__")
	except BaseException:  # noqa: BLE001 — показать любую ошибку спецификации в окне
		return {"ok": False, "error": traceback.format_exc(), "log": log.getvalue()}
	widgets = [dict(w, roots=t3d.parse(w["text"])) for w in umg.SAVED]
	return {"ok": True, "widgets": widgets, "states": list(umg.STATES), "log": log.getvalue()}


def main():
	args = [a for a in sys.argv[1:] if not a.startswith("--")]
	out = run(args[0], write="--write" in sys.argv)
	sys.stdout.reconfigure(encoding="utf-8")
	sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
	main()
