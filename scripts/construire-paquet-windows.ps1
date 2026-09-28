# PowerShell depuis la racine du dépôt :
# powershell -ExecutionPolicy Bypass -File scripts/construire-paquet-windows.ps1
param([string]$PythonExecutable = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$pythonSource = if ($PythonExecutable) { $PythonExecutable } else { 'python' }
$version = (& $pythonSource -m carnet.version).Trim()
if ($LASTEXITCODE -ne 0 -or !$version) { throw 'Version de Petits Pas indisponible.' }
Set-Content -LiteralPath version-application.txt -Value $version -Encoding utf8

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
$ancienPath = $env:PATH
if (!$env:PETITS_PAS_PANGO_BIN -or !(Test-Path (Join-Path $env:PETITS_PAS_PANGO_BIN 'libgobject-2.0-0.dll'))) {
    throw 'Installer Pango UCRT64 et définir PETITS_PAS_PANGO_BIN avant la construction.'
}
try {
    $env:PATH = "$env:PETITS_PAS_PANGO_BIN;$ancienPath"
    & $python -m PyInstaller --noconfirm --clean scripts/PetitsPas.spec
} finally {
    $env:PATH = $ancienPath
}
if ($LASTEXITCODE -ne 0) { throw 'La construction PyInstaller a échoué.' }
$verification = Start-Process -FilePath (Resolve-Path .\dist\PetitsPas\PetitsPas.exe).Path -ArgumentList '--verifier-distribution' -Wait -PassThru
if ($verification.ExitCode -ne 0) { throw 'Le contrôle du paquet Windows a échoué.' }
Copy-Item scripts\Installer-PetitsPas.ps1 dist\PetitsPas\Installer-PetitsPas.ps1
Copy-Item scripts\Installer-PetitsPas.cmd dist\PetitsPas\Installer-PetitsPas.cmd
Copy-Item scripts\Demarrer-PetitsPas.cmd dist\PetitsPas\Demarrer-PetitsPas.cmd
$zip = Join-Path (Resolve-Path dist).Path 'PetitsPas-windows.zip'
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\PetitsPas -DestinationPath $zip
Write-Host "Paquet Windows : $zip"
Write-Host 'Lancer : .\dist\PetitsPas\PetitsPas.exe'
