@echo off
setlocal
where python >nul 2>&1
if errorlevel 1 (
    echo Python 3 is required. Install Python and ensure python is on PATH.
    exit /b 1
)
python "%~dp0build_plugin.py"
exit /b %errorlevel%
