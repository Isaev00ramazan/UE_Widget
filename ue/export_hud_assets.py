"""
UMG Studio — выгрузка UI-ассетов проекта для превью (запуск в редакторе UE 5.7).

Что делает (только читает проект, ничего в нём не меняет):
  1. Все Material Instance в /Game/UI: родитель, мастер и значения scalar / vector / texture-параметров.
  2. Все Texture2D в /Game/UI → PNG (иконки T_Ico_*, T_Wpn_*, T_Skill_* …).
  3. Список ассетов /Game/UI (путь и класс) — чтобы видеть, что уже заведено.

Результат: <Проект>/Saved/UMGStudio/hud_assets.json и <Проект>/Saved/UMGStudio/Textures/*.png.
В umgstudio.json укажите: "assets": ".../Saved/UMGStudio/hud_assets.json", "textures": [".../Saved/UMGStudio/Textures"].

Запуск: Tools → Execute Python Script… → этот файл (нужен плагин Python Editor Script Plugin).
Каждый шаг в try: ошибки пишутся в Output Log с пометкой [UMGStudio], остальное продолжается.
"""
import json
import os

import unreal

ROOT = "/Game/UI"
OUT = os.path.join(unreal.Paths.project_saved_dir(), "UMGStudio")
TEX_OUT = os.path.join(OUT, "Textures")

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary


def log(msg):
    unreal.log("[UMGStudio] " + msg)


def warn(msg):
    unreal.log_warning("[UMGStudio] " + msg)


def class_name(data):
    try:
        return str(data.asset_class_path.asset_name)
    except AttributeError:  # старые версии
        return str(data.asset_class)


def list_assets():
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    return reg.get_assets_by_path(ROOT, recursive=True)


def material_params(mi):
    params = {}
    for name in mel.get_scalar_parameter_names(mi):
        params[str(name)] = mel.get_material_instance_scalar_parameter_value(mi, name)
    for name in mel.get_vector_parameter_names(mi):
        c = mel.get_material_instance_vector_parameter_value(mi, name)
        params[str(name)] = [c.r, c.g, c.b, c.a]
    for name in mel.get_texture_parameter_names(mi):
        t = mel.get_material_instance_texture_parameter_value(mi, name)
        params[str(name)] = t.get_path_name() if t else None
    return params


def export_texture(tex, name):
    path = os.path.join(TEX_OUT, name + ".png")
    task = unreal.AssetExportTask()
    task.set_editor_property("object", tex)
    task.set_editor_property("filename", path)
    task.set_editor_property("automated", True)
    task.set_editor_property("prompt", False)
    task.set_editor_property("replace_identical", True)
    try:
        task.set_editor_property("exporter", unreal.TextureExporterPNG())
    except Exception:  # noqa — пусть UE выберет экспортёр по расширению
        pass
    return unreal.Exporter.run_asset_export_task(task)


def main():
    os.makedirs(TEX_OUT, exist_ok=True)
    out = {"root": ROOT, "engine": unreal.SystemLibrary.get_engine_version(), "assets": [], "materials": {}, "textures": []}
    for data in list_assets():
        cls = class_name(data)
        pkg = str(data.package_name)
        name = str(data.asset_name)
        out["assets"].append({"path": pkg, "class": cls})
        if cls == "MaterialInstanceConstant":
            try:
                mi = data.get_asset()
                parent = mi.get_editor_property("parent")
                base = mi.get_base_material()
                out["materials"][name] = {
                    "path": pkg,
                    "parent": base.get_name() if base else (parent.get_name() if parent else None),
                    "direct_parent": parent.get_name() if parent else None,
                    "params": material_params(mi),
                }
            except Exception as e:  # noqa
                warn("MI %s: %s" % (pkg, e))
        elif cls == "Texture2D":
            try:
                if export_texture(data.get_asset(), name):
                    out["textures"].append(name)
                else:
                    warn("текстура %s не выгрузилась" % pkg)
            except Exception as e:  # noqa
                warn("текстура %s: %s" % (pkg, e))
    with open(os.path.join(OUT, "hud_assets.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log("готово: %d ассетов, %d MI, %d текстур → %s" % (len(out["assets"]), len(out["materials"]),
                                                         len(out["textures"]), OUT))


main()
