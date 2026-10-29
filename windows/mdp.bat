@echo off
chcp 65001 >NUL

rem ! OUTILLAGE DELEGATION
rem !
rem ! @author RGL

rem Positionnement de la taille de la fenêtre
mode con cols=200 lines=51

rem Couleur de la police et du fond de la fenêtre
color 0A

rem Lire le fichier de properties
set FICHIERINI=%~dp0config.ini
for /f "usebackq tokens=1,2 delims==" %%a in ("%FICHIERINI%") do (call set %%a=%%b)
set PATH=%MYPATH%;%PATH%

rem Création du nom du fichier de traces et renommage de la fenêtre
mkdir "%LOGS%" 2> NUL 
mkdir "%TEMP%" 2> NUL 
basename %0 > "%TEMP%\nombatch.txt"
set /P NOMBATCH=<"%TEMP%\nombatch.txt"
title %NOMBATCH%
set LOGFILE=%LOGS%\%NOMBATCH:~0,-4%.txt
rm "%LOGFILE%" > NUL 2>&1 
rm "%TEMP%\nombatch.txt"
touch "%LOGFILE%"

echo Debut de traitement 2>&1 | tee -a "%LOGFILE%"

cd "C:\Users\rguillor\Documents\GitHub\"
python mdp.py 2>&1 | tee -a "%LOGFILE%"

pause

echo Fin de traitement 2>&1 | tee -a "%LOGFILE%"