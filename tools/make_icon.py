"""
Значок программы из логотипа: python tools/make_icon.py [assets/logo.png] → assets/UMGStudio.ico + studio/umgstudio/web/favicon.ico

Размеры 16…128 — несжатые BMP (32 бит, с альфой): Проводник Windows маленькие PNG-кадры в .ico не всегда читает
и показывает у exe стандартный значок. 256 — PNG (так делает сама Windows). Нужен Pillow.
"""
import io
import os
import struct
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def bmp_entry(im):
	w, h = im.size
	px = im.tobytes("raw", "BGRA")
	rows = [px[y * w * 4:(y + 1) * w * 4] for y in range(h)]
	xor = b"".join(reversed(rows))                       # DIB — снизу вверх
	mask_row = ((w + 31) // 32) * 4
	mask = b"\0" * (mask_row * h)                         # прозрачность — в альфе, маска пустая
	header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
	return header + xor + mask


def make_ico(src, sizes=SIZES):
	logo = Image.open(src).convert("RGBA")
	frames = []
	for s in sizes:
		im = logo.resize((s, s), Image.LANCZOS)
		if s >= 256:
			buf = io.BytesIO()
			im.save(buf, "PNG", optimize=True)
			frames.append((s, buf.getvalue()))
		else:
			frames.append((s, bmp_entry(im)))
	out = struct.pack("<HHH", 0, 1, len(frames))
	offset = 6 + 16 * len(frames)
	body = b""
	for s, data in frames:
		out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset + len(body))
		body += data
	return out + body


def main():
	src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "logo.png")
	data = make_ico(src)
	for dst in (os.path.join(ROOT, "assets", "UMGStudio.ico"),):
		with open(dst, "wb") as f:
			f.write(data)
		print("записан", dst, len(data), "байт")
	# окно программы (WinForms) — тот же значок, без 256 (меньше файл)
	small = make_ico(src, (16, 20, 24, 32, 48, 64))
	dst = os.path.join(ROOT, "studio", "umgstudio", "web", "favicon.ico")
	with open(dst, "wb") as f:
		f.write(small)
	print("записан", dst, len(small), "байт")


if __name__ == "__main__":
	main()
