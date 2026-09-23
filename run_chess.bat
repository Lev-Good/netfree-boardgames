@echo off
cd /d "%~dp0"
title NetFree Online Chess
python chess_window.py
if errorlevel 1 (
    echo.
    echo Error: Failed to run Chess application.
    pause
)
