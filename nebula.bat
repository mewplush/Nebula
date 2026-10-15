@echo off
rem Launcher da Nebula. NAO muda de pasta: os arquivos sao procurados onde voce digitou o comando.
setlocal EnableExtensions
set "NEB_DIR=%~dp0"
set "NEB_ENTRY=%NEB_DIR%src\shell.py"
if not exist "%NEB_ENTRY%" set "NEB_ENTRY=%NEB_DIR%shell.py"
set "PYTHONUTF8=1"

where py >nul 2>&1
if not errorlevel 1 goto usepy
where python >nul 2>&1
if not errorlevel 1 goto usepython

echo [Nebula] Python 3 nao foi encontrado. Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH". 1>&2
exit /b 9009

:usepy
py -3 "%NEB_ENTRY%" %*
exit /b %errorlevel%

:usepython
python "%NEB_ENTRY%" %*
exit /b %errorlevel%
