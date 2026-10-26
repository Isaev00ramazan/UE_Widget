# HUD-кит проекта: шрифт, цвета, материалы, ассеты

Первоисточник вида — дизайн-система Claude Design (artifact `4A89FtC2sf26j3VYxruB3L`): README компонента +
`project/components/bundle.css`. Локальная выгрузка кита — `SourceArt/UI/HUD/HUD_UE57_Kit/` (README, `Style/HudStyle.json`).
Значения брать оттуда, **не со скриншотов**.

## Шрифт F_HUD (`/Game/UI/HUD/Fonts/F_HUD`)

Barlow Condensed + Fira Sans Condensed для кириллицы (U+0400–04FF). Начертания — строки `TypefaceFontName`:
`Medium`, `SemiBold`, `Bold`, `SemiBoldItalic`, `BoldItalic`. **Medium Italic нет** → брать `SemiBoldItalic`.
Глифа ▲/▼ в шрифте нет → иконка `T_Ico_Up` / `T_Ico_Down`. ∞ есть.

Проект на `FontDPIPreset=Standard` (96 DPI) → **Size в UE = px × 0.75**. Letter Spacing — тысячные em (CSS 0.08em → 80).

| Токен | Начертание | px | Size UE | LS | UPPER | Где |
|---|---|---|---|---|---|---|
| t-speed | BoldItalic | 104 | 78 | -10 | — | скорость |
| t-num-lg | BoldItalic | 46 | 34.5 | 0 | — | боезапас тяжёлого |
| t-num-md | SemiBoldItalic | 28 | 21 | 0 | — | HULL, круг, секунды перезарядки |
| t-num-sm | SemiBoldItalic | 20 | 15 | 0 | — | отрывы, таймеры дебаффов, проценты |
| t-title | SemiBold | 16 | 12 | 120 | да | заголовки панелей |
| t-name | Medium | 19 | 14.25 | 40 | да | имена |
| t-label | SemiBold | 14 | 10.5 | 80 | да | подписи, клавиши |

Тень текста почти везде: Offset (0, 1), цвет `(R=0.000000,G=0.000000,B=0.000000,A=0.700000)`. Без тени — текст на
цветной заливке (теги YOU/FASTEST, клавиши).

## Цвета

Designer/MI — линейные; Graph (пины BP) — HEX sRGB. Перевод: `py scripts/umg.py color F5C56B [альфа]`,
обратно `py scripts/umg.py linear R G B`.

| Токен | HEX sRGB | Линейный | Где |
|---|---|---|---|
| glass | `0E2026` | `(R=0.004400,G=0.014400,B=0.019400,A=0.740000)` | заливка панелей |
| glass-strong | `08161B` | `(R=0.002400,G=0.008000,B=0.011000,A=0.860000)` | диски навыков, бейджи, клавиши |
| glass-head | `78AAB0` | `(R=0.187800,G=0.402000,B=0.434200,A=0.200000)` | полоса заголовка панели |
| edge | `BEEBEB` | `(R=0.514918,G=0.830770,B=0.830770,A=0.200000)` | блик края, разделители (A 0.08–0.10) |
| ink | `F3F6F2` | `(R=0.896269,G=0.921582,B=0.887923,A=1.000000)` | цифры, имена |
| ink-muted | `A8BEC0` | `(R=0.391573,G=0.514918,B=0.527115,A=1.000000)` | подписи, места, отрывы |
| ink-faint | `8AA2A5` | `(R=0.254152,G=0.361307,B=0.376262,A=1.000000)` | неактивное |
| track | `C8EBEB` | `(R=0.577580,G=0.830770,B=0.830770,A=0.140000)` | пустая часть шкал |
| race | `54E6C6` | `(R=0.088656,G=0.791298,B=0.564712,A=1.000000)` | акцент гонки |
| nitro | `47C8FF` | `(R=0.063010,G=0.577580,B=1.000000,A=1.000000)` | нитро, BOOST |
| combat | `F5C56B` | `(R=0.913099,G=0.558340,B=0.147027,A=1.000000)` | акцент боя |
| sand | `ECDCB8` | `(R=0.838799,G=0.715694,B=0.479320,A=1.000000)` | иконки оружия и навыков |
| hp | `FF5242` | `(R=1.000000,G=0.084376,B=0.054480,A=1.000000)` | HULL, пусто |
| player | `FF8C1A` | `(R=1.000000,G=0.262251,B=0.010330,A=1.000000)` | «это ты» |
| debuff | `C08CFF` | `(R=0.527115,G=0.262251,B=1.000000,A=1.000000)` | дебаффы |
| on-accent | `071418` | `(R=0.002125,G=0.006995,B=0.009134,A=1.000000)` | текст на заливках race/combat/player |

В ответе пользователю имя токена — только в скобках рядом со значением (см. правила в SKILL.md).

## Материалы (`/Game/UI/HUD/Materials`)

Мастера — Custom-нода из `SourceArt/UI/HUD/HUD_UE57_Kit/Materials/*.hlsl`, создаются скриптом
`Scripts/ue_setup_hud.py` (таблица `MATERIALS` — **полный список параметров и их дефолты**; `UPDATE_IN_PLACE` —
мастера, которые скрипт перестраивает на месте, не ломая MI). Новый параметр/мастер: правка `.hlsl` + `MATERIALS`
→ пользователь перезапускает скрипт (Tools → Execute Python Script).

