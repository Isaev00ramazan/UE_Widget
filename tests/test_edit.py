"""
Правка свойств из панели → .py (прямо в W(...) или строкой tweak), «Отменить», ИИ через Claude Code (поддельный CLI),
значок программы.
"""
import json
import os
import queue
import shutil
import struct
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "studio"))

from umgstudio import codegen, runner, server, specedit, t3d  # noqa: E402

EX = os.path.join(ROOT, "examples", "UMGPaste")


def key_spec():
	with open(os.path.join(EX, "WBP_Key.copy.txt"), encoding="utf-8-sig") as f:
		return codegen.spec_from_text(f.read(), "WBP_Key", "/Game/UI/HUD/Widgets")


def nodes(path):
	r = runner.run(path)
	assert r["ok"], r.get("error")
	return {n["name"]: n for w in r["widgets"] for root in w["roots"] for n, _ in t3d.walk(root)}


class SpecEdit(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()

	def tearDown(self):
		shutil.rmtree(self.tmp, ignore_errors=True)

	def write(self, name, text):
		p = os.path.join(self.tmp, name)
		with open(p, "w", encoding="utf-8") as f:
			f.write(text)
		return p

	def test_no_edits_keeps_file(self):
		text = key_spec()
		self.assertEqual(specedit.apply(text, "WBP_Key", [])[0], text)

	def test_generated_spec_in_place(self):
		text = key_spec()
		red = "(SpecifiedColor=(R=1.000000,G=0.000000,B=0.000000,A=1.000000))"
		pad = "(Left=2.000000,Top=0.000000,Right=0.000000,Bottom=0.000000)"
		new, rep = specedit.apply(text, "WBP_Key", [
			{"name": "KeyText", "props": {"ColorAndOpacity": red, "Justification": "Center"}, "slot": {"Padding": pad}, "var": False},
			{"name": "KeyIcon", "slot": {"HorizontalAlignment": None}, "collapsed": False},
			{"name": "Border_46", "props": {"Padding": None}},
		])
		self.assertEqual(sorted(rep["inplace"]), ["Border_46", "KeyIcon", "KeyText"])
		self.assertEqual(rep["tweak"], [])
		self.assertNotIn("tweak(", new)
		# правится только нужное: остальные строки файла как были
		self.assertIn("'Justification': 'Center',\n", new)
		n = nodes(self.write("key.py", new))
		self.assertEqual(n["KeyText"]["raw"]["ColorAndOpacity"], red)
		self.assertEqual(n["KeyText"]["raw"]["Justification"], "Center")
		self.assertEqual(n["KeyText"]["slot"]["$raw"]["Padding"], pad)
		self.assertNotIn("bIsVariable", n["KeyText"]["raw"])
		self.assertNotIn("HorizontalAlignment", n["KeyIcon"]["slot"]["$raw"])
		self.assertNotIn("Visibility", n["KeyIcon"]["raw"])
		self.assertNotIn("Padding", n["Border_46"]["raw"])

	def test_factories_go_to_tweak(self):
		with open(os.path.join(EX, "pickup_banner.py"), encoding="utf-8") as f:
			text = f.read()
		e1 = [{"name": "Title", "props": {"Justification": "Center"}, "slot": {"ZOrder": "1"}},
			  {"name": "Banner", "slot": {"bAutoSize": None}, "var": False}]
		new, rep = specedit.apply(text, "WBP_PickupBanner", e1)
		self.assertEqual(sorted(rep["tweak"]), ["Banner", "Title"])
		# флаг var — прямо в box(...), остальное — tweak под импортом umg
		self.assertIn('box("Overlay", "Banner", var=False', new)
		self.assertIn(specedit.HEADER, new)
		new2, _ = specedit.apply(new, "WBP_PickupBanner", [{"name": "Title", "props": {"RenderOpacity": "0.500000"}}])
		self.assertEqual(new2.count("tweak('WBP_PickupBanner', 'Title'"), 1, "правки одного элемента — в одну строку")
		n = nodes(self.write("pb.py", new2))
		self.assertEqual(n["Title"]["raw"]["Justification"], "Center")
		self.assertEqual(n["Title"]["raw"]["RenderOpacity"], "0.500000")
		self.assertEqual(n["Title"]["slot"]["$raw"]["ZOrder"], "1")
		self.assertNotIn("bAutoSize", n["Banner"]["slot"]["$raw"])
		self.assertNotIn("bIsVariable", n["Banner"]["raw"])

	def test_same_name_twice_uses_tweak(self):
		text = 'from umg import *\nfor i in range(2):\n\tpass\nroot = box("CanvasPanel", "R", [box("Overlay", "A"), box("Overlay", "A2")])\n' \
			   'r2 = box("CanvasPanel", "A", [])\n'
		new, rep = specedit.apply(text, "WBP_X", [{"name": "A", "props": {"RenderOpacity": "0.5"}}])
		self.assertEqual(rep["tweak"], ["A"])
		self.assertIn("tweak('WBP_X', 'A', props={'RenderOpacity': '0.5'})", new)


class EditAndUndo(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.spec = os.path.join(self.tmp, "wb_key.py")
		with open(self.spec, "w", encoding="utf-8") as f:
			f.write(key_spec())
		self.st = server.Studio([self.tmp])

	def tearDown(self):
		self.st.agent.stop()
		shutil.rmtree(self.tmp, ignore_errors=True)

	def read(self):
		with open(self.spec, encoding="utf-8") as f:
			return f.read()

	def test_edit_then_undo(self):
		before = self.read()
		r = self.st.edit("0/wb_key.py", "WBP_Key", [{"name": "KeyText", "props": {"Justification": "Right"}}])
		self.assertTrue(r["ok"], r)
		self.assertIn("'Justification': 'Right'", self.read())
		u = self.st.undo()
		self.assertTrue(u["ok"])
		self.assertEqual(self.read(), before)
		self.assertFalse(self.st.undo()["ok"])

	def test_undo_redo(self):
		before = self.read()
		self.st.edit("0/wb_key.py", "WBP_Key", [{"name": "KeyText", "props": {"Justification": "Right"}}])
		after = self.read()
		self.assertEqual(self.st.history_state()["redo"], None)
		self.assertTrue(self.st.undo()["ok"])
		self.assertEqual(self.read(), before)
		r = self.st.redo()
		self.assertTrue(r["ok"], r)
		self.assertEqual(self.read(), after)
		self.assertFalse(self.st.redo()["ok"])
		self.st.undo()
		# новая правка после отмены — «вернуть» больше нечего
		self.st.edit("0/wb_key.py", "WBP_Key", [{"name": "KeyText", "props": {"Justification": "Center"}}])
		self.assertIsNone(self.st.history_state()["redo"])
		self.assertFalse(self.st.redo()["ok"])

	def test_text_source_not_editable(self):
		shutil.copy(os.path.join(EX, "WBP_Key.copy.txt"), self.tmp)
		r = self.st.edit("0/WBP_Key.copy.txt", "WBP_Key", [{"name": "KeyText", "props": {"Justification": "Right"}}])
		self.assertFalse(r["ok"])

	def wait_done(self, q, timeout=60):
		end = time.time() + timeout
		events = []
		while time.time() < end:
			try:
				msg = q.get(timeout=1)
			except queue.Empty:
				continue
			if "agent" in msg:
				events.append(msg["agent"])
				if msg["agent"]["kind"] == "done":
					return events
		self.fail("ИИ не ответил: %r" % events)

	def test_agent_with_fake_claude(self):
		log = os.path.join(HERE, "fake_claude.log.json")
		if os.path.exists(log):
			os.remove(log)
		self.st.agent.paths["claude"] = os.path.join(HERE, "fake_claude.py")
		self.assertTrue(self.st.agent.status()["ok"])
		q = queue.Queue()
		self.st.clients.append(q)
		before = self.read()
		r = self.st.agent_send("Сделай рамку полупрозрачной", "0/wb_key.py", "WBP_Key",
							   {"name": "KeyText", "cls": "TextBlock", "props": {}, "slot": {}})
		self.assertTrue(r["ok"], r)
		ev = self.wait_done(q)
		kinds = [e["kind"] for e in ev]
		self.assertEqual(kinds[0], "user")
		self.assertIn("tool", kinds)
		self.assertIn("text", kinds)
		done = ev[-1]
		self.assertNotIn("error", done)
		self.assertTrue(done["undo"])
		self.assertEqual(done["files"], ["wb_key.py"])
		self.assertIn("A=0.500000))'", self.read())
		# скилл для Claude Code положен в рабочую папку
		self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".claude", "skills", "umg-widgets", "SKILL.md")))
		# второй запрос продолжает диалог
		self.st.agent_send("Ещё раз", "0/wb_key.py", "WBP_Key")
		self.wait_done(q)
		with open(log, encoding="utf-8") as f:
			calls = [json.loads(x) for x in f]
		self.assertNotIn("--resume", calls[0]["argv"])
		self.assertIn("--resume", calls[1]["argv"])
		self.assertIn("sess-1", calls[1]["argv"])
		self.assertIn("Правила:", calls[0]["prompt"])
		self.assertNotIn("Правила:", calls[1]["prompt"])
		self.assertIn("Выбран элемент: KeyText", calls[0]["prompt"])
		self.assertEqual(os.path.normcase(os.path.realpath(calls[0]["cwd"])), os.path.normcase(os.path.realpath(self.tmp)))
		# «Отменить» дважды — файл как до ИИ
		self.st.undo()
		self.st.undo()
		self.assertEqual(self.read(), before)
		os.remove(log)

	def test_agent_model_choice(self):
		log = os.path.join(HERE, "fake_claude.log.json")
		self.st.agent.paths["claude"] = os.path.join(HERE, "fake_claude.py")
		q = queue.Queue()
		self.st.clients.append(q)
		self.st.agent.configure(engine="claude", model="opus")
		self.st.agent_send("Раз", "0/wb_key.py", "WBP_Key")
		self.wait_done(q)
		self.st.agent.configure(model="sonnet")   # другая модель — новый диалог (без --resume)
		self.st.agent_send("Два", "0/wb_key.py", "WBP_Key")
		self.wait_done(q)
		with open(log, encoding="utf-8") as f:
			calls = [json.loads(x) for x in f]
		os.remove(log)
		self.assertEqual(calls[0]["argv"][calls[0]["argv"].index("--model") + 1], "opus")
		self.assertEqual(calls[1]["argv"][calls[1]["argv"].index("--model") + 1], "sonnet")
		self.assertNotIn("--resume", calls[1]["argv"])
		choices = self.st.agent.status()["choices"]
		self.assertIn({"engine": "codex", "model": None, "label": "Codex — по умолчанию"}, choices)

	def test_agent_codex(self):
		log = os.path.join(HERE, "fake_codex.log.json")
		if os.path.exists(log):
			os.remove(log)
		self.st.agent.configure(engine="codex", paths={"codex": os.path.join(HERE, "fake_codex.py")})
		st = self.st.agent.status()
		self.assertTrue(st["ok"], st)
		self.assertEqual(st["title"], "Codex")
		q = queue.Queue()
		self.st.clients.append(q)
		before = self.read()
		self.assertTrue(self.st.agent_send("Сделай текст прозрачнее", "0/wb_key.py", "WBP_Key")["ok"])
		ev = self.wait_done(q)
		done = ev[-1]
		self.assertNotIn("error", done, ev)
		self.assertEqual(done["files"], ["wb_key.py"])
		self.assertIn("A=0.250000))'", self.read())
		self.assertIn("Готово: альфа 0.25.", [e.get("text") for e in ev])
		self.assertIn("Команда", [e.get("name") for e in ev])
		self.st.agent_send("Ещё", "0/wb_key.py", "WBP_Key")
		self.wait_done(q)
		self.st.agent_send("СЛОМАЙ", "0/wb_key.py", "WBP_Key")
		bad = self.wait_done(q)[-1]
		with open(log, encoding="utf-8") as f:
			calls = [json.loads(x) for x in f]
		os.remove(log)
		a0, a1 = calls[0]["argv"], calls[1]["argv"]
		self.assertEqual(a0[:2], ["exec", "--json"])
		self.assertIn("workspace-write", a0)
		self.assertEqual(a0[-1], "-")
		self.assertNotIn("resume", a0)
		self.assertEqual(a1[a1.index("resume") + 1], "thr-7")
		self.assertIn("apply_patch", calls[0]["prompt"])
		self.assertIn("codex login", bad["error"])
		while self.st.undo()["ok"]:
			pass
		self.assertEqual(self.read(), before)

	def test_agent_error_is_reported(self):
		self.st.agent.paths["claude"] = os.path.join(HERE, "fake_claude.py")
		q = queue.Queue()
		self.st.clients.append(q)
		self.st.agent_send("СЛОМАЙ", "0/wb_key.py", "WBP_Key")
		done = self.wait_done(q)[-1]
		self.assertIn("login", done["error"])
		self.assertIn("войди", done["error"])
		self.assertFalse(done["undo"])
		log = os.path.join(HERE, "fake_claude.log.json")
		if os.path.exists(log):
			os.remove(log)

	def test_agent_missing(self):
		self.st.agent.paths["claude"] = os.path.join(self.tmp, "нет-такого-claude.exe")
		self.assertFalse(self.st.agent.status()["ok"])
		self.assertFalse(self.st.agent_send("привет", "0/wb_key.py", "WBP_Key")["ok"])


class Icon(unittest.TestCase):
	def test_ico_small_frames_are_bmp(self):
		# Проводник Windows не всегда читает маленькие PNG-кадры .ico — у exe был стандартный значок
		for p in (os.path.join(ROOT, "assets", "UMGStudio.ico"), os.path.join(ROOT, "studio", "umgstudio", "web", "favicon.ico")):
			with open(p, "rb") as f:
				d = f.read()
			_, kind, count = struct.unpack("<HHH", d[:6])
			self.assertEqual(kind, 1)
			sizes = []
			for i in range(count):
				w, h, _, _, planes, bpp, size, off = struct.unpack("<BBBBHHII", d[6 + 16 * i:22 + 16 * i])
				w = w or 256
				sizes.append(w)
				self.assertEqual((planes, bpp), (1, 32), p)
				if w < 256:
					self.assertEqual(struct.unpack("<I", d[off:off + 4])[0], 40, "%s: кадр %d — не BMP" % (p, w))
			for s in (16, 32, 48):
				self.assertIn(s, sizes)


if __name__ == "__main__":
	unittest.main()
