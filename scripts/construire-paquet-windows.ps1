# PowerShell depuis la racine du dépôt :
# powershell -ExecutionPolicy Bypass -File scripts/construire-paquet-windows.ps1
param([string]$PythonExecutable = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (!(Test-Path .venv-paquet\Scripts\python.exe)) {
    if ($PythonExecutable) {
        & $PythonExecutable -m venv .venv-paquet
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv-paquet
    } else {
        & python -m venv .venv-paquet
    }
    if ($LASTEXITCODE -ne 0) { throw 'Impossible de créer le venv : installer Python 3 (64 bits).' }
}
$python = (Resolve-Path .venv-paquet\Scripts\python.exe).Path
& $python -m pip install -r requirements-paquet-local.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances impossible.' }
$env:DJANGO_SETTINGS_MODULE = 'carnet.settings'
& $python -m PyInstaller --noconfirm --clean scripts/PetitsPas.spec
if ($LASTEXITCODE -ne 0) { throw 'La construction PyInstaller a échoué.' }
& .\dist\PetitsPas\PetitsPas.exe --verifier-distribution
if ($LASTEXITCODE -ne 0) { throw 'Le contrôle du paquet Windows a échoué.' }
Copy-Item scripts\Installer-PetitsPas.ps1 dist\PetitsPas\Installer-PetitsPas.ps1
Copy-Item scripts\Installer-PetitsPas.cmd dist\PetitsPas\Installer-PetitsPas.cmd
$zip = Join-Path (Resolve-Path dist).Path 'PetitsPas-windows.zip'
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\PetitsPas -DestinationPath $zip
Write-Host "Paquet Windows : $zip"
Write-Host 'Lancer : .\dist\PetitsPas\PetitsPas.exe'
