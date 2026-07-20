@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 아직 설치가 완료되지 않았습니다. 먼저 setup-webapp.bat을 실행해 주세요.
    pause
    exit /b 1
)
if not exist "webapp\dist\index.html" (
    echo 아직 설치가 완료되지 않았습니다. 먼저 setup-webapp.bat을 실행해 주세요.
    pause
    exit /b 1
)

set CAPCUT_PORT=8842
if exist "ffmpeg\bin\ffmpeg.exe" (
    set CAPCUT_AUTO_FFMPEG_DIR=%~dp0ffmpeg\bin
)

echo CapCut Auto Editor를 준비하는 중입니다...
start "CapCut Auto Editor 서버 - 이 창을 닫으면 프로그램이 종료됩니다" /min ".venv\Scripts\python.exe" -m uvicorn capcut_auto.server:app --host 127.0.0.1 --port %CAPCUT_PORT%

set READY=0
for /l %%i in (1,1,60) do (
    if !READY! equ 0 (
        curl -s -f http://127.0.0.1:%CAPCUT_PORT%/ >nul 2>nul
        if !errorlevel! equ 0 (
            set READY=1
        ) else (
            timeout /t 1 >nul
        )
    )
)

if !READY! equ 0 (
    echo.
    echo [오류] 서버가 제한 시간 안에 시작되지 않았습니다.
    echo 새로 뜬 "CapCut Auto Editor 서버" 창에 오류 메시지가 있는지 확인해주세요.
    pause
    exit /b 1
)

start "" "http://127.0.0.1:%CAPCUT_PORT%/"
echo 브라우저에서 CapCut Auto Editor가 열렸습니다.
echo 프로그램을 끝내려면, 작업 표시줄에 최소화되어 있는
echo "CapCut Auto Editor 서버" 창을 찾아 닫아주세요.
pause
