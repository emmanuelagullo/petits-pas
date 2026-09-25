# Installer une archive extraite pour l'utilisateur courant (Windows).
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$programme = Join-Path $source 'PetitsPas.exe'
if (!(Test-Path $programme) -or !(Test-Path (Join-Path $source '_internal'))) {
    throw "Dossier PetitsPas incomplet : $source"
}

# Inclure les ressources et _internal : un changement de gabarit doit créer
# un nouveau dossier même si PetitsPas.exe n'a pas changé.
$liste = (Get-ChildItem -LiteralPath $source -File -Recurse | Sort-Object FullName | ForEach-Object {
    $relatif = $_.FullName.Substring($source.Length).Replace('\', '/')
    "$relatif $((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
}) -join "`n"
$hachage = [System.Security.Cryptography.SHA256]::Create()
try {
    $octets = [System.Text.Encoding]::UTF8.GetBytes($liste)
    $empreinte = ([BitConverter]::ToString($hachage.ComputeHash($octets))).Replace('-', '').Substring(0, 16).ToLowerInvariant()
} finally {
    $hachage.Dispose()
}
$racine = Join-Path $env:LOCALAPPDATA 'Programs\PetitsPas'
$destination = Join-Path $racine $empreinte
New-Item -ItemType Directory -Path $racine -Force | Out-Null
if (!(Test-Path $destination)) {
    $etape = Join-Path $racine ([Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $etape | Out-Null
    try {
        Copy-Item -Path (Join-Path $source '*') -Destination $etape -Recurse -Force
        Move-Item -LiteralPath $etape -Destination $destination
    } finally {
        if (Test-Path $etape) { Remove-Item -LiteralPath $etape -Recurse -Force }
    }
}

$installe = Join-Path $destination 'PetitsPas.exe'
if (!(Test-Path $installe)) { throw "Installation incomplète : $destination" }
$menu = [Environment]::GetFolderPath('Programs')
$raccourci = Join-Path $menu 'Petits Pas.lnk'
$shell = New-Object -ComObject WScript.Shell
$lien = $shell.CreateShortcut($raccourci)
$lien.TargetPath = $installe
$lien.WorkingDirectory = $destination
$lien.IconLocation = "$installe,0"
$lien.Save()
Write-Host "Application installée : $destination"
Write-Host "Raccourci du menu Démarrer : $raccourci"
Write-Host "Les données de l'école restent dans le paquet autonome, séparé du programme."
