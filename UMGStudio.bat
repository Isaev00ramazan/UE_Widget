@echo off
rem UMG Studio — окно программы. Первый запуск ставит pywebview (окно на WebView2).
chcp 65001 >nul
cd /d "%~dp0"
set PY=py
where py >nul 2>nul || set PY=python
%PY% -c "import webview" 2>nul || %PY% -m pip install --user -r requirements.txt
set PYTHONPATH=%~dp0studio
%PY% -m umgstudio %*
if errorlevel 1 pause
