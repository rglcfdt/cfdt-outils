@echo off

rem UTF-8 pour gérer les accents
chcp 65001 >NUL

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

echo. 2>&1 | tee -a "%LOGFILE%"
echo ====================================== 2>&1 | tee -a "%LOGFILE%"
echo Ouverture du tunnel SSH 2>&1 | tee -a "%LOGFILE%"
echo ====================================== 2>&1 | tee -a "%LOGFILE%"

powershell -NoProfile -Command ^
"$p = Start-Process ssh -ArgumentList '-N -L %DB_LOCAL_PORT%:%DB_HOST%:%DB_PORT% %SSH_ALIAS%' -WindowStyle Minimized -PassThru; Set-Content '%TEMP%\cfdt_tunnel.pid' $p.Id"

set /P TUNNEL_PID=<"%TEMP%\cfdt_tunnel.pid"

echo PID tunnel : %TUNNEL_PID% 2>&1 | tee -a "%LOGFILE%"

timeout /t 3 /nobreak >nul

echo Test du tunnel... 2>&1 | tee -a "%LOGFILE%"

powershell -Command "exit !(Test-NetConnection localhost -Port %DB_LOCAL_PORT% -InformationLevel Quiet)" 2>&1 | tee -a "%LOGFILE%"

if NOT %errorlevel%==0 (
    echo.
    echo ERREUR : tunnel SSH ou PostgreSQL inaccessible. 2>&1 | tee -a "%LOGFILE%"
    del %TEMP%\cfdt_tunnel.pid >nul 2>&1
    pause
    exit /b 1
)

echo. 2>&1 | tee -a "%LOGFILE%"
echo Tunnel etabli. 2>&1 | tee -a "%LOGFILE%"
echo Lancement de DBeaver... 2>&1 | tee -a "%LOGFILE%"

echo Connexion DBeaver = [%DBEAVER_CON%]
rem echo Commande : "%DBEAVER%\dbeaverc.exe" -newInstance -con "name=%DBEAVER_CON%"

start /wait "" "%DBEAVER%\dbeaverc.exe" -data "C:\Users\rguillor\AppData\Roaming\DBeaverData\CFDTPROD"

echo. 2>&1 | tee -a "%LOGFILE%"
echo Fermeture de DBeaver detectee. 2>&1 | tee -a "%LOGFILE%"
echo Fermeture du tunnel SSH... 2>&1 | tee -a "%LOGFILE%"

:WAIT_DBEAVER

timeout /t 5 /nobreak >nul

tasklist /FI "IMAGENAME eq dbeaver.exe" | find /I "dbeaver.exe" >nul

if not errorlevel 1 goto WAIT_DBEAVER

echo Fermeture de DBeaver detectee.
echo Fermeture du tunnel SSH...

taskkill /PID %TUNNEL_PID% /F >nul 2>&1

echo Tunnel ferme.

exit /b 0