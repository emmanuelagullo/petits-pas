@echo off
setlocal
set "DOSSIER_LOG=%LOCALAPPDATA%\petits-pas\logs"
if not exist "%DOSSIER_LOG%" mkdir "%DOSSIER_LOG%"
if not exist "%DOSSIER_LOG%" (
  echo Impossible de creer le dossier de diagnostic "%DOSSIER_LOG%".
  pause
  exit /b 1
)
set "JOURNAL=%DOSSIER_LOG%\dernier-demarrage.log"
echo Demarrage de Petits Pas...
"%~dp0PetitsPas.exe" %* > "%JOURNAL%" 2>&1
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo Petits Pas s'est arrete avec le code %CODE%.
  echo Journal : "%JOURNAL%"
  type "%JOURNAL%"
  echo.
  pause
)
exit /b %CODE%
