; Windows installer for Quire (Inno Setup 6). Built by `python scripts/build.py --installer`,
; which passes AppVersion, Publisher, Homepage, SourceDir (the PyInstaller folder build),
; IconFile and OutputDir with /D.
;
; Installs for the current user by default (no admin prompt); the wizard offers
; "install for all users" too. Your notes and settings live in AppData, so upgrading
; or uninstalling never touches them.

#define AppName "Quire"
#define AppExe "Quire.exe"

[Setup]
; Never change AppId: Windows uses it to recognise upgrades of the same app.
AppId={{A8A67700-9677-45B8-8C82-78A07D4DFD71}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#Homepage}
AppSupportURL={#Homepage}/issues
AppUpdatesURL={#Homepage}/releases
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#Publisher}
VersionInfoDescription={#AppName} setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Upgrading while Quire is open: offer to close it, then start it again afterwards.
CloseApplications=yes
RestartApplications=yes
OutputDir={#OutputDir}
OutputBaseFilename=Quire-{#AppVersion}-windows-x64-setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Drop files from the previous version's folder build before copying the new one.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
