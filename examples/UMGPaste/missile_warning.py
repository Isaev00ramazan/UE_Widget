"""
Сенсор ракет: WBP_MissileWarning — текст для вставки в UMG (Ctrl+V). Родитель — UMissileWarningWidget (C++),
WBP создаёт скрипт HUD_UE57_Kit/Scripts/ue_setup_missile_warning.py. Дизайн — Claude Design «Missile Warning HUD»
(лист «Спецификация для UMG»). Библиотека и правила — скилл .claude/skills/umg-widgets. Запуск: py missile_warning.py

Дуги и подписи времени создаёт код (по одной на ракету) — в вёрстке только их образцы (ArcTemplate, LabelTemplate,
скрыты). Кольцо код ставит на лодку на экране; в вёрстке оно стоит примерно там, где лодка при обычной камере.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../.claude/skills/umg-widgets/scripts"))
import umg  # noqa: E402
from umg import *  # noqa: E402,F401,F403

umg.TEXT_NAMESPACE = "MissileWarning"

RING = 640          # сторона кольца, px (радиус обода 264 + 56 под подписи)
BADGE_TOP = 510     # верх бейджа: 74 px выше нижнего края обода (320 + 264 - 74)

root = box("CanvasPanel", "MWRoot", [
	sizebox("RingRoot", RING, RING, var=True,
			slot=cslot(960, 700, RING, RING, align=(0.5, 0.5)),
			child=box("CanvasPanel", "RingCanvas", var=True, slot=bs(h="Fill", v="Fill"), children=[
				# обод и засечки
				image("RingTrack", RING, RING, MAT.format("MI_WarnRing"), slot=cslot(0, 0, 0, 0, **FULL)),
				# образец дуги: код копирует его материал для каждой ракеты
				image("ArcTemplate", RING, RING, MAT.format("MI_WarnArc"), var=True, collapsed=True,
					  slot=cslot(0, 0, 0, 0, **FULL)),
				# образец подписи времени: SemiBoldItalic 20px (t-num-sm), тень (0,1) A0.7 — цвет ставит код
				text("LabelTemplate", "2.1s", "SemiBoldItalic", 20, 0, HP, var=True, collapsed=True, just="Center",
					 slot=cslot(320, 16, 0, 0, align=(0.5, 0.5), auto=True)),
				# бейдж по ближайшей ракете: стекло со скосами 7 px, рамка 1.5 px и свечение 14 px цвета уровня
				box("Overlay", "BadgeBox", slot=cslot(0, BADGE_TOP, 0, 0, amin=(0.5, 0), amax=(0.5, 0), align=(0.5, 0),
													auto=True, z=10), children=[
					image("BadgeBg", 140, 30, MAT.format("MI_Panel_Warn"), var=True, slot=bs(h="Fill", v="Fill")),
					box("HorizontalBox", "BadgeRow", slot=bs((12, 6, 12, 6), v="Center"), children=[
						image("BadgeIcon", 16, 16, TEX.format("T_Ico_Warn"), COMBAT, var=True, slot=bs(v="Center")),
						text("BadgeText", "Missile", "SemiBold", 14, 80, COMBAT, upper=True, var=True,
							 slot=bs((8, 0, 0, 0), v="Center")),
						text("BadgeCount", "×2", "SemiBoldItalic", 20, 0, INK, var=True, collapsed=True,
							 slot=bs((8, 0, 0, 0), v="Center")),
					]),
				]),
			])),
])

save(root, "WBP_MissileWarning", os.path.dirname(os.path.abspath(__file__)))
