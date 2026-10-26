"""
Тесты ядра UMG Studio: py -m unittest discover -s tests

- спецификации из examples/ дают тот же текст вставки байт в байт, что лежит рядом (эталон — как было в проекте);
- все тексты вставки и копии из UE разбираются в дерево IR, имена уникальны, у каждого ребёнка есть слот;
- значения свойств разбираются в структуры.
"""
import glob
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDIO = os.path.join(ROOT, "studio")
EX = os.path.join(ROOT, "examples", "UMGPaste")
sys.path.insert(0, STUDIO)

from umgstudio import t3d  # noqa: E402
from umgstudio.design import Design, parse_card  # noqa: E402
from umgstudio.server import read_masters  # noqa: E402


def run_spec(path):
	env = dict(os.environ, PYTHONPATH=STUDIO, PYTHONIOENCODING="utf-8")
	p = subprocess.run([sys.executable, "-m", "umgstudio.runner", path], capture_output=True, env=env, cwd=EX)
	return json.loads(p.stdout.decode("utf-8"))


class Golden(unittest.TestCase):
	def test_specs_match_paste_files(self):
		specs = sorted(glob.glob(os.path.join(EX, "*.py")))
		self.assertTrue(specs)
		for spec in specs:
			res = run_spec(spec)
			self.assertTrue(res["ok"], res.get("error"))
			for w in res["widgets"]:
				with open(os.path.join(EX, w["wbp"] + ".paste.txt"), newline="", encoding="utf-8") as f:
					ref = f.read().replace("\r\n", "\n")
				self.assertEqual(ref, w["text"], "%s → %s" % (os.path.basename(spec), w["wbp"]))

	def test_runner_does_not_write(self):
		before = {p: os.path.getmtime(p) for p in glob.glob(os.path.join(EX, "*.paste.txt"))}
		run_spec(os.path.join(EX, "pickup_banner.py"))
		after = {p: os.path.getmtime(p) for p in before}
		self.assertEqual(before, after)


class Parse(unittest.TestCase):
	def test_all_texts_parse(self):
		files = glob.glob(os.path.join(EX, "*.txt"))
		self.assertTrue(files)
		for f in files:
			with open(f, encoding="utf-8-sig") as fh:
				roots = t3d.parse(fh.read())
			self.assertEqual(len(roots), 1, f)
			names = [n["name"] for n, _ in t3d.walk(roots[0])]
			self.assertEqual(len(names), len(set(names)), f)
			for n, depth in t3d.walk(roots[0]):
				self.assertFalse(n.get("missing"), "%s: нет объекта %s" % (f, n["name"]))
				if depth:
					self.assertIn("cls", n["slot"], n["name"])

	def test_values(self):
		v = t3d.parse_value
		self.assertEqual(v("(Left=1.500000,Bottom=-2.000000)"), {"Left": 1.5, "Bottom": -2.0})
		self.assertEqual(v('NSLOCTEXT("ns", "k", "Harbor Run · 3 laps")'), {"$text": "Harbor Run · 3 laps", "ns": "ns", "key": "k"})
		self.assertEqual(v('NSLOCTEXT("a", "b", "say \\"hi\\", (ok)")')["$text"], 'say "hi", (ok)')
		self.assertEqual(v("True"), True)
		self.assertEqual(v("HAlign_Center"), "HAlign_Center")
		self.assertEqual(v("(1,2,3)"), [1, 2, 3])
		b = v("(TintColor=(SpecifiedColor=(R=1.000000,G=0.5,B=0,A=1)),ResourceObject=\"/Script/Engine.Texture2D'/Game/T.T'\")")
		self.assertEqual(b["TintColor"]["SpecifiedColor"]["G"], 0.5)
		self.assertEqual(b["ResourceObject"], "/Script/Engine.Texture2D'/Game/T.T'")

	def test_copy_from_ue_has_labels_and_vars(self):
		with open(os.path.join(EX, "WBP_Drive.copy.txt"), encoding="utf-8-sig") as f:
			root = t3d.parse(f.read())[0]
		by = {n["name"]: n for n, _ in t3d.walk(root)}
		self.assertTrue(by["SpeedValue"]["props"]["bIsVariable"])
		self.assertEqual(by["SpeedValue"]["props"]["Font"]["TypefaceFontName"], "BoldItalic")


class Materials(unittest.TestCase):
	def test_masters_from_setup_script(self):
		m = read_masters(os.path.join(ROOT, "Skills", "ue_setup_hud.py"))
		self.assertEqual(m["M_UI_Panel"]["Cut"], 12)
		self.assertEqual(m["M_UI_SegBar"]["OnColor"], [0.0887, 0.7913, 0.5647, 1.0])
		self.assertNotIn("UV", m["M_UI_Panel"])


class Window(unittest.TestCase):
	@unittest.skipUnless(sys.platform == "win32", "потоки NTFS — только Windows")
	def test_unblock_removes_zone_identifier(self):
		import tempfile
		from umgstudio import window
		d = tempfile.mkdtemp()
		dll = os.path.join(d, "x.dll")
		with open(dll, "wb") as f:
			f.write(b"MZ")
		with open(dll + ":Zone.Identifier", "w") as f:
			f.write("[ZoneTransfer]\nZoneId=3\n")
		self.assertTrue(os.path.exists(dll + ":Zone.Identifier"))
		self.assertEqual(window.unblock(d), 1)
		self.assertFalse(os.path.exists(dll + ":Zone.Identifier"))

	def test_unblock_noop_elsewhere(self):
		from umgstudio import window
		if sys.platform != "win32":
			self.assertEqual(window.unblock(ROOT), 0)


class DesignSnapshot(unittest.TestCase):
	def test_tokens_and_components(self):
		d = Design(os.path.join(ROOT, "design", "RacingHud"))
		self.assertTrue(d.ok)
		css = d.tokens_css()
		self.assertIn("--glass: rgba(14,32,38,0.74);", css)
		self.assertIn(".t-speed {", css)
		names = [c["name"] for c in d.components()]
		self.assertIn("RaceResults", names)
		page = d.page("RaceResults")
		self.assertIn("/design/components/bundle.css", page)

	def test_card(self):
		self.assertEqual(parse_card(' group="Screen" width=1280 height=720 page subtitle="a b" '),
						 {"group": "Screen", "width": 1280, "height": 720, "page": True, "subtitle": "a b"})


if __name__ == "__main__":
	unittest.main()
