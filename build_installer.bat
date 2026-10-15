@echo off
setlocal
cd /d "%~dp0"
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto noiscc

python -m unittest discover -s tests
if errorlevel 1 goto testfail

"%ISCC%" pyneb_installer.iss
exit /b %errorlevel%

:noiscc
echo Inno Setup 6 nao encontrado. Instale em https://jrsoftware.org/isdl.php
exit /b 1

:testfail
echo Os testes falharam; instalador NAO gerado.
exit /b 1
