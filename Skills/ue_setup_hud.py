"""
Racing HUD — импорт в Unreal Engine 5.7.

Что делает:
  1. Импортирует PNG из ../Textures в /Game/UI/HUD/Textures и ставит UI-настройки.
  2. Импортирует TTF из ../Fonts в /Game/UI/HUD/Fonts (Font Face на каждое начертание)
     и собирает Composite Font F_HUD: Barlow Condensed + Fira Sans Condensed для кириллицы.
  3. Создаёт UI-материалы из ../Materials/*.hlsl (Custom-нода + параметры) в /Game/UI/HUD/Materials.

Как запустить:
  - Включите плагин «Python Editor Script Plugin» (Edit > Plugins), перезапустите редактор.
  - Tools > Execute Python Script... > выберите этот файл.
    Или в консоли Output Log (режим Python): exec(open(r"<путь>/ue_setup_hud.py", encoding="utf-8").read())
  - Повторный запуск обновляет ассеты, дубликатов не создаёт.

Скрипт не проверен в живом редакторе: каждый шаг обёрнут в try, ошибки пишутся в Output Log
с пометкой [HUD]. Если какой-то шаг не прошёл — сделайте его руками по README.md.

Правки под MadWater (2026-10-02, сверено с исходниками UE 5.7):
  - цвета подаются в Custom-ноду с выхода RGBA Vector Parameter: основной выход у него RGB без альфы,
    а HLSL берёт .a (прозрачность фона, выключенных сегментов, пика) — иначе материалы не компилируются;
  - Texture Object Parameter получает заглушку WhiteSquareTexture: без текстуры по умолчанию материал не компилируется;
  - существующие материалы НЕ удаляются при повторном запуске (на них будут ссылаться Material Instance —
    удаление оставило бы их без родителя). Пересобрать: REBUILD_MATERIALS = True;
  - шрифт: FFontData.FontFaceAsset и FCompositeSubFont.CharacterRanges в 5.7 — UPROPERTY() без Edit,
    из Python их не задать — F_HUD собирается руками (README, «Если шрифт не собрался»).
"""

import os
import unreal

DEST = "/Game/UI/HUD"
REBUILD_MATERIALS = False   # True — удалить и пересоздать материалы (сломает родителя у существующих MI)
# Пересобрать ГРАФ этих материалов на месте: ассет тот же, Material Instance сохраняют родителя и свои значения
UPDATE_IN_PLACE = {"M_UI_SegBar", "M_UI_Panel"}
PLACEHOLDER_TEXTURE = "/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture"
try:
    KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:  # запуск через exec(): __file__ нет — укажите путь к распакованному набору
    KIT = r"C:/HUD_UE57_Kit"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log("[HUD] " + msg)


def warn(msg):
    unreal.log_warning("[HUD] " + msg)


def import_files(files, dest):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    asset_tools.import_asset_tasks(tasks)
    out = []
    for t in tasks:
        out += list(t.get_editor_property("imported_object_paths"))
    return out


# ---------------------------------------------------------------- 1. текстуры
def setup_textures():
    folder = os.path.join(KIT, "Textures")
    files = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith(".png")]
    paths = import_files(files, DEST + "/Textures")
    for p in paths:
        tex = unreal.load_asset(p)
        if not isinstance(tex, unreal.Texture2D):
            continue
        try:
            tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)  # = UserInterface2D (RGBA)
            tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
            tex.set_editor_property("never_stream", True)
            tex.set_editor_property("srgb", True)
            eal.save_loaded_asset(tex)
        except Exception as e:  # noqa
            warn("texture settings failed for %s: %s" % (p, e))
    log("textures: %d" % len(paths))


# ---------------------------------------------------------------- 2. шрифты
FACES = ["Medium", "SemiBold", "Bold", "SemiBoldItalic", "BoldItalic"]


