@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  CapCut Auto Editor - 데스크톱 앱 빌드
echo ============================================
echo.
echo 이 스크립트는 웹 화면과 데스크톱 앱을 빌드해서
echo 설치 파일을 만듭니다. 몇 분 정도 걸립니다.
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [오류] Node.js가 설치되어 있지 않습니다.
    echo https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행해주세요.
    pause
    exit /b 1
)

echo [1/4] 웹 화면 패키지 설치 중...
cd webapp
call npm install
if errorlevel 1 (
    echo [오류] 웹 화면 패키지 설치에 실패했습니다.
    cd ..
    pause
    exit /b 1
)

echo [2/4] 웹 화면 빌드 중...
call npm run build
if errorlevel 1 (
    echo [오류] 웹 화면 빌드에 실패했습니다.
    cd ..
    pause
    exit /b 1
)
cd ..

echo [3/4] 데스크톱 앱 패키지 설치 중...
cd desktop
call npm install
if errorlevel 1 (
    echo [오류] 데스크톱 앱 패키지 설치에 실패했습니다.
    cd ..
    pause
    exit /b 1
)

echo [4/4] 설치 파일 만드는 중...
call npm run dist
if errorlevel 1 (
    echo [오류] 설치 파일 만들기에 실패했습니다.
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo ============================================
echo  완료되었습니다!
echo ============================================
echo desktop\dist-electron 폴더 안에서 설치 파일을 찾으세요.
echo 그 파일을 실행하면 CapCut Auto Editor가 설치됩니다.
echo 앱을 처음 실행할 때 필요한 파이썬 패키지를 자동으로
echo  한 번 더 설치하니, 인터넷이 연결되어 있어야 합니다.
echo.
pause
