# UMG Studio — правила для агента

Программа для вёрстки виджетов UMG по спецификации и переноса в Unreal Engine 5.8 (MadWater и любые другие проекты).
Пользователь общается по-русски; ответы и комментарии в коде — по-русски.

## Где что

| Путь | Что |
|---|---|
| `studio/umgstudio/umg.py` | библиотека спецификаций (тот же API, что `umg.py` скилла umg-widgets) — **вывод paste.txt не менять без эталонов** |
| `studio/umgstudio/t3d.py` | разбор текста буфера UMG (paste/copy) → дерево IR |
| `studio/umgstudio/runner.py`, `server.py`, `__main__.py`, `window.py` | запуск спецификаций, локальный сервер, окно |
| `studio/umgstudio/config.py` | настройки проекта (`umgstudio.json`): папки на диске, пути Content (`umg.set_content`) |
| `studio/umgstudio/codegen.py` | спецификация `.py` из дерева UE (copy.txt) — round-trip без отличий |
| `studio/umgstudio/web/` | интерфейс: `slate.js` (раскладка по правилам Slate), `materials.js` (двойники мастер-материалов), `app.js` |
| `design/<Имя>/` | снимок дизайн-системы Claude Design (токены, шрифты, компоненты) — источник вида и шрифтов |
| `examples/UMGPaste/` | эталонные спецификации и тексты (из проекта игры) — на них тесты |
| `ue/UMGStudio/` | плагин редактора UE 5.8 (мост HTTP :30110): импорт/экспорт дерева WBP — не собирается здесь, проверять по сборке пользователя |
| `ue/export_hud_assets.py` | выгрузка MI, текстур, списка ассетов из редактора |
| `Materials/*.hlsl` | код UI-мастеров (превью переводит в GLSL, `web/shaders.js`) |
| `UI/*.cpp` | C++ UI проекта (справка: VM_*, базы виджетов) |
| `tests/mock_ue.py` | имитация плагина для тестов связи |
| `Skills/` | присланные пользователем скиллы и файлы проекта — справка, не править |

## Проверка

- `py -m unittest discover -s tests` — эталоны (спецификация → paste.txt байт в байт), разбор, дифф, связь с UE (имитация).
- Шейдеры: страница превью в Chromium с `--use-angle=swiftshader` — все мастера должны собираться (`GLMaterials.errors`).
- Превью: `PYTHONPATH=studio python -m umgstudio serve`, открыть `http://127.0.0.1:8765/`; для скриншотов — Playwright.

## Дизайн из Claude Design

Вид, размеры, цвета и шрифты берутся из дизайн-системы, не со скриншотов. Обновить снимок:
`Artifact read` артефакта из `design/<Имя>/design.json` (`source`) → файлы `project/*` в `design/<Имя>/`
(без `project/`), ассет-сцену (`/_blob/<id>`) — в `assets/scene.jpg` и заменить ссылку `/_blob/…` в
`components/bundle.css` на `../assets/scene.jpg`; обновить `version` и `synced` в `design.json`.
Нет нужного компонента — сказать пользователю и предложить заказать его в Claude Design.

## Вайбкодинг экрана

Спецификация `<экран>.py` — единственный источник правды. Правила вёрстки, значений и ловушки — `Skills/umg-widgets/`
(SKILL.md, references/). Для превью можно добавить `umg.state("WBP_X", "Имя", show=[...], hide=[...], texts={...})` —
в текст вставки это не попадает.
