@echo off
setlocal
rem Drag audio files (mp3/wav/etc.) onto this script to convert them to the
rem format the engine expects: mono 44.1 kHz OGG Vorbis, written into audio\.
rem The output name is the input name (rename takes to lap_1.mp3 etc. BEFORE
rem dropping, and they land as drop-in replacements). Overwrites silently.

set "OUT=%~dp0..\audio"

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg not found on PATH. Install it, e.g.:  winget install Gyan.FFmpeg
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Drag one or more audio files onto this script to convert them
    echo to mono 44.1 kHz OGG Vorbis in the audio\ folder.
    pause
    exit /b 0
)

:loop
if "%~1"=="" goto done
echo Converting %~nx1  -^>  audio\%~n1.ogg
ffmpeg -hide_banner -loglevel warning -y -i "%~1" -ac 1 -ar 44100 -c:a libvorbis -q:a 5 "%OUT%\%~n1.ogg"
if errorlevel 1 echo   FAILED: %~nx1
shift
goto loop

:done
echo.
echo Done. Files written to %OUT%
pause
