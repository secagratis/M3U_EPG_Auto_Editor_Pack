@echo off
title Compilazione M3U_EPG_Auto_Editor.exe
cd /d "%~dp0"

echo ===================================================
echo   Compilazione M3U & EPG Auto-Editor in EXE
echo ===================================================
echo.

if not exist "m3u_epg_auto_editor.py" (
    echo [ERRORE] File "m3u_epg_auto_editor.py" non trovato in questa cartella!
    pause
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Python non trovato nel PATH di sistema.
    pause
    exit /b 1
)

echo [1/3] Controllo PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller non trovato. Installazione in corso...
    pip install pyinstaller
)

echo.
echo [2/3] Compilazione in corso (attendere)...
pyinstaller --noconsole --onefile --clean --name "M3U_EPG_Auto_Editor" m3u_epg_auto_editor.py

echo.
echo [3/3] Pulizia file temporanei di compilazione...
if exist "build" rmdir /s /q "build"
if exist "M3U_EPG_Auto_Editor.spec" del /f /q "M3U_EPG_Auto_Editor.spec"

echo.
if exist "dist\M3U_EPG_Auto_Editor.exe" (
    echo [OK] Compilazione completata con successo!
    echo L'eseguibile si trova in: %~dp0dist\M3U_EPG_Auto_Editor.exe
    explorer "dist"
) else (
    echo [ERRORE] Compilazione non riuscita.
)
echo.
pause

