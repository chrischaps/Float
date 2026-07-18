@echo off
setlocal
rem Drag MUSIC files onto this script to convert them for the engine:
rem STEREO 44.1 kHz OGG Vorbis into audio\. (SFX use convert_audio.bat,
rem which forces mono — don't use that one for music.)
rem Rename takes to their target names first: music_day, music_dusk,
rem music_night, music_deep. Overwrites silently.

set "OUT=%~dp0..\audio"

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg not found on PATH. Install it, e.g.:  winget install Gyan.FFmpeg
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Drag one or more music files onto this script to convert them
    echo to stereo 44.1 kHz OGG Vorbis in the audio\ folder.
    pause
    exit /b 0
)

:loop
if "%~1"=="" goto done
echo Converting %~nx1  -^>  audio\%~n1.ogg
ffmpeg -hide_banner -loglevel warning -y -i "%~1" -ar 44100 -c:a libvorbis -q:a 6 "%OUT%\%~n1.ogg"
if errorlevel 1 echo   FAILED: %~nx1
shift
goto loop

:done
echo.
echo Done. Files written to %OUT%
pause
