# Что ещё нужно

## Получено ✅

Скиллы, спецификации и тексты `UMGPaste`, `ue_setup_hud.py`, `.hlsl` мастеров (`Materials/`), `.cpp` UI (`UI/`),
`WBP_Key.copy.txt`. Ответы: UE 5.8, плагин в этом репозитории, WBP перезаписывать можно.
Дизайн-систему Racing HUD агент забрал из Claude Design сам (`design/RacingHud`).

## Нужно

1. **Результат выгрузки**: папка `D:\MOD Dropbox\MAD WATER\PROJECT\MadWater_5.8\Saved\UMGStudio` целиком
   (`hud_assets.json` + `Textures\`) → в `inbox/` этого репозитория. Скрипт отработал, но файлы остались у тебя.
2. **Заголовки `.h`** из `Source/.../UI/` (пришли только `.cpp`) — нужны для этапа 4 (View Bindings, BindWidget).
3. **Сборка плагина**: `ue\install_plugin.bat "<папка проекта>"`, собрать, открыть редактор → в окне программы
   «● UE 5.8 · MadWater». Если не собралось — первые ошибки сборки.
4. Лучше клонировать репозиторий через git (GitHub Desktop), а не качать ZIP: обновления — одной кнопкой Pull.
