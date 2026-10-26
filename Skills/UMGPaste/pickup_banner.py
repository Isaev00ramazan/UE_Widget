"""
Плашка подбора «Шеврон»: WBP_PickupBanner — текст для вставки в UMG (Ctrl+V). Родитель — UPickupBannerWidget (C++),
WBP создаёт скрипт HUD_UE57_Kit/Scripts/ue_setup_pickup_banner.py. Дизайн — канвас «Shield Pickup HUD», доска
«Баннер подбора», вариант 3. Библиотека и правила — скилл .claude/skills/umg-widgets. Запуск: py pickup_banner.py

Слово, подпись, иконку и цвет ставит код из DA_PickupFeedback_*; в вёрстке — образец SHIELD · 5 SEC.
Плашка по центру сверху, 48 px от края, ширина по тексту. Подложка Plate шире строки на скос: 52 · tan 20° ≈ 19 px,
поэтому отступы строки 40 = 30 (дизайн) + 10 (половина скоса).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../.claude/skills/umg-widgets/scripts"))
import umg  # noqa: E402
from umg import *  # noqa: E402,F401,F403

umg.TEXT_NAMESPACE = "PickupBanner"

ICE = hex_lin("CFF3FF")
H = 52

root = box("CanvasPanel", "PBRoot", [
	box("Overlay", "Banner", var=True, slot=cslot(0, 48, 0, 0, amin=(0.5, 0), amax=(0.5, 0), align=(0.5, 0), auto=True),
		children=[
			# подложка-шеврон: M_UI_Chevron, размер и цвет пишет код в свой MID
			image("Plate", 300, H, MAT.format("MI_Chevron"), var=True, slot=bs(h="Fill", v="Fill")),
			sizebox("RowBox", h=H, slot=bs(h="Center", v="Fill"), child=
				box("HorizontalBox", "Row", slot=bs((40, 0, 40, 0), v="Center"), children=[
					# Tint белый: цвет даёт код через Color and Opacity — иначе цвета перемножатся
					image("Icon", 26, 26, TEX.format("T_Ico_PickupShield"), None, var=True, slot=bs(v="Center")),
					# BoldItalic 22.5 (30px), LS 40 — подобрать на глаз
					text("Title", "SHIELD", "BoldItalic", 30, 40, INK, shadow=False, var=True,
						 slot=bs((12, 0, 0, 0), v="Center")),
					# SemiBold 12 (16px), LS 80 — цвет ставит код
					text("Value", "5 SEC", "SemiBold", 16, 80, ICE, shadow=False, var=True,
						 slot=bs((12, 0, 0, 0), v="Center")),
				])),
		]),
])

save(root, "WBP_PickupBanner", os.path.dirname(os.path.abspath(__file__)))
