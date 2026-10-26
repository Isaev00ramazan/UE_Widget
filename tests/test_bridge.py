"""
Связь программы с редактором через имитацию плагина (tests/mock_ue.py): «В UE» → «Забрать из UE» → дифф пустой;
правка в «UE» видна в диффе. Плюс разбор пути ассета и параметров размера превью.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "studio"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mock_ue  # noqa: E402
from umgstudio import server, t3d, diff, ue_bridge  # noqa: E402

EX = os.path.join(ROOT, "examples", "UMGPaste")


class Bridge(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.httpd = mock_ue.start(0)
		cls.url = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
		cls.tmp = tempfile.mkdtemp()
		for f in ("race_results.py", "WBP_Drive.paste.txt", "WBP_Drive.copy.txt"):
			shutil.copy(os.path.join(EX, f), cls.tmp)
		cls.studio = server.Studio([cls.tmp], ue_url=cls.url)

	@classmethod
	def tearDownClass(cls):
		cls.httpd.shutdown()
		shutil.rmtree(cls.tmp, ignore_errors=True)

	def test_round_trip(self):
		r = self.studio.ue_push("0/race_results.py", "WBP_RaceResults")
		self.assertTrue(r["ok"], r)
		self.assertEqual(r["root"], "ResultsRoot")
		self.assertEqual(r["received"]["asset"], "/Game/UI/HUD/Widgets/WBP_RaceResults")
		self.assertFalse(self.studio.ue_push("0/race_results.py", "WBP_RaceResults")["created"])
		p = self.studio.ue_pull("0/race_results.py", "WBP_RaceResults")
		self.assertTrue(p["ok"], p)
		self.assertTrue(os.path.isfile(os.path.join(self.tmp, "WBP_RaceResults.copy.txt")))
		d = self.studio.diff("0/race_results.py", "WBP_RaceResults")
		self.assertEqual(d["items"], [])

	def test_push_from_text_source_uses_export_path(self):
		r = self.studio.ue_push("0/WBP_Drive.paste.txt", "WBP_Drive")
		self.assertEqual(r["received"]["asset"], "/Game/UI/HUD/Widgets/WBP_Drive")

	def test_diff_finds_hand_edits(self):
		d = self.studio.diff("0/WBP_Drive.paste.txt", "WBP_Drive")
		kinds = {(i["kind"], i["name"]) for i in d["items"]}
		self.assertIn(("removed", "NitroPctBox"), kinds)
		self.assertIn(("parent", "NitroPct"), kinds)

	def test_offline(self):
		r = ue_bridge.call("http://127.0.0.1:9", "/umgstudio/ping", timeout=0.5)
		self.assertFalse(r["ok"])
		self.assertTrue(r["offline"])


class Helpers(unittest.TestCase):
	def test_design_options(self):
		self.assertEqual(ue_bridge.design_options((1920, 1080)), {"designSizeMode": "Custom", "designSize": [1920.0, 1080.0]})
		self.assertEqual(ue_bridge.design_options("desired"), {"designSizeMode": "Desired"})
		self.assertEqual(ue_bridge.design_options(None), {})

	def test_diff_ignores_noise(self):
		with open(os.path.join(EX, "WBP_Key.copy.txt"), encoding="utf-8") as f:
			text = f.read()
		a = t3d.parse(text)[0]
		b = t3d.parse(text.replace('"[BDFDEF4AA260B17D185886F12809987A]"', '"Other"').replace('DisplayLabel="KeyText"', ""))[0]
		self.assertEqual(diff.diff(a, b), [])


if __name__ == "__main__":
	unittest.main()
