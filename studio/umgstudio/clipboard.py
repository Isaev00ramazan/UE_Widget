"""Текст в системный буфер обмена без зависимостей: Windows — WinAPI через ctypes, иначе pbcopy / xclip."""
import subprocess
import sys


def copy(text):
	if sys.platform == "win32":
		return _win32(text)
	for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
		try:
			subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)
			return True
		except (OSError, subprocess.SubprocessError):
			continue
	return False


def _win32(text):
	import ctypes
	from ctypes import wintypes

	CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
	k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
	k32.GlobalAlloc.restype = wintypes.HGLOBAL
	k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
	k32.GlobalLock.restype = wintypes.LPVOID
	k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
	k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
	u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
	u32.SetClipboardData.restype = wintypes.HANDLE

	data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-16-le") + b"\0\0"
	if not u32.OpenClipboard(None):
		return False
	try:
		u32.EmptyClipboard()
		h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
		ptr = k32.GlobalLock(h)
		ctypes.memmove(ptr, data, len(data))
		k32.GlobalUnlock(h)
		return bool(u32.SetClipboardData(CF_UNICODETEXT, h))
	finally:
		u32.CloseClipboard()
