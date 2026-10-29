@echo off

rem Gesttion des accents
chcp 65001 >NUL

rem Positionnement de la taille de la fenêtre
mode con cols=200 lines=51

rem Couleur de la police et du fond de la fenêtre
color 0A

:: Verification des droits administrateur
fltmc >nul 2>&1
if errorlevel 1 (
    echo Elevation en administrateur...
    powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================
echo   Arret force de DBeaver
echo ========================================
echo.

taskkill /F /T /IM dbeaver.exe

if errorlevel 1 (
    echo.
    echo ERREUR : certains processus n'ont pas pu etre arretes.
) else (
    echo.
    echo DBeaver a ete arrete.
)

echo.
pause