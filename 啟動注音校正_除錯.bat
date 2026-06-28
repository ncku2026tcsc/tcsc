@echo off
rem 繁中自動選字 — 除錯啟動（保留主控台顯示錯誤）
cd /d "%~dp0"
"%USERPROFILE%\anaconda3\python.exe" "%~dp0tray_app.py"
echo.
pause
