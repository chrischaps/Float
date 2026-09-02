@echo off
REM Build the release binary, then assemble dist\Float\ + the itch.io zip.
REM   package.bat            -> dist\Float-1.0-win64.zip
REM   package.bat 1.1        -> dist\Float-1.1-win64.zip
cd /d "%~dp0"

call build.bat
if errorlevel 1 exit /b 1

set VERSION=%1
if "%VERSION%"=="" set VERSION=1.0

python tools\package.py --version %VERSION%
