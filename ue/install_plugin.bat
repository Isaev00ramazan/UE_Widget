@echo off
rem Копирует плагин UMG Studio Bridge в проект: install_plugin.bat "D:\MOD Dropbox\MAD WATER\PROJECT\MadWater_5.8"
chcp 65001 >nul
set PROJECT=%~1
if "%PROJECT%"=="" set /p PROJECT=Папка проекта (где .uproject): 
if not exist "%PROJECT%\*.uproject" (
  echo Не нашёл .uproject в "%PROJECT%"
  pause
  exit /b 1
)
robocopy "%~dp0UMGStudio" "%PROJECT%\Plugins\UMGStudio" /MIR /XD Binaries Intermediate /NFL /NDL /NJH /NJS
echo.
echo Готово: %PROJECT%\Plugins\UMGStudio
echo Закрой редактор и собери проект (или запусти .uproject — UE предложит пересобрать модуль UMGStudio).
pause
