@echo off
REM KORRIGIERT 2026-09-03: daemon.py::main() loggt jetzt selbst immer nach
REM logs\daemon.log (RotatingFileHandler, siehe paths.py/daemon.py - wurde
REM fuer die neue PyInstaller-.exe ergaenzt). Die alte ">> logs\daemon.log"-
REM Umleitung hier hat DIESELBE Datei gleichzeitig offen gehalten wie der
REM RotatingFileHandler - Windows' Datei-Sperre liess das zweite Oeffnen
REM fehlschlagen (PermissionError), der Daemon stuerzte beim Autostart sofort
REM ab. Umleitung entfernt, das Python-eigene Logging reicht jetzt aus.
cd /d "%~dp0"
start "" /B ".venv-windows\Scripts\pythonw.exe" -m streamdeck_driver.daemon
