"""
Новый проект: мост сообщает папку проекта → программа берёт её; список WBP; «забрать по пути» → copy.txt + .py;
спецификация из дерева UE даёт то же дерево; настройки Content-путей доходят до спецификаций.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "studio"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mock_ue  # noqa: E402
from umgstudio import codegen, config, diff, server, t3d  # noqa: E402

EX = os.path.join(ROOT, "examples", "UMGPaste")


class Codegen(unittest.TestCase):
	def test_round_trip_all_texts(self):
		tmp = tempfile.mkdtemp()
		try:
			st = server.Studio([tmp])
			for f in sorted(os.listdir(EX)):
				if not f.endswith(".txt"):
					continue
				with open(os.path.join(EX, f), encoding="utf-8-sig") as fh:
					text = fh.read()
				wbp = f.split(".")[0]
				p = os.path.join(tmp, codegen.snake(wbp) + "_t.py")
				with open(p, "w", encoding="utf-8") as fh:
					fh.write(codegen.spec_from_text(text, wbp, "/Game/Test", parent="/Script/Game.Base", design=[800, 600]))
				r = st.run_spec(p)
				self.assertTrue(r["ok"], r.get("error"))
				w = r["widgets"][0]
				self.assertEqual(diff.diff(w["roots"][0], t3d.parse(text)[0]), [], f)
				self.assertEqual(w["asset"], "/Game/Test/" + wbp)
				self.assertEqual(w["parent"], "/Script/Game.Base")
		finally:
			shutil.rmtree(tmp, ignore_errors=True)

	def test_snake(self):
		self.assertEqual(codegen.snake("WBP_RaceResults"), "race_results")
		self.assertEqual(codegen.snake("WBP_HUD"), "hud")


class NewProject(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.proj = os.path.join(self.tmp, "TestUE")
		os.makedirs(self.proj)
		self.httpd = mock_ue.start(0)
		mock_ue.STORE.clear()
		mock_ue.PROJECT_DIR = self.proj
		with open(os.path.join(EX, "WBP_Key.copy.txt"), encoding="utf-8") as f:
			mock_ue.STORE["/Game/Test/WBP_Key"] = f.read()
		mock_ue.META["/Game/Test/WBP_Key"] = {"parent": "/Script/TestUE.KeyBase", "designSizeMode": "Custom", "designSize": [120, 40]}
		self.settings_file = os.path.join(self.tmp, "umgstudio.json")
		self.patch = mock.patch.object(config, "settings_path", lambda: self.settings_file)
		self.patch.start()
		cfg = config.resolve({"ue": "http://127.0.0.1:%d" % self.httpd.server_address[1]})
		cfg["settings"] = {"ue": cfg["ue"]}
		self.st = server.Studio.from_config(cfg)

	def tearDown(self):
		self.patch.stop()
		self.httpd.shutdown()
		mock_ue.PROJECT_DIR = None
		shutil.rmtree(self.tmp, ignore_errors=True)

	def test_adopt_list_fetch_push(self):
		self.assertTrue(self.st.adopt_project(self.proj))
		self.assertEqual(self.st.work_dir, os.path.join(self.proj, "UMGStudio"))
		with open(self.settings_file, encoding="utf-8") as f:
			self.assertEqual(json.load(f)["project"], self.proj)
		self.assertFalse(self.st.adopt_project("/other"))   # заданный проект не перезаписывается

		lst = self.st.ue_list()
		self.assertEqual([w["name"] for w in lst["widgets"]], ["WBP_Key"])
		self.assertIsNone(lst["widgets"][0]["spec"])

		r = self.st.ue_fetch("/Game/Test/WBP_Key")
		self.assertTrue(r["ok"], r)
		self.assertTrue(r["created"])
		self.assertTrue(os.path.isfile(os.path.join(self.proj, "UMGStudio", "key.py")))
		self.assertTrue(os.path.isfile(os.path.join(self.proj, "UMGStudio", "WBP_Key.copy.txt")))
		self.assertTrue(os.path.isfile(os.path.join(self.proj, "UMGStudio", "umg.py")))
		with open(r["path"], encoding="utf-8") as f:
			code = f.read()
		self.assertIn("parent='/Script/TestUE.KeyBase'", code)
		self.assertIn("design=(120, 40)", code)

		self.assertFalse(self.st.ue_fetch("/Game/Test/WBP_Key")["created"])   # второй раз — та же спецификация
		self.assertEqual(self.st.ue_list()["widgets"][0]["spec"], r["src"])
		self.assertEqual(self.st.diff(r["src"], "WBP_Key")["items"], [])

		push = self.st.ue_push(r["src"], "WBP_Key")
		self.assertTrue(push["ok"], push)
		self.assertEqual(push["received"]["asset"], "/Game/Test/WBP_Key")
		self.assertEqual(push["received"]["parent"], "/Script/TestUE.KeyBase")
		self.assertEqual(push["received"]["designSize"], [120.0, 40.0])

	def test_compare_and_adopt_from_ue(self):
		# спецификация забрана из UE, потом в UE поменяли значения — программа видит это и переносит в .py
		self.st.adopt_project(self.proj)
		r = self.st.ue_fetch("/Game/Test/WBP_Key")
		self.assertEqual(self.st.ue_compare(r["src"], "WBP_Key")["items"], [])
		text = mock_ue.STORE["/Game/Test/WBP_Key"]
		text = text.replace("Size=10.500000", "Size=15.000000").replace("   bIsVariable=True\n", "", 1)
		mock_ue.STORE["/Game/Test/WBP_Key"] = text
		d = self.st.ue_compare(r["src"], "WBP_Key")
		self.assertTrue(d["ok"], d)
		self.assertGreaterEqual(d["adoptable"], 2)
		self.assertEqual(d["structural"], 0)
		a = self.st.ue_adopt(r["src"], "WBP_Key")
		self.assertTrue(a["ok"], a)
		self.assertEqual(self.st.ue_compare(r["src"], "WBP_Key")["items"], [])
		with open(r["path"], encoding="utf-8") as f:
			self.assertIn("Size=15.000000", f.read())
		self.assertTrue(self.st.undo()["ok"])
		self.assertNotEqual(self.st.ue_compare(r["src"], "WBP_Key")["items"], [])

	def test_texture_from_ue(self):
		png = b"\x89PNG\r\n\x1a\nfake"
		mock_ue.TEXTURES["/Game/Art/T_Mage"] = png
		self.assertEqual(self.st.texture_bytes("T_Mage", "/Game/Art/T_Mage"), png)
		self.assertIsNone(self.st.texture_bytes("T_None", "/Game/Art/T_None"))

	def test_incomplete_tree_refused(self):
		text = mock_ue.STORE["/Game/Test/WBP_Key"]
		# как старый плагин: только корень, без объектов детей
		mock_ue.STORE["/Game/Test/WBP_Root"] = text.split("Begin Object Class=/Script/UMG.Overlay")[0]
		r = self.st.ue_fetch("/Game/Test/WBP_Root")
		self.assertFalse(r["ok"])
		self.assertIn("неполное дерево", r["error"])

	def test_regenerate_keeps_backup(self):
		self.st.adopt_project(self.proj)
		r = self.st.ue_fetch("/Game/Test/WBP_Key")
		with open(r["path"], "a", encoding="utf-8") as f:
			f.write("# правка\n")
		r2 = self.st.ue_fetch("/Game/Test/WBP_Key", regenerate=True)
		self.assertTrue(r2["ok"] and r2["created"])
		self.assertEqual(r2["path"], r["path"])
		self.assertTrue(os.path.isfile(r["path"] + ".bak"))
		with open(r["path"], encoding="utf-8") as f:
			self.assertNotIn("# правка", f.read())
		self.assertTrue(any(s["generated"] for s in self.st.sources() if s["kind"] == "spec"))

	def test_fetch_bad_path(self):
		self.assertFalse(self.st.ue_fetch("WBP_Key")["ok"])

	def test_content_paths_reach_specs(self):
		s = {"project": self.proj, "widgets": "/Game/MyUI", "font": "/Game/Fonts/F_Main"}
		self.st.apply(s)
		os.makedirs(self.st.work_dir, exist_ok=True)
		spec = os.path.join(self.st.work_dir, "t.py")
		with open(spec, "w", encoding="utf-8") as f:
			f.write("import os\nfrom umg import *\nsave(text('T', 'x'), 'WBP_T', os.path.dirname(os.path.abspath(__file__)))\n")
		r = self.st.run_spec(spec)
		self.assertTrue(r["ok"], r.get("error"))
		self.assertEqual(r["widgets"][0]["asset"], "/Game/MyUI/WBP_T")
		self.assertIn("/Game/Fonts/F_Main.F_Main", r["widgets"][0]["text"])


class Settings(unittest.TestCase):
	def test_resolve_defaults_from_project(self):
		c = config.resolve({"project": "/p"})
		self.assertEqual(c["work_dir"], os.path.join("/p", "UMGStudio"))
		self.assertEqual(c["assets"], os.path.join("/p", "Saved", "UMGStudio", "hud_assets.json"))
		self.assertEqual(c["content"]["widgets"], "/Game/UI/HUD/Widgets")
		c = config.resolve({})
		self.assertIn(os.path.join(config.REPO, "examples", "UMGPaste"), c["specs"])


if __name__ == "__main__":
	unittest.main()
