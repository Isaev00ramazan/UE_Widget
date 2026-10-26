"""
Библиотека генерации текста для вставки виджетов в UMG Designer (Ctrl+V), UE 5.7.
Каноническая копия — UMG Studio (studio/umgstudio/umg.py); API совпадает с umg.py скилла umg-widgets.

Формат сверен с реальной копией из редактора (WBP_Weapons, 2026-10-08): каждый виджет — отдельный
верхнеуровневый Begin Object; слоты детей — подобъекты РОДИТЕЛЯ (сначала объявление, потом блок с
Parent/Content и свойствами слота) + Slots(i); у ребёнка строки Slot= НЕТ. У корня выделения — WidgetSlotPair
(у корня пустого виджета — только WidgetName).

Использование — в файле-спецификации рядом с ассетом:
	import sys; sys.path.insert(0, r"<проект>/.claude/skills/umg-widgets/scripts")
	from umg import *
	root = box("CanvasPanel", "Root", [...])
	save(root, "WBP_Name", "<папка>")

CLI:
	py umg.py color 47C8FF [0.55]     — sRGB HEX → линейный (R=…,G=…,B=…,A=…)
	py umg.py linear 0.0887 0.7913 0.5647  — линейный → sRGB HEX
"""
import os
import sys

# ─── проект ───
WIDGET_DIR = "/Game/UI/HUD/Widgets"
FONT = "/Script/Engine.Font'/Game/UI/HUD/Fonts/F_HUD.F_HUD'"
MAT = "/Script/Engine.MaterialInstanceConstant'/Game/UI/HUD/Materials/{0}.{0}'"
TEX = "/Script/Engine.Texture2D'/Game/UI/HUD/Textures/{0}.{0}'"
# Шрифт: FontDPIPreset=Standard (96 DPI) → размер UE = px дизайна × 0.75 (14px → 10.5, 46px → 34.5)
PT = 0.75
# Начертания F_HUD — ровно эти строки (без пробелов). «Medium Italic» нет.
FACES = {"Medium", "SemiBold", "Bold", "SemiBoldItalic", "BoldItalic"}
TEXT_NAMESPACE = "Widgets"

# ─── цвета дизайн-системы (линейные) ───
INK = (0.896269, 0.921582, 0.887923, 1)
MUTED = (0.391573, 0.514918, 0.527115, 1)
FAINT = (0.254152, 0.361307, 0.376262, 1)
RACE = (0.088656, 0.791298, 0.564712, 1)
COMBAT = (0.913099, 0.558340, 0.147027, 1)
PLAYER = (1.0, 0.262251, 0.010330, 1)
HP = (1.0, 0.084376, 0.054480, 1)
ONACC = (0.002125, 0.006995, 0.009134, 1)
WHITE = (1, 1, 1, 1)

SLOT_OF = {
	"CanvasPanel": "CanvasPanelSlot", "VerticalBox": "VerticalBoxSlot", "HorizontalBox": "HorizontalBoxSlot",
	"Overlay": "OverlaySlot", "SizeBox": "SizeBoxSlot", "Border": "BorderSlot", "ScaleBox": "ScaleBoxSlot",
	"BackgroundBlur": "BackgroundBlurSlot", "UniformGridPanel": "UniformGridSlot", "GridPanel": "GridSlot",
	"WrapBox": "WrapBoxSlot", "ScrollBox": "ScrollBoxSlot", "SafeZone": "SafeZoneSlot",
	"RetainerBox": "PanelSlot", "InvalidationBox": "PanelSlot", "NamedSlot": "PanelSlot",
	"Button": "ButtonSlot",
}


