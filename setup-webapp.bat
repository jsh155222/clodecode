@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  CapCut Auto Editor - 웹 화면 버전 설치
echo  처음 한 번만 실행하면 됩니다. 다소 시간이
echo  걸릴 수 있습니다 - 인터넷 상태에 따라 다름
echo ============================================
echo.

REM ---------------------------------------------------------------
REM 1) 파이썬 확인
REM ---------------------------------------------------------------
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [1/5] 파이썬이 설치되어 있지 않습니다.
    echo   https://python.org/downloads 에서 파이썬을 먼저 설치한 뒤,
    echo   설치 화면에서 "Add python.exe to PATH"를 꼭 체크하고
    echo   이 setup-webapp.bat을 다시 실행해 주세요.
    pause
    exit /b 1
) else (
    echo [1/5] 파이썬 확인 완료.
)

REM ---------------------------------------------------------------
REM 2) 가상환경 생성 + 패키지 설치
REM ---------------------------------------------------------------
echo [2/5] 파이썬 가상환경 준비 중...
if not exist ".venv" (
    python -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo       필요한 패키지 설치 중 - 용량이 커서 몇 분 걸릴 수 있습니다...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo   패키지 설치 중 오류가 발생했습니다. 위 오류 메시지를 확인해 주세요.
    pause
    exit /b 1
)

REM ---------------------------------------------------------------
REM 3) ffmpeg 다운로드
REM ---------------------------------------------------------------
if exist "ffmpeg\bin\ffmpeg.exe" (
    echo [3/5] ffmpeg 이미 준비되어 있음.
) else (
    echo [3/5] ffmpeg 다운로드 중...
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'ffmpeg_temp.zip'"
    if not exist "ffmpeg_temp.zip" (
        echo   ffmpeg 다운로드에 실패했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.
        pause
        exit /b 1
    )
    powershell -NoProfile -Command "Expand-Archive -Path 'ffmpeg_temp.zip' -DestinationPath 'ffmpeg_extract' -Force"
    for /d %%D in (ffmpeg_extract\ffmpeg-*) do (
        mkdir "ffmpeg\bin" 2>nul
        copy "%%D\bin\ffmpeg.exe" "ffmpeg\bin\ffmpeg.exe" >nul
        copy "%%D\bin\ffprobe.exe" "ffmpeg\bin\ffprobe.exe" >nul
    )
    del "ffmpeg_temp.zip" 2>nul
    rmdir /s /q "ffmpeg_extract" 2>nul
    if not exist "ffmpeg\bin\ffmpeg.exe" (
        echo   ffmpeg 설치에 실패했습니다. https://www.gyan.dev/ffmpeg/builds/ 에서
        echo   수동으로 받아 ffmpeg\bin\ffmpeg.exe, ffprobe.exe로 넣어주세요.
        pause
        exit /b 1
    )
)

REM ---------------------------------------------------------------
REM 4) Node.js 확인
REM ---------------------------------------------------------------
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [4/5] Node.js가 설치되어 있지 않습니다.
    echo   https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행해주세요.
    pause
    exit /b 1
) else (
    echo [4/5] Node.js 확인 완료.
)

REM ---------------------------------------------------------------
REM 5) 웹 화면 빌드
REM ---------------------------------------------------------------
echo [5/5] 웹 화면 빌드 중...
cd webapp
call npm install
if %errorlevel% neq 0 (
    echo   웹 화면 패키지 설치에 실패했습니다.
    cd ..
    pause
    exit /b 1
)
call npm run build
if %errorlevel% neq 0 (
    echo   웹 화면 빌드에 실패했습니다.
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo   설치가 모두 끝났습니다!
echo   이제부터는 run-webapp.bat 을 더블클릭하면 프로그램이 실행됩니다.
echo   바탕화면 바로가기를 만들까요? 아래에 y 를 입력하면 만들어 드립니다.
set /p MAKE_SHORTCUT="바탕화면 바로가기 생성 (y/n): "
if /i "!MAKE_SHORTCUT!"=="y" (
    (
        echo $shell = New-Object -COM WScript.Shell
        echo $shortcut = $shell.CreateShortcut^("$env:USERPROFILE\Desktop\CapCut Auto Editor.lnk"^)
        echo $shortcut.TargetPath = "%~dp0run-webapp.bat"
        echo $shortcut.WorkingDirectory = "%~dp0"
        echo $shortcut.IconLocation = "shell32.dll,220"
        echo $shortcut.Save^(^)
    ) > "%TEMP%\capcut_auto_shortcut.ps1"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\capcut_auto_shortcut.ps1"
    del "%TEMP%\capcut_auto_shortcut.ps1" 2>nul
    echo   바탕화면에 "CapCut Auto Editor" 바로가기를 만들었습니다.
)

echo.
pause
