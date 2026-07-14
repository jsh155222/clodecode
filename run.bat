@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    chcp 65001 >nul
    echo 아직 설치가 완료되지 않았습니다. 먼저 install.bat을 실행해 주세요.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m capcut_auto.gui