# ─── цвет ───
def srgb_to_linear(c):
	return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
	return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_lin(h, a=1.0):
	"""'47C8FF' → линейный кортеж (как пикер UE в режиме sRGB)."""
	h = h.lstrip("#")
	r, g, b = (srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
	if len(h) == 8:
		a = int(h[6:8], 16) / 255
	return (r, g, b, a)


def lin_hex(r, g, b):
	return "".join("%02X" % round(max(0, min(1, linear_to_srgb(x))) * 255) for x in (r, g, b))


def with_alpha(c, a):
	return (c[0], c[1], c[2], a)


# ─── форматирование ───
def f6(x):
	return "%.6f" % x


def col(c):
	return "(R=%.6f,G=%.6f,B=%.6f,A=%.6f)" % tuple(c)


def scol(c):
	return "(SpecifiedColor=%s)" % col(c)


def mar(l=0, t=0, r=0, b=0):
	return "(Left=%.6f,Top=%.6f,Right=%.6f,Bottom=%.6f)" % (l, t, r, b)


def v2(x, y):
	return "(X=%.6f,Y=%.6f)" % (x, y)


def q(s):
	return '"%s"' % s


# ─── узел дерева ───
class W:
	"""cls — имя класса UMG ('TextBlock') или полный путь BP-класса ('/Game/UI/HUD/Widgets/WBP_Key.WBP_Key_C')."""

	def __init__(self, cls, name, props=None, slot=None, children=None, var=False, collapsed=False, label=None):
		self.cls, self.name = cls, name
		self.props = dict(props or {})
		self.slot = dict(slot or {})
		self.children = list(children or [])
		self.var = var
		self.collapsed = collapsed
		self.label = label

	@property
	def class_path(self):
		return self.cls if self.cls.startswith("/") else "/Script/UMG." + self.cls

	@property
	def slot_class(self):
		short = self.cls.rsplit(".", 1)[-1]
		return SLOT_OF.get(short)


# ─── фабрики виджетов ───
def text(name, txt, face="SemiBold", px=14, ls=0, color=INK, upper=False, shadow=True, just=None, slot=None,
		 var=False, collapsed=False, shadow_off=(0, 1), shadow_a=0.7, extra=None):
	"""px — размер из дизайна (переводится ×PT). ls — Letter Spacing в тысячных em (CSS 0.08em → 80)."""
	assert face in FACES, "нет начертания %r в F_HUD: %s" % (face, sorted(FACES))
	font = 'FontObject="%s",TypefaceFontName="%s",Size=%s' % (FONT, face, f6(px * PT))
	if ls:
		font += ",LetterSpacing=%d" % ls
	p = {
		"Text": 'NSLOCTEXT("%s", "%s", "%s")' % (TEXT_NAMESPACE, name, txt),
		"ColorAndOpacity": scol(color),
		"Font": "(%s)" % font,
	}
	if shadow:
		p["ShadowOffset"] = v2(*shadow_off)
		p["ShadowColorAndOpacity"] = col((0, 0, 0, shadow_a))
	if just:
		p["Justification"] = just
	if upper:
		p["TextTransformPolicy"] = "ToUpper"
	if extra:
		p.update(extra)
	return W("TextBlock", name, p, slot, var=var, collapsed=collapsed)


def image(name, w, h, res=None, tint=None, slot=None, var=False, collapsed=False, extra=None):
	"""res — MAT.format('MI_X') / TEX.format('T_X') / None (белый квадрат). tint — Brush Tint (линейный)."""
	parts = []
	if tint:
		parts.append("TintColor=%s" % scol(tint))
	parts.append("ImageType=FullColor")
	parts.append("ImageSize=%s" % v2(w, h))
	if res:
		parts.append('ResourceObject="%s"' % res)
	p = {"Brush": "(%s)" % ",".join(parts)}
	if extra:
		p.update(extra)
	return W("Image", name, p, slot, var=var, collapsed=collapsed)


def sizebox(name, w=None, h=None, minw=None, minh=None, child=None, slot=None, var=False, collapsed=False):
	p = {}
	vals = (("WidthOverride", w), ("HeightOverride", h), ("MinDesiredWidth", minw), ("MinDesiredHeight", minh))
	for k, v in vals:
		if v is not None:
			p[k] = f6(v)
	for k, v in vals:
		if v is not None:
			p["bOverride_" + k] = "True"
	return W("SizeBox", name, p, slot, [child] if child else [], var=var, collapsed=collapsed)


def box(cls, name, children=None, slot=None, var=False, collapsed=False, props=None):
	"""Любая панель: CanvasPanel, VerticalBox, HorizontalBox, Overlay, UniformGridPanel, ScaleBox…"""
	return W(cls, name, props, slot, children, var=var, collapsed=collapsed)


def spacer(name, x=0, y=0, slot=None):
	return W("Spacer", name, {"Size": v2(x, y)} if (x or y) else {}, slot)


def border(name, brush_color, pad, child, slot=None, var=False, collapsed=False, background=None):
	"""Padding Border'а синхронизируется со слотом ребёнка — пишем в оба одинаково."""
	p = {}
	if background:
		p["Background"] = background
	p["BrushColor"] = col(brush_color)
	p["Padding"] = mar(*pad)
	child.slot.setdefault("Padding", mar(*pad))
	return W("Border", name, p, slot, [child], var=var, collapsed=collapsed)


def rounded(radius=0, outline=None, outline_w=0):
	"""Background для Border: Rounded Box (радиус, обводка — линейный цвет)."""
	s = "CornerRadii=(X={0},Y={0},Z={0},W={0})".format(f6(radius))
	if outline is not None:
		s += ",Color=%s,Width=%s" % (scol(outline), f6(outline_w))
	return "(DrawAs=RoundedBox,OutlineSettings=(%s,RoundingType=FixedRadius))" % s


def retainer(name, mat, retain, child, slot=None, var=False, tex_param="Texture"):
	"""Retainer Box с эффект-материалом (параметр текстуры в материале — 'Texture', см. M_UI_TextGlow)."""
	p = {
		"bRetainRender": "True" if retain else "False",
		"EffectMaterial": q(MAT.format(mat)),
		"TextureParameter": q(tex_param),
	}
	return W("RetainerBox", name, p, slot, [child], var=var)


def user_widget(name, wbp, props=None, slot=None, var=False, collapsed=False, folder=WIDGET_DIR):
	"""Экземпляр своего WBP (например WBP_Key). props — его Instance Editable переменные как есть."""
	return W("%s/%s.%s_C" % (folder, wbp, wbp), name, props, slot, var=var, collapsed=collapsed)


# ─── слоты ───
def cslot(l, t, r, b, amin=(0, 0), amax=(0, 0), align=(0, 0), auto=False, z=0):
	"""Canvas: при точечном якоре l,t — Position, r,b — Size; при растянутом — отступы от краёв."""
	s = {"LayoutData": "(Offsets=%s,Anchors=(Minimum=%s,Maximum=%s),Alignment=%s)" % (
		mar(l, t, r, b), v2(*amin), v2(*amax), v2(*align))}
	if auto:
		s["bAutoSize"] = "True"
	if z:
		s["ZOrder"] = str(z)
	return s


FULL = dict(amin=(0, 0), amax=(1, 1))


def bs(pad=None, h=None, v=None, fill=False, fill_value=None):
	"""Слот Box/Overlay/SizeBox/Border: pad=(L,T,R,B), h/v = Left|Center|Right|Fill / Top|Center|Bottom|Fill."""
	s = {}
	if fill:
		s["Size"] = "(SizeRule=Fill)" if fill_value is None else "(SizeRule=Fill,Value=%s)" % f6(fill_value)
	if pad:
		s["Padding"] = mar(*pad)
	if h:
		s["HorizontalAlignment"] = "HAlign_" + h
	if v:
		s["VerticalAlignment"] = "VAlign_" + v
	return s


def grid(row, column, h=None, v=None):
	s = {"Row": str(row), "Column": str(column)}
	s.update(bs(h=h, v=v))
	return s


# ─── экспорт ───
def export(root, wbp, folder=WIDGET_DIR):
	base = "%s/%s.%s:WidgetTree" % (folder, wbp, wbp)
	out = []
	seen = set()

	def emit(w):
		assert w.name not in seen, "имя повторяется: %s (вставка молча переименует — BindWidget не найдёт)" % w.name
		seen.add(w.name)
		sc = w.slot_class
		assert sc or not w.children, "неизвестный класс слота для %s — добавь в SLOT_OF" % w.cls
		L = ['Begin Object Class=%s Name="%s" ExportPath="%s\'%s.%s\'"' % (w.class_path, w.name, w.class_path, base, w.name)]
		names = ["%s_%d" % (sc, i) for i in range(len(w.children))]
		for sn in names:
			L.append('   Begin Object Class=/Script/UMG.%s Name="%s" ExportPath="/Script/UMG.%s\'%s.%s.%s\'"' % (
				sc, sn, sc, base, w.name, sn))
			L.append("   End Object")
		for sn, c in zip(names, w.children):
			L.append('   Begin Object Name="%s" ExportPath="/Script/UMG.%s\'%s.%s.%s\'"' % (sn, sc, base, w.name, sn))
			for k, v in c.slot.items():
				L.append("      %s=%s" % (k, v))
			L.append('      Parent="%s\'%s\'"' % (w.class_path, w.name))
			L.append('      Content="%s\'%s\'"' % (c.class_path, c.name))
			L.append("   End Object")
		for k, v in w.props.items():
			L.append("   %s=%s" % (k, v))
		for i, sn in enumerate(names):
			L.append('   Slots(%d)="/Script/UMG.%s\'%s\'"' % (i, sc, sn))
		if w.var:
			L.append("   bIsVariable=True")
		if w.collapsed:
			L.append("   Visibility=Collapsed")
		if w.children:
			L.append("   bExpandedInDesigner=True")
		if w.label:
			L.append('   DisplayLabel="%s"' % w.label)
		L.append("End Object")
		out.append("\n".join(L))
		if w is root:
			# корень вставки: без свойств слота — встаёт корнем пустого виджета или в выделенную панель
			out.append('Begin Object Class=/Script/UMGEditor.WidgetSlotPair Name="WidgetSlotPair_0" '
					   'ExportPath="/Script/UMGEditor.WidgetSlotPair\'/Engine/Transient.WidgetSlotPair_0\'"\n'
					   '   WidgetName="%s"\nEnd Object' % w.name)
		for c in w.children:
			emit(c)

	emit(root)
	return "\n".join(out) + "\n"


# UMG Studio: каждый save() попадает в SAVED (превью берёт дерево отсюда); WRITE=False — без записи файла
WRITE = True
SAVED = []
STATES = []


def save(root, wbp, out_dir, folder=WIDGET_DIR, suffix=""):
	path = os.path.join(out_dir, "%s%s.paste.txt" % (wbp, suffix))
	text = export(root, wbp, folder)
	SAVED.append({"wbp": wbp + suffix, "folder": folder, "path": path, "text": text})
	if not WRITE:
		return path
	with open(path, "w", encoding="utf-8", newline="\r\n") as f:
		f.write(text)
	print("saved", path)
	return path


def state(wbp, name, show=(), hide=(), texts=None):
	"""Состояние для превью (в текст вставки не попадает): show/hide — имена элементов, texts — {имя: текст}."""
	STATES.append({"wbp": wbp, "name": name, "show": list(show), "hide": list(hide), "texts": dict(texts or {})})


if __name__ == "__main__":
	a = sys.argv[1:]
	if len(a) >= 2 and a[0] == "color":
		c = hex_lin(a[1], float(a[2]) if len(a) > 2 else 1.0)
		print(col(c))
	elif len(a) >= 4 and a[0] == "linear":
		print(lin_hex(*map(float, a[1:4])))
	else:
		print(__doc__)
