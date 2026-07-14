@echo off
REM Heartbeat Lab - stop script. Pure ASCII on purpose; see start.bat for why.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