| Мастер | Для чего | Ключевые параметры |
|---|---|---|
| M_UI_Panel | стеклянная панель со скосами | Size (= размер Image!), Cut, Corners (TL,TR,BR,BL), Circle, Fill, HeadH, HeadColor, Edge, Zone, StrokeW/StrokeColor, InnerGlowPx/InnerGlowColor |
| M_UI_SegBar | сегментная/сплошная шкала | Size, Segments, Gap, SkewTan 0.364, Fill, Ramp, Continuous, OnColor, OffColor, PeakColor, Glow*, Trail/TrailColor, OnColorEnd, OffStroke/OffStrokeW, GainFrom/GainColor/GainHeadColor (восполнение), GapFlash/GapFlashColor (вспышка делений) |
| M_UI_Ring | кольцо кулдауна | Size, RingW, Pad, Progress, FillColor, TrackColor, GlowColor |
| M_UI_Pips | пипсы магазина (непрерывные) | Size, PipSize, Count, Gap, Round, Mask (texobj), Fill, OnColor, OffColor, EdgeColor |
| M_UI_Glow | свечение под шкалой | Size, Pad, Falloff, Color, Fill, Segments, Gap, SkewTan, Ramp, Continuous |
| M_UI_Radar | радар | Size, RadarR, Map, Player, Yaw, Zoom, … |
| M_UI_Marker, M_UI_RadialGlow | метки радара | Size, Shape, Radius, Fill/Outline/Glow |
| M_UI_Gradient | горизонтальный градиент 4 точки | C0, P1, C1, P2, C2, C3 |
| M_UI_RadialDim | радиальное затемнение экрана | Center, Radius, Inner, Outer |
| M_UI_TextGlow | эффект Retainer Box — свечение текста | Texture (имя параметра ровно `Texture`), Size, Radius, GlowColor |
| M_UI_FisheyePulse | эффект Retainer Box — рыбий глаз нитро | Texture, Screen, K, Exponent, CenterY |
| M_UI_WarnRing | обод сенсора ракет с засечками | Size, Radius, RingW, TrackColor, TickCount, TickLen, TickW, TickColor |
| M_UI_WarnArc | дуга угрозы (центр сверху, поворот — Render Transform Image) + шеврон + свечение | Size, Radius, ArcDeg, Width, ChevW, ChevH, GlowPx, Color, Opacity |
| M_UI_Chevron | плашка-шеврон подбора: параллелограмм −20°, обводка боков, бегущие полосы | Size (фактический, пишет код), SkewTan, Color, FillAlpha, BorderW, StripeAlpha, StripePeriod, StripeSpeed |

Сенсор ракет (2026-10-19): мастера и MI_WarnRing / MI_WarnArc / MI_Panel_Warn, иконку T_Ico_Warn и WBP_MissileWarning
создаёт `HUD_UE57_Kit/Scripts/ue_setup_missile_warning.py` (не перезапуская ue_setup_hud — тот переимпортирует шрифты).
Плашка подбора (2026-10-21): M_UI_Chevron, MI_Chevron, иконки T_Ico_Pickup{Shield,Hull,Rockets,Nitro} (растр —
`raster_ico_pickups.py`) и WBP_PickupBanner — `ue_setup_pickup_banner.py`.

Готовые MI лежат там же (`MI_Panel_*`, `MI_SegBar_*`, `MI_Glow_*`, `MI_Ring_*`, `MI_TextGlow_*`, `MI_Gradient_*`…) —
перед заведением нового посмотреть `ls Content/UI/HUD/Materials`.

## Текстуры (`/Game/UI/HUD/Textures`)

`T_Ico_*` (Flag, Kills, Up, Down, Hull, Nitro, Slow, Swap), `T_Wpn_*`, `T_Skill_*`, `T_Radar_*`, `T_Ammo_Pip*`.
Исходники PNG — `HUD_UE57_Kit/Textures`; иконки из SVG дизайна растрируются скриптом (×2, белые в альфе,
цвет — Tint). Настройки импорта: Texture Group UI, UserInterface2D, No Mipmaps, Never Stream, sRGB.

## Виджеты (`/Game/UI/HUD/Widgets`)

`WBP_HUD` (корень: Canvas, кластеры по углам, отступ 48) → `WBP_RaceStandings`, `WBP_Drive`, `WBP_CombatDock`
(`WBP_Weapons`, `WBP_Abilities`, `WBP_Hull`, `WBP_Debuffs`); мелкие: `WBP_Key` (клавиша: `TextButton`, `Size`,
`SetPaddingText`, `Accent`), `WBP_ActiveKey`, `WBP_DebuffBadge`, `WBP_StandingRow`, `WBP_Radar`, `WBP_RadarIcon`;
экран результатов `WBP_RaceResults` + `WBP_ResultRow` (спецификация — `SourceArt/UI/HUD/UMGPaste/race_results.py`).
Сетка 1920×1080, DPI Scale Rule = Shortest Side.
