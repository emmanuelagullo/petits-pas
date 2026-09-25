# Installer une archive extraite pour l'utilisateur courant (Windows).
param([ValidateSet('Installer', 'Lister', 'Revenir', 'Nettoyer')][string]$Action = 'Installer')
$ErrorActionPreference = 'Stop'
$racine = Join-Path $env:LOCALAPPDATA 'Programs\PetitsPas'
$actuelle = Join-Path $racine 'actuelle'
$precedente = Join-Path $racine 'precedente'
$menu = [Environment]::GetFolderPath('Programs')
$raccourci = Join-Path $menu 'Petits Pas.lnk'

if ($Action -ne 'Installer') {
    if (!(Test-Path $actuelle)) { throw 'Aucune installation Petits Pas trouvée.' }
    $active = (Get-Content -LiteralPath $actuelle -Raw).Trim()
    if ($active -cnotmatch '^[0-9a-f]{16}$' -or !(Test-Path (Join-Path $racine "$active\PetitsPas.exe"))) {
        throw 'Version active invalide.'
    }
    $ancienne = if (Test-Path $precedente) { (Get-Content -LiteralPath $precedente -Raw).Trim() } else { '' }
    switch ($Action) {
        'Lister' {
            Write-Host "Version active : $active"
            if ($ancienne) { Write-Host "Version précédente : $ancienne" }
            Get-ChildItem -LiteralPath $racine -Directory | Where-Object { $_.Name -cmatch '^[0-9a-f]{16}$' } | ForEach-Object {
                Write-Host "Installée : $($_.Name)"
            }
        }
        'Revenir' {
            if ($ancienne -cnotmatch '^[0-9a-f]{16}$' -or !(Test-Path (Join-Path $racine "$ancienne\PetitsPas.exe"))) {
                throw 'Aucune version précédente disponible.'
            }
            $dossier = Join-Path $racine $ancienne
            $exe = Join-Path $dossier 'PetitsPas.exe'
            $shell = New-Object -ComObject WScript.Shell
            $lien = $shell.CreateShortcut($raccourci)
            $lien.TargetPath = $exe
            $lien.WorkingDirectory = $dossier
            $lien.IconLocation = "$exe,0"
            $lien.Save()
            Set-Content -LiteralPath $precedente -Value $active -Encoding Ascii
            Set-Content -LiteralPath $actuelle -Value $ancienne -Encoding Ascii
            Write-Host "Raccourci revenu à la version $ancienne. Fermez toute fenêtre encore ouverte avant de relancer."
        }
        'Nettoyer' {
            Get-ChildItem -LiteralPath $racine -Directory | Where-Object {
                $_.Name -cmatch '^[0-9a-f]{16}$' -and $_.Name -cne $active -and $_.Name -cne $ancienne
            } | ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
                Write-Host "Ancienne version supprimée : $($_.Name)"
            }
        }
    }
    exit
}

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
$shell = New-Object -ComObject WScript.Shell
$lien = $shell.CreateShortcut($raccourci)
$lien.TargetPath = $installe
$lien.WorkingDirectory = $destination
$lien.IconLocation = "$installe,0"
$lien.Save()
if (Test-Path $actuelle) {
    $active = (Get-Content -LiteralPath $actuelle -Raw).Trim()
    if ($active -cne $empreinte) { Set-Content -LiteralPath $precedente -Value $active -Encoding Ascii }
}
Set-Content -LiteralPath $actuelle -Value $empreinte -Encoding Ascii
Write-Host "Application installée : $destination"
Write-Host "Raccourci du menu Démarrer : $raccourci"
Write-Host "Version installée : $empreinte"
Write-Host "Les données de l'école restent dans le paquet autonome, séparé du programme."
