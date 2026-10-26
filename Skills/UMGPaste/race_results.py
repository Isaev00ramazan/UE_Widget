"""
Экран результатов гонки: WBP_ResultRow и WBP_RaceResults — текст для вставки в UMG (Ctrl+V).
Библиотека и правила — скилл .claude/skills/umg-widgets. Запуск: py race_results.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../.claude/skills/umg-widgets/scripts"))
import umg  # noqa: E402
from umg import *  # noqa: E402,F401,F403

umg.TEXT_NAMESPACE = "RaceResults"


def label(name, txt, color=MUTED, slot=None, var=False, ls=80):
	# подпись: SemiBold 14px, LS 80, UPPER, тень
	return text(name, txt, "SemiBold", 14, ls, color, upper=True, slot=slot, var=var)


def title(name, txt, color, slot=None, var=False, ls=120, px=16):
	# заголовок: SemiBold 16px, LS 120 по макету (в UE пользователь поднимает до ~210 — на глаз), UPPER, тень
	return text(name, txt, "SemiBold", px, ls, color, upper=True, slot=slot, var=var)


# ═════════════════════════ WBP_ResultRow ═════════════════════════
def tag(name, txt, color):
	return text(name, txt, "Bold", 12, 80, color, upper=True, shadow=False)


row = sizebox("RowRoot", 1160, 62, child=box("Overlay", "RowOverlay", [
	image("RowBg", 1160, 62, MAT.format("MI_Gradient_YouRow"), slot=bs(h="Fill", v="Fill"), var=True, collapsed=True),
	image("YouStripe", 3, 62, None, PLAYER, slot=bs(h="Left", v="Fill"), var=True, collapsed=True),
	image("Divider", 1108, 1, None, (0.514918, 0.830770, 0.830770, 0.08), slot=bs((24, 0, 0, 0), h="Left", v="Top"), var=True),
	box("HorizontalBox", "RowCols", slot=bs((24, 0, 28, 0), h="Fill", v="Fill"), children=[
		retainer("PosGlow", "MI_TextGlow_P1", False, slot=bs((-16, -16, -16, -16), v="Center"), var=True,
				 child=sizebox("PosBox", 104, 94, child=text(
					 "PosText", "1", "BoldItalic", 30, 0, MUTED, slot=bs((16, 0, 0, 0), h="Left", v="Center"), var=True))),
		box("HorizontalBox", "Racer", slot=bs(fill=True, v="Center"), children=[
			text("NameText", "Dmitry", "Medium", 22, 40, INK, upper=True, slot=bs(v="Center"), var=True),
			border("YouTag", PLAYER, (6, 4, 6, 3), tag("YouTagText", "You", ONACC),
				   slot=bs((12, 0, 0, 0), v="Center"), var=True, collapsed=True),
		]),
		sizebox("TimeCol", 210, slot=bs(v="Center"), child=box("Overlay", "TimeOverlay", [
			text("TimeText", "4:10.552", "SemiBoldItalic", 24, 0, INK, slot=bs(v="Center"), var=True),
			box("VerticalBox", "LiveBox", slot=bs(v="Center"), var=True, collapsed=True, children=[
				box("HorizontalBox", "LiveTop", [
					label("LiveStatus", "On track", RACE, var=True),
					label("LiveLap", "Lap 3/3", MUTED, slot=bs((10, 0, 0, 0)), var=True),
				]),
				image("LiveBar", 160, 4, MAT.format("MI_SegBar_Live"), slot=bs((0, 7, 0, 0)), var=True),
			]),
		])),
		sizebox("GapCol", 130, slot=bs(v="Center"),
				child=text("GapText", "+1.834", "SemiBoldItalic", 20, 0, MUTED, var=True)),
		sizebox("BestCol", 220, slot=bs(v="Center"), child=box("HorizontalBox", "BestBox", [
			text("BestText", "1:22.904", "SemiBoldItalic", 20, 0, MUTED, slot=bs(v="Center"), var=True),
			border("FastestTag", (0, 0, 0, 0), (6, 4, 6, 3), tag("FastestText", "Fastest", RACE),
				   slot=bs((10, 0, 0, 0), v="Center"), var=True, collapsed=True,
				   background=rounded(0, with_alpha(RACE, 0.6), 1)),
		])),
		sizebox("KillsCol", 64, slot=bs(v="Center"),
				child=text("KillsText", "2", "SemiBoldItalic", 22, 0, INK, just="Center", slot=bs(h="Center"), var=True)),
	]),
]))


# ═════════════════════════ WBP_RaceResults ═════════════════════════
def stat(i, r, c, lab, valname, val, unit=None):
	value = text(valname, val, "SemiBoldItalic", 28, 0, INK, slot=bs((0, 8, 0, 0)), var=True)
	if unit:
		# единица отдельным текстом (t-label после пробела, как в макете): своя настройка, число в коде — без неё.
		# Низ по низу + Bottom 3 — выравнивание по базовой линии (у 28px выносной элемент ниже, чем у 14px)
		value.slot = bs(v="Bottom")
		value = box("HorizontalBox", valname + "Box", slot=bs((0, 8, 0, 0)), children=[
			value,
			label(valname + "Unit", unit, slot=bs((4, 0, 0, 3), v="Bottom"), var=True),
		])
	return box("VerticalBox", "Stat%d" % i, slot={"Row": str(r), "Column": str(c)}, children=[
		label("StatLabel%d" % i, lab),
		value,
	])


def head_col(name, w, child):
	return sizebox(name, w, slot=bs(v="Center"), child=child)


FOOT_LINE = (0.514918, 0.830770, 0.830770, 0.10)

results = box("CanvasPanel", "ResultsRoot", [
	W("BackgroundBlur", "Blur", {"BlurStrength": "6.000000"}, cslot(0, 0, 0, 0, **FULL)),
	image("Dim", 1920, 1080, MAT.format("MI_RadialDim_Results"), slot=cslot(0, 0, 0, 0, **FULL)),

	box("VerticalBox", "Head", slot=cslot(160, 72, 0, 0, auto=True), children=[
		box("HorizontalBox", "HeadTitle", [
			image("FlagIcon", 22, 22, TEX.format("T_Ico_Flag"), RACE, slot=bs((0, 0, 10, 0), v="Center")),
			title("RaceComplete", "Race complete", INK, slot=bs(v="Center"), ls=208),
			image("HeadDot", 4, 4, None, FAINT, slot=bs((10, 0, 10, 0), v="Center"),
				  extra={"RenderTransform": "(Angle=45.000000)"}),
			title("TrackTitle", "Harbor Run · 3 laps", MUTED, slot=bs((2, 0, 0, 0), v="Center"), var=True, ls=140, px=18),
		]),
		box("HorizontalBox", "Place", slot=bs((0, 10, 0, 0)), children=[
			retainer("PlaceGlow", "MI_TextGlow_Place", True, slot=bs((-40, -40, -40, -40), v="Bottom"),
					 child=sizebox("PlaceBox", 141, 200, child=text(
						 "PlaceNum", "2", "BoldItalic", 150, -20, PLAYER, slot=bs((0, 0, 40, 0), h="Right", v="Center"),
						 var=True, shadow_off=(0, 2), shadow_a=0.6))),
			text("PlaceSuffix", "nd", "BoldItalic", 46, 0, PLAYER, upper=True, slot=bs((6, 1, 0, 0), v="Top"), var=True),
			box("VerticalBox", "PlaceMeta", slot=bs((25, 0, 0, 4), v="Bottom"), children=[
				title("PlaceLabel", "Place", MUTED, ls=208),
				text("PlaceOf", "of 8", "SemiBoldItalic", 34, 0, INK, slot=bs((0, 5, 0, 0)), var=True),
				box("HorizontalBox", "PlaceDelta", slot=bs((0, 3, 0, 0)), var=True, collapsed=True, children=[
					image("DeltaIcon", 12, 12, TEX.format("T_Ico_Up"), RACE, slot=bs(v="Center"), var=True),
					text("DeltaText", "1 on final lap", "SemiBoldItalic", 18, 118, RACE, upper=True,
						 slot=bs((6, 0, 0, 0), v="Center"), var=True),
				]),
			]),
		]),
	]),

	box("VerticalBox", "Close", slot=cslot(-160, 95, 380, 42, (1, 0), (1, 0), (1, 0), auto=True), var=True, children=[
		box("HorizontalBox", "CloseRow", [
			label("CloseLabel", "Race closes in", slot=bs((0, 0, 0, 2), fill=True, v="Bottom"), ls=120),
			text("CloseTime", "0:24", "SemiBoldItalic", 28, 0, INK, slot=bs(v="Bottom"), var=True),
		]),
		image("CloseBar", 380, 4, MAT.format("MI_SegBar_Close"), slot=bs((0, 7, 0, 0)), var=True),
	]),

	box("Overlay", "Table", slot=cslot(160, 296, 1160, 554), children=[
		image("TableBg", 1160, 554, MAT.format("MI_Panel_ResultsTable"), slot=bs(h="Fill", v="Fill")),
		box("VerticalBox", "TableBody", slot=bs(h="Fill", v="Fill"), children=[
			sizebox("TableHeadBox", h=44, child=box("HorizontalBox", "TableHead", slot=bs((24, 0, 28, 0)), children=[
				head_col("HeadPosCol", 72, label("HeadPos", "Pos", slot=bs(v="Center"))),
				label("HeadRacer", "Racer", slot=bs(fill=True, v="Center")),
				head_col("HeadTimeCol", 210, label("HeadTime", "Time", slot=bs(v="Center"))),
				head_col("HeadGapCol", 130, label("HeadGap", "Gap", slot=bs(v="Center"))),
				head_col("HeadBestCol", 220, label("HeadBest", "Best lap", slot=bs(v="Center"))),
				head_col("HeadKillsCol", 64, image("HeadKills", 18, 18, TEX.format("T_Ico_Kills"), MUTED,
												   slot=bs(h="Center", v="Center"))),
			])),
			box("VerticalBox", "RowContainer", slot=bs((0, 4, 0, 10)), var=True, children=[]),
		]),
	]),

	box("Overlay", "YourRace", slot=cslot(-160, 296, 380, 266, (1, 0), (1, 0), (1, 0)), children=[
		image("YourRaceBg", 380, 266, MAT.format("MI_Panel_YourRace"), slot=bs(h="Fill", v="Fill")),
		box("VerticalBox", "YourRaceBody", slot=bs(h="Fill", v="Fill"), children=[
			sizebox("YourRaceHeadBox", h=30, child=title("YourRaceTitle", "Your race", MUTED, slot=bs((20, 1, 0, 0), v="Center"), ls=220)),
			box("UniformGridPanel", "StatsGrid", slot=bs((24, 20, 22, 22)),
				props={"SlotPadding": mar(0, 0, 16, 22)}, children=[
					stat(1, 0, 0, "Total time", "StatTime", "4:12.386"),
					stat(2, 0, 1, "Best lap", "StatBestLap", "1:22.871"),
					stat(3, 1, 0, "Top speed", "StatSpeed", "118", unit="km/h"),
					stat(4, 1, 1, "Kills", "StatKills", "3"),
					stat(5, 2, 0, "Damage", "StatDamage", "8,450"),
					stat(6, 2, 1, "Wrecked", "StatWrecked", "1"),
				]),
		]),
	]),

	box("Overlay", "Foot", slot=cslot(160, -62, 160, 56, (0, 1), (1, 1), (0, 1)), children=[
		image("FootBg", 1600, 56, MAT.format("MI_Gradient_Foot"), slot=bs(h="Fill", v="Fill")),
		image("FootLine", 1600, 1, None, FOOT_LINE, slot=bs(h="Fill", v="Top")),
		box("HorizontalBox", "FootActions", slot=bs((24, 0, 24, 0), v="Center"), children=[
			border("KeySpace", INK, (10, 0, 10, 0), slot=bs(v="Center"),
				   background=rounded(3),
				   child=sizebox("KeySpaceBox", h=26, minw=44, child=text(
					   "KeySpaceText", "Space", "SemiBold", 13, 60, ONACC, shadow=False, slot=bs(h="Center", v="Center")))),
			label("ContinueText", "Continue", INK, slot=bs((10, 0, 0, 0), v="Center")),
		]),
	]),
])

here = os.path.dirname(os.path.abspath(__file__))
save(row, "WBP_ResultRow", here)
save(results, "WBP_RaceResults", here)
