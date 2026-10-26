---
name: umg-widgets
description: "Use this skill whenever the task involves creating, laying out, restyling or wiring UMG widgets in this project: HUD clusters (WBP_HUD, Drive, Weapons, Abilities, Hull, Debuffs, RaceStandings, Radar), menus, results/finish screens, popups, any WBP_* / Widget Blueprint / User Widget / виджет / вёрстка / дерево виджета / Hierarchy / Designer / Canvas Panel / Size Box / Retainer Box / UI-материал / MI_Panel / M_UI_* / шрифт F_HUD / цвета HUD / Claude Design → Unreal, MVVM viewmodel bindings (UVM_*, ABoatHUD feeder), C++ widget base classes with BindWidget, or reading text the user copied from the UMG Designer. Generates UMG clipboard text (paste with Ctrl+V into the Designer) from a Python tree spec, decodes copied widget text into a readable tree, converts design px/colors to UE values, and lists the project's HUD kit (font faces, color tokens, UI master materials and their parameters, textures, existing widgets) plus the UI pitfalls already hit in this project."
metadata:
  version: 1.0.0
---

# UMG-виджеты MadWater — создание и настройка

Виджеты в редакторе собирает **пользователь**; агент даёт ему готовый текст для вставки (Ctrl+V в Designer),
точные значения для того, что вставкой не задаётся, и код (viewmodel / C++-база виджета). `.uasset` вслепую не трогать.

Пути ниже — от корня проекта. Скрипты: `.claude/skills/umg-widgets/scripts/`.

## Порядок работы

1. **Откуда вид.** Дизайн — Claude Design: artifact `https://claude.ai/artifact/4A89FtC2sf26j3VYxruB3L`
   (README компонента + `project/components/bundle.css`; читать `Artifact` action `read` / `path`). Размеры,
   отступы, цвета, шрифты — **оттуда, не со скриншотов**. Нет компонента в системе — сказать и предложить заказать
   его в Claude Design, а не придумывать.
2. **Что уже есть.** `ls Content/UI/HUD/{Widgets,Materials,Textures}` — MI и иконки часто уже заведены
   (`references/hud-kit.md`). Существующий виджет: попросить выделить корень в Hierarchy → Ctrl+C → прислать текст,
   разобрать `py scripts/umg_dump.py <файл>` (дерево + шрифты в px + цвета в HEX). По скриншоту не гадать.
3. **Откуда данные** (решения — `Docs/Agent/project-decision.md` → «HUD»):
   - простые значения → **MVVM**: C++ `UVM_*` (FieldNotify) в глобальной коллекции, питатель `ABoatHUD`
     (опрос 20 Гц / события), виджет — обычный User Widget без кода, связи в View Bindings
     (Creation Type = Global Viewmodel Collection, имя = `CollectionName` VM);
   - списки, динамические строки, своя анимация → C++-база виджета (`Source/.../UI/`, `BindWidgetOptional`),
     пользователь делает **Reparent Blueprint** — вёрстка сохраняется. Имена элементов ✎ = имена `BindWidget`.
   - Сначала можно сверстать как обычный User Widget, базу дать потом.
4. **Спецификация → текст вставки.** Файл `SourceArt/UI/HUD/UMGPaste/<экран>.py` (образец — `race_results.py`):
   ```python
   import os, sys
   sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../.claude/skills/umg-widgets/scripts"))
   import umg; from umg import *
   umg.TEXT_NAMESPACE = "MyScreen"
   root = box("CanvasPanel", "Root", [ ... ])
   save(root, "WBP_MyScreen", os.path.dirname(os.path.abspath(__file__)))
   ```
   Фабрики: `text` (px дизайна → Size UE сам), `image`, `sizebox`, `box` (любая панель), `border` + `rounded`,
   `retainer`, `spacer`, `user_widget` (свой WBP, напр. `WBP_Key`); слоты `cslot` (Canvas), `bs` (Box/Overlay/…),
   `grid`; цвета — константы `INK, MUTED, …` или `hex_lin("F5C56B")`. Запуск `py <экран>.py` → `WBP_*.paste.txt`.
   Генератор проверяет уникальность имён и начертания шрифта. Формат и свойства — `references/paste-format.md`.
5. **Отдать пользователю:**
   - файлы `.paste.txt` (ссылками) + как вставить: открыть файл → Ctrl+A, Ctrl+C → в Designer выделить пустую
     Hierarchy (или панель-родителя) → Ctrl+V;
   - короткое дерево с ✎ (что должно быть Is Variable) — для сверки;
   - то, что вставкой не задаётся или чего нет: новые MI — таблицей с параметрами и значениями; новые иконки;
     превью Custom-размера виджета; View Bindings MVVM — построчно (виджет.свойство ← VM.поле, функция-конвертер);
   - что проверить: какие состояния включить для проверки вида.
6. **Пользователь доверстал руками → синхронизировать спецификацию.** Его копия — правда. Большая копия
   (> ~50 тыс. символов) в сообщение не влезает и обрезается — просить сохранить в файл
   `SourceArt/UI/HUD/UMGPaste/<WBP>.copy.txt`. Сравнить:
   `diff <(py scripts/umg_dump.py <WBP>.copy.txt) <(py scripts/umg_dump.py <WBP>.paste.txt)` и перенести
   отличия в `<экран>.py`, чтобы повторная генерация не затёрла его правки.
7. **Если вставка не встала** — `references/paste-format.md` → «Если вставка не сработала». Попросить реальную копию
   похожего элемента и подогнать фабрику в `umg.py`, а не уговаривать пользователя собирать руками.

