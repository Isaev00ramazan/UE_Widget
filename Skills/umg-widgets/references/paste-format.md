# Формат буфера обмена UMG (UE 5.7)

Источник: `FWidgetBlueprintEditorUtils::ExportWidgetsToText` / `ImportWidgetsFromText`
(`Engine/Source/Editor/UMGEditor/Private/WidgetBlueprintEditorUtils.cpp`), сверено с реальной копией
из `WBP_Weapons` (2026-10-08). Генератор `scripts/umg.py` пишет ровно так.

## Структура

```
Begin Object Class=/Script/UMG.HorizontalBox Name="Head" ExportPath="/Script/UMG.HorizontalBox'/Game/UI/HUD/Widgets/WBP_X.WBP_X:WidgetTree.Head'"
   Begin Object Class=/Script/UMG.HorizontalBoxSlot Name="HorizontalBoxSlot_0" ExportPath="…WidgetTree.Head.HorizontalBoxSlot_0'"
   End Object                                        ← 1) объявление каждого слота
   Begin Object Name="HorizontalBoxSlot_0" ExportPath="…WidgetTree.Head.HorizontalBoxSlot_0'"
      Size=(SizeRule=Fill)                           ← 2) свойства слота
      Padding=(Left=15.000000,Right=12.000000)
      HorizontalAlignment=HAlign_Center
      VerticalAlignment=VAlign_Center
      Parent="/Script/UMG.HorizontalBox'Head'"
      Content="/Script/UMG.TextBlock'LightName'"     ← ребёнок по имени
   End Object
   Slots(0)="/Script/UMG.HorizontalBoxSlot'HorizontalBoxSlot_0'"   ← порядок детей = порядок Slots(i)
   bExpandedInDesigner=True
End Object
Begin Object Class=/Script/UMGEditor.WidgetSlotPair Name="WidgetSlotPair_24" ExportPath="/Script/UMGEditor.WidgetSlotPair'/Engine/Transient.WidgetSlotPair_24'"
   WidgetName="Head"                                 ← только у корня выделения
End Object
Begin Object Class=/Script/UMG.TextBlock Name="LightName" ExportPath="…WidgetTree.LightName'"
   …свойства…                                        ← строки Slot= у ребёнка НЕТ
End Object
```

- Все виджеты выделения и все потомки идут **плоско**, каждый — свой верхний `Begin Object`.
- Имена слотов уникальны только внутри родителя (`SizeBoxSlot_0` у разных SizeBox — норма).
- **Имена виджетов уникальны во всём дереве.** При совпадении с уже существующим UE молча переименует → BindWidget
  не найдёт. Генератор проверяет.
- `WidgetSlotPair` корня, вырезанного из Canvas, несёт его Canvas-слот: `SlotPropertyNames(i)` / `SlotPropertyValues(i)`.
  Для вставки в пустой виджет или в выделенную панель хватает одного `WidgetName`.
- `DisplayLabel` пишется, только если имя в Hierarchy переименовали; генератор даёт сразу нормальные `Name`.
- Порядок строк свойств не важен; значения по умолчанию в экспорт не попадают — отсутствие строки = дефолт.

## Классы слотов

| Панель | Слот | Свойства слота |
|---|---|---|
| CanvasPanel | CanvasPanelSlot | `LayoutData=(Offsets=(Left,Top,Right,Bottom),Anchors=(Minimum=(X,Y),Maximum=(X,Y)),Alignment=(X,Y))`, `bAutoSize=True`, `ZOrder` |
| VerticalBox / HorizontalBox | …BoxSlot | `Size=(SizeRule=Fill[,Value=…])`, `Padding`, `HorizontalAlignment`, `VerticalAlignment` |
| Overlay, SizeBox, Border, ScaleBox, BackgroundBlur | OverlaySlot, SizeBoxSlot, BorderSlot, ScaleBoxSlot, BackgroundBlurSlot | `Padding`, `HorizontalAlignment`, `VerticalAlignment` |
| UniformGridPanel | UniformGridSlot | `Row`, `Column`, выравнивания |
| RetainerBox, InvalidationBox, NamedSlot | PanelSlot (базовый) | нет — отступ задавать в слоте родителя |

Canvas Offsets: при точечном якоре `Left/Top` = Position, `Right/Bottom` = Size; при растянутом — отступы от краёв
(у растянутого по X: `Left`, `Right` — отступы, `Top` — Position Y, `Bottom` — Size Y).

## Свойства виджетов (как пишет редактор)

| Виджет | Строки |
|---|---|
| TextBlock | `Text=NSLOCTEXT("ns", "key", "текст")`; `ColorAndOpacity=(SpecifiedColor=(R=…,G=…,B=…,A=…))`; `Font=(FontObject="/Script/Engine.Font'/Game/UI/HUD/Fonts/F_HUD.F_HUD'",TypefaceFontName="SemiBold",Size=10.500000,LetterSpacing=80)`; `ShadowOffset=(X=0.000000,Y=1.000000)`; `ShadowColorAndOpacity=(R=0,G=0,B=0,A=0.7)` (по умолчанию тени нет); `TextTransformPolicy=ToUpper`; `Justification=Center` |
| Image | `Brush=(TintColor=(SpecifiedColor=(…)),ImageType=FullColor,ImageSize=(X=…,Y=…),ResourceObject="/Script/Engine.MaterialInstanceConstant'/Game/…/MI_X.MI_X'")`. Без `ResourceObject` — белый квадрат (для полос/ромбов это и нужно) |
| SizeBox | `WidthOverride=…`, `HeightOverride=…`, `MinDesiredWidth=…` + `bOverride_WidthOverride=True` и т.д. |
| Border | `Background=(DrawAs=RoundedBox,OutlineSettings=(CornerRadii=(X,Y,Z,W),Color=(SpecifiedColor=(…)),Width=1,RoundingType=FixedRadius))`, `BrushColor=(R…)`, `Padding=(…)` |
| RetainerBox | `bRetainRender=True/False`, `EffectMaterial="…MI_…'"`, `TextureParameter="Texture"` |
| BackgroundBlur | `BlurStrength=6.000000` |
| UniformGridPanel | `SlotPadding=(…)`, `MinDesiredSlotHeight` |
| Spacer | `Size=(X=8.000000,Y=0.000000)` |
| Любой | `bIsVariable=True`, `Visibility=Collapsed`, `RenderTransform=(Angle=45.000000)` / `(Scale=(X=1.25,Y=1))`, `bHiddenInDesigner=True` |
| Свой WBP | `Class=/Game/UI/HUD/Widgets/WBP_Key.WBP_Key_C`, в `Content=` тот же путь класса; свойства — его Instance Editable переменные (`TextButton=NSLOCTEXT(…)`, `Size=10.000000`, `Accent=True`) |

## Если вставка не сработала

1. Ctrl+V ничего не сделал — синтаксис: непарный `Begin/End Object`, кавычки в тексте (экранировать `\"`).
2. Встало, но не всё — неизвестное имя свойства тихо пропускается. Попросить пользователя скопировать такой же
   элемент из редактора и разобрать `py scripts/umg_dump.py file.txt --raw`; поправить фабрику в `umg.py`.
3. Ссылка на ассет (`MI_`, `T_`) не найдена — Brush пустой, остальное встаёт. Проверить путь в `Content/UI/HUD/…`.
