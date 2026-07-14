@echo off
setlocal
cd /d "%~dp0"
if not exist snapshots mkdir snapshots

set FLINT=engine\target\release\flint.exe
set SCENE=scenes\float.scene.toml
set SCHEMAS=--schemas engine\schemas --schemas schemas

echo Rendering seated view (approximate player eye, looking down at raft edge)...
%FLINT% render %SCENE% %SCHEMAS% --output snapshots\seated.png --width 1280 --height 720 --no-grid --distance 3.0 --pitch 30 --yaw 0 --target 0,0.2,1.0

echo Rendering raft overview...
%FLINT% render %SCENE% %SCHEMAS% --output snapshots\overview.png --width 1280 --height 720 --no-grid --distance 8 --pitch 25 --yaw 35 --target 0,0.3,0

echo Done. Output in snapshots\
