@echo off
rem 繁中自動選字 — 背景啟動（無主控台視窗）
cd /d "%~dp0"
start "" "%USERPROFILE%\anaconda3\pythonw.exe" "%~dp0tray_app.py"
