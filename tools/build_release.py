"""
Сборка релиза UMG Studio: python tools/build_release.py v0.2.0

	dist/UMGStudio-<версия>-win64.zip        — программа (UMGStudio.exe без установки Python) + плагин + примеры
	dist/UMGStudio-Plugin-<версия>-UE5.8.zip — только плагин редактора (папка UMGStudio → Plugins/ проекта)
	dist/RELEASE_NOTES.md                    — текст релиза

Нужны: pip install pyinstaller pywebview. Собирается под ту ОС, где запущено (релиз — на Windows в GitHub Actions).
"""
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")


def pyinstaller():
	sep = os.pathsep
	pkg = os.path.join(ROOT, "studio", "umgstudio")
	cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "UMGStudio", "--windowed",
		   "--distpath", os.path.join(BUILD, "dist"), "--workpath", os.path.join(BUILD, "work"),
		   "--specpath", BUILD, "--paths", os.path.join(ROOT, "studio"),
		   "--add-data", os.path.join(pkg, "web") + sep + "umgstudio/web",
		   "--add-data", os.path.join(pkg, "umg.py") + sep + "umgstudio",
		   "--hidden-import", "umgstudio.runner",
		   "--icon", os.path.join(ROOT, "assets", "UMGStudio.ico")]
	# стандартные модули, которые могут понадобиться спецификациям экранов
	for mod in ("json", "math", "re", "collections", "itertools", "functools", "copy", "textwrap", "colorsys"):
		cmd += ["--hidden-import", mod]
	try:
		import webview  # noqa: F401
		cmd += ["--collect-all", "webview"]
	except ImportError:
		print("pywebview не установлен — сборка без окна (откроется браузер)")
	cmd.append(os.path.join(ROOT, "tools", "launcher.py"))
	subprocess.run(cmd, check=True)
	return os.path.join(BUILD, "dist", "UMGStudio")


def copy(src, dst, ignore=None):
	src, dst = os.path.join(ROOT, src), os.path.join(dst, src)
	if os.path.isdir(src):
		shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)
	else:
		os.makedirs(os.path.dirname(dst), exist_ok=True)
		shutil.copy2(src, dst)


def zipdir(folder, zip_path, arc_root):
	with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
		for base, _, files in os.walk(folder):
			for f in files:
				p = os.path.join(base, f)
				z.write(p, os.path.join(arc_root, os.path.relpath(p, folder)))


def main():
	version = sys.argv[1] if len(sys.argv) > 1 else "dev"
	shutil.rmtree(DIST, ignore_errors=True)
	os.makedirs(DIST)
	app = pyinstaller()

	junk = shutil.ignore_patterns("__pycache__", "*.pyc", "Binaries", "Intermediate")
	for item in ("design", "examples", "Materials", "docs", "ue", "Skills/ue_setup_hud.py", "umgstudio.example.json",
				 "studio/umgstudio/umg.py"):
		copy(item, app, junk)
	# umg.py рядом с exe — для спецификаций вне программы (py экран.py) и для чтения
	shutil.move(os.path.join(app, "studio", "umgstudio", "umg.py"), os.path.join(app, "umg.py"))
	shutil.rmtree(os.path.join(app, "studio"), ignore_errors=True)
	with open(os.path.join(ROOT, "tools", "README.release.txt"), encoding="utf-8") as f:
		readme = f.read().replace("{version}", version)
	with open(os.path.join(app, "README.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
		f.write(readme)
	with open(os.path.join(app, "VERSION"), "w", encoding="utf-8") as f:
		f.write(version + "\n")

	app_zip = os.path.join(DIST, "UMGStudio-%s-win64.zip" % version)
	zipdir(app, app_zip, "UMGStudio")
	plugin_zip = os.path.join(DIST, "UMGStudio-Plugin-%s-UE5.8.zip" % version)
	zipdir(os.path.join(ROOT, "ue", "UMGStudio"), plugin_zip, "UMGStudio")

	with open(os.path.join(ROOT, "docs", "RELEASE_NOTES.md"), encoding="utf-8") as f:
		notes = f.read().replace("{version}", version)
	with open(os.path.join(DIST, "RELEASE_NOTES.md"), "w", encoding="utf-8") as f:
		f.write(notes)
	for p in (app_zip, plugin_zip):
		print("%s  %.1f MB" % (os.path.basename(p), os.path.getsize(p) / 1e6))
	print("app folder:", app)


if __name__ == "__main__":
	main()
