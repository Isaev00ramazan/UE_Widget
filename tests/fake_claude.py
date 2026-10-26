"""
Поддельный Claude Code для тестов ИИ в программе: читает запрос из stdin, отвечает потоком stream-json как
`claude -p --output-format stream-json --verbose` и правит файл в рабочей папке (cwd).
Аргументы запуска и запрос пишет в fake_claude.log.json рядом с собой.
Запрос с «СЛОМАЙ» — ошибка (как не вошедший в аккаунт Claude Code).
"""
import json
import os
import sys

if "--version" in sys.argv:
	print("9.9.9 (Claude Code, подделка для тестов)")
	sys.exit(0)
prompt = sys.stdin.read()
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "fake_claude.log.json"), "a", encoding="utf-8") as f:
	f.write(json.dumps({"argv": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd()}, ensure_ascii=False) + "\n")


def out(ev):
	sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
	sys.stdout.flush()


sid = "sess-1"
out({"type": "system", "subtype": "init", "session_id": sid, "cwd": os.getcwd()})
if "СЛОМАЙ" in prompt:
	out({"type": "result", "subtype": "error", "is_error": True, "result": "Invalid API key · Please run /login", "session_id": sid})
	sys.exit(1)
target = next(f for f in sorted(os.listdir(".")) if f.endswith(".py") and f != "umg.py")
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": os.path.abspath(target)}}]}})
with open(target, encoding="utf-8") as f:
	text = f.read()
with open(target, "w", encoding="utf-8") as f:
	f.write(text.replace("A=1.000000))'", "A=0.500000))'", 1))
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": os.path.abspath(target)}}]}})
out({"type": "assistant", "message": {"content": [{"type": "text", "text": "Сделал полупрозрачным."}]}})
out({"type": "result", "subtype": "success", "is_error": False, "result": "Сделал полупрозрачным.", "session_id": sid})
