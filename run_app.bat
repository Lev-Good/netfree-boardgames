@echo off
cd /d "%~dp0"
title NetFree Google Sheets Test
python main.py
if errorlevel 1 (
    echo.
    echo Error: Failed to run application.
    pause
)
