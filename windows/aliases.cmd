@echo off
REM ==================================================
REM Configuration du PATH
REM ==================================================

rem Lire le fichier de properties
set FICHIERINI=%~dp0config.ini
for /f "usebackq tokens=1,2 delims==" %%a in ("%FICHIERINI%") do (call set %%a=%%b)
set PATH=%MYPATH%;%PATH%

REM ==================================================
REM Alias Python
REM ==================================================

doskey py=python $*
doskey pip=pip $*
doskey venv=python -m venv .venv
doskey activate=.venv\Scripts\activate.bat
doskey freeze=pip freeze > requirements.txt
doskey installreq=pip install -r requirements.txt
doskey streamlit=python -m streamlit $*
doskey pytest=python -m pytest $*
doskey pipinstall=python -m pip install $*

REM ==================================================
REM Alias PostgreSQL
REM ==================================================

doskey psql=psql $*
doskey createdb=createdb $*
doskey dropdb=dropdb $*
doskey pgdump=pg_dump $*
doskey pgdumpall=pg_dumpall $*

REM Connexion locale
doskey pglocal=psql -h localhost -U postgres $*

REM Sauvegarde rapide
doskey pgbackup=pg_dump -U postgres -Fc $1 > $1.dump

REM ==================================================
REM Alias Git
REM ==================================================

doskey gs=git status
doskey ga=git add .
doskey gc=git commit -m "$*"
doskey gp=git push
doskey gl=git pull
doskey gb=git branch
doskey gco=git checkout $*

echo.
echo =====================================
echo  Aliases charges
echo =====================================
echo py         = python
echo pipinstall = python -m pip install
echo psql      = PostgreSQL
echo gs        = git status
echo activate  = active .venv
echo =====================================
echo.

