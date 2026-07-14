@echo off
REM =====================================================================
REM  Heartbeat Lab - one-click launcher for Windows.
REM
REM  This file is intentionally 100%% pure ASCII, comments included.
REM  cmd.exe decodes .bat files using the console's legacy codepage (GBK
REM  on Chinese Windows). UTF-8 Chinese text here would be misread, and
REM  the resulting bytes can contain characters cmd treats as command
REM  separators - which breaks parsing even inside REM lines.
REM
REM  All real logic and all Chinese messages live in start.ps1, which
REM  handles Unicode correctly.
REM =====================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 pause