def setup_fonts():
    folder = os.path.join(KIT, "Fonts")
    files = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith(".ttf")]
    paths = import_files(files, DEST + "/Fonts")
    faces = {}
    # импорт TTF может создать Font Face и/или Font — собираем все Font Face из папки
    for p in list(paths) + list(eal.list_assets(DEST + "/Fonts", recursive=False)):
        a = unreal.load_asset(p)
        if isinstance(a, unreal.FontFace):
            faces[a.get_name()] = a
    log("font faces: %s" % ", ".join(sorted(faces)))

    try:
        font_path = DEST + "/Fonts/F_HUD"
        font = unreal.load_asset(font_path) if eal.does_asset_exist(font_path) else \
            asset_tools.create_asset("F_HUD", DEST + "/Fonts", unreal.Font, unreal.FontFactory())
        font.set_editor_property("font_cache_type", unreal.FontCacheType.RUNTIME)

        def typeface(prefix):
            entries = []
            for f in FACES:
                face = faces.get("%s_%s" % (prefix, f))
                if face is None:
                    continue
                fd = unreal.FontData()
                fd.set_editor_property("font_face_asset", face)
                te = unreal.TypefaceEntry()
                te.set_editor_property("name", f)
                te.set_editor_property("font", fd)
                entries.append(te)
            tf = unreal.Typeface()
            tf.set_editor_property("fonts", entries)
            return tf

        cf = font.get_editor_property("composite_font")
        cf.set_editor_property("default_typeface", typeface("BarlowCondensed"))

        # кириллица U+0400..U+04FF -> Fira Sans Condensed
        sub = unreal.CompositeSubFont()
        sub.set_editor_property("typeface", typeface("FiraSansCondensed"))
        rng = unreal.Int32Range()
        lo = unreal.Int32RangeBound(); lo.set_editor_property("type", unreal.RangeBoundTypes.INCLUSIVE); lo.set_editor_property("value", 0x0400)
        hi = unreal.Int32RangeBound(); hi.set_editor_property("type", unreal.RangeBoundTypes.INCLUSIVE); hi.set_editor_property("value", 0x04FF)
        rng.set_editor_property("lower_bound", lo)
        rng.set_editor_property("upper_bound", hi)
        sub.set_editor_property("character_ranges", [rng])
        cf.set_editor_property("sub_typefaces", [sub])

        font.set_editor_property("composite_font", cf)
        eal.save_loaded_asset(font)
        log("composite font F_HUD ready")
    except Exception as e:  # noqa
        warn("composite font step failed, build F_HUD by hand (README, step 3): %s" % e)


