@echo off
rem Opens the bot's control window; no terminal stays open. Same as: .venv\Scripts\python.exe gui.py
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" gui.py
