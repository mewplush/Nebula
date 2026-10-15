@echo off
rem Usado ao dar duplo clique em um arquivo .neb: executa e espera uma tecla antes de fechar.
call "%~dp0nebula.bat" %*
echo.
pause
