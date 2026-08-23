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

timeout /t 6 >nul

start "" "http://127.0.0.1:%CAPCUT_PORT%/"
echo.
echo 브라우저에서 CapCut Auto Editor를 열었습니다.
echo 화면이 비어있거나 오류가 보이면, 몇 초 더 기다렸다가
echo 브라우저에서 새로고침^(F5^)을 한 번 눌러주세요.
echo.
echo 프로그램을 끝내려면, 작업 표시줄에 최소화되어 있는
echo "CapCut Auto Editor 서버" 창을 찾아 닫아주세요.
echo.
pause