## Как писать значения пользователю (его правила)

- **Значение — прямо в строке элемента**: «SemiBold 10.5 (14px), LS 80, UPPER, `(R=0.391573,G=0.514918,B=0.527115,A=1.000000)`,
  тень (0,1) A0.7». Не «стиль t-label», не легенда цветов с именами (`ink`, `race`) — имя токена можно только в скобках.
- Цвет в **Designer и MI** — линейный в формате копирования UE `(R=…,G=…,B=…,A=…)`, 6 знаков.
  Цвет на **пинах в Graph** (Set Color and Opacity, Set Vector Parameter Value) — HEX sRGB + альфа отдельно.
  Перевод: `py scripts/umg.py color F5C56B 0.6` / `py scripts/umg.py linear 0.9131 0.5583 0.147`.
- **Шрифт: Size UE = px × 0.75** (проект на 96 DPI, `FontDPIPreset=Standard`). В дереве писать UE-значение,
  px — в скобках. Letter Spacing = тысячные em (0.08em → 80). На глаз в UE разрядка выглядит меньше макетной —
  пользователь поднимает её сам (заголовки t-title 120 → 208–220, подписи 80 → 100–130). Давать значение из макета
  с пометкой «подобрать на глаз», не пересчитывать молча.
- Начертания F_HUD: `Medium`, `SemiBold`, `Bold`, `SemiBoldItalic`, `BoldItalic` — без пробелов; Medium Italic нет.
- Упрощать визуал нельзя («лучше не упрощать на визуале»): свечение — Retainer + `M_UI_TextGlow`, градиенты — `M_UI_Gradient`,
  обводки — `M_UI_Panel` StrokeW, а не «сделаем плоско».
- Нужен эффект, которого нет среди мастеров — новый `.hlsl` в `SourceArt/UI/HUD/HUD_UE57_Kit/Materials/` +
  запись в `MATERIALS` (и при перестройке существующего — в `UPDATE_IN_PLACE`) в `Scripts/ue_setup_hud.py`;
  пользователь перезапускает скрипт. Текстуры-иконки из SVG дизайна — растрировать скриптом (×2, белые, цвет Tint).

## Ловушки (уже ловили)

- **Поток.** Делегаты GAS (атрибуты, эффекты) приходят в потоке, где атрибут поменяли, — бывает физпоток → assert
  Slate. Любой подписчик UI: `IsInGameThread()` иначе `AsyncTask(GameThread)` (`ABoatHUD::DeferToGameThread`),
  теги/атрибуты читать через `UGASTagLibrary` (`Docs/Agent/Gotchas.md` → «Физика и потоки»).
- **Экземпляр виджета внутри другого хранит свою копию свойств** (`EditDefaultsOnly` в Details экземпляра не видно) —
  настройки-таблицы читать из CDO (`Gotchas.md` → «UI: виджеты, меню, пауза, CommonUI», случай `UDebuffContainerWidget::Styles`).
- **Виджеты в `TMap`/`TArray` без `UPROPERTY` живут, только пока в панели** — краш GC (случай `URacePositionsWidget`).
- `M_UI_Panel`: параметр `Size` = фактический размер Image, иначе скосы/обводка плывут. Обводку делать `StrokeW`,
  а не красной подложкой под полупрозрачным стеклом (просвечивает всегда).
- `M_UI_TextGlow`: `Size` в MI = фактический размер содержимого Retainer Box (меняли ширину Size Box внутри —
  менять и MI), иначе радиус свечения по осям искажается (`Radius / Size` в UV).
- Retainer Box: параметр текстуры эффект-материала называется ровно `Texture` (это и дефолт `TextureParameter`;
  `bRetainRender` по умолчанию True — в копии этих строк может не быть); у Retainer слот без Padding —
  отступ (обычно отрицательный, под радиус свечения) ставить в слоте родителя. `bRetainRender` выключен = эффекта нет.
- Border: Padding дублируется в слот ребёнка — писать одинаково (фабрика `border` делает сама).
- ▲/▼ в F_HUD нет — Image `T_Ico_Up` / `T_Ico_Down`.
- Image без ресурса = белый квадрат — так и задумано для полос/ромбов, цвет через Tint.
- `Visibility=Collapsed` для элементов-состояний (теги, бейджи): Hidden оставляет место в раскладке.
- C++: новый/изменённый `BindWidget`, `UPROPERTY`, `UFUNCTION`, VM-поле → **полная сборка с закрытым редактором**;
  только тела функций → Live Coding. Сборку запускает пользователь (`Build.bat` не трогать).

## Скрипты

| Скрипт | Что делает |
|---|---|
| `scripts/umg.py` | библиотека генерации текста вставки + `color` / `linear` в CLI |
| `scripts/umg_dump.py <файл> [--raw]` | разбор скопированного из Designer текста в дерево |

## Справочники

- `references/paste-format.md` — формат буфера обмена UMG, классы слотов, имена свойств, отладка вставки.
- `references/hud-kit.md` — шрифт и типографика (px → UE), цвета (HEX ↔ линейные), мастер-материалы и параметры,
  текстуры, список виджетов HUD.

Нашли новую ловушку UI — в `Docs/Agent/Gotchas.md` (а сюда — строку-ссылку), новое решение по HUD — в
`project-decision.md`. Новое свойство/класс в формате вставки — в `paste-format.md` и фабрику `umg.py`.