# ---------------------------------------------------------------- 3. материалы
# (имя входа, тип, значение по умолчанию) — типы: uv | scalar | vector | texobj | time
MATERIALS = {
    "M_UI_Panel": [
        ("UV", "uv", None), ("Size", "vector", (344, 62, 0, 0)), ("Cut", "scalar", 12),
        ("Corners", "vector", (1, 0, 1, 0)), ("Circle", "vector", (0, 0, 0, 0)),
        ("Fill", "vector", (0.0044, 0.0144, 0.0194, 0.74)), ("HeadH", "scalar", 0),
        ("HeadColor", "vector", (0.1878, 0.402, 0.4342, 0.2)), ("Edge", "vector", (0.5149, 0.8308, 0.8308, 0.2)),
        ("Zone", "vector", (0.9131, 0.5583, 0.147, 1.0)),
        ("StrokeW", "scalar", 1), ("StrokeColor", "vector", (1.0, 0.0844, 0.0545, 0.0)),
        ("InnerGlowPx", "scalar", 0), ("InnerGlowColor", "vector", (0.527, 0.262, 1.0, 0.0)),
    ],
    "M_UI_Ring": [
        ("UV", "uv", None), ("Size", "scalar", 110), ("RingW", "scalar", 4), ("Pad", "scalar", 7),
        ("Progress", "scalar", 1.0), ("FillColor", "vector", (0.9131, 0.5583, 0.147, 1.0)),
        ("TrackColor", "vector", (0.5776, 0.8308, 0.8308, 0.14)), ("GlowColor", "vector", (0.9131, 0.5583, 0.147, 0.6)),
    ],
    "M_UI_SegBar": [
        ("UV", "uv", None), ("Size", "vector", (430, 24, 0, 0)), ("Segments", "scalar", 22), ("Gap", "scalar", 4),
        ("SkewTan", "scalar", 0.364), ("Fill", "scalar", 0.64), ("Ramp", "scalar", 0.58), ("Continuous", "scalar", 0),
        ("OnColor", "vector", (0.0887, 0.7913, 0.5647, 1.0)), ("OffColor", "vector", (0.5776, 0.8308, 0.8308, 0.14)),
        ("PeakColor", "vector", (0.8963, 0.9216, 0.8879, 1.0)), ("GlowPad", "scalar", 0),
        ("GlowColor", "vector", (0.0887, 0.7913, 0.5647, 0.55)), ("GlowFalloff", "scalar", 3),
        ("Trail", "scalar", 0), ("TrailColor", "vector", (0.8963, 0.9216, 0.8879, 0.0)),
        ("OnColorEnd", "vector", (1.0, 0.0844, 0.0545, 0.0)),
        ("OffStroke", "vector", (0.527, 0.262, 1.0, 0.0)), ("OffStrokeW", "scalar", 1),
        # восполнение (UHUDHullWidget / UHUDDriveWidget, 2026-10-21) — выключено по умолчанию
        ("GainFrom", "scalar", -1), ("GainColor", "vector", (0.107023, 1.0, 0.337164, 0.0)),
        ("GainHeadColor", "vector", (0.822786, 1.0, 0.887923, 0.0)),
        ("GapFlash", "vector", (0, 0, 0, 0)), ("GapFlashColor", "vector", (1.0, 1.0, 1.0, 1.0)),
    ],
    "M_UI_Radar": [
        ("UV", "uv", None), ("Size", "scalar", 250), ("RadarR", "scalar", 116), ("Map", "texobj", None),
        ("Player", "vector", (0.5, 0.5, 0, 0)), ("Yaw", "scalar", 0), ("Zoom", "scalar", 0.12), ("Time", "time", None),
        ("SweepPeriod", "scalar", 5),
        ("BgCenter", "vector", (0.006, 0.0273, 0.0342, 0.78)), ("BgEdge", "vector", (0.0024, 0.008, 0.011, 0.9)),
        ("TrackColor", "vector", (0.3048, 0.6445, 0.6445, 0.26)), ("LineColor", "vector", (0.5149, 0.8308, 0.8308, 0.2)),
        ("LineW", "scalar", 0.75), ("TickColor", "vector", (0.3916, 0.5149, 0.5271, 0.55)), ("TickW", "scalar", 1.45),
        ("SweepColor", "vector", (0.0887, 0.7913, 0.5647, 0.22)), ("BezelColor", "vector", (0.0024, 0.008, 0.011, 0.72)),
        ("OuterAlpha", "scalar", 0.12),
    ],
    "M_UI_Marker": [
        ("UV", "uv", None), ("Size", "scalar", 44), ("Shape", "scalar", 2), ("Radius", "scalar", 12.3),
        ("FillColor", "vector", (1.0, 0.2623, 0.0103, 1.0)), ("OutlineColor", "vector", (0.0018, 0.008, 0.0103, 1.0)),
        ("OutlineW", "scalar", 1.45), ("GlowColor", "vector", (1.0, 0.2623, 0.0103, 0.8)), ("GlowPx", "scalar", 6),
    ],
    "M_UI_RadialGlow": [
        ("UV", "uv", None), ("Size", "scalar", 44), ("Core", "scalar", 6), ("Color", "vector", (1.0, 0.2623, 0.0103, 0.8)),
    ],
    "M_UI_Glow": [
        ("UV", "uv", None), ("Size", "vector", (328, 42, 0, 0)), ("Pad", "scalar", 14), ("Falloff", "scalar", 3),
        ("Color", "vector", (0.063, 0.5776, 1.0, 0.75)), ("Fill", "scalar", 0.76), ("Segments", "scalar", 4),
        ("Gap", "scalar", 2), ("SkewTan", "scalar", 0.364), ("Ramp", "scalar", 0), ("Continuous", "scalar", 1),
    ],
    "M_UI_Pips": [
        ("UV", "uv", None), ("Size", "vector", (39, 16, 0, 0)), ("PipSize", "vector", (4, 16, 0, 0)),
        ("Count", "scalar", 6), ("Gap", "scalar", 3),
        ("Round", "scalar", 0), ("Mask", "texobj", None), ("Fill", "scalar", 0.75),
        ("OnColor", "vector", (0.8388, 0.7157, 0.4793, 1.0)), ("OffColor", "vector", (0.5776, 0.8308, 0.8308, 0.14)),
        ("EdgeColor", "vector", (0.9131, 0.5583, 0.147, 0.0)),
    ],
    "M_UI_Gradient": [
        ("UV", "uv", None), ("C0", "vector", (1.0, 0.2623, 0.0103, 0.30)), ("P1", "scalar", 0.55),
        ("C1", "vector", (1.0, 0.2623, 0.0103, 0.10)), ("P2", "scalar", 1.0),
        ("C2", "vector", (1.0, 0.2623, 0.0103, 0.03)), ("C3", "vector", (1.0, 0.2623, 0.0103, 0.03)),
    ],
    "M_UI_RadialDim": [
        ("UV", "uv", None), ("Center", "vector", (0.40, 0.45, 0, 0)), ("Radius", "vector", (1.2, 0.9, 0, 0)),
        ("Inner", "vector", (0.0018, 0.006, 0.008, 0.42)), ("Outer", "vector", (0.0012, 0.0037, 0.0048, 0.86)),
    ],
    "M_UI_TextGlow": [
        ("UV", "uv", None), ("Tex", "texobj_retainer", None), ("Size", "vector", (200, 220, 0, 0)),
        ("Radius", "scalar", 40), ("GlowColor", "vector", (1.0, 0.2623, 0.0103, 0.35)),
    ],
    "M_UI_FisheyePulse": [
        ("UV", "uv", None), ("Tex", "texobj_retainer", None), ("Screen", "vector", (1920, 1080, 0, 0)),
        ("K", "scalar", 0), ("Exponent", "scalar", 1), ("CenterY", "scalar", 0),
    ],
    # Сенсор ракет (WBP_MissileWarning, 2026-10-19): обод с засечками и дуга угрозы
    "M_UI_WarnRing": [
        ("UV", "uv", None), ("Size", "scalar", 640), ("Radius", "scalar", 264), ("RingW", "scalar", 2),
        ("TrackColor", "vector", (0.5776, 0.8308, 0.8308, 0.14)),
        ("TickCount", "scalar", 12), ("TickLen", "scalar", 10), ("TickW", "scalar", 2),
        ("TickColor", "vector", (0.5149, 0.8308, 0.8308, 0.2)),
    ],
    "M_UI_WarnArc": [
        ("UV", "uv", None), ("Size", "scalar", 640), ("Radius", "scalar", 264), ("ArcDeg", "scalar", 18),
        ("Width", "scalar", 6), ("ChevW", "scalar", 18), ("ChevH", "scalar", 12), ("GlowPx", "scalar", 8),
        ("Color", "vector", (0.9131, 0.5583, 0.147, 1.0)), ("Opacity", "scalar", 1.0),
    ],
    # Плашка подбора «Шеврон» (WBP_PickupBanner, 2026-10-21)
    "M_UI_Chevron": [
        ("UV", "uv", None), ("Size", "vector", (300, 52, 0, 0)), ("SkewTan", "scalar", 0.364),
        ("Color", "vector", (0.62396, 0.896269, 1.0, 1.0)), ("FillAlpha", "scalar", 0.16), ("BorderW", "scalar", 4),
        ("StripeAlpha", "scalar", 0.10), ("StripePeriod", "scalar", 24), ("StripeSpeed", "scalar", 80),
        ("Time", "time", None),
    ],
}


