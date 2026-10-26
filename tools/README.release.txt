UMG Studio {version}
====================

Вёрстка виджетов UMG по спецификации (.py), превью как в Designer, сверка с макетами Claude Design
и перенос в Unreal Engine 5.8 кнопкой «В UE».

ЗАПУСК
  1. Распакуйте папку UMGStudio куда угодно (не в Program Files — программа пишет файлы рядом с собой).
  2. Запустите UMGStudio.exe. Windows может предупредить о неизвестном издателе (файл не подписан):
     «Подробнее» → «Выполнить в любом случае».
  Окно — WebView2 (есть в Windows 10/11); если оно не открылось, программа откроется в Edge отдельным окном.
  Что пошло не так — в %LOCALAPPDATA%\UMGStudio\log.txt.

СВОИ ФАЙЛЫ ПРОЕКТА
  Скопируйте umgstudio.example.json в umgstudio.json (рядом с UMGStudio.exe) и поправьте пути:
    specs     — папка спецификаций и paste/copy-текстов (SourceArt/UI/HUD/UMGPaste)
    materials — .hlsl UI-мастеров (HUD_UE57_Kit/Materials)
    setup_hud — Scripts/ue_setup_hud.py (параметры мастеров)
    assets, textures — выгрузка из UE (ue/export_hud_assets.py → Saved/UMGStudio)
  Без umgstudio.json программа открывает примеры из папки examples.

КНОПКА «В UE» (плагин редактора)
  ue\install_plugin.bat "D:\MOD Dropbox\MAD WATER\PROJECT\MadWater_5.8"
  Затем закрыть редактор и собрать проект (или открыть .uproject — UE предложит пересобрать модуль UMGStudio).
  В окне программы справа вверху появится «● UE 5.8 · MadWater». Подробнее: ue\UMGStudio\README.md

СОСТАВ
  UMGStudio.exe            программа
  umg.py                   библиотека спецификаций (тот же API, что в скилле umg-widgets)
  design\RacingHud         снимок дизайн-системы Claude Design (шрифты, токены, макеты)
  examples\UMGPaste        примеры спецификаций и текстов
  Materials                .hlsl мастеров для превью
  ue\                      плагин UE 5.8, установщик, скрипт выгрузки ассетов
  docs\                    дорожная карта и архитектура
