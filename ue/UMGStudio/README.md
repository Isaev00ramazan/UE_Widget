# UMG Studio Bridge (плагин редактора, UE 5.8)

Принимает от программы UMG Studio текст вставки и сам создаёт / обновляет Widget Blueprint, выгружает дерево обратно.

## Что делает «В UE»

1. Резервная копия `.uasset` → `Saved/UMGStudio/Backups/WBP_X_<дата>.uasset` (новый WBP создаётся без копии).
2. Закрывает редактор этого виджета, если открыт.
3. Старое дерево убирает (как удаление в Designer), новое вставляет тем же импортом, что Ctrl+V в Designer
   (`FWidgetBlueprintEditorUtils::ImportWidgetsFromText`). Имена те же → BindWidget, ссылки в графе, анимации и
   View Bindings находят свои элементы. Всё в одной транзакции: Ctrl+Z в редакторе откатывает.
4. Родитель (`save(..., parent="/Script/MadWater.HUDDriveWidget")`) и размер превью (`design=(1920, 1080)`).
5. Компиляция, сохранение, отчёт в программу: ошибки компилятора, переименованные при вставке элементы.

«Забрать из UE» — дерево WBP целиком в формате Ctrl+C → `<WBP>.copy.txt` рядом со спецификацией.
Список «В проекте UE» в программе — `GET /umgstudio/list` (все Widget Blueprint из /Game); выгрузка отдаёт ещё родителя
и размер превью, чтобы спецификация из UE их сохранила. Ping сообщает папку проекта — программа берёт её сама.
Текстуры для превью — `GET /umgstudio/texture?asset=/Game/…/T_X&max=1024` (PNG из исходника текстуры).
Папка для нового WBP — `GET /umgstudio/contentpath` (папка, открытая в Content Browser): туда программа создаёт виджет, если в «⚙ Проект» не задана папка виджетов.

## Установка

1. `ue\install_plugin.bat "D:\MOD Dropbox\MAD WATER\PROJECT\MadWater_5.8"` — копирует плагин в `Plugins\UMGStudio`.
2. Закрыть редактор, собрать проект (Visual Studio / Rider) — или открыть `.uproject`: UE предложит пересобрать модуль.
3. В Output Log при запуске: `[UMGStudio] мост слушает http://127.0.0.1:30110/umgstudio`.
4. В окне UMG Studio справа вверху: `● UE 5.8 · MadWater`.

Порт меняется в `Config/DefaultEditorPerProjectUserSettings.ini`:
```ini
[UMGStudio]
Port=30110
```
Мост принимает запросы только для чтения/записи WBP; чтобы он не был виден в локальной сети, в `Config/DefaultEngine.ini`:
```ini
[HTTPServer.Listeners]
DefaultBindAddress=127.0.0.1
```

## Из Python-консоли редактора

```python
ok, report = unreal.UMGStudioLibrary.import_widget_text("/Game/UI/HUD/Widgets/WBP_Test", text, "", "Desired", unreal.Vector2D(0, 0))
ok, text = unreal.UMGStudioLibrary.export_widget_text("/Game/UI/HUD/Widgets/WBP_Drive")
```

## Если не собралось

Плагин не проверен компиляцией (писался без движка). Пришли первые ошибки из Output/Build — поправлю.
Самые вероятные места: сигнатуры `FWidgetBlueprintEditorUtils::ImportWidgetsFromText / ExportWidgetsToText`
и `FHttpRequestHandler` в 5.8.
