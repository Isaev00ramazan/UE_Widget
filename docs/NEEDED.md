# Что ещё нужно

## Получено ✅

Скиллы (`Skills/`), спецификации и тексты `UMGPaste`, `ue_setup_hud.py`. Дизайн-систему Racing HUD агент забрал
из Claude Design сам (`design/RacingHud`).

## Нужно

1. **`.hlsl` UI-мастеров** из `SourceArt/UI/HUD/HUD_UE57_Kit/Materials/` — для точных копий материалов в превью.
2. **Выгрузка ассетов**: в UE выполнить `ue/export_hud_assets.py`, закоммитить в `inbox/`
   `Saved/UMGStudio/hud_assets.json` и папку `Saved/UMGStudio/Textures/` — реальные цвета MI и иконки в превью.
3. **Версия движка**: 5.7 или уже 5.8 (в UE_Performance идёт миграция Oceanology V10 / UE 5.8); лаунчер или исходники.
4. **Заголовки C++** (для этапов 2 и 4): `ABoatHUD`, `UVM_*`, C++-базы виджетов (`UMissileWarningWidget`,
   `UPickupBannerWidget`, `UHUDHullWidget`, `UHUDDriveWidget`…), имя игрового модуля; включены ли плагины MVVM и Remote Control API.
5. **`WBP_Key`** — copy.txt (Ctrl+C корня в Hierarchy): он вложен в WBP_Drive и в превью пока заглушка.

## Решения за тобой

- ~~Форма программы~~ — десктопное окно (pywebview + WebView2).
- Где жить плагину: здесь в `ue/UMGStudio/` (подключать в проект симлинком/сабмодулем) или сразу в репозитории игры.
- Можно ли плагину перезаписывать существующие WBP (с резервной копией), или сначала только создавать новые рядом.