def read_code(name):
    # Комментарии (там кириллица) вырезаем: не-ASCII в коде Custom-ноды компилятор шейдеров может не принять.
    # В .hlsl они остаются — для чтения.
    with open(os.path.join(KIT, "Materials", name + ".hlsl"), encoding="utf-8") as f:
        lines = [l.split("//", 1)[0].rstrip() for l in f.read().splitlines()]
    code = "\n".join(l for l in lines if l.strip())
    if any(ord(ch) > 127 for ch in code):
        warn("%s: в коде остались не-ASCII символы" % name)
    return code


def make_material(name, inputs):
    path = "%s/Materials/%s" % (DEST, name)
    mat = None
    if eal.does_asset_exist(path):
        if name in UPDATE_IN_PLACE:
            mat = unreal.load_asset(path)
            mel.delete_all_material_expressions(mat)
            log("material %s: граф пересобирается на месте" % name)
        elif not REBUILD_MATERIALS:
            log("material %s exists — skipped (REBUILD_MATERIALS = False)" % name)
            return
        else:
            eal.delete_asset(path)
    if mat is None:
        mat = asset_tools.create_asset(name, DEST + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_UI)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)

    custom = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, -200, 0)
    custom.set_editor_property("code", read_code(name))
    custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    custom.set_editor_property("description", name)
    ci = []
    for n, _, _ in inputs:
        c = unreal.CustomInput()
        c.set_editor_property("input_name", n)
        ci.append(c)
    custom.set_editor_property("inputs", ci)

    y = -400
    for n, kind, val in inputs:
        y += 90
        if kind == "uv":
            e = mel.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -600, y)
        elif kind == "time":
            e = mel.create_material_expression(mat, unreal.MaterialExpressionTime, -600, y)
        elif kind == "scalar":
            e = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -600, y)
            e.set_editor_property("parameter_name", n)
            e.set_editor_property("default_value", float(val))
        elif kind == "vector":
            e = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -600, y)
            e.set_editor_property("parameter_name", n)
            e.set_editor_property("default_value", unreal.LinearColor(*[float(v) for v in val]))
        elif kind in ("texobj", "texobj_retainer"):
            e = mel.create_material_expression(mat, unreal.MaterialExpressionTextureObjectParameter, -600, y)
            e.set_editor_property("parameter_name", "Texture" if kind == "texobj_retainer" else n)
            placeholder = unreal.load_asset(PLACEHOLDER_TEXTURE)
            if placeholder:
                e.set_editor_property("texture", placeholder)
        else:
            continue
        # У Vector Parameter основной выход — RGB без альфы; HLSL читает .a — берём RGBA
        mel.connect_material_expressions(e, "RGBA" if kind == "vector" else "", custom, n)

    rgb = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, 100, -60)
    for ch, on in (("r", True), ("g", True), ("b", True), ("a", False)):
        rgb.set_editor_property(ch, on)
    alpha = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, 100, 60)
    for ch, on in (("r", False), ("g", False), ("b", False), ("a", True)):
        alpha.set_editor_property(ch, on)
    mel.connect_material_expressions(custom, "", rgb, "")
    mel.connect_material_expressions(custom, "", alpha, "")
    mel.connect_material_property(rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)  # Final Color в UI-домене
    mel.connect_material_property(alpha, "", unreal.MaterialProperty.MP_OPACITY)

    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    log("material %s ready" % name)


def setup_materials():
    for name, inputs in MATERIALS.items():
        try:
            make_material(name, inputs)
        except Exception as e:  # noqa
            warn("material %s failed, build by hand (README, step 4): %s" % (name, e))


# ---------------------------------------------------------------- run
for step in (setup_textures, setup_fonts, setup_materials):
    try:
        step()
    except Exception as e:  # noqa
        warn("%s failed: %s" % (step.__name__, e))
log("done — see Content Browser: %s" % DEST)
