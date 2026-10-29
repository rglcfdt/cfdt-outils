@echo off

title Console Dev Python/PostgreSQL/Docker

rem Gestion des accents
chcp 65001 >NUL

rem Positionnement de la taille de la fenêtre
mode con cols=200 lines=51

rem Couleur de la police et du fond de la fenêtre
color 0A

cmd.exe /K "%~dp0aliases.cmd"

