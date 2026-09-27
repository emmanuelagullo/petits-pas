; Compiler depuis la racine du dépôt après construire-paquet-windows.ps1 :
; ISCC.exe /DAppVersion=0.6-dev /DOutputDir=dist scripts\PetitsPas-Windows.iss
#ifndef AppVersion
  #error AppVersion doit être fourni à ISCC.
#endif
#ifndef OutputDir
  #define OutputDir "dist"
#endif

[Setup]
AppId=PetitsPas.Local.EmmanuelAgullo
AppName=Petits Pas
AppVersion={#AppVersion}
AppPublisher=Petits Pas
AppPublisherURL=https://petits-pas.gitlabpages.inria.fr/petits-pas/
DefaultDirName={localappdata}\Programs\PetitsPas\app
DefaultGroupName=Petits Pas
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
OutputDir={#OutputDir}
OutputBaseFilename=PetitsPas-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
WizardStyle=modern
UninstallDisplayName=Petits Pas
; Les données résident dans {localappdata}\petits-pas\paquet-autonome.
; Ne jamais ajouter de directive [UninstallDelete] sur ce dossier.

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\dist\PetitsPas\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; Le même nom que le raccourci #L7 remplace son point d'entrée.
Name: "{userprograms}\Petits Pas"; Filename: "{app}\Demarrer-PetitsPas.cmd"; WorkingDir: "{app}"
Name: "{group}\Désinstaller Petits Pas"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Demarrer-PetitsPas.cmd"; Description: "Ouvrir Petits Pas"; Flags: postinstall nowait skipifsilent
