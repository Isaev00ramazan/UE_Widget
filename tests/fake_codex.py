"""
Поддельный OpenAI Codex CLI для тестов: `codex exec --json … [resume <id>] -` — запрос из stdin, ответ JSONL
(thread.started, item.*, turn.completed), правит первый .py в рабочей папке через «file_change».
Аргументы и запрос пишет в fake_codex.log.json рядом с собой. «СЛОМАЙ» в запросе — ошибка входа.
"""
import json
import os
import sys

if "--version" in sys.argv:
	print("codex-cli 9.9.9 (подделка для тестов)")
	sys.exit(0)
prompt = sys.stdin.buffer.read().decode("utf-8")
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "fake_codex.log.json"), "a", encoding="utf-8") as f:
	f.write(json.dumps({"argv": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd()}, ensure_ascii=False) + "\n")


def out(ev):
	sys.stdout.buffer.write((json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
	sys.stdout.buffer.flush()


out({"type": "thread.started", "thread_id": "thr-7"})
out({"type": "turn.started"})
if "СЛОМАЙ" in prompt:
	out({"type": "turn.failed", "error": {"message": "Not logged in"}})
	sys.exit(1)
target = next(f for f in sorted(os.listdir(".")) if f.endswith(".py") and f != "umg.py")
out({"type": "item.started", "item": {"id": "i1", "type": "command_execution", "command": "cat " + target, "status": "in_progress"}})
with open(target, encoding="utf-8") as f:
	text = f.read()
with open(target, "w", encoding="utf-8") as f:
	f.write(text.replace("A=1.000000))'", "A=0.250000))'", 1))
out({"type": "item.completed", "item": {"id": "i2", "type": "file_change", "changes": [{"path": target, "kind": "update"}], "status": "completed"}})
out({"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "Готово: альфа 0.25."}})
out({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
