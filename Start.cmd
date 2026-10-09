@echo off
pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0outputs\qq-ai-setup\start-qq-bot.ps1" %*
if errorlevel 1 pause

